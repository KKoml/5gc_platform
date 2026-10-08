"""Frozen event evaluation for the Core fault experiment package.

The binary evaluators deliberately do *not* perform point adjustment.  A
binary alert is a maximal sequence of positive, score-valid task rows.  A
valid negative, an invalid/ineligible row, a run boundary, or a time gap
strictly greater than 7.5 seconds ends the segment.  Only the segment onset is
eligible for event matching.

Matching is a deterministic one-to-one greedy procedure.  Alerts are visited
first in ``(run_id, alert_start_time, alert_id)`` order, then the earliest
available candidate event is selected in ``(event_start_time, event_id)``
order.  FD alert onsets must be in ``[s, e)``; FP alert onsets must be in
``[s - 60 s, s - 10 s]``.

The effective normal exposure denominator is exactly the number of
score-valid, eligible rows whose frozen task label is ``y == 0``, multiplied
by five seconds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


GRID_SECONDS = 5.0
GAP_SECONDS = 7.5
FD_TASK = "FD_detection"
FP_TASK = "FP_forewarning"
FL_TASK = "FL_localization"
BINARY_TASKS = (FD_TASK, FP_TASK)
ABSTAIN_LABEL = "__abstain__"
MATCHING_POLICY = (
    "one_to_one_greedy_by_alert_start_alert_id_then_event_start_event_id"
)

_SECOND_NS = 1_000_000_000
_FP_MAX_LEAD_NS = 60 * _SECOND_NS
_FP_MIN_LEAD_NS = 10 * _SECOND_NS
_GAP_NS = int(GAP_SECONDS * _SECOND_NS)


def _average_precision(y_true: np.ndarray, scores: np.ndarray) -> float:
    """Binary average precision with tied scores evaluated as one threshold."""

    truth = np.asarray(y_true, dtype=int)
    score = np.asarray(scores, dtype=float)
    positive_count = int(np.sum(truth == 1))
    if not positive_count:
        return np.nan
    order = np.argsort(-score, kind="mergesort")
    sorted_truth = truth[order]
    sorted_scores = score[order]
    cumulative_tp = np.cumsum(sorted_truth == 1)
    cumulative_fp = np.cumsum(sorted_truth == 0)
    group_ends = np.r_[
        np.flatnonzero(sorted_scores[:-1] != sorted_scores[1:]), len(sorted_scores) - 1
    ]
    tp = cumulative_tp[group_ends].astype(float)
    fp = cumulative_fp[group_ends].astype(float)
    recall = tp / positive_count
    precision = tp / (tp + fp)
    recall_increment = np.diff(np.r_[0.0, recall])
    return float(np.sum(recall_increment * precision))


def _macro_f1(
    y_true: np.ndarray, y_pred: np.ndarray, labels: Sequence[str]
) -> float:
    values: list[float] = []
    for label in labels:
        true_positive = int(np.sum((y_true == label) & (y_pred == label)))
        false_positive = int(np.sum((y_true != label) & (y_pred == label)))
        false_negative = int(np.sum((y_true == label) & (y_pred != label)))
        denominator = 2 * true_positive + false_positive + false_negative
        values.append(2 * true_positive / denominator if denominator else 0.0)
    return float(np.mean(values)) if values else np.nan


def _confusion_matrix(
    y_true: Sequence[str], y_pred: Sequence[str], labels: Sequence[str]
) -> np.ndarray:
    label_positions = {str(label): position for position, label in enumerate(labels)}
    matrix = np.zeros((len(labels), len(labels)), dtype=int)
    for truth, prediction in zip(y_true, y_pred):
        truth_key = str(truth)
        prediction_key = str(prediction)
        if truth_key not in label_positions or prediction_key not in label_positions:
            raise ValueError(
                "Confusion-matrix value is outside the frozen label order: "
                f"truth={truth_key!r}, prediction={prediction_key!r}"
            )
        matrix[label_positions[truth_key], label_positions[prediction_key]] += 1
    return matrix


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


def _bool_series(values: pd.Series, *, default: bool = False) -> pd.Series:
    """Parse booleans without treating the string ``'False'`` as true."""

    out = pd.Series(default, index=values.index, dtype=bool)
    known = values.notna()
    if not known.any():
        return out
    subset = values.loc[known]
    if pd.api.types.is_bool_dtype(subset.dtype):
        out.loc[known] = subset.astype(bool)
        return out
    if pd.api.types.is_numeric_dtype(subset.dtype):
        numeric = pd.to_numeric(subset, errors="raise")
        if not numeric.isin([0, 1]).all():
            raise ValueError("Boolean field contains values other than 0/1")
        out.loc[known] = numeric.astype(bool)
        return out
    normalized = subset.astype(str).str.strip().str.lower()
    mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
        "yes": True,
        "no": False,
    }
    if not normalized.isin(mapping).all():
        bad = sorted(normalized.loc[~normalized.isin(mapping)].unique().tolist())
        raise ValueError(f"Unrecognized boolean values: {bad}")
    out.loc[known] = normalized.map(mapping).astype(bool)
    return out


def _time_ns(values: pd.Series, name: str) -> np.ndarray:
    parsed = pd.to_datetime(values, utc=True, format="mixed", errors="raise")
    if parsed.isna().any():
        raise ValueError(f"{name} contains missing timestamps")
    return parsed.astype("int64").to_numpy(dtype=np.int64)


def load_episodes(root: str | Path, run_ids: Iterable[str] | None = None) -> pd.DataFrame:
    """Load the sealed 621-record episode ledger with standardized names."""

    frame = pd.read_csv(Path(root) / "metadata" / "ALL_CORE_EPISODES.csv")
    if "event_id" not in frame and "fault_id" in frame:
        frame = frame.rename(columns={"fault_id": "event_id"})
    if "target" not in frame and "target_instance" in frame:
        frame = frame.rename(columns={"target_instance": "target"})
    if run_ids is not None:
        selected = {str(run_id) for run_id in run_ids}
        frame = frame.loc[frame["run_id"].astype(str).isin(selected)]
    return frame.reset_index(drop=True)


def load_event_evaluability(
    root: str | Path, run_ids: Iterable[str] | None = None
) -> pd.DataFrame:
    """Load the sealed per-event FD/FP evaluability ledger."""

    frame = pd.read_csv(Path(root) / "metadata" / "EVENT_EVALUABILITY.csv")
    if "event_id" not in frame and "fault_id" in frame:
        frame = frame.rename(columns={"fault_id": "event_id"})
    if run_ids is not None:
        selected = {str(run_id) for run_id in run_ids}
        frame = frame.loc[frame["run_id"].astype(str).isin(selected)]
    return frame.reset_index(drop=True)


def audit_event_closure(
    episodes: pd.DataFrame,
    event_evaluability: pd.DataFrame | None = None,
    *,
    expected_total: int | None = None,
    expected_main: int | None = None,
    expected_nonmain: int | None = None,
) -> dict[str, object]:
    """Verify that each recorded event has exactly one evaluability disposition."""

    normalized = _normalize_episodes(episodes, run_ids=None)
    identity = ["run_id", "event_id"]
    main = normalized["episode_scope"].eq("main")
    total = int(len(normalized))
    main_count = int(main.sum())
    nonmain_count = total - main_count

    if expected_total is not None and total != expected_total:
        raise ValueError(f"Expected {expected_total} event records, found {total}")
    if expected_main is not None and main_count != expected_main:
        raise ValueError(f"Expected {expected_main} main events, found {main_count}")
    if expected_nonmain is not None and nonmain_count != expected_nonmain:
        raise ValueError(
            f"Expected {expected_nonmain} non-main events, found {nonmain_count}"
        )

    evaluability_count = None
    if event_evaluability is not None:
        ledger = event_evaluability.copy()
        if "event_id" not in ledger and "fault_id" in ledger:
            ledger = ledger.rename(columns={"fault_id": "event_id"})
        _require_columns(ledger, identity, "event_evaluability")
        ledger["run_id"] = ledger["run_id"].astype(str)
        ledger["event_id"] = ledger["event_id"].astype(str)
        if ledger.duplicated(identity).any():
            raise ValueError("event_evaluability contains duplicate event identities")
        episode_ids = pd.MultiIndex.from_frame(normalized[identity])
        ledger_ids = pd.MultiIndex.from_frame(ledger[identity])
        missing = episode_ids.difference(ledger_ids)
        extra = ledger_ids.difference(episode_ids)
        if len(missing) or len(extra):
            raise ValueError(
                "Episode/evaluability identities do not close: "
                f"missing={len(missing)}, extra={len(extra)}"
            )
        evaluability_count = int(len(ledger))

    scope_counts = {
        str(key): int(value)
        for key, value in normalized["episode_scope"].value_counts(dropna=False).items()
    }
    return {
        "status": "closed",
        "event_record_count": total,
        "main_event_count": main_count,
        "nonmain_event_count": nonmain_count,
        "scope_counts": scope_counts,
        "evaluability_record_count": evaluability_count,
    }


def validate_package_event_closure(root: str | Path) -> dict[str, object]:
    """Verify the package-level frozen contract: 620 main + 1 prelude record."""

    episodes = load_episodes(root)
    evaluability = load_event_evaluability(root)
    return audit_event_closure(
        episodes,
        evaluability,
        expected_total=621,
        expected_main=620,
        expected_nonmain=1,
    )


def _normalize_episodes(
    episodes: pd.DataFrame, run_ids: Iterable[str] | None
) -> pd.DataFrame:
    frame = episodes.copy()
    if "event_id" not in frame and "fault_id" in frame:
        frame = frame.rename(columns={"fault_id": "event_id"})
    if "target" not in frame and "target_instance" in frame:
        frame = frame.rename(columns={"target_instance": "target"})
    _require_columns(
        frame,
        ["run_id", "event_id", "start_time", "end_time"],
        "episodes",
    )
    frame["run_id"] = frame["run_id"].astype(str)
    frame["event_id"] = frame["event_id"].astype(str)
    if run_ids is not None:
        selected = {str(run_id) for run_id in run_ids}
        frame = frame.loc[frame["run_id"].isin(selected)].copy()
    if frame.duplicated(["run_id", "event_id"]).any():
        raise ValueError("episodes contains duplicate event identities")
    if "episode_scope" not in frame:
        frame["episode_scope"] = "main"
    frame["episode_scope"] = frame["episode_scope"].fillna("main").astype(str)
    for column in ("fault_type", "target"):
        if column not in frame:
            frame[column] = "unknown"
        frame[column] = frame[column].fillna("unknown").astype(str)
    if "end_exclusion_time" not in frame:
        frame["end_exclusion_time"] = frame["end_time"]
    frame["end_exclusion_time"] = frame["end_exclusion_time"].fillna(
        frame["end_time"]
    )
    frame["_start_ns"] = _time_ns(frame["start_time"], "episodes.start_time")
    frame["_end_ns"] = _time_ns(frame["end_time"], "episodes.end_time")
    frame["_exclude_end_ns"] = _time_ns(
        frame["end_exclusion_time"], "episodes.end_exclusion_time"
    )
    if (frame["_end_ns"] <= frame["_start_ns"]).any():
        raise ValueError("Every event must have end_time strictly after start_time")
    if (frame["_exclude_end_ns"] < frame["_end_ns"]).any():
        raise ValueError("end_exclusion_time cannot precede end_time")
    frame = frame.sort_values(
        ["run_id", "_start_ns", "event_id"], kind="mergesort"
    ).reset_index(drop=True)
    frame["_event_pos"] = np.arange(len(frame), dtype=int)
    return frame


def _join_binary(index: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        index,
        ["sample_id", "run_id", "anchor_time", "eligible", "y"],
        "index",
    )
    _require_columns(predictions, ["sample_id", "score"], "predictions")
    if index["sample_id"].duplicated().any():
        raise ValueError("index contains duplicate sample_id values")
    if predictions["sample_id"].duplicated().any():
        raise ValueError("predictions contains duplicate sample_id values")
    if not predictions["sample_id"].isin(index["sample_id"]).all():
        raise ValueError("predictions contains sample_id values outside the supplied index")

    prediction_columns = ["sample_id", "score"]
    if "prediction_valid" in predictions:
        prediction_columns.append("prediction_valid")
    pred = predictions[prediction_columns].copy()
    pred["_prediction_present"] = True
    if "prediction_valid" not in pred:
        pred["prediction_valid"] = True

    rows = index.copy()
    rows["run_id"] = rows["run_id"].astype(str)
    rows = rows.merge(pred, on="sample_id", how="left", validate="one_to_one")
    rows["eligible"] = _bool_series(rows["eligible"])
    rows["prediction_valid"] = _bool_series(rows["prediction_valid"])
    rows["_prediction_present"] = rows["_prediction_present"].fillna(False).astype(bool)
    rows["score"] = pd.to_numeric(rows["score"], errors="coerce")
    rows["_time_ns"] = _time_ns(rows["anchor_time"], "index.anchor_time")
    rows = rows.sort_values(
        ["run_id", "_time_ns", "sample_id"], kind="mergesort"
    ).reset_index(drop=True)
    if rows.duplicated(["run_id", "_time_ns"]).any():
        raise ValueError("Binary evaluation requires one cutoff per run and timestamp")

    finite = np.isfinite(rows["score"].to_numpy(dtype=float))
    rows["_valid"] = (
        rows["eligible"].to_numpy(dtype=bool)
        & rows["prediction_valid"].to_numpy(dtype=bool)
        & rows["_prediction_present"].to_numpy(dtype=bool)
        & finite
    )
    rows["_y_numeric"] = pd.to_numeric(rows["y"], errors="coerce")
    invalid_labels = rows["_valid"] & ~rows["_y_numeric"].isin([0.0, 1.0])
    if invalid_labels.any():
        raise ValueError("Every score-valid eligible binary row must have y in {0, 1}")

    times = rows["_time_ns"].to_numpy(dtype=np.int64)
    same_run = rows["run_id"].eq(rows["run_id"].shift()).to_numpy(dtype=bool)
    gap = np.empty(len(rows), dtype=np.int64)
    if len(rows):
        gap[0] = np.iinfo(np.int64).max
        if len(rows) > 1:
            gap[1:] = times[1:] - times[:-1]
    rows["_contiguous_previous"] = same_run & (gap > 0) & (gap <= _GAP_NS)
    return rows


def _binary_inputs(
    predictions_df: pd.DataFrame, index: pd.DataFrame | None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Accept either one combined prediction table or an explicit task index."""

    if index is not None:
        return index.copy(), predictions_df.copy()
    combined = predictions_df.copy().reset_index(drop=True)
    if "sample_id" not in combined:
        combined["sample_id"] = [f"evaluation-row-{i}" for i in range(len(combined))]
    if "eligible" not in combined:
        # The stable pipeline API supplies eligible rows only.
        combined["eligible"] = True
    _require_columns(
        combined,
        ["sample_id", "run_id", "anchor_time", "eligible", "y", "score"],
        "predictions_df",
    )
    prediction_columns = ["sample_id", "score"]
    if "prediction_valid" in combined:
        prediction_columns.append("prediction_valid")
    prediction_frame = combined[prediction_columns].copy()
    index_frame = combined.drop(
        columns=["score", "prediction_valid"], errors="ignore"
    )
    return index_frame, prediction_frame


