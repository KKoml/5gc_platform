"""D05 freezing, held-out evaluation, and auditable result aggregation."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .data import CLASS_NAMES, PackageData, digest_strings, write_json
from .evaluation import (
    calibrate_thresholds,
    evaluate_binary,
    evaluate_localization,
)
from .train import predict_job, sha256_file


ROOT = Path(__file__).resolve().parents[1]
BUDGETS = (0.1, 1.0)
ALL_SPLITS = (
    "train",
    "validation",
    "test",
    "external_validation",
    "supplementary_only",
    "diagnostic_holdout",
    "development_only",
)
BINARY_TASKS = ("FD_detection", "FP_forewarning")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fit_jobs(manifest: dict, phases: Iterable[str] | None = None) -> list[dict]:
    jobs = [job for job in manifest["jobs"] if job["kind"] in ("deep", "classical")]
    if phases is not None:
        allowed = set(phases)
        jobs = [job for job in jobs if job["phase"] in allowed]
    return jobs


def _job_dir(job: dict) -> Path:
    return ROOT / job["output"]


def _budget_name(budget: float) -> str:
    return str(float(budget)).replace(".", "p")


def _runs_for_split(data: PackageData, split: str) -> list[str]:
    return data.runs.loc[data.runs["split"].eq(split), "run_id"].astype(str).tolist()


def _episodes_for_split(data: PackageData, split: str) -> pd.DataFrame:
    runs = set(_runs_for_split(data, split))
    return data.episodes.loc[data.episodes.run_id.astype(str).isin(runs)].reset_index(drop=True)


def _evaluability_for_split(data: PackageData, split: str) -> pd.DataFrame:
    # Role comes from runs.csv; EVENT_EVALUABILITY.run_split has one known
    # legacy Core24h value and is never used for role assignment.
    runs = set(_runs_for_split(data, split))
    return data.evaluability.loc[
        data.evaluability.run_id.astype(str).isin(runs)
    ].reset_index(drop=True)


def _prediction(job: dict, split: str) -> Path | None:
    data = PackageData(json.loads((_job_dir(job) / "experiment_config.json").read_text())["package_root"])
    index = data.index(job["task"], split=split, feature_set=job["feature_set"])
    if index.empty:
        return None
    path = _job_dir(job) / "predictions" / f"{split}.parquet"
    if path.exists():
        sidecar = path.with_suffix(".json")
        if not sidecar.exists():
            raise RuntimeError(f"Prediction cache lacks sidecar: {path}")
        receipt = json.loads(sidecar.read_text())
        expected_ids = index.sample_id.astype(str).tolist()
        actual = pd.read_parquet(path, columns=["sample_id"])
        actual_ids = actual.sample_id.astype(str).tolist()
        checks = {
            "task": receipt.get("task") == job["task"],
            "model": receipt.get("model") == job["model"],
            "seed": int(receipt.get("seed", -1)) == int(job["seed"]),
            "split": receipt.get("split") == split,
            "sample_count": int(receipt.get("sample_count", -1)) == len(index),
            "sample_id_sha256": receipt.get("sample_id_sha256") == digest_strings(expected_ids),
            "prediction_file_sha256": receipt.get("prediction_file_sha256") == sha256_file(path),
            "exact_sample_id_order": actual_ids == expected_ids,
        }
        failed = [name for name, okay in checks.items() if not okay]
        if failed:
            raise RuntimeError(
                f"Prediction cache failed closed for {job['id']} {split}: {failed}"
            )
        return path
    predict_job(_job_dir(job), split, device="cuda")
    # Validate newly written output through the same fail-closed cache path.
    return _prediction(job, split)


def _verify_receipt_files(
    folder: Path,
    receipt_name: str,
    expected: dict,
    required_files: set[str],
) -> dict:
    path = folder / receipt_name
    if not path.exists():
        raise RuntimeError(f"Evaluation cache lacks receipt: {path}")
    receipt = json.loads(path.read_text())
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise RuntimeError(
                f"Evaluation receipt mismatch at {path}: {key}={receipt.get(key)!r}, expected {value!r}"
            )
    file_hashes = receipt.get("file_sha256")
    if not isinstance(file_hashes, dict) or set(file_hashes) != required_files:
        raise RuntimeError(
            f"Evaluation receipt file set mismatch at {path}: "
            f"found={sorted(file_hashes or {})}, expected={sorted(required_files)}"
        )
    for relative, digest in file_hashes.items():
        target = folder / relative
        if not target.is_file() or sha256_file(target) != digest:
            raise RuntimeError(f"Evaluation cache hash mismatch: {target}")
    return receipt


def _identity(job: dict, split: str, budget: float | None = None) -> dict:
    return {
        "job_id": job["id"],
        "phase": job["phase"],
        "task": job["task"],
        "feature_set": job["feature_set"],
        "model": job["model"],
        "seed": int(job["seed"]),
        "control": bool(job.get("control", False)),
        "split": split,
        "operating_budget_false_alerts_per_hour": budget,
    }


def _threshold_path(job: dict) -> Path:
    return _job_dir(job) / "thresholds" / "D05.json"


def _ensure_thresholds(job: dict, data: PackageData) -> dict[str, dict]:
    path = _threshold_path(job)
    if path.exists():
        payload = json.loads(path.read_text())
        prediction_path = _prediction(job, "validation")
        checks = {
            "status": payload.get("status") == "frozen",
            "job_id": payload.get("job_id") == job["id"],
            "task": payload.get("task") == job["task"],
            "model": payload.get("model") == job["model"],
            "seed": int(payload.get("seed", -1)) == int(job["seed"]),
            "feature_set": payload.get("feature_set") == job["feature_set"],
            "validation_prediction_sha256": (
                payload.get("validation_prediction_sha256") == sha256_file(prediction_path)
            ),
            "operating_points": set(payload.get("operating_points", {}))
            == {str(float(value)) for value in BUDGETS},
        }
        failed = [name for name, okay in checks.items() if not okay]
        if failed:
            raise RuntimeError(f"Frozen threshold cache mismatch for {job['id']}: {failed}")
        return payload
    prediction_path = _prediction(job, "validation")
    if prediction_path is None:
        raise RuntimeError(f"{job['id']} has no D05 samples")
    frame = pd.read_parquet(prediction_path)
    thresholds = calibrate_thresholds(
        frame,
        _episodes_for_split(data, "validation"),
        job["task"],
        budgets=BUDGETS,
        event_evaluability=_evaluability_for_split(data, "validation"),
    )
    payload = {
        "status": "frozen",
        "created_at": now(),
        "job_id": job["id"],
        "task": job["task"],
        "model": job["model"],
        "seed": int(job["seed"]),
        "feature_set": job["feature_set"],
        "calibration_split": "validation",
        "calibration_slot": "D05",
        "test_or_external_used": False,
        "selection_rule": (
            "within budget maximize main-event hits, then minimize false alerts, "
            "then choose the higher threshold"
        ),
        "operating_points": thresholds,
        "validation_prediction_sha256": sha256_file(prediction_path),
    }
    write_json(path, payload)
    return payload


def _evaluate_binary_split(
    job: dict,
    data: PackageData,
    split: str,
    thresholds: dict,
) -> tuple[list[dict], list[pd.DataFrame]]:
    prediction_path = _prediction(job, split)
    if prediction_path is None:
        return [], []
    frame = pd.read_parquet(prediction_path)
    episodes = _episodes_for_split(data, split)
    evaluability = _evaluability_for_split(data, split)
    metric_rows: list[dict] = []
    event_tables: list[pd.DataFrame] = []
    for budget in BUDGETS:
        frozen = thresholds["operating_points"][str(float(budget))]
        threshold = frozen.get("threshold")
        if threshold is None:
            raise RuntimeError(
                f"{job['id']} budget={budget} has no evaluable D05 threshold: {frozen['status']}"
            )
        folder = _job_dir(job) / "evaluation" / split / f"budget_{_budget_name(budget)}"
        metrics_path = folder / "metrics.json"
        if metrics_path.exists():
            _verify_receipt_files(
                folder,
                "evaluation_receipt.json",
                {
                    "job_id": job["id"],
                    "split": split,
                    "budget": float(budget),
                    "prediction_file_sha256": sha256_file(prediction_path),
                    "threshold_file_sha256": sha256_file(_threshold_path(job)),
                },
                {"metrics.json", "event_results.parquet", "alerts.parquet", "strata.csv"},
            )
            metrics = json.loads(metrics_path.read_text())
            events = pd.read_parquet(folder / "event_results.parquet")
            expected_event_ids = {
                (str(run_id), str(event_id))
                for run_id, event_id in episodes[["run_id", "fault_id"]].itertuples(
                    index=False, name=None
                )
            }
            actual_event_ids = {
                (str(run_id), str(event_id))
                for run_id, event_id in events[["run_id", "event_id"]].itertuples(
                    index=False, name=None
                )
            }
            if (
                len(events) != len(episodes)
                or events[["run_id", "event_id"]].duplicated().any()
                or actual_event_ids != expected_event_ids
                or float(metrics.get("threshold")) != float(threshold)
                or bool(metrics.get("point_adjustment"))
            ):
                raise RuntimeError(f"Binary evaluation cache failed closure: {folder}")
        else:
            result = evaluate_binary(
                frame,
                episodes,
                float(threshold),
                job["task"],
                event_evaluability=evaluability,
            )
            metrics = {
                **_identity(job, split, budget),
                "evaluation_status": "evaluated",
                "target_budget_per_hour": budget,
                "d05_threshold_status": frozen["status"],
                "d05_actual_false_alerts_per_hour": frozen.get(
                    "actual_false_alerts_per_hour"
                ),
                "prediction_file_sha256": sha256_file(prediction_path),
                "threshold_file_sha256": sha256_file(_threshold_path(job)),
                **result["metrics"],
            }
            folder.mkdir(parents=True, exist_ok=True)
            write_json(metrics_path, metrics)
            result["event_results"].to_parquet(folder / "event_results.parquet", index=False)
            result["alerts"].to_parquet(folder / "alerts.parquet", index=False)
            result["event_metrics_by_group"].to_csv(folder / "strata.csv", index=False)
            events = result["event_results"]
            write_json(folder / "evaluation_receipt.json", {
                "status": "complete",
                "job_id": job["id"],
                "split": split,
                "budget": float(budget),
                "prediction_file_sha256": sha256_file(prediction_path),
                "threshold_file_sha256": sha256_file(_threshold_path(job)),
                "file_sha256": {
                    name: sha256_file(folder / name)
                    for name in ("metrics.json", "event_results.parquet", "alerts.parquet", "strata.csv")
                },
            })
        metric_rows.append(metrics)
        events = events.copy()
        for key, value in _identity(job, split, budget).items():
            events[key] = value
        event_tables.append(events)
    return metric_rows, event_tables


def _evaluate_fl_split(
    job: dict, data: PackageData, split: str
) -> tuple[list[dict], list[pd.DataFrame]]:
    prediction_path = _prediction(job, split)
    if prediction_path is None:
        return [], []
    folder = _job_dir(job) / "evaluation" / split
    metrics_path = folder / "metrics.csv"
    if metrics_path.exists():
        expected_count = len(data.index(
            "FL_localization", split=split, feature_set=job["feature_set"]
        ))
        _verify_receipt_files(
            folder,
            "evaluation_receipt.json",
            {
                "job_id": job["id"],
                "split": split,
                "prediction_file_sha256": sha256_file(prediction_path),
                "expected_event_count": expected_count,
            },
            {"metrics.csv", "event_results.parquet", "confusion_matrix.csv"},
        )
        metrics_frame = pd.read_csv(metrics_path)
        events = pd.read_parquet(folder / "event_results.parquet")
        expected_ids = set(
            data.index(
                "FL_localization", split=split, feature_set=job["feature_set"]
            ).sample_id.astype(str)
        )
        actual_ids = set(events.sample_id.astype(str))
        if (
            len(events) != expected_count
            or events["sample_id"].duplicated().any()
            or actual_ids != expected_ids
            or int(metrics_frame.loc[metrics_frame["group"].eq("all"), "event_count"].iloc[0])
            != expected_count
        ):
            raise RuntimeError(f"FL evaluation cache failed closure: {folder}")
    else:
        frame = pd.read_parquet(prediction_path)
        result = evaluate_localization(frame, labels=CLASS_NAMES)
        folder.mkdir(parents=True, exist_ok=True)
        result["metrics"].to_csv(metrics_path, index=False)
        result["event_results"].to_parquet(folder / "event_results.parquet", index=False)
        result["confusion_matrix"].to_csv(folder / "confusion_matrix.csv", index=False)
        metrics_frame = result["metrics"]
        events = result["event_results"]
        expected_count = len(data.index(
            "FL_localization", split=split, feature_set=job["feature_set"]
        ))
        if len(events) != expected_count or events["sample_id"].duplicated().any():
            raise RuntimeError(f"New FL evaluation failed closure: {folder}")
        write_json(folder / "evaluation_receipt.json", {
            "status": "complete",
            "job_id": job["id"],
            "split": split,
            "prediction_file_sha256": sha256_file(prediction_path),
            "expected_event_count": expected_count,
            "file_sha256": {
                name: sha256_file(folder / name)
                for name in ("metrics.csv", "event_results.parquet", "confusion_matrix.csv")
            },
        })
    all_rows = metrics_frame.loc[metrics_frame["group"].eq("all")]
    if len(all_rows) != 1:
        raise RuntimeError(f"{job['id']} {split} lacks one all-events FL row")
    metric = {
        **_identity(job, split),
        "evaluation_status": "evaluated",
        **all_rows.iloc[0].to_dict(),
    }
    events = events.copy()
    for key, value in _identity(job, split).items():
        events[key] = value
    return [metric], [events]


def _evaluate_job_split(
    job: dict, data: PackageData, split: str, thresholds: dict | None
) -> tuple[list[dict], list[pd.DataFrame]]:
    if job["task"] in BINARY_TASKS:
        if thresholds is None:
            raise RuntimeError("Binary evaluation requires frozen thresholds")
        return _evaluate_binary_split(job, data, split, thresholds)
    return _evaluate_fl_split(job, data, split)


def _source_hashes() -> dict[str, str]:
    names = ("data.py", "models.py", "train.py", "evaluation.py", "pipeline.py", "reporting.py")
    return {name: sha256_file(ROOT / "code" / name) for name in names}


def freeze_m2(manifest: dict) -> dict:
    existing_path = ROOT / "artifacts" / "M2_D05_FREEZE.json"
    if existing_path.exists():
        existing = json.loads(existing_path.read_text())
        checks = {
            "status": existing.get("status") == "frozen",
            "base_config_sha256": existing.get("base_config_sha256")
            == sha256_file(ROOT / "configs" / "base_config.json"),
            "queue_manifest_sha256": existing.get("queue_manifest_sha256")
            == sha256_file(ROOT / "configs" / "queue_manifest.json"),
            "code_sha256": existing.get("code_sha256") == _source_hashes(),
        }
        failed = [name for name, okay in checks.items() if not okay]
        if failed:
            raise RuntimeError(f"Existing M2 freeze receipt failed closed: {failed}")
        expected_threshold_jobs = {
            job["id"]
            for job in _fit_jobs(manifest, phases=("M2",))
            if job["task"] in BINARY_TASKS
        }
        actual_threshold_jobs = set(existing.get("threshold_file_sha256", {}))
        if actual_threshold_jobs != expected_threshold_jobs:
            raise RuntimeError(
                "Existing M2 threshold job set mismatch: "
                f"missing={sorted(expected_threshold_jobs-actual_threshold_jobs)}, "
                f"extra={sorted(actual_threshold_jobs-expected_threshold_jobs)}"
            )
        for job_id, digest in existing["threshold_file_sha256"].items():
            job = next(job for job in manifest["jobs"] if job["id"] == job_id)
            if sha256_file(_threshold_path(job)) != digest:
                raise RuntimeError(f"M2 threshold drift after freeze: {job_id}")
        return existing
    data = PackageData(manifest["package_root"])
    jobs = _fit_jobs(manifest, phases=("M2",))
    metrics: list[dict] = []
    threshold_files: dict[str, str] = {}
    for job in jobs:
        config_path = _job_dir(job) / "experiment_config.json"
        config = json.loads(config_path.read_text())
        if config.get("status") != "trained":
            raise RuntimeError(f"M2 fit is not complete: {job['id']}")
        thresholds = None
        if job["task"] in BINARY_TASKS:
            thresholds = _ensure_thresholds(job, data)
            threshold_files[job["id"]] = sha256_file(_threshold_path(job))
        rows, _ = _evaluate_job_split(job, data, "validation", thresholds)
        metrics.extend(rows)

    pd.DataFrame(metrics).to_csv(ROOT / "metrics" / "M2_D05_PRELIMINARY.csv", index=False)
    observed_seconds = 0.0
    observed_by_identity: dict[tuple[str, str, str], float] = {}
    for job in jobs:
        cfg = json.loads((_job_dir(job) / "experiment_config.json").read_text())
        seconds = float(cfg.get("fit_seconds", 0.0))
        observed_seconds += seconds
        observed_by_identity[(job["task"], job["feature_set"], job["model"])] = seconds
    estimated_remaining = 0.0
    for job in _fit_jobs(manifest, phases=("M3",)):
        estimated_remaining += observed_by_identity[
            (job["task"], job["feature_set"], job["model"])
        ]
    heldout = [
        str(path)
        for job in jobs
        for path in (_job_dir(job) / "predictions").glob("*.parquet")
        if path.stem != "validation"
    ]
    if heldout:
        raise RuntimeError(f"Held-out prediction appeared before D05 freeze: {heldout[:3]}")
    receipt = {
        "status": "frozen",
        "created_at": now(),
        "phase": "M2 seed17 correctness and D05 configuration freeze",
        "fit_count": len(jobs),
        "deep_fit_count": sum(job["kind"] == "deep" for job in jobs),
        "control_fit_count": sum(bool(job.get("control")) for job in jobs),
        "base_config_sha256": sha256_file(ROOT / "configs" / "base_config.json"),
        "queue_manifest_sha256": sha256_file(ROOT / "configs" / "queue_manifest.json"),
        "code_sha256": _source_hashes(),
        "threshold_file_sha256": threshold_files,
        "validation_only_at_freeze": True,
        "heldout_prediction_count_before_freeze": 0,
        "observed_seed17_fit_seconds": observed_seconds,
        "observed_seed17_fit_gpu_hours_wall_clock_equivalent": observed_seconds / 3600.0,
        "estimated_remaining_fit_seconds_from_matched_seed17_fits": estimated_remaining,
        "estimated_remaining_gpu_hours_wall_clock_equivalent": estimated_remaining / 3600.0,
        "estimate_note": "Measured seed17 per-fit wall times copied to matching seed29/43 jobs; classical CPU fits are included in wall time and are not called GPU hours.",
        "fp_claim_boundary": "relative to recorded faults.jsonl start only; physical first-effect time is not certified",
    }
    write_json(existing_path, receipt)
    return receipt


def _seed_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    keys = [
        "task", "feature_set", "model", "control", "split",
        "operating_budget_false_alerts_per_hour",
    ]
    candidate_metrics = [
        "event_recall_all_main", "event_recall_eligible_main",
        "false_alerts_per_hour", "auprc_unadjusted", "f1_unadjusted",
        "first_detection_delay_median_seconds",
        "recorded_onset_lead_median_seconds",
        "top1", "balanced_accuracy", "macro_f1",
    ]
    records: list[dict] = []
    for identity, group in metrics.groupby(keys, dropna=False, sort=True):
        seeds = sorted(pd.to_numeric(group["seed"], errors="raise").astype(int).unique())
        if len(seeds) != 3:
            continue
        row = dict(zip(keys, identity))
        row["seed_count"] = 3
        row["seeds"] = ";".join(map(str, seeds))
        for field in candidate_metrics:
            if field not in group:
                continue
            values = pd.to_numeric(group[field], errors="coerce").dropna().to_numpy(float)
            if not len(values):
                continue
            row[f"{field}_mean"] = float(values.mean())
            row[f"{field}_std"] = float(values.std(ddof=1)) if len(values) > 1 else np.nan
            row[f"{field}_min"] = float(values.min())
            row[f"{field}_max"] = float(values.max())
        records.append(row)
    return pd.DataFrame.from_records(records)


def _paired_ablation(event_tables: list[pd.DataFrame]) -> pd.DataFrame:
    fl = pd.concat(
        [frame for frame in event_tables if len(frame) and frame["task"].iloc[0] == "FL_localization"],
        ignore_index=True,
    )
    fl = fl.loc[
        fl["model"].isin(["TCN", "RF"])
        & fl["feature_set"].isin(["FL_primary_10", "FL_baseline_6"])
        & ~fl["control"].astype(bool)
    ].copy()
    records: list[dict] = []
    rng = np.random.default_rng(172943)
    for (model, split), group in fl.groupby(["model", "split"], sort=True):
        per_event: list[pd.DataFrame] = []
        feature_seed_counts: list[int] = []
        for feature, suffix in [("FL_primary_10", "10"), ("FL_baseline_6", "6")]:
            part = group.loc[group["feature_set"].eq(feature)].copy()
            per_case_seed_count = part.groupby(["run_id", "event_id"])["seed"].nunique()
            if per_case_seed_count.empty or per_case_seed_count.nunique() != 1:
                raise RuntimeError(
                    f"FL paired ablation seed closure failed for {model} {split} {feature}"
                )
            feature_seed_counts.append(int(per_case_seed_count.iloc[0]))
            part[f"correct_{suffix}"] = part["matched"].astype(float)
            part = part.groupby(["run_id", "event_id"], as_index=False)[f"correct_{suffix}"].mean()
            per_event.append(part)
        joined = per_event[0].merge(per_event[1], on=["run_id", "event_id"], how="inner", validate="one_to_one")
        if joined.empty:
            continue
        if feature_seed_counts[0] != feature_seed_counts[1] or feature_seed_counts[0] != 3:
            raise RuntimeError(
                f"FL paired ablation requires three matched seeds: {model} {split} {feature_seed_counts}"
            )
        delta = joined["correct_10"].to_numpy(float) - joined["correct_6"].to_numpy(float)
        boots = np.empty(2000, dtype=float)
        for i in range(len(boots)):
            take = rng.integers(0, len(delta), len(delta))
            boots[i] = float(delta[take].mean())
        records.append({
            "model": model,
            "split": split,
            "paired_event_count": len(joined),
            "seed_count_per_event": feature_seed_counts[0],
            "FL_primary_10_top1_mean": float(joined["correct_10"].mean()),
            "FL_baseline_6_top1_mean": float(joined["correct_6"].mean()),
            "paired_delta_10_minus_6": float(delta.mean()),
            "event_cluster_bootstrap_replicates": 2000,
            "paired_delta_ci95_low": float(np.quantile(boots, 0.025)),
            "paired_delta_ci95_high": float(np.quantile(boots, 0.975)),
            "bootstrap_unit": "original event, with three seed predictions kept within event",
        })
    return pd.DataFrame.from_records(records)


def _event_ledger(data: PackageData) -> pd.DataFrame:
    ledger = data.episodes.copy()
    roles = data.runs[["run_id", "split", "family", "slot"]].rename(
        columns={"split": "authoritative_split", "slot": "authoritative_slot"}
    )
    ledger = ledger.drop(columns=["run_split", "slot"], errors="ignore").merge(
        roles, on="run_id", how="left", validate="many_to_one"
    )
    evaluability = data.evaluability[[
        "run_id", "fault_id", "FD_eligible_active_windows",
        "FP_eligible_positive_windows", "FP_has_eligible_pre_window",
    ]]
    ledger = ledger.merge(
        evaluability, on=["run_id", "fault_id"], how="left", validate="one_to_one"
    )
    fl = data.index("FL_localization")[["run_id", "fault_id"]].drop_duplicates()
    fl["FL_case_present"] = True
    ledger = ledger.merge(fl, on=["run_id", "fault_id"], how="left", validate="one_to_one")
    ledger["FL_case_present"] = ledger["FL_case_present"].eq(True)
    if len(ledger) != 621 or int(ledger.episode_scope.eq("main").sum()) != 620:
        raise RuntimeError("Global 621/620 event ledger closure failed")
    return ledger


def _write_tracker(metrics: pd.DataFrame, summary: pd.DataFrame, fit_count: int) -> None:
    text = f"""# Core fault experiment execution tracker

