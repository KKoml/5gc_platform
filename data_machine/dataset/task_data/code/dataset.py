"""Read-only, portable observation loaders. No fitting or model training."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

TASKS = ("FD_detection", "FL_localization", "FP_forewarning")
SIX = ("amf-a", "amf-b", "smf-silver", "smf-gold", "upf-silver", "upf-gold")
FD_COLUMNS = ([f"{nf}__cpu_millicores" for nf in SIX]
              + [f"{nf}__memory_bytes" for nf in SIX]
              + [f"core-host-local__{name}" for name in
                 ("cpu_pct", "mem_used_pct", "loadavg_1", "swap_used_bytes")]
              + [f"core-if-upfgtp-silver__{name}" for name in
                 ("rx_bitrate_bps", "tx_bitrate_bps", "rx_packet_rate_pps",
                  "tx_packet_rate_pps", "tx_dropped_delta", "tx_errors_delta")]
              + ["upf-silver__ready", "upf-gold__ready"])
FL_COLUMNS = [f"{nf}__{metric}" for nf in ("upf-silver", "upf-gold")
              for metric in ("cpu_millicores", "memory_bytes", "ready")]
FEATURE_SETS = {
    "FD_detection_24": FD_COLUMNS,
    "FP_warning_16": FD_COLUMNS[:14] + FD_COLUMNS[16:18],
    "FL_baseline_6": FL_COLUMNS,
    "FL_primary_10": FL_COLUMNS + [f"{nf}__{metric}"
                                   for nf in ("smf-silver", "smf-gold")
                                   for metric in ("cpu_millicores", "memory_bytes")],
}
DEFAULT_SETS = {"FD_detection": "FD_detection_24",
                "FL_localization": "FL_primary_10", "FP_forewarning": "FP_warning_16"}
SOURCE_TASKS = {"FD_detection": ("T2", "T2_detection_24"),
                "FL_localization": ("T4_upf", "T4_upf_localization_6"),
                "FP_forewarning": ("T3", "T3_warning_candidate_16")}


def require(condition, message):
    if not bool(condition):
        raise ValueError(message)


def package_path(root, relative):
    """Accept only package-relative paths, including after symlink resolution."""
    root = Path(root).expanduser().resolve()
    relative = Path(relative)
    require(not relative.is_absolute(), "Package paths must be relative")
    path = (root / relative).resolve()
    require(path.is_relative_to(root), "Path escapes package")
    return path


def feature_names(root, feature_set):
    sets = json.loads(package_path(root, "metadata/feature_sets.json").read_text())
    require(set(sets) == set(FEATURE_SETS), "Unexpected feature-set names")
    for name, expected in FEATURE_SETS.items():
        require(sets[name] == expected, f"Altered whitelist or column order: {name}")
    require(feature_set in sets, f"Unknown feature set: {feature_set}")
    return list(sets[feature_set])


def load_run(root, run_id, feature_set):
    """Return only whitelisted values. Preserve NaN; never read original paths."""
    runs = pd.read_csv(package_path(root, "metadata/runs.csv"), keep_default_na=False)
    match = runs.loc[runs.run_id.eq(run_id)]
    require(len(match) == 1, f"Unknown or duplicate run: {run_id}")
    names = feature_names(root, feature_set)
    frame = pd.read_parquet(package_path(root, Path(match.iloc[0].data_path)
                                       / "core_features_5s.parquet"), columns=names)
    require(all(pd.api.types.is_numeric_dtype(frame[c]) for c in names), "Nonnumeric observation")
    require(not np.isinf(frame.to_numpy(float)).any(), "Infinite observation")
    return frame


def load_index(root, task, split=None, eligible_only=False):
    """Load labels/metadata separately, including excluded candidates by default."""
    require(task in TASKS, f"Unknown task: {task}")
    frame = pd.read_parquet(package_path(root, f"tasks/{task}/index.parquet"))
    require(pd.api.types.is_bool_dtype(frame.eligible), "eligible must be boolean")
    require(frame.sample_id.is_unique, "Duplicate sample_id")
    if split is not None:
        frame = frame.loc[frame.split.eq(split)]
    if eligible_only:
        frame = frame.loc[frame.eligible]
    return frame.reset_index(drop=True)


def training_index(root, task):
    """FD fits only clean normal windows; FP/FL fit eligible training windows."""
    frame = load_index(root, task, split="train", eligible_only=True)
    if task == "FD_detection":
        require(pd.api.types.is_bool_dtype(frame.normal_train_window),
                "normal_train_window must be boolean")
        frame = frame.loc[frame.normal_train_window]
        require(frame.y.eq(0).all(), "FD normal training contains positive labels")
    return frame.reset_index(drop=True)


def iter_samples(root, task, split=None, fit=False, feature_set=None):
    """Yield X/mask/y/metadata separately; fit=True always uses training_index.

    FL_baseline_6 changes only columns, never candidates or eligibility. Run the
    full package validator before training. Inputs remain unscaled and unfilled.
    """
    require(task in TASKS, f"Unknown task: {task}")
    if fit:
        require(split in (None, "train"), "fit=True cannot use validation/test")
        index = training_index(root, task)
    else:
        index = load_index(root, task, split=split, eligible_only=True)
    name = feature_set or DEFAULT_SETS[task]
    allowed = ({"FL_primary_10", "FL_baseline_6"} if task == "FL_localization"
               else {DEFAULT_SETS[task]})
    require(name in allowed, f"Feature override not permitted for {task}")
    names = feature_names(root, name)
    for run_id, group in index.groupby("run_id", sort=False):
        values = load_run(root, run_id, name).to_numpy(dtype=np.float32)
        for row in group.to_dict("records"):
            start, stop = int(row["start_row"]), int(row["stop_row"])
            require(0 <= start < stop <= len(values) and stop - start == 12,
                    f"Invalid window: {row['sample_id']}")
            x = values[start:stop].copy()
            mask = np.isfinite(x)
            row["loaded_feature_set"] = name
            row["loaded_observed_fraction"] = float(mask.mean())
            row["loaded_min_channel_observed_fraction"] = float(mask.mean(axis=0).min())
            row["loaded_missing_channel_count"] = int((~mask.any(axis=0)).sum())
            yield {"X": x, "observed_mask": mask, "y": row["y"], "metadata": row}