def _match_bounds_ns(events: pd.DataFrame, task: str) -> tuple[np.ndarray, np.ndarray]:
    if task == FD_TASK:
        return (
            events["_start_ns"].to_numpy(dtype=np.int64),
            events["_end_ns"].to_numpy(dtype=np.int64),
        )
    if task == FP_TASK:
        start = events["_start_ns"].to_numpy(dtype=np.int64)
        return start - _FP_MAX_LEAD_NS, start - _FP_MIN_LEAD_NS
    raise ValueError(f"Unknown binary task {task!r}; expected one of {BINARY_TASKS}")


def _inside_bounds(times: np.ndarray, lower: int, upper: int, task: str) -> np.ndarray:
    if task == FD_TASK:
        return (times >= lower) & (times < upper)
    return (times >= lower) & (times <= upper)


def _attach_event_evaluability(
    events: pd.DataFrame,
    rows: pd.DataFrame,
    task: str,
    event_evaluability: pd.DataFrame | None,
) -> pd.DataFrame:
    events = events.copy()
    lower, upper = _match_bounds_ns(events, task)
    row_times = rows["_time_ns"].to_numpy(dtype=np.int64)
    row_runs = rows["run_id"].to_numpy(dtype=str)
    eligible_rows = rows["eligible"].to_numpy(dtype=bool)
    valid_rows = rows["_valid"].to_numpy(dtype=bool)

    derived_eligible = np.zeros(len(events), dtype=bool)
    scorable = np.zeros(len(events), dtype=bool)
    for position, event in events.iterrows():
        candidate = (row_runs == event["run_id"]) & _inside_bounds(
            row_times, int(lower[position]), int(upper[position]), task
        )
        derived_eligible[position] = bool(np.any(candidate & eligible_rows))
        scorable[position] = bool(np.any(candidate & valid_rows))

    if event_evaluability is None:
        events["eligible_event"] = derived_eligible
        events["event_eligibility_source"] = "derived_from_supplied_index"
    else:
        ledger = event_evaluability.copy()
        if "event_id" not in ledger and "fault_id" in ledger:
            ledger = ledger.rename(columns={"fault_id": "event_id"})
        _require_columns(ledger, ["run_id", "event_id"], "event_evaluability")
        ledger["run_id"] = ledger["run_id"].astype(str)
        ledger["event_id"] = ledger["event_id"].astype(str)
        if ledger.duplicated(["run_id", "event_id"]).any():
            raise ValueError("event_evaluability contains duplicate event identities")
        if task == FD_TASK:
            _require_columns(
                ledger, ["FD_eligible_active_windows"], "event_evaluability"
            )
            ledger["_ledger_eligible"] = (
                pd.to_numeric(ledger["FD_eligible_active_windows"], errors="raise") > 0
            )
        else:
            if "FP_has_eligible_pre_window" in ledger:
                ledger["_ledger_eligible"] = _bool_series(
                    ledger["FP_has_eligible_pre_window"]
                )
            elif "FP_eligible_positive_windows" in ledger:
                ledger["_ledger_eligible"] = (
                    pd.to_numeric(
                        ledger["FP_eligible_positive_windows"], errors="raise"
                    )
                    > 0
                )
            else:
                raise ValueError(
                    "event_evaluability needs FP_has_eligible_pre_window or "
                    "FP_eligible_positive_windows"
                )
        keys = ["run_id", "event_id"]
        joined = events[keys].merge(
            ledger[keys + ["_ledger_eligible"]],
            on=keys,
            how="left",
            validate="one_to_one",
        )
        if joined["_ledger_eligible"].isna().any():
            raise ValueError("event_evaluability is missing supplied episode identities")
        events["eligible_event"] = joined["_ledger_eligible"].to_numpy(dtype=bool)
        events["event_eligibility_source"] = "EVENT_EVALUABILITY.csv"
    events["scorable_event"] = scorable
    events["derived_eligible_event"] = derived_eligible
    return events


