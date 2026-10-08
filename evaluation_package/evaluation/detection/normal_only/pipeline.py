"""Orchestration entry point for the sealed Core-fault experiment.

This module never writes inside PACKAGE_ROOT.  It prepares training-only
preprocessors, emits an explicit local queue manifest, dispatches individual
fits, and hands D05 freezing/final held-out evaluation to ``reporting.py``.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from .data import PackageData, digest_strings, write_json
from .train import fit_classical, fit_deep, sha256_file


HERE = Path(__file__).resolve().parents[1]
BASE_CONFIG = HERE / "configs" / "base_config.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_config() -> dict:
    return json.loads(BASE_CONFIG.read_text())


def safe_name(value: object) -> str:
    return str(value).replace("-", "_").replace(" ", "_")


def _assert_isolation(package_root: Path, result_root: Path) -> None:
    package_root = package_root.resolve()
    result_root = result_root.resolve()
    if package_root == result_root:
        raise RuntimeError("PACKAGE_ROOT and RESULT_ROOT must differ")
    if package_root in result_root.parents:
        raise RuntimeError("RESULT_ROOT cannot be inside PACKAGE_ROOT")
    if result_root in package_root.parents:
        raise RuntimeError("PACKAGE_ROOT cannot be inside RESULT_ROOT")
    required = ["README.md", "REMOTE_RUNBOOK.md", "SHA256SUMS.txt", "tasks", "metadata"]
    missing = [name for name in required if not (package_root / name).exists()]
    if missing:
        raise RuntimeError(f"PACKAGE_ROOT is not the package root; missing {missing}")


def prepare() -> dict:
    cfg = read_config()
    package_root = Path(cfg["package_root"])
    result_root = Path(cfg["result_root"])
    _assert_isolation(package_root, result_root)
    data = PackageData(package_root)
    specifications = [
        ("FD_detection", "FD_detection_24"),
        ("FL_localization", "FL_primary_10"),
        ("FL_localization", "FL_baseline_6"),
        ("FP_forewarning", "FP_warning_16"),
    ]
    forbidden_fp = {
        "next_core_fault_id", "next_core_onset_time",
        "seconds_to_next_core_onset", "next_core_episode_scope",
    }
    receipts: list[dict] = []
    fl_ids: dict[str, list[str]] = {}
    for task, feature_set in specifications:
        preprocessor, index = data.fit_preprocessor(task, feature_set)
        path = result_root / "artifacts" / "preprocessors" / f"{task}__{feature_set}.json"
        preprocessor.save(path)
        id_path = result_root / "artifacts" / "fit_sample_ids" / f"{task}__{feature_set}.csv.gz"
        id_path.parent.mkdir(parents=True, exist_ok=True)
        index[["sample_id", "run_id", "slot"]].to_csv(id_path, index=False)
        columns = data.feature_names(feature_set)
        if task == "FP_forewarning" and forbidden_fp.intersection(columns):
            raise RuntimeError("FP answer fields entered the model feature list")
        if task == "FL_localization":
            fl_ids[feature_set] = index.sample_id.astype(str).tolist()
        receipts.append({
            "task": task,
            "feature_set": feature_set,
            "feature_columns": columns,
            "feature_column_sha256": digest_strings(columns),
            "value_dimension": len(columns),
            "mask_dimension": len(columns),
            "full_input_dimension": 2 * len(columns),
            "fit_sample_count": len(index),
            "fit_sample_id_sha256": digest_strings(index.sample_id.astype(str)),
            "preprocessor_path": str(path),
            "preprocessor_sha256": sha256_file(path),
            "fit_ids_path": str(id_path),
            "fit_ids_sha256": sha256_file(id_path),
        })
    if len(receipts[0:1]) != 1 or receipts[0]["fit_sample_count"] != 55196:
        raise RuntimeError("FD preprocessing was not fitted on exactly 55,196 windows")
    if fl_ids["FL_primary_10"] != fl_ids["FL_baseline_6"]:
        raise RuntimeError("FL 6-to-10 ablation does not retain the same cases/order")

    all_events = data.episodes.copy()
    if len(all_events) != 621:
        raise RuntimeError(f"Expected 621 event records, found {len(all_events)}")
    main_events = int(all_events.episode_scope.eq("main").sum())
    auxiliary_events = int((~all_events.episode_scope.eq("main")).sum())
    if (main_events, auxiliary_events) != (620, 1):
        raise RuntimeError("620-main plus 1-auxiliary event closure failed")
    receipt = {
        "status": "prepared",
        "created_at": now(),
        "package_root": str(package_root.resolve()),
        "result_root": str(result_root.resolve()),
        "root_isolation_verified": True,
        "base_config_sha256": sha256_file(BASE_CONFIG),
        "event_closure": {"records": 621, "main": 620, "auxiliary": 1},
        "fp_answer_fields_excluded_from_x": sorted(forbidden_fp),
        "preprocessors": receipts,
    }
    out = result_root / "artifacts" / "PREPARE_RECEIPT.json"
    write_json(out, receipt)
    return receipt


def _preprocessor_path(task: str, feature_set: str) -> str:
    return str(HERE / "artifacts" / "preprocessors" / f"{task}__{feature_set}.json")


def _fit_job(
    task: str,
    model: str,
    seed: int,
    feature_set: str,
    *,
    phase: str,
    kind: str,
    mode: str = "full",
    control: bool = False,
    depends_on: list[str] | None = None,
) -> dict:
    job_id = "__".join(
        [phase.lower(), safe_name(task), safe_name(feature_set), safe_name(model), f"seed{seed}"]
    )
    return {
        "id": job_id,
        "phase": phase,
        "kind": kind,
        "task": task,
        "model": model,
        "seed": seed,
        "feature_set": feature_set,
        "mode": mode,
        "control": bool(control),
        "preprocessor": _preprocessor_path(task, feature_set),
        "output": f"fits/{job_id}",
        "expected_output": f"fits/{job_id}/experiment_config.json",
        "expected_json_status": "trained",
        "depends_on": list(depends_on or []),
    }


def build_manifest() -> dict:
    cfg = read_config()
    result_root = Path(cfg["result_root"])
    if not (result_root / "artifacts" / "PREPARE_RECEIPT.json").exists():
        raise RuntimeError("Run prepare before building the manifest")
    m2: list[dict] = []
    for task, feature_set, models in [
        ("FD_detection", "FD_detection_24", ["AE", "TranAD_adapted_v2", "KAN-AD"]),
        ("FL_localization", "FL_primary_10", ["LSTM", "TCN", "small_Transformer"]),
        ("FP_forewarning", "FP_warning_16", ["LSTM", "TCN", "small_Transformer"]),
        ("FL_localization", "FL_baseline_6", ["TCN"]),
    ]:
        m2.extend(
            _fit_job(task, model, 17, feature_set, phase="M2", kind="deep")
            for model in models
        )
    for task, feature_set, model in [
        ("FD_detection", "FD_detection_24", "IsolationForest"),
        ("FL_localization", "FL_primary_10", "RF"),
        ("FP_forewarning", "FP_warning_16", "LR"),
        ("FL_localization", "FL_baseline_6", "RF"),
    ]:
        m2.append(_fit_job(task, model, 17, feature_set, phase="M2", kind="classical"))
    for task, feature_set, model, mode in [
        ("FD_detection", "FD_detection_24", "ReadyMaskIF", "ready_mask"),
        ("FL_localization", "FL_primary_10", "ReadyMaskRF", "ready_mask"),
        ("FP_forewarning", "FP_warning_16", "Constant", "full"),
        ("FP_forewarning", "FP_warning_16", "TimingLR", "full"),
        ("FP_forewarning", "FP_warning_16", "MaskOnlyLR", "mask_only"),
    ]:
        m2.append(_fit_job(
            task, model, 17, feature_set, phase="M2", kind="classical",
            mode=mode, control=True,
        ))

    freeze_id = "m2_freeze_d05"
    freeze = {
        "id": freeze_id,
        "phase": "M2",
        "kind": "freeze_m2",
        "depends_on": [job["id"] for job in m2],
        "expected_output": "artifacts/M2_D05_FREEZE.json",
        "expected_json_status": "frozen",
    }

    m3: list[dict] = []
    for seed in (29, 43):
        for task, feature_set, models in [
            ("FD_detection", "FD_detection_24", ["AE", "TranAD_adapted_v2", "KAN-AD"]),
            ("FL_localization", "FL_primary_10", ["LSTM", "TCN", "small_Transformer"]),
            ("FP_forewarning", "FP_warning_16", ["LSTM", "TCN", "small_Transformer"]),
            ("FL_localization", "FL_baseline_6", ["TCN"]),
        ]:
            m3.extend(
                _fit_job(
                    task, model, seed, feature_set, phase="M3", kind="deep",
                    depends_on=[freeze_id],
                )
                for model in models
            )
        for task, feature_set, model in [
            ("FD_detection", "FD_detection_24", "IsolationForest"),
            ("FL_localization", "FL_primary_10", "RF"),
            ("FP_forewarning", "FP_warning_16", "LR"),
            ("FL_localization", "FL_baseline_6", "RF"),
        ]:
            m3.append(_fit_job(
                task, model, seed, feature_set, phase="M3", kind="classical",
                depends_on=[freeze_id],
            ))

    all_fits = m2 + m3
    deep_main = [
        job for job in all_fits
        if job["kind"] == "deep" and job["feature_set"] != "FL_baseline_6"
    ]
    deep_fl6 = [
        job for job in all_fits
        if job["kind"] == "deep" and job["feature_set"] == "FL_baseline_6"
    ]
    if len(deep_main) != 27 or len(deep_fl6) != 3:
        raise RuntimeError(
            f"Deep-fit cap violation: main={len(deep_main)}, FL6={len(deep_fl6)}"
        )
    final = {
        "id": "m4_final_evaluate",
        "phase": "M4",
        "kind": "final_evaluate",
        "depends_on": [job["id"] for job in m3] + [freeze_id],
        "expected_output": "metrics/FINAL_SUMMARY.json",
        "expected_json_status": "complete",
    }
    manifest = {
        "schema_version": 1,
        "project": "core_fault_frozen_v1",
        "created_at": now(),
        "cwd": str(result_root.resolve()),
        "package_root": str(Path(cfg["package_root"]).resolve()),
        "python": cfg["runtime_python"],
        "base_config": str(BASE_CONFIG),
        "base_config_sha256": sha256_file(BASE_CONFIG),
        "environment": {
            "PYTHONDONTWRITEBYTECODE": "1",
            "XDG_CACHE_HOME": str(result_root / "runtime_cache" / "xdg"),
            "TORCH_HOME": str(result_root / "runtime_cache" / "torch"),
            "MPLCONFIGDIR": str(result_root / "runtime_cache" / "matplotlib"),
            "CUDA_VISIBLE_DEVICES": "0",
            "OMP_NUM_THREADS": "8",
            "MKL_NUM_THREADS": "8",
            "OPENBLAS_NUM_THREADS": "8",
            "NUMEXPR_NUM_THREADS": "8",
        },
        "oom_max_attempts": 1,
        "deep_fit_counts": {"main": len(deep_main), "FL_baseline_6_TCN": len(deep_fl6)},
        "jobs": m2 + [freeze] + m3 + [final],
    }
    path = result_root / "configs" / "queue_manifest.json"
    write_json(path, manifest)
    return manifest


def run_job(manifest_path: str | Path, job_id: str) -> None:
    manifest = json.loads(Path(manifest_path).read_text())
    matches = [job for job in manifest["jobs"] if job["id"] == job_id]
    if len(matches) != 1:
        raise ValueError(f"Unknown/non-unique job ID: {job_id}")
    job = matches[0]
    cfg = read_config()
    result_root = Path(cfg["result_root"])
    package_root = Path(cfg["package_root"])
    _assert_isolation(package_root, result_root)
    if job["kind"] == "deep":
        fit_deep(
            package_root, job["task"], job["model"], int(job["seed"]),
            job["feature_set"], job["preprocessor"], result_root / job["output"],
            device="cuda", max_epochs=int(cfg["max_epochs"]),
            patience=int(cfg["early_stopping_patience"]),
        )
    elif job["kind"] == "classical":
        fit_classical(
            package_root, job["task"], job["model"], int(job["seed"]),
            job["feature_set"], job["preprocessor"], result_root / job["output"],
            mode=job.get("mode", "full"),
        )
    elif job["kind"] == "freeze_m2":
        from .reporting import freeze_m2
        freeze_m2(manifest)
    elif job["kind"] == "final_evaluate":
        from .reporting import final_evaluate
        final_evaluate(manifest)
    else:
        raise ValueError(job["kind"])


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    sub.add_parser("build-manifest")
    dispatch = sub.add_parser("run-job")
    dispatch.add_argument("--manifest", required=True)
    dispatch.add_argument("--job-id", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        print(json.dumps(prepare(), indent=2, default=str))
    elif args.command == "build-manifest":
        print(json.dumps(build_manifest(), indent=2, default=str))
    else:
        run_job(args.manifest, args.job_id)


if __name__ == "__main__":
    main()
