"""Read-only package access and training-only preprocessing.

Only the package's ``code/dataset.py`` API is used to resolve observations and
task indices.  Labels and index metadata never enter model tensors.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset


TASKS = ("FD_detection", "FL_localization", "FP_forewarning")
SPLITS = (
    "train", "validation", "test", "external_validation",
    "supplementary_only", "diagnostic_holdout", "development_only",
)
CLASS_NAMES = ["upf-gold", "upf-silver"]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_strings(values: Iterable[str]) -> str:
    return sha256_bytes(("\n".join(map(str, values)) + "\n").encode())


def _json_default(value):
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value).__name__)


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True,
                                     default=_json_default) + "\n")


@dataclass
class Preprocessor:
    task: str
    feature_set: str
    columns: list[str]
    raw_median: np.ndarray
    scale: np.ndarray
    fallback: list[str]
    observed_count: np.ndarray
    ready: np.ndarray
    fit_sample_count: int
    fit_sample_id_sha256: str
    fit_split: str = "train"

    @property
    def value_dim(self):
        return len(self.columns)

    @property
    def full_input_dim(self):
        return 2 * self.value_dim

    def transform(self, raw):
        raw = np.asarray(raw, dtype=np.float32)
        observed = np.isfinite(raw)
        # Median imputation occurs in raw space.  For robust-scaled channels the
        # imputed median becomes exactly zero; Ready remains an observed 0/1
        # value and a missing Ready is imputed by its training median.
        filled = np.where(observed, raw, self.raw_median)
        values = (filled - self.raw_median) / self.scale
        values[..., self.ready] = filled[..., self.ready]
        if not np.isfinite(values).all():
            raise ValueError("Non-finite transformed values")
        return values.astype(np.float32), observed

    def to_dict(self):
        return {
            "task": self.task,
            "feature_set": self.feature_set,
            "columns": self.columns,
            "column_sha256": digest_strings(self.columns),
            "value_channels": self.value_dim,
            "mask_channels": self.value_dim,
            "full_input_dim": self.full_input_dim,
            "raw_training_median": self.raw_median.tolist(),
            "robust_scale": self.scale.tolist(),
            "scale_fallback": self.fallback,
            "observed_fit_value_count": self.observed_count.tolist(),
            "ready_columns": [c for c, flag in zip(self.columns, self.ready) if flag],
            "ready_policy": "observed Ready stays 0/1; missing Ready uses training median and remains mask=0",
            "numeric_policy": "training median imputation then median/IQR scaling; IQR=0 falls back to training std then 1",
            "fit_scope": "package dataset.training_index(task) only",
            "fit_split": self.fit_split,
            "fit_sample_count": self.fit_sample_count,
            "fit_sample_id_sha256": self.fit_sample_id_sha256,
            "window_weighting": "every observed value occurrence in every allowed 12-step training window",
            "test_or_external_statistics_used": False,
        }

    def save(self, path):
        write_json(path, self.to_dict())

    @classmethod
    def from_dict(cls, d):
        columns = list(d["columns"])
        ready_names = set(d["ready_columns"])
        return cls(
            d["task"], d["feature_set"], columns,
            np.asarray(d["raw_training_median"], dtype=np.float64),
            np.asarray(d["robust_scale"], dtype=np.float64),
            list(d["scale_fallback"]),
            np.asarray(d["observed_fit_value_count"], dtype=np.int64),
            np.asarray([c in ready_names for c in columns], dtype=bool),
            int(d["fit_sample_count"]), d["fit_sample_id_sha256"], d.get("fit_split", "train"),
        )

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text()))


class PackageData:
    """Cached read-only view over the sealed package."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        spec = importlib.util.spec_from_file_location(
            "sealed_core_fault_dataset", self.root / "code" / "dataset.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load sealed package dataset API")
        self.loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.loader)
        self.protocol = json.loads((self.root / "metadata" / "protocol.json").read_text())
        self.feature_sets = json.loads((self.root / "metadata" / "feature_sets.json").read_text())
        self.runs = pd.read_csv(self.root / "metadata" / "runs.csv", keep_default_na=False)
        self.episodes = pd.read_csv(self.root / "metadata" / "ALL_CORE_EPISODES.csv",
                                    keep_default_na=False)
        self.evaluability = pd.read_csv(self.root / "metadata" / "EVENT_EVALUABILITY.csv",
                                        keep_default_na=False)
        self._values_cache = {}

    def default_feature_set(self, task):
        return self.protocol["task_feature_sets"][task]

    def feature_names(self, feature_set):
        # The package loader re-verifies both whitelist membership and order.
        return self.loader.feature_names(self.root, feature_set)

    def values(self, run_id, feature_set):
        key = (str(run_id), str(feature_set))
        if key not in self._values_cache:
            self._values_cache[key] = self.loader.load_run(
                self.root, run_id, feature_set).to_numpy(dtype=np.float32)
        return self._values_cache[key]

    def index(self, task, split=None, fit=False, feature_set=None):
        if task not in TASKS:
            raise ValueError(task)
        if fit:
            if split not in (None, "train"):
                raise ValueError("fit=True is train-only")
            frame = self.loader.training_index(self.root, task)
        else:
            frame = self.loader.load_index(self.root, task, split=split, eligible_only=True)
        if feature_set is not None:
            allowed = ({"FL_primary_10", "FL_baseline_6"} if task == "FL_localization"
                       else {self.default_feature_set(task)})
            if feature_set not in allowed:
                raise ValueError(f"Feature set {feature_set} is not allowed for {task}")
            frame = frame.copy()
            frame["feature_set"] = feature_set
        if fit and task == "FD_detection":
            if len(frame) != 55196 or not frame.y.eq(0).all() or not frame.normal_train_window.all():
                raise RuntimeError("FD fitting scope is not exactly 55,196 clean normal windows")
        return frame.reset_index(drop=True)

    def raw_windows(self, index, feature_set):
        """Materialize contracted windows without crossing runs."""
        columns = self.feature_names(feature_set)
        output = np.empty((len(index), 12, len(columns)), dtype=np.float32)
        for run_id, positions in index.groupby("run_id", sort=False).indices.items():
            positions = np.asarray(positions, dtype=np.int64)
            rows = index.iloc[positions]
            starts = rows.start_row.to_numpy(dtype=np.int64)
            stops = rows.stop_row.to_numpy(dtype=np.int64)
            if not np.all(stops - starts == 12):
                raise ValueError("Window length is not 12")
            values = self.values(run_id, feature_set)
            if (starts < 0).any() or (stops > len(values)).any():
                raise ValueError("Window leaves its own run")
            offsets = starts[:, None] + np.arange(12, dtype=np.int64)[None, :]
            output[positions] = values[offsets]
        return output

    def fit_preprocessor(self, task, feature_set=None):
        feature_set = feature_set or self.default_feature_set(task)
        index = self.index(task, fit=True, feature_set=feature_set)
        raw = self.raw_windows(index, feature_set).astype(np.float64, copy=False)
        names = self.feature_names(feature_set)
        flat = raw.reshape(-1, raw.shape[-1])
        observed = np.isfinite(flat)
        count = observed.sum(axis=0)
        if (count == 0).any():
            missing = [n for n, c in zip(names, count) if c == 0]
            raise ValueError(f"No observed training values for {missing}")
        median = np.nanmedian(flat, axis=0)
        q25 = np.nanpercentile(flat, 25, axis=0)
        q75 = np.nanpercentile(flat, 75, axis=0)
        iqr = q75 - q25
        std = np.nanstd(flat, axis=0)
        ready = np.asarray([name.endswith("__ready") for name in names], dtype=bool)
        scale = np.ones(len(names), dtype=np.float64)
        fallback = []
        for j, name in enumerate(names):
            if ready[j]:
                fallback.append("ready_identity")
            elif np.isfinite(iqr[j]) and iqr[j] > 0:
                scale[j] = iqr[j]
                fallback.append("iqr")
            elif np.isfinite(std[j]) and std[j] > 0:
                scale[j] = std[j]
                fallback.append("std")
            else:
                scale[j] = 1.0
                fallback.append("one")
        return Preprocessor(
            task, feature_set, names, median, scale, fallback, count, ready,
            len(index), digest_strings(index.sample_id.astype(str)),
        ), index