def _prepare_binary(
    index: pd.DataFrame,
    predictions: pd.DataFrame,
    episodes: pd.DataFrame,
    task: str,
    event_evaluability: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if task not in BINARY_TASKS:
        raise ValueError(f"task must be one of {BINARY_TASKS}, got {task!r}")
    rows = _join_binary(index, predictions)
    events = _normalize_episodes(episodes, rows["run_id"].unique())
    events = _attach_event_evaluability(
        events, rows, task, event_evaluability=event_evaluability
    )

    match_excluded = np.zeros(len(rows), dtype=bool)
    contaminated = np.zeros(len(rows), dtype=bool)
    times = rows["_time_ns"].to_numpy(dtype=np.int64)
    runs = rows["run_id"].to_numpy(dtype=str)
    lower, upper = _match_bounds_ns(events, task)
    for position, event in events.iterrows():
        same_run = runs == event["run_id"]
        match_excluded |= same_run & _inside_bounds(
            times, int(lower[position]), int(upper[position]), task
        )
        contaminated |= same_run & (times >= int(event["_start_ns"])) & (
            times < int(event["_exclude_end_ns"])
        )

    # Frozen denominator: every valid y=0 cutoff contributes exactly one
    # five-second grid unit.  Do not silently subtract event neighborhoods;
    # task eligibility and the frozen y label already encode exclusions.
    clean_negative = (
        rows["_valid"].to_numpy(dtype=bool)
        & rows["_y_numeric"].eq(0).to_numpy(dtype=bool)
    )
    rows["_in_event_matching_interval"] = match_excluded
    rows["_in_activity_recovery_or_prelude"] = contaminated
    rows["_clean_negative"] = clean_negative
    return rows, events


def _empty_alerts() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "alert_id",
            "run_id",
            "start_time",
            "end_time",
            "start_sample_id",
            "end_sample_id",
            "grid_point_count",
            "matched",
            "matched_event_id",
            "matched_episode_scope",
            "candidate_event_ids",
            "false_alert_clean_negative",
            "ongoing_at_event_onset",
            "classification",
        ]
    )