- Status: training and offline evaluation within the frozen scope completed
- Updated: {now()}
- Training/control fits: {fit_count} (exactly 30 deep-model fits)
- Main deep fits: 27; FL six-column TCN ablation: 3
- D05 operating points: 0.1 false alarms/hour (main) and 1/hour (supplementary), frozen per model and seed
- Test roles: D06–D07 reevaluate previously accessed tests, not new blind tests; V4, Core24h, diagnostic, and baseline2h remain separate
- Per-window/event results: `fits/*/predictions` and `fits/*/evaluation`
- Aggregate results: `metrics/ALL_METRICS.csv`, `metrics/THREE_SEED_SUMMARY.csv`
- Event accounting: `event_matches/EVENT_LEDGER_621.csv` and `event_matches/ALL_BINARY_EVENT_RESULTS.parquet`
- FP scope: evaluates predictability relative to recorded starts only; physical onset and command-to-log delay are unverified

This tracker records actual completion, not training plans or unexecuted configurations as results.
"""
    stamped = ROOT / "tracker" / f"EXPERIMENT_TRACKER_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.md"
    stamped.write_text(text)
    (ROOT / "tracker" / "EXPERIMENT_TRACKER.md").write_text(text)


def _fmt(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return "—" if not np.isfinite(number) else f"{number:.4f}"


def _write_final_report(seed_summary: pd.DataFrame, ablation: pd.DataFrame) -> Path:
    roles = {
        "test": "D06–D07 previously accessed test reevaluation",
        "external_validation": "V4 external validation",
        "supplementary_only": "Core24h supplementary",
        "diagnostic_holdout": "diagnostic holdout",
        "development_only": "baseline2h development",
    }
    primary = seed_summary.loc[
        ~seed_summary["control"].astype(bool)
        & seed_summary["split"].isin(roles)
        & ~seed_summary["feature_set"].eq("FL_baseline_6")
        & (
            seed_summary["operating_budget_false_alerts_per_hour"].isna()
            | seed_summary["operating_budget_false_alerts_per_hour"].eq(0.1)
        )
    ].copy()
    lines = [
        "# Frozen Core fault experiments across three tasks",
        "",
        f"Generated: {now()}. This report summarizes actual training and per-event evaluation artifacts; planned items are not counted as completed.",
        "",
        "## Completion status",
        "",
        "- Completed: 27 main deep fits, 3 FL six-column TCN fits; three seeds each for IF/RF/LR and FL six-column RF; 5 separate controls.",
        "- Failed: 0 (this report is generated only after all queue dependencies succeed).",
        "- Not executed: new fault injection, additional collection, online deployment, physical-onset certification, or natural-fault generalization experiments.",
        "- D06–D07 reevaluate previously used tests, not new blind tests; all run roles are reported separately.",
        "",
        "## Three-seed main results (main operating point: 0.1 false alarms/hour)",
        "",
        "|Task|Model|Role|All main-event recall/Top-1|Eligible main-event recall/BalAcc|AUPRC/Macro-F1|Actual false alarms/h|Delay or lead time relative to recorded start (s)|",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in primary.sort_values(["task", "model", "split"]).to_dict("records"):
        task = row["task"]
        if task == "FD_detection":
            first = row.get("event_recall_all_main_mean")
            second = row.get("event_recall_eligible_main_mean")
            third = row.get("auprc_unadjusted_mean")
            timing = row.get("first_detection_delay_median_seconds_mean")
        elif task == "FP_forewarning":
            first = row.get("event_recall_all_main_mean")
            second = row.get("event_recall_eligible_main_mean")
            third = row.get("auprc_unadjusted_mean")
            timing = row.get("recorded_onset_lead_median_seconds_mean")
        else:
            first = row.get("top1_mean")
            second = row.get("balanced_accuracy_mean")
            third = row.get("macro_f1_mean")
            timing = np.nan
        lines.append(
            f"|{task}|{row['model']}|{roles[row['split']]}|{_fmt(first)}|"
            f"{_fmt(second)}|{_fmt(third)}|{_fmt(row.get('false_alerts_per_hour_mean'))}|"
            f"{_fmt(timing)}|"
        )
    lines.extend([
        "",
        "0.1/h is a target budget; finite D05 samples need not attain exactly 0.1. Per-model threshold files also record actual false-alarm counts, valid hours, actual false alarms/h, and the supplementary 1/h operating point.",
        "",
        "## Paired FL six-to-ten-column ablation",
        "",
        "|Model|Role|Events|Ten-column Top-1|Six-column Top-1|Paired difference|Event bootstrap 95% CI|",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for row in ablation.sort_values(["model", "split"]).to_dict("records"):
        lines.append(
            f"|{row['model']}|{roles.get(row['split'], row['split'])}|{row['paired_event_count']}|"
            f"{_fmt(row['FL_primary_10_top1_mean'])}|{_fmt(row['FL_baseline_6_top1_mean'])}|"
            f"{_fmt(row['paired_delta_10_minus_6'])}|"
            f"[{_fmt(row['paired_delta_ci95_low'])}, {_fmt(row['paired_delta_ci95_high'])}]|"
        )
    lines.extend([
        "",
        "## Evidence and boundaries",
        "",
        "- FD statistics, imputation, and scaling are fitted only to 55,196 clean normal training windows. AE scores the mean squared residual of valid standardized numerical values at the final step; entirely missing final steps are not scored.",
        "- TranAD results use the explicitly labeled `TranAD_adapted_v2`, retaining dual-decoder self-conditioning without claiming exact numerical reproduction of the paper. KAN-AD uses pinned upstream source and a shared univariate adaptation.",
        "- FL labels denote controlled injection targets or associated paths, not complete natural root-cause discovery. The original 612 cases remain unchanged.",
        "- FP denotes predictability relative to starts recorded in `faults.jsonl`. Recorded starts are not certified physical first-onset times. Without verified historical command/physical-onset evidence, these results are not physical fault precursors or true physical lead times.",
        "- gNB/UE actions are user-behavior background, not Core fault labels, localization targets, or main inputs. Jointly executed W1 behavior may confound results and does not support randomized causal interpretation.",
        "- Ready/mask-only, constant, and run-timer controls are separately reported in `metrics/CONTROL_RESULTS.csv`, outside main results. Formal main models still use their contracted Ready and mask channels.",
        "- Numerical data have only conservative local availability times; central arrival times are unverified. This experiment does not establish online deployment effectiveness or natural-fault generalization.",
        "- Three seeds are initialization/training repetitions. Overlapping windows, runs, and seeds are not treated as independent physical experiments.",
        "",
        "Full per-window scores, per-event matches, D05 thresholds, confusion matrices, stratified metrics, and logs are under `fits/<job>/`; aggregate tables are under `metrics/`.",
        "",
    ])
    report = "\n".join(lines)
    folder = ROOT / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    stamped = folder / f"FINAL_REPORT_ZH_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.md"
    stamped.write_text(report)
    (folder / "FINAL_REPORT_ZH.md").write_text(report)
    return stamped


def _write_output_manifest(paths: dict[str, str]) -> None:
    records = []
    for purpose, relative in paths.items():
        path = ROOT / relative
        records.append({
            "purpose": purpose,
            "path": relative,
            "exists": path.exists(),
            "sha256": sha256_file(path) if path.is_file() else None,
        })
    write_json(ROOT / "OUTPUT_MANIFEST.json", {
        "status": "complete",
        "created_at": now(),
        "artifacts": records,
    })


def final_evaluate(manifest: dict) -> dict:
    m2 = json.loads((ROOT / "artifacts" / "M2_D05_FREEZE.json").read_text())
    if m2.get("status") != "frozen":
        raise RuntimeError("M2 D05 freeze receipt is absent or invalid")
    if m2["base_config_sha256"] != sha256_file(ROOT / "configs" / "base_config.json"):
        raise RuntimeError("Base configuration changed after M2 freeze")
    if m2["queue_manifest_sha256"] != sha256_file(ROOT / "configs" / "queue_manifest.json"):
        raise RuntimeError("Queue manifest changed after M2 freeze")
    if m2["code_sha256"] != _source_hashes():
        raise RuntimeError("Training/evaluation source changed after M2 freeze")
    data = PackageData(manifest["package_root"])
    jobs = _fit_jobs(manifest)
    thresholds: dict[str, dict | None] = {}
    validation_metrics: list[dict] = []
    validation_events: list[pd.DataFrame] = []
    threshold_hashes: dict[str, str] = {}
    for job in jobs:
        cfg = json.loads((_job_dir(job) / "experiment_config.json").read_text())
        if cfg.get("status") != "trained":
            raise RuntimeError(f"Fit is not trained: {job['id']}")
        frozen = None
        if job["task"] in BINARY_TASKS:
            frozen = _ensure_thresholds(job, data)
            threshold_hashes[job["id"]] = sha256_file(_threshold_path(job))
        thresholds[job["id"]] = frozen
        rows, events = _evaluate_job_split(job, data, "validation", frozen)
        validation_metrics.extend(rows)
        validation_events.extend(events)

    for job_id, digest in m2.get("threshold_file_sha256", {}).items():
        job = next(job for job in jobs if job["id"] == job_id)
        if threshold_hashes.get(job_id) != digest or sha256_file(_threshold_path(job)) != digest:
            raise RuntimeError(f"Seed17 D05 threshold changed after M2 freeze: {job_id}")

    final_freeze = {
        "status": "frozen",
        "created_at": now(),
        "fit_count": len(jobs),
        "threshold_fit_count": len(threshold_hashes),
        "threshold_file_sha256": threshold_hashes,
        "base_config_sha256": sha256_file(ROOT / "configs" / "base_config.json"),
        "queue_manifest_sha256": sha256_file(ROOT / "configs" / "queue_manifest.json"),
        "code_sha256": _source_hashes(),
        "heldout_predictions_created_after_this_receipt": True,
        "heldout_prediction_count_before_freeze": 0,
        "test_or_external_feedback_allowed": False,
    }
    final_freeze_path = ROOT / "artifacts" / "FINAL_D05_FREEZE.json"
    if final_freeze_path.exists():
        existing = json.loads(final_freeze_path.read_text())
        checks = {
            "status": existing.get("status") == "frozen",
            "base_config_sha256": existing.get("base_config_sha256")
            == final_freeze["base_config_sha256"],
            "queue_manifest_sha256": existing.get("queue_manifest_sha256")
            == final_freeze["queue_manifest_sha256"],
            "code_sha256": existing.get("code_sha256") == final_freeze["code_sha256"],
            "threshold_file_sha256": existing.get("threshold_file_sha256")
            == final_freeze["threshold_file_sha256"],
            "heldout_prediction_count_before_freeze": existing.get(
                "heldout_prediction_count_before_freeze"
            ) == 0,
        }
        failed = [name for name, okay in checks.items() if not okay]
        if failed:
            raise RuntimeError(f"Existing final D05 freeze failed closed: {failed}")
        final_freeze = existing
    else:
        heldout = [
            str(path)
            for job in jobs
            for path in (_job_dir(job) / "predictions").glob("*.parquet")
            if path.stem != "validation"
        ]
        if heldout:
            raise RuntimeError(
                "Held-out predictions predate FINAL_D05_FREEZE: " + ", ".join(heldout[:3])
            )
        write_json(final_freeze_path, final_freeze)

    metric_rows = list(validation_metrics)
    event_tables = list(validation_events)
    for job in jobs:
        for split in ALL_SPLITS:
            if split == "validation":
                continue
            rows, events = _evaluate_job_split(job, data, split, thresholds[job["id"]])
            metric_rows.extend(rows)
            event_tables.extend(events)

    metrics = pd.DataFrame.from_records(metric_rows)
    metrics.to_csv(ROOT / "metrics" / "ALL_METRICS.csv", index=False)
    seed_summary = _seed_summary(metrics)
    seed_summary.to_csv(ROOT / "metrics" / "THREE_SEED_SUMMARY.csv", index=False)
    controls = metrics.loc[metrics["control"].astype(bool)].copy()
    controls.to_csv(ROOT / "metrics" / "CONTROL_RESULTS.csv", index=False)
    ablation = _paired_ablation(event_tables)
    ablation.to_csv(ROOT / "metrics" / "FL_PAIRED_6_TO_10_ABLATION.csv", index=False)

    ledger = _event_ledger(data)
    ledger.to_csv(ROOT / "event_matches" / "EVENT_LEDGER_621.csv", index=False)
    binary_events = pd.concat(
        [frame for frame in event_tables if len(frame) and frame["task"].iloc[0] in BINARY_TASKS],
        ignore_index=True,
    )
    binary_events.to_parquet(
        ROOT / "event_matches" / "ALL_BINARY_EVENT_RESULTS.parquet", index=False
    )
    expected_binary_groups = {
        (job["id"], float(budget))
        for job in jobs
        if job["task"] in BINARY_TASKS
        for budget in BUDGETS
    }
    actual_binary_groups = {
        (str(job_id), float(budget))
        for job_id, budget in binary_events[
            ["job_id", "operating_budget_false_alerts_per_hour"]
        ].drop_duplicates().itertuples(index=False, name=None)
    }
    if actual_binary_groups != expected_binary_groups:
        missing = sorted(expected_binary_groups - actual_binary_groups)
        extra = sorted(actual_binary_groups - expected_binary_groups)
        raise RuntimeError(
            f"Binary job/budget closure failed: missing={missing[:3]}, extra={extra[:3]}"
        )
    for (job_id, budget), group in binary_events.groupby(
        ["job_id", "operating_budget_false_alerts_per_hour"], dropna=False
    ):
        expected_ids = {
            (str(run_id), str(event_id))
            for run_id, event_id in ledger[["run_id", "fault_id"]].itertuples(
                index=False, name=None
            )
        }
        actual_ids = {
            (str(run_id), str(event_id))
            for run_id, event_id in group[["run_id", "event_id"]].itertuples(
                index=False, name=None
            )
        }
        if (
            len(group) != 621
            or group[["run_id", "event_id"]].duplicated().any()
            or actual_ids != expected_ids
        ):
            raise RuntimeError(
                f"Binary event closure failed for {job_id}, budget={budget}: {len(group)}"
            )

    fl_events = pd.concat(
        [frame for frame in event_tables if len(frame) and frame["task"].iloc[0] == "FL_localization"],
        ignore_index=True,
    )
    fl_events.to_parquet(
        ROOT / "event_matches" / "ALL_FL_EVENT_RESULTS.parquet", index=False
    )
    expected_fl_jobs = {job["id"] for job in jobs if job["task"] == "FL_localization"}
    actual_fl_jobs = set(fl_events["job_id"].astype(str).unique())
    if actual_fl_jobs != expected_fl_jobs:
        raise RuntimeError(
            f"FL job closure failed: missing={sorted(expected_fl_jobs-actual_fl_jobs)}"
        )
    for job_id, group in fl_events.groupby("job_id", sort=True):
        job = next(job for job in jobs if job["id"] == job_id)
        expected_ids = set(
            data.index(
                "FL_localization", feature_set=job["feature_set"]
            ).sample_id.astype(str)
        )
        actual_ids = set(group["sample_id"].astype(str))
        if (
            len(group) != 612
            or group["sample_id"].duplicated().any()
            or actual_ids != expected_ids
        ):
            raise RuntimeError(f"FL 612-case closure failed for {job_id}: {len(group)}")

    _write_tracker(metrics, seed_summary, len(jobs))
    stamped_report = _write_final_report(seed_summary, ablation)
    write_json(ROOT / "failures" / "FAILURES.json", {
        "status": "none",
        "fit_failure_count": 0,
        "evaluation_failure_count": 0,
        "note": "This file is emitted only after every queue dependency completed successfully.",
    })
    summary = {
        "status": "complete",
        "completed_at": now(),
        "fit_count": len(jobs),
        "deep_fit_count": sum(job["kind"] == "deep" for job in jobs),
        "main_deep_fit_count": sum(
            job["kind"] == "deep" and job["feature_set"] != "FL_baseline_6"
            for job in jobs
        ),
        "fl6_tcn_fit_count": sum(
            job["kind"] == "deep" and job["feature_set"] == "FL_baseline_6"
            for job in jobs
        ),
        "classical_and_control_fit_count": sum(job["kind"] == "classical" for job in jobs),
        "metric_row_count": len(metrics),
        "three_seed_summary_row_count": len(seed_summary),
        "binary_event_result_row_count": len(binary_events),
        "fl_event_result_row_count": len(fl_events),
        "event_ledger_records": len(ledger),
        "event_ledger_main_records": int(ledger.episode_scope.eq("main").sum()),
        "event_ledger_nonmain_records": int((~ledger.episode_scope.eq("main")).sum()),
        "point_adjustment": False,
        "test_feedback_used": False,
        "physical_onset_certified": False,
        "fp_claim_scope": "predictability relative to recorded faults.jsonl start time only",
        "old_test_status": "D06-D07 previously used post-hoc reevaluation, not a fresh blind test",
        "split_roles_kept_separate": True,
        "unsupported_claims": [
            "physical-fault precursor or true physical lead time",
            "online deployment effectiveness",
            "natural-fault generalization",
            "complete natural root-cause discovery",
        ],
        "primary_files": {
            "all_metrics": "metrics/ALL_METRICS.csv",
            "three_seed_summary": "metrics/THREE_SEED_SUMMARY.csv",
            "controls": "metrics/CONTROL_RESULTS.csv",
            "fl_ablation": "metrics/FL_PAIRED_6_TO_10_ABLATION.csv",
            "event_ledger": "event_matches/EVENT_LEDGER_621.csv",
            "binary_event_results": "event_matches/ALL_BINARY_EVENT_RESULTS.parquet",
            "fl_event_results": "event_matches/ALL_FL_EVENT_RESULTS.parquet",
            "tracker": "tracker/EXPERIMENT_TRACKER.md",
            "final_report_zh": "reports/FINAL_REPORT_ZH.md",
            "failures": "failures/FAILURES.json",
        },
    }
    write_json(ROOT / "metrics" / "FINAL_SUMMARY.json", summary)
    _write_output_manifest({
        **summary["primary_files"],
        "final_summary": "metrics/FINAL_SUMMARY.json",
        "m0_acceptance": "artifacts/M0_PACKAGE_ACCEPTANCE.json",
        "preparation": "artifacts/PREPARE_RECEIPT.json",
        "m2_freeze": "artifacts/M2_D05_FREEZE.json",
        "final_d05_freeze": "artifacts/FINAL_D05_FREEZE.json",
        "environment": "configs/env-spec.json",
        "queue_manifest": "configs/queue_manifest.json",
    })
    return summary