class WindowDataset(Dataset):
    """Task dataset with model X and metadata kept structurally separate."""

    def __init__(self, package: PackageData, task: str, index: pd.DataFrame,
                 preprocessor: Preprocessor, mode="full"):
        if mode not in ("full", "values_only", "mask_only", "ready_mask"):
            raise ValueError(mode)
        self.package = package
        self.task = task
        self.index = index.reset_index(drop=True).copy()
        self.preprocessor = preprocessor
        self.mode = mode
        self._runs = {}
        for run_id in self.index.run_id.unique():
            values, mask = preprocessor.transform(package.values(run_id, preprocessor.feature_set))
            if mode == "full":
                x = np.concatenate((values, mask.astype(np.float32)), axis=-1)
            elif mode == "values_only":
                x = values
            elif mode == "mask_only":
                x = mask.astype(np.float32)
            else:
                ready_idx = np.flatnonzero(preprocessor.ready)
                x = np.concatenate((values[:, ready_idx], mask.astype(np.float32)), axis=-1)
            self._runs[run_id] = (
                torch.from_numpy(np.ascontiguousarray(x)),
                torch.from_numpy(np.ascontiguousarray(values)),
                torch.from_numpy(np.ascontiguousarray(mask)),
            )
        self._run_ids = self.index.run_id.to_numpy()
        self._starts = self.index.start_row.to_numpy(dtype=np.int64)
        self._stops = self.index.stop_row.to_numpy(dtype=np.int64)
        if not np.all(self._stops - self._starts == 12):
            raise ValueError("Dataset contains a non-12-step window")
        if task == "FL_localization":
            mapping = {name: i for i, name in enumerate(CLASS_NAMES)}
            labels = self.index.y.map(mapping)
            if labels.isna().any():
                raise ValueError("Unknown FL class")
            self.labels = torch.tensor(labels.to_numpy(), dtype=torch.long)
        else:
            labels = self.index.y.to_numpy(dtype=np.float32)
            if not np.isfinite(labels).all():
                raise ValueError("Eligible training/evaluation labels must be finite")
            self.labels = torch.from_numpy(labels)

    @property
    def input_dim(self):
        sample = self[0]
        return int(sample["x"].shape[-1])

    @property
    def value_dim(self):
        return self.preprocessor.value_dim

    def __len__(self):
        return len(self.index)

    def __getitem__(self, i):
        x, values, mask = self._runs[self._run_ids[i]]
        a, b = int(self._starts[i]), int(self._stops[i])
        return {
            "x": x[a:b], "values": values[a:b], "mask": mask[a:b],
            "y": self.labels[i], "row_id": int(i),
        }