def _build_alerts(rows: pd.DataFrame, threshold: float) -> pd.DataFrame:
    if threshold is None or not np.isscalar(threshold):
        raise ValueError("threshold must be a scalar")
    score = rows["score"].to_numpy(dtype=float)
    positive = rows["_valid"].to_numpy(dtype=bool) & (score >= float(threshold))
    contiguous = rows["_contiguous_previous"].to_numpy(dtype=bool)
    previous_positive = np.r_[False, positive[:-1]] if len(rows) else np.array([], bool)
    next_positive = np.r_[positive[1:], False] if len(rows) else np.array([], bool)
    start_mask = positive & ~(previous_positive & contiguous)
    next_contiguous = np.r_[contiguous[1:], False] if len(rows) else np.array([], bool)
    end_mask = positive & ~(next_positive & next_contiguous)
    starts = np.flatnonzero(start_mask)
    ends = np.flatnonzero(end_mask)
    if len(starts) != len(ends):
        raise RuntimeError("Internal alert segmentation inconsistency")
    if not len(starts):
        return _empty_alerts()

    records: list[dict[str, object]] = []
    for number, (start, end) in enumerate(zip(starts, ends), start=1):
        start_row = rows.iloc[start]
        end_row = rows.iloc[end]
        records.append(
            {
                "alert_id": f"alert-{number:06d}",
                "run_id": start_row["run_id"],
                "start_time": start_row["anchor_time"],
                "end_time": end_row["anchor_time"],
                "start_sample_id": start_row["sample_id"],
                "end_sample_id": end_row["sample_id"],
                "grid_point_count": int(end - start + 1),
                "_start_row": int(start),
                "_end_row": int(end),
                "_start_ns": int(start_row["_time_ns"]),
                "_end_ns": int(end_row["_time_ns"]),
                "_start_clean_negative": bool(start_row["_clean_negative"]),
            }
        )
    return pd.DataFrame.from_records(records)


def _event_candidates(
    events: pd.DataFrame, run_id: str, alert_start_ns: int, task: str
) -> np.ndarray:
    same_run = events["run_id"].eq(str(run_id)).to_numpy(dtype=bool)
    lower, upper = _match_bounds_ns(events, task)
    if task == FD_TASK:
        inside = (alert_start_ns >= lower) & (alert_start_ns < upper)
    else:
        inside = (alert_start_ns >= lower) & (alert_start_ns <= upper)
    return np.flatnonzero(same_run & inside)


def _greedy_match(
    alerts: pd.DataFrame, events: pd.DataFrame, task: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    matched_events = events.copy()
    matched_events["matched"] = False
    matched_events["matched_alert_id"] = None
    matched_events["first_alert_time"] = None
    matched_events["delay_seconds"] = np.nan
    matched_events["lead_seconds"] = np.nan
    matched_events["delay_or_lead_seconds"] = np.nan

    if alerts.empty:
        output_alerts = _empty_alerts()
    else:
        output_alerts = alerts.copy().sort_values(
            ["run_id", "_start_ns", "alert_id"], kind="mergesort"
        ).reset_index(drop=True)
        output_alerts["matched"] = False
        output_alerts["matched_event_id"] = None
        output_alerts["matched_episode_scope"] = None
        output_alerts["candidate_event_ids"] = ""
        output_alerts["false_alert_clean_negative"] = False
        output_alerts["ongoing_at_event_onset"] = False
        output_alerts["classification"] = "unmatched_non_normal"

        # Candidate lists are descriptive and include already-used events.
        # They are populated before matching so their contents do not depend
        # on the greedy state.
        for alert_position, alert in output_alerts.iterrows():
            candidates = _event_candidates(
                matched_events,
                str(alert["run_id"]),
                int(alert["_start_ns"]),
                task,
            )
            output_alerts.at[alert_position, "candidate_event_ids"] = ";".join(
                matched_events.iloc[candidates]["event_id"].astype(str).tolist()
            )

        # Frozen deterministic one-to-one order from base_config.json:
        # process alerts by (run_id, onset, alert_id), then choose the earliest
        # still-unused candidate event by (event onset, event_id).
        used_events: set[int] = set()
        for alert_position, alert in output_alerts.iterrows():
            candidates = _event_candidates(
                matched_events,
                str(alert["run_id"]),
                int(alert["_start_ns"]),
                task,
            )
            available = [
                int(position)
                for position in candidates
                if int(position) not in used_events
            ]
            if not available:
                continue
            event_position = available[0]
            used_events.add(event_position)
            event = matched_events.iloc[event_position]
            output_alerts.at[alert_position, "matched"] = True
            output_alerts.at[alert_position, "matched_event_id"] = event["event_id"]
            output_alerts.at[
                alert_position, "matched_episode_scope"
            ] = event["episode_scope"]
            matched_events.at[event_position, "matched"] = True
            matched_events.at[event_position, "matched_alert_id"] = alert["alert_id"]
            matched_events.at[event_position, "first_alert_time"] = alert["start_time"]
            delta = (int(alert["_start_ns"]) - int(event["_start_ns"])) / _SECOND_NS
            if task == FD_TASK:
                matched_events.at[event_position, "delay_seconds"] = float(delta)
                matched_events.at[
                    event_position, "delay_or_lead_seconds"
                ] = float(delta)
            else:
                lead = float(-delta)
                matched_events.at[event_position, "lead_seconds"] = lead
                matched_events.at[
                    event_position, "delay_or_lead_seconds"
                ] = lead

        for alert_position, alert in output_alerts.iterrows():
            same_run = matched_events["run_id"].eq(str(alert["run_id"]))
            crosses_onset = (
                same_run
                & matched_events["_start_ns"].gt(int(alert["_start_ns"]))
                & matched_events["_start_ns"].le(int(alert["_end_ns"]))
            )
            ongoing = bool(crosses_onset.any())
            output_alerts.at[alert_position, "ongoing_at_event_onset"] = ongoing
            clean_false = bool(alert["_start_clean_negative"]) and not bool(
                output_alerts.at[alert_position, "matched"]
            )
            output_alerts.at[
                alert_position, "false_alert_clean_negative"
            ] = clean_false
            if bool(output_alerts.at[alert_position, "matched"]):
                if output_alerts.at[alert_position, "matched_episode_scope"] == "main":
                    classification = "matched"
                else:
                    classification = "matched_nonmain"
            elif clean_false:
                classification = "false_alert"
            elif ongoing:
                classification = "preexisting_alarm_crossing_event"
            else:
                classification = "unmatched_non_normal"
            output_alerts.at[alert_position, "classification"] = classification

    primary = matched_events["episode_scope"].eq("main")
    status = np.full(len(matched_events), "excluded_nonmain", dtype=object)
    status[primary.to_numpy() & matched_events["matched"].to_numpy(dtype=bool)] = "matched"
    status[
        primary.to_numpy()
        & ~matched_events["matched"].to_numpy(dtype=bool)
        & ~matched_events["eligible_event"].to_numpy(dtype=bool)
    ] = "no_eligible_task_window"
    status[
        primary.to_numpy()
        & ~matched_events["matched"].to_numpy(dtype=bool)
        & matched_events["eligible_event"].to_numpy(dtype=bool)
        & ~matched_events["scorable_event"].to_numpy(dtype=bool)
    ] = "no_valid_prediction"
    status[
        primary.to_numpy()
        & ~matched_events["matched"].to_numpy(dtype=bool)
        & matched_events["eligible_event"].to_numpy(dtype=bool)
        & matched_events["scorable_event"].to_numpy(dtype=bool)
    ] = "missed"
    status[
        ~primary.to_numpy() & matched_events["matched"].to_numpy(dtype=bool)
    ] = "excluded_nonmain_matched"
    matched_events["evaluation_status"] = status
    matched_events["primary_event"] = primary.to_numpy(dtype=bool)

    if not output_alerts.empty:
        output_alerts = output_alerts.drop(
            columns=[
                "_start_row",
                "_end_row",
                "_start_ns",
                "_end_ns",
                "_start_clean_negative",
            ]
        )
    return output_alerts, matched_events


def _sample_metrics(rows: pd.DataFrame, threshold: float) -> dict[str, object]:
    scored = rows["_valid"].to_numpy(dtype=bool) & rows["_y_numeric"].notna().to_numpy()
    y = rows.loc[scored, "_y_numeric"].to_numpy(dtype=int)
    score = rows.loc[scored, "score"].to_numpy(dtype=float)
    predicted = score >= float(threshold)
    tp = int(np.sum((y == 1) & predicted))
    fp = int(np.sum((y == 0) & predicted))
    fn = int(np.sum((y == 1) & ~predicted))
    tn = int(np.sum((y == 0) & ~predicted))
    eligible_count = int(rows["eligible"].sum())
    if len(np.unique(y)) == 2:
        auprc = _average_precision(y, score)
    else:
        auprc = np.nan
    return {
        "scored_sample_count": int(len(y)),
        "eligible_sample_count": eligible_count,
        "prediction_coverage": (
            float(len(y) / eligible_count) if eligible_count else np.nan
        ),
        "sample_true_positive_count": tp,
        "sample_false_positive_count": fp,
        "sample_false_negative_count": fn,
        "sample_true_negative_count": tn,
        "auprc": auprc,
        "auprc_unadjusted": auprc,
        "precision": float(tp / (tp + fp)) if tp + fp else 0.0,
        "recall": float(tp / (tp + fn)) if tp + fn else 0.0,
        "f1": float(2 * tp / (2 * tp + fp + fn)) if 2 * tp + fp + fn else 0.0,
        "f1_unadjusted": (
            float(2 * tp / (2 * tp + fp + fn)) if 2 * tp + fp + fn else 0.0
        ),
        "point_adjustment": False,
    }


def _event_metric_record(events: pd.DataFrame) -> dict[str, object]:
    primary = events["episode_scope"].eq("main")
    eligible = primary & events["eligible_event"]
    scorable = primary & events["scorable_event"]
    hits = primary & events["matched"]
    event_count = int(primary.sum())
    eligible_count = int(eligible.sum())
    return {
        "event_count": event_count,
        "eligible_event_count": eligible_count,
        "scorable_event_count": int(scorable.sum()),
        "hit_event_count": int(hits.sum()),
        "missed_event_count": int(event_count - hits.sum()),
        "event_recall": float(hits.sum() / event_count) if event_count else np.nan,
        "event_recall_all_main": (
            float(hits.sum() / event_count) if event_count else np.nan
        ),
        "eligible_event_recall": (
            float(hits.sum() / eligible_count) if eligible_count else np.nan
        ),
        "event_recall_eligible_main": (
            float(hits.sum() / eligible_count) if eligible_count else np.nan
        ),
        "event_record_count": int(len(events)),
        "main_event_count": event_count,
        "nonmain_event_count": int((~primary).sum()),
        "nonmain_hit_count": int((~primary & events["matched"]).sum()),
        "prelude_event_count": int(
            events["episode_scope"].str.contains("prelude", case=False, na=False).sum()
        ),
    }


def _timing_metric_record(events: pd.DataFrame, task: str) -> dict[str, object]:
    primary_matched = events["episode_scope"].eq("main") & events["matched"]
    if task == FD_TASK:
        values = events.loc[primary_matched, "delay_seconds"].dropna().to_numpy(float)
        prefix = "first_detection_delay"
    else:
        values = events.loc[primary_matched, "lead_seconds"].dropna().to_numpy(float)
        prefix = "recorded_onset_lead"
    if not len(values):
        return {
            f"{prefix}_count": 0,
            f"{prefix}_mean_seconds": np.nan,
            f"{prefix}_median_seconds": np.nan,
            f"{prefix}_p25_seconds": np.nan,
            f"{prefix}_p75_seconds": np.nan,
            f"{prefix}_min_seconds": np.nan,
            f"{prefix}_max_seconds": np.nan,
        }
    return {
        f"{prefix}_count": int(len(values)),
        f"{prefix}_mean_seconds": float(np.mean(values)),
        f"{prefix}_median_seconds": float(np.median(values)),
        f"{prefix}_p25_seconds": float(np.quantile(values, 0.25)),
        f"{prefix}_p75_seconds": float(np.quantile(values, 0.75)),
        f"{prefix}_min_seconds": float(np.min(values)),
        f"{prefix}_max_seconds": float(np.max(values)),
    }


def summarize_event_strata(event_results: pd.DataFrame) -> pd.DataFrame:
    """Summarize all-main and eligible-main recall by frozen reporting strata."""

    if event_results.empty:
        return pd.DataFrame(
            columns=[
                "group",
                "event_count",
                "eligible_event_count",
                "scorable_event_count",
                "hit_event_count",
                "event_recall_all_main",
                "event_recall_eligible_main",
            ]
        )
    primary = event_results.loc[event_results["episode_scope"].eq("main")].copy()
    primary["stop_network"] = np.where(
        primary["fault_type"].eq("instance-stop"), "stop", "network"
    )
    groups: list[tuple[str, pd.DataFrame]] = [("all", primary)]
    for field in ("run_id", "fault_type", "target", "stop_network"):
        groups.extend(
            (f"{field}={key}", group)
            for key, group in primary.groupby(field, sort=True, dropna=False)
        )
    records: list[dict[str, object]] = []
    for name, group in groups:
        event_count = int(len(group))
        eligible_count = int(group["eligible_event"].sum())
        hits = int(group["matched"].sum())
        records.append(
            {
                "group": name,
                "event_count": event_count,
                "eligible_event_count": eligible_count,
                "scorable_event_count": int(group["scorable_event"].sum()),
                "hit_event_count": hits,
                "event_recall_all_main": (
                    float(hits / event_count) if event_count else np.nan
                ),
                "event_recall_eligible_main": (
                    float(hits / eligible_count) if eligible_count else np.nan
                ),
            }
        )
    return pd.DataFrame.from_records(records)


def summarize_strata(event_results: pd.DataFrame) -> pd.DataFrame:
    """Stable pipeline alias for binary event strata."""

    return summarize_event_strata(event_results)


def _threshold_result(
    rows: pd.DataFrame,
    events: pd.DataFrame,
    threshold: float,
    task: str,
    *,
    return_tables: bool,
) -> dict[str, object] | tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    segmented = _build_alerts(rows, threshold)
    alerts, event_results = _greedy_match(segmented, events, task)
    exposure_hours = float(rows["_clean_negative"].sum() * GRID_SECONDS / 3600.0)
    false_alert_count = (
        int(alerts["false_alert_clean_negative"].sum()) if len(alerts) else 0
    )
    metrics = {
        "threshold": float(threshold),
        **_event_metric_record(event_results),
        **_timing_metric_record(event_results, task),
        "alert_count": int(len(alerts)),
        "matched_alert_count": int(alerts["matched"].sum()) if len(alerts) else 0,
        "false_alert_count": false_alert_count,
        "effective_normal_grid_points": int(rows["_clean_negative"].sum()),
        "effective_normal_hours": exposure_hours,
        "exposure_hours": exposure_hours,
        "false_alerts_per_hour": (
            float(false_alert_count / exposure_hours) if exposure_hours else np.nan
        ),
        "actual_false_alerts_per_hour": (
            float(false_alert_count / exposure_hours) if exposure_hours else np.nan
        ),
        "grid_seconds": GRID_SECONDS,
        "segment_gap_seconds": GAP_SECONDS,
        "matching_policy": MATCHING_POLICY,
        "point_adjustment": False,
        **_sample_metrics(rows, threshold),
    }
    if not return_tables:
        return metrics
    clean_events = event_results.drop(
        columns=["_start_ns", "_end_ns", "_exclude_end_ns", "_event_pos"],
        errors="ignore",
    )
    return metrics, clean_events, alerts


def evaluate_binary(
    predictions_df: pd.DataFrame,
    episodes_df: pd.DataFrame,
    threshold: float,
    task: str,
    *,
    index: pd.DataFrame | None = None,
    event_evaluability: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Evaluate frozen FD or FP scores without point adjustment.

    ``event_evaluability`` should be the package ledger when available.  Main
    recall is always reported against all main events and, separately, against
    main events with at least one eligible task window.  Non-main/prelude rows
    remain in ``event_results`` with an explicit exclusion status.
    """

    index_frame, prediction_frame = _binary_inputs(predictions_df, index)
    rows, events = _prepare_binary(
        index_frame,
        prediction_frame,
        episodes_df,
        task,
        event_evaluability=event_evaluability,
    )
    metrics, event_results, alerts = _threshold_result(
        rows, events, threshold, task, return_tables=True
    )
    return {
        "metrics": metrics,
        "event_results": event_results,
        "alerts": alerts,
        "event_metrics_by_group": summarize_event_strata(event_results),
    }


def _event_windows_overlap(events: pd.DataFrame, task: str) -> bool:
    lower, upper = _match_bounds_ns(events, task)
    work = events[["run_id"]].copy()
    work["lower"] = lower
    work["upper"] = upper
    for _, group in work.groupby("run_id", sort=False):
        ordered = group.sort_values(["lower", "upper"], kind="mergesort")
        previous_upper: int | None = None
        for row in ordered.itertuples(index=False):
            if previous_upper is not None:
                if task == FD_TASK and int(row.lower) < previous_upper:
                    return True
                if task == FP_TASK and int(row.lower) <= previous_upper:
                    return True
            previous_upper = max(previous_upper or int(row.upper), int(row.upper))
    return False


def _single_candidate_event_map(
    rows: pd.DataFrame, events: pd.DataFrame, task: str
) -> np.ndarray:
    mapping = np.full(len(rows), -1, dtype=int)
    times = rows["_time_ns"].to_numpy(dtype=np.int64)
    runs = rows["run_id"].to_numpy(dtype=str)
    lower, upper = _match_bounds_ns(events, task)
    for position, event in events.iterrows():
        inside = (runs == event["run_id"]) & _inside_bounds(
            times, int(lower[position]), int(upper[position]), task
        )
        if np.any(mapping[inside] >= 0):
            raise RuntimeError("Fast threshold scan received overlapping event windows")
        mapping[inside] = int(position)
    return mapping


def _fast_threshold_records(
    rows: pd.DataFrame, events: pd.DataFrame, task: str
) -> list[dict[str, object]]:
    """Exact descending threshold sweep for non-overlapping event windows."""

    valid = rows["_valid"].to_numpy(dtype=bool)
    score = rows["score"].to_numpy(dtype=float)
    valid_positions = np.flatnonzero(valid)
    if not len(valid_positions):
        return []
    order = valid_positions[
        np.argsort(-score[valid_positions], kind="mergesort")
    ]
    candidate_event = _single_candidate_event_map(rows, events, task)
    clean = rows["_clean_negative"].to_numpy(dtype=bool)
    contiguous = rows["_contiguous_previous"].to_numpy(dtype=bool)
    main = events["episode_scope"].eq("main").to_numpy(dtype=bool)
    event_start_counts = np.zeros(len(events), dtype=int)
    active = np.zeros(len(rows), dtype=bool)
    active_starts = np.zeros(len(rows), dtype=bool)
    hit_main = 0
    hit_nonmain = 0
    false_alert_count = 0
    alert_count = 0
    exposure_hours = float(clean.sum() * GRID_SECONDS / 3600.0)

    def contribute(position: int, direction: int) -> None:
        nonlocal hit_main, hit_nonmain, false_alert_count, alert_count
        alert_count += direction
        if clean[position]:
            false_alert_count += direction
        event_position = int(candidate_event[position])
        if event_position >= 0:
            before = event_start_counts[event_position] > 0
            event_start_counts[event_position] += direction
            after = event_start_counts[event_position] > 0
            if main[event_position]:
                hit_main += int(after) - int(before)
            else:
                hit_nonmain += int(after) - int(before)

    def add_start(position: int) -> None:
        if active_starts[position]:
            raise RuntimeError("Attempted to add an active alert start twice")
        active_starts[position] = True
        contribute(position, 1)

    def remove_start(position: int) -> None:
        if not active_starts[position]:
            raise RuntimeError("Attempted to remove a non-start grid point")
        contribute(position, -1)
        active_starts[position] = False

    def record(threshold: float) -> dict[str, object]:
        event_count = int(main.sum())
        eligible_count = int((main & events["eligible_event"].to_numpy(bool)).sum())
        return {
            "threshold": float(threshold),
            "event_count": event_count,
            "eligible_event_count": eligible_count,
            "scorable_event_count": int(
                (main & events["scorable_event"].to_numpy(bool)).sum()
            ),
            "hit_event_count": int(hit_main),
            "event_recall": (
                float(hit_main / event_count) if event_count else np.nan
            ),
            "eligible_event_recall": (
                float(hit_main / eligible_count) if eligible_count else np.nan
            ),
            "nonmain_hit_count": int(hit_nonmain),
            "false_alert_count": int(false_alert_count),
            "alert_count": int(alert_count),
            "effective_normal_hours": exposure_hours,
            "exposure_hours": exposure_hours,
            "false_alerts_per_hour": (
                float(false_alert_count / exposure_hours)
                if exposure_hours
                else np.nan
            ),
            "actual_false_alerts_per_hour": (
                float(false_alert_count / exposure_hours)
                if exposure_hours
                else np.nan
            ),
        }

    records = [record(float("inf"))]
    cursor = 0
    while cursor < len(order):
        value = float(score[order[cursor]])
        batch_end = cursor
        while batch_end < len(order) and score[order[batch_end]] == value:
            batch_end += 1
        for order_position in range(cursor, batch_end):
            position = int(order[order_position])
            left_active = (
                position > 0
                and contiguous[position]
                and active[position - 1]
            )
            right_active = (
                position + 1 < len(rows)
                and contiguous[position + 1]
                and active[position + 1]
            )
            if right_active:
                remove_start(position + 1)
            active[position] = True
            if not left_active:
                add_start(position)
        records.append(record(value))
        cursor = batch_end
    return records


def _threshold_records(
    rows: pd.DataFrame, events: pd.DataFrame, task: str
) -> tuple[list[dict[str, object]], str]:
    valid_scores = rows.loc[rows["_valid"], "score"].to_numpy(dtype=float)
    if not len(valid_scores):
        return [], "no_valid_scores"
    if not _event_windows_overlap(events, task):
        return _fast_threshold_records(rows, events, task), "exact_unique_scores_fast_sweep"

    # Overlapping event windows require the full frozen greedy matcher because
    # one onset may be eligible for multiple events.  This path is exact; the
    # package's recorded events are non-overlapping, so ordinary runs use the
    # linearithmic sweep above.
    candidates = [float("inf")]
    candidates.extend(sorted(np.unique(valid_scores).tolist(), reverse=True))
    records = [
        _threshold_result(rows, events, threshold, task, return_tables=False)
        for threshold in candidates
    ]
    return records, "exact_unique_scores_full_greedy_overlap_fallback"


def calibrate_thresholds(
    predictions_df: pd.DataFrame,
    episodes_df: pd.DataFrame,
    task: str,
    *,
    budgets: Sequence[float] = (0.1, 1.0),
    index: pd.DataFrame | None = None,
    event_evaluability: pd.DataFrame | None = None,
) -> dict[str, dict[str, object]]:
    """Freeze D05 thresholds without reading test predictions or labels.

    Among candidates satisfying each false-alert budget, selection maximizes
    main-event hits, then minimizes the false-alert count, then chooses the
    higher threshold.  Every returned row reports the target budget, achieved
    false-alert rate, and effective normal hours.  A missing-score or
    zero-exposure state is explicit rather than silently claiming the budget.
    """

    index_frame, prediction_frame = _binary_inputs(predictions_df, index)
    _require_columns(index_frame, ["split"], "index")
    if len(index_frame) and not index_frame["split"].astype(str).eq("validation").all():
        raise ValueError("Threshold calibration is restricted to validation rows")
    if (
        "slot" in index_frame
        and len(index_frame)
        and not index_frame["slot"].astype(str).eq("D05").all()
    ):
        raise ValueError("Threshold calibration is restricted to D05")
    normalized_budgets = [float(budget) for budget in budgets]
    if any(not np.isfinite(budget) or budget < 0 for budget in normalized_budgets):
        raise ValueError("False-alert budgets must be finite and non-negative")

    rows, events = _prepare_binary(
        index_frame,
        prediction_frame,
        episodes_df,
        task,
        event_evaluability=event_evaluability,
    )
    records, search = _threshold_records(rows, events, task)
    exposure_hours = float(rows["_clean_negative"].sum() * GRID_SECONDS / 3600.0)
    valid_score_count = int(rows["_valid"].sum())
    output: dict[str, dict[str, object]] = {}

    for budget in normalized_budgets:
        common: dict[str, object] = {
            "target_budget_per_hour": budget,
            "budget_per_hour": budget,
            "effective_normal_hours": exposure_hours,
            "exposure_hours": exposure_hours,
            "false_alarm_resolution_per_hour": (
                float(1.0 / exposure_hours) if exposure_hours else np.nan
            ),
            "calibration_split": "validation",
            "calibration_slot": "D05",
            "matching_policy": MATCHING_POLICY,
            "point_adjustment": False,
            "test_data_used": False,
            "validation_labels_used": True,
            "valid_score_count": valid_score_count,
            "candidate_count": int(len(records)),
            "search": search,
        }
        if not valid_score_count:
            output[str(budget)] = {
                **common,
                "status": "no_valid_scores",
                "threshold": None,
                "hit_event_count": 0,
                "false_alert_count": 0,
                "false_alerts_per_hour": np.nan,
                "actual_false_alerts_per_hour": np.nan,
                "feasible_candidate_count": 0,
            }
            continue
        if exposure_hours <= 0:
            output[str(budget)] = {
                **common,
                "status": "no_clean_negative_exposure",
                "threshold": None,
                "hit_event_count": 0,
                "false_alert_count": 0,
                "false_alerts_per_hour": np.nan,
                "actual_false_alerts_per_hour": np.nan,
                "feasible_candidate_count": 0,
            }
            continue

        feasible = [
            record
            for record in records
            if np.isfinite(record["false_alerts_per_hour"])
            and float(record["false_alerts_per_hour"]) <= budget + 1e-12
        ]
        if not feasible:
            output[str(budget)] = {
                **common,
                "status": "no_feasible_threshold",
                "threshold": None,
                "hit_event_count": 0,
                "false_alert_count": 0,
                "false_alerts_per_hour": np.nan,
                "actual_false_alerts_per_hour": np.nan,
                "feasible_candidate_count": 0,
            }
            continue
        best = max(
            feasible,
            key=lambda record: (
                int(record["hit_event_count"]),
                -int(record["false_alert_count"]),
                float(record["threshold"]),
            ),
        )
        no_alert = int(best["alert_count"]) == 0
        output[str(budget)] = {
            **best,
            **common,
            "status": "frozen_no_alert_threshold" if no_alert else "frozen",
            "feasible_candidate_count": int(len(feasible)),
        }
    return output


def calibrate_threshold(
    predictions_df: pd.DataFrame,
    episodes_df: pd.DataFrame,
    budget: float,
    task: str,
    *,
    index: pd.DataFrame | None = None,
    event_evaluability: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Freeze one D05 operating point; see :func:`calibrate_thresholds`."""

    normalized_budget = float(budget)
    result = calibrate_thresholds(
        predictions_df,
        episodes_df,
        task,
        budgets=(normalized_budget,),
        index=index,
        event_evaluability=event_evaluability,
    )
    return result[str(normalized_budget)]


def classification_scores(
    y_true: Sequence[object],
    y_pred: Sequence[object],
    labels: Sequence[object] | None = None,
) -> dict[str, object]:
    """Event-level localization scores; abstentions remain failed cases."""

    truth = np.asarray(y_true).astype(str)
    prediction = np.asarray(y_pred).astype(str)
    if len(truth) != len(prediction):
        raise ValueError("y_true and y_pred must have equal length")
    known_labels = [str(label) for label in (labels or sorted(np.unique(truth)))]
    present_labels = [label for label in known_labels if np.any(truth == label)]
    covered = prediction != ABSTAIN_LABEL
    recalls = [
        float(np.mean(prediction[truth == label] == label))
        for label in present_labels
    ]
    return {
        "event_count": int(len(truth)),
        "predicted_event_count": int(covered.sum()),
        "coverage": float(covered.mean()) if len(truth) else np.nan,
        "top1": float(np.mean(truth == prediction)) if len(truth) else np.nan,
        "balanced_accuracy": float(np.mean(recalls)) if recalls else np.nan,
        "macro_f1": (
            _macro_f1(truth, prediction, present_labels)
            if len(truth) and present_labels
            else np.nan
        ),
    }


def _join_localization(
    index: pd.DataFrame, predictions: pd.DataFrame
) -> pd.DataFrame:
    _require_columns(
        index,
        [
            "sample_id",
            "run_id",
            "eligible",
            "y",
            "fault_id",
            "fault_type",
            "target_instance",
        ],
        "index",
    )
    _require_columns(predictions, ["sample_id", "y_pred"], "predictions")
    if index["sample_id"].duplicated().any():
        raise ValueError("FL index contains duplicate sample_id values")
    if index.duplicated(["run_id", "fault_id"]).any():
        raise ValueError("FL index must contain exactly one row per run/event")
    if predictions["sample_id"].duplicated().any():
        raise ValueError("FL predictions contains duplicate sample_id values")
    if not predictions["sample_id"].isin(index["sample_id"]).all():
        raise ValueError("FL predictions contains sample_id values outside the index")
    columns = ["sample_id", "y_pred"]
    if "prediction_valid" in predictions:
        columns.append("prediction_valid")
    pred = predictions[columns].copy()
    pred["_prediction_present"] = True
    if "prediction_valid" not in pred:
        pred["prediction_valid"] = True
    rows = index.copy().merge(pred, on="sample_id", how="left", validate="one_to_one")
    rows["eligible"] = _bool_series(rows["eligible"])
    rows["prediction_valid"] = _bool_series(rows["prediction_valid"])
    rows["_prediction_present"] = rows["_prediction_present"].fillna(False).astype(bool)
    valid = (
        rows["eligible"]
        & rows["prediction_valid"]
        & rows["_prediction_present"]
        & rows["y_pred"].notna()
        & rows["y_pred"].astype(str).ne(ABSTAIN_LABEL)
    )
    rows["localization_prediction"] = np.where(
        valid, rows["y_pred"].astype(str), ABSTAIN_LABEL
    )
    rows["abstained"] = ~valid
    rows["event_id"] = rows["fault_id"].astype(str)
    rows["target"] = rows["target_instance"].astype(str)
    rows["matched"] = rows["localization_prediction"].eq(rows["y"].astype(str))
    rows["primary_event"] = True
    if "episode_scope" in rows:
        rows["primary_event"] = rows["episode_scope"].fillna("main").eq("main")
    return rows


def _localization_inputs(
    predictions_df: pd.DataFrame, index: pd.DataFrame | None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if index is not None:
        return index.copy(), predictions_df.copy()
    combined = predictions_df.copy().reset_index(drop=True)
    if "sample_id" not in combined:
        combined["sample_id"] = [f"localization-row-{i}" for i in range(len(combined))]
    if "eligible" not in combined:
        combined["eligible"] = True
    _require_columns(combined, ["sample_id", "y_pred"], "predictions_df")
    prediction_columns = ["sample_id", "y_pred"]
    if "prediction_valid" in combined:
        prediction_columns.append("prediction_valid")
    prediction_frame = combined[prediction_columns].copy()
    index_frame = combined.drop(
        columns=["y_pred", "prediction_valid"], errors="ignore"
    )
    return index_frame, prediction_frame


def evaluate_localization(
    predictions_df: pd.DataFrame,
    *,
    index: pd.DataFrame | None = None,
    labels: Sequence[object] | None = None,
) -> dict[str, pd.DataFrame]:
    """Evaluate one FL prediction per original event case."""

    index_frame, prediction_frame = _localization_inputs(predictions_df, index)
    rows = _join_localization(index_frame, prediction_frame)
    label_order = [
        str(label) for label in (labels or sorted(rows["y"].astype(str).unique()))
    ]
    rows["stop_network"] = np.where(
        rows["fault_type"].eq("instance-stop"), "stop", "network"
    )
    groups: list[tuple[str, pd.DataFrame]] = [("all", rows)]
    for field in ("split", "run_id", "fault_type", "target", "stop_network"):
        if field in rows:
            groups.extend(
                (f"{field}={key}", group)
                for key, group in rows.groupby(field, sort=True, dropna=False)
            )

    metrics: list[dict[str, object]] = []
    matrices: list[dict[str, object]] = []
    predicted_labels = label_order + [ABSTAIN_LABEL]
    for name, group in groups:
        score = classification_scores(
            group["y"].astype(str),
            group["localization_prediction"].astype(str),
            labels=label_order,
        )
        metrics.append(
            {
                "group": name,
                **score,
                "eligible_event_count": int(group["eligible"].sum()),
                "abstained_event_count": int(group["abstained"].sum()),
            }
        )
        matrix = _confusion_matrix(
            group["y"].astype(str),
            group["localization_prediction"].astype(str),
            predicted_labels,
        )
        for true_position, truth in enumerate(label_order):
            for prediction_position, prediction in enumerate(predicted_labels):
                matrices.append(
                    {
                        "group": name,
                        "y_true": truth,
                        "y_pred": prediction,
                        "count": int(matrix[true_position, prediction_position]),
                    }
                )

    return {
        "metrics": pd.DataFrame.from_records(metrics),
        "event_results": rows.drop(
            columns=["_prediction_present"], errors="ignore"
        ),
        "confusion_matrix": pd.DataFrame.from_records(matrices),
    }
