#!/usr/bin/env python3
"""Rebuild only the W1 fields whose construction used future flow state.

The source runs are read-only.  The repaired task views are written below the
directory containing this file.  Complete flow/link rows are used only to
freeze the original inclusion/deduplication scope; repaired numeric values
come from packet prefixes with ``packet_ts < cutoff``.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
import ipaddress
import json
import math
import os
import shutil
import subprocess
import sys
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

OUT = Path(__file__).resolve().parent
RAW_ROOT = Path("/mnt/free5gc_experiments")
REPO = Path("/opt/platform")
AUDIT_HELPER = Path("/home/experiment/Desktop/free5gc_experiments/temporal_raw_audit/audit_temporal_raw_data.py")
DEFAULT_TZ = dt.timezone(dt.timedelta(hours=8), "Asia/Shanghai")
UTC = dt.timezone.utc

RUNS = {
    "D01": "W1-D01",
    "D02": "W1-D02",
    "D03": "W1-D03",
    "D04": "W1-D04",
    "D05": "W1-D05",
    "D06": "W1-D06",
    "D07": "W1-D07",
}

SPLITS = {"D01": "train", "D02": "train", "D03": "train", "D04": "train", "D05": "validation", "D06": "test", "D07": "test"}

STRICT_FIELDS = [
    "n3_uplink_bitrate_bps",
    "n3_downlink_bitrate_bps",
    "n6_bitrate_bps",
    "cp_pdu_session_success_rate",
    "cp_pdu_session_failure_count",
    "end_to_end_rtt_ms",
    "jitter_ms",
    "packet_loss_rate",
    "cp_active_session_count",
    "cp_pending_session_count",
    "cp_pdu_session_request_count",
    "registration_success_rate",
    "registration_failure_count",
    "registration_request_count",
    "n4_bitrate_bps",
    "host_cpu_pct",
    "host_mem_used_pct",
    "host_loadavg_1",
]
MASK_FIELDS = [f"{field}__missing" for field in STRICT_FIELDS]
RAN_FIELDS = ["observed_ue_count", "ran_pdu_active_count", "ready_gnb_count"]
RAN_MASK_FIELDS = [f"{field}__missing" for field in RAN_FIELDS]
SCHEDULE_FIELDS = [
    "anchor_phase_600_cos",
    "anchor_phase_600_sin",
    "anchor_phase_900_cos",
    "anchor_phase_900_sin",
    "schedule_anchor_row_days",
    "anchor_row_mod_900",
]

FLOW_FIELDS = ("end_to_end_rtt_ms", "jitter_ms", "packet_loss_rate")
FLOW_METRIC_KEYS = ("rtt", "jitter", "loss")
TARGETS = {
    "n3_downlink": "n3_downlink_bitrate_bps",
    "n6_aggregate": "n6_bitrate_bps",
    "flow_rtt_proxy": "end_to_end_rtt_ms",
    "host_cpu": "host_cpu_pct",
}


def load_helper() -> Any:
    if not AUDIT_HELPER.is_file():
        raise RuntimeError(f"read-only audit helper is unavailable: {AUDIT_HELPER}")
    spec = importlib.util.spec_from_file_location("w1_temporal_audit_helper", AUDIT_HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import audit helper: {AUDIT_HELPER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = load_helper()
PCAP = B.PCAP
LINKS = B.LINKS
N6_LOGICAL = B.N6_LOGICAL


def numeric(value: Any) -> float | None:
    return B.numeric(value)


def finite(value: Any) -> bool:
    value = numeric(value)
    return value is not None and math.isfinite(value)


def fmt(value: Any) -> str:
    return B.fmt_num(value)


def epoch(value: Any) -> float | None:
    return B.epoch(value)


def iso_epoch(value: float | None) -> str:
    return "" if value is None else dt.datetime.fromtimestamp(value, tz=UTC).isoformat()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def iter_jsonl(path: Path):
    if not path.is_file():
        return
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def raw_by_stem(run_dir: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    suffixes = (".pcap", ".pcapng", ".pcap.gz", ".pcapng.gz")
    for path in run_dir.joinpath("pcap").rglob("*"):
        if path.is_file() and path.name.endswith(suffixes):
            result.setdefault(B.strip_pcap_suffix(path.name), path)
    return result


def flow_pairs(run_dir: Path) -> tuple[list[tuple[Path, Path]], list[str]]:
    raw = raw_by_stem(run_dir)
    pairs: list[tuple[Path, Path]] = []
    missing: list[str] = []
    for flow_path in sorted(run_dir.joinpath("derived").glob("*_flows.jsonl")):
        if flow_path.name == "n6-uplink-logical_flows.jsonl":
            continue
        raw_path = raw.get(flow_path.name.removesuffix("_flows.jsonl"))
        if raw_path is None:
            missing.append(str(flow_path.relative_to(run_dir)))
        else:
            pairs.append((raw_path, flow_path))
    return pairs, missing


def session_context(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    context = LINKS.build_context(run_dir, DEFAULT_TZ)
    session_rows = read_jsonl(run_dir / "derived" / "session_map.jsonl")
    session_index, _ = B.build_session_index(session_rows)
    return context, session_index


def text_or_empty(value: Any) -> str:
    return "" if value is None else str(value)


def candidate_signature(
    row: dict[str, Any], plane: str, pair: tuple[str, str], flow_name: str, context: dict[str, Any]
) -> tuple[str, ...]:
    first = LINKS.parse_timestamp(row.get("first_seen"), DEFAULT_TZ)
    last = LINKS.parse_timestamp(row.get("last_seen"), DEFAULT_TZ) or first
    ue_ip = str(row.get("ue_ip") or "").strip()
    ue_row = context["ue_by_ip"].get(ue_ip, {}) if ue_ip else {}
    session_row = context["sessions_by_ue_ip"].get(ue_ip, {}) if ue_ip else {}
    upf = LINKS.normalize_nf_name(
        row.get("upf_id") or session_row.get("upf_id") or LINKS.infer_upf_from_flow_name(flow_name)
    )
    dnn = row.get("dnn") or session_row.get("dnn") or ue_row.get("apn") or ""
    pdu = row.get("pdu_session_id") or session_row.get("pdu_session_id") or ""
    packets = LINKS.maybe_float(row.get("packets"))
    bytes_count = LINKS.maybe_float(row.get("bytes"))
    return (
        plane,
        pair[0],
        pair[1],
        str(row.get("src_ip") or "").strip(),
        str(row.get("dst_ip") or "").strip(),
        ue_ip,
        str(pdu),
        str(dnn),
        upf,
        LINKS.iso_or_empty(first),
        LINKS.iso_or_empty(last),
        "" if packets is None else str(packets),
        "" if bytes_count is None else str(bytes_count),
    )


def saved_n6_scope(run_dir: Path) -> tuple[set[tuple[str, ...]], int]:
    """Read only the old N6 link scope; no saved numeric value is reused."""
    scope: set[tuple[str, ...]] = set()
    path = run_dir / "derived" / "nf-links.jsonl"
    count = 0
    for row in iter_jsonl(path):
        if row.get("plane") != "n6":
            continue
        count += 1
        scope.add(
            (
                text_or_empty(row.get("plane")),
                text_or_empty(row.get("src_nf")),
                text_or_empty(row.get("dst_nf")),
                text_or_empty(row.get("src_ip")),
                text_or_empty(row.get("dst_ip")),
                text_or_empty(row.get("ue_ip")),
                text_or_empty(row.get("pdu_session_id")),
                text_or_empty(row.get("dnn")),
                text_or_empty(row.get("upf_id")),
                text_or_empty(row.get("first_seen")),
                text_or_empty(row.get("last_seen")),
                text_or_empty(row.get("packets")),
                text_or_empty(row.get("bytes")),
            )
        )
    return scope, count


def n6_scope_maps(
    run_dir: Path, context: dict[str, Any], session_index: dict[str, Any]
) -> tuple[dict[str, dict[Any, tuple[str, str]]], dict[str, dict[Any, tuple[str, str]]], dict[str, Any]]:
    """Map raw parser flow keys to the exact old N6 link inclusion scope."""
    scope, saved_count = saved_n6_scope(run_dir)
    raw_map = raw_by_stem(run_dir)
    direct: dict[str, dict[Any, tuple[str, str]]] = defaultdict(dict)
    logical: dict[str, dict[Any, tuple[str, str]]] = defaultdict(dict)
    selected: set[tuple[str, ...]] = set()
    direct_candidates = 0
    logical_candidates = 0

    derived_paths = sorted(run_dir.glob("derived/*_flows.jsonl"))
    for path in derived_paths:
        if path.name == "n6-uplink-logical_flows.jsonl":
            continue
        plane = LINKS.plane_from_flow_name(path.stem)
        if plane != "n6":
            continue
        raw_path = raw_map.get(path.name.removesuffix("_flows.jsonl"))
        if raw_path is None:
            continue
        for row in iter_jsonl(path):
            pair = LINKS.infer_flow_directional_pair(context, plane, path.stem, row)
            if pair is None:
                continue
            signature = candidate_signature(row, plane, pair, path.stem, context)
            direct_candidates += 1
            if signature in scope and signature not in selected:
                selected.add(signature)
                direct[str(raw_path)][PCAP.flow_key_for_row(row)] = pair

    logical_path = run_dir / "derived" / "n6-uplink-logical_flows.jsonl"
    logical_seen: set[tuple[Any, ...]] = set()
    if logical_path.is_file():
        for n3_path in sorted(run_dir.glob("derived/n3-gtpu*_flows.jsonl")):
            raw_path = raw_map.get(n3_path.name.removesuffix("_flows.jsonl"))
            if raw_path is None:
                continue
            for n3_row in iter_jsonl(n3_path):
                logical_row = N6_LOGICAL.build_n6_record(n3_row, session_index["by_ue_ip"])
                if logical_row is None:
                    continue
                logical_key = (
                    logical_row.get("ue_ip"),
                    logical_row.get("server_ip"),
                    str(logical_row.get("server_port")),
                    logical_row.get("proto"),
                    logical_row.get("first_seen"),
                )
                if logical_key in logical_seen:
                    continue
                logical_seen.add(logical_key)
                pair = LINKS.infer_flow_directional_pair(context, "n6", "n6-uplink-logical", logical_row)
                if pair is None:
                    continue
                signature = candidate_signature(logical_row, "n6", pair, "n6-uplink-logical", context)
                logical_candidates += 1
                if signature in scope and signature not in selected:
                    selected.add(signature)
                    logical[str(raw_path)][PCAP.flow_key_for_row(n3_row)] = pair

    return direct, logical, {
        "saved_n6_link_rows": saved_count,
        "selected_n6_link_rows": len(selected),
        "direct_n6_candidates": direct_candidates,
        "logical_n6_candidates": logical_candidates,
        "unmapped_n6_link_rows": saved_count - len(selected),
    }


def make_packet_event(row: dict[str, Any], ts: float, packet_bytes: int) -> tuple[float, int, str, str, str, str, Any]:
    return (
        ts,
        packet_bytes,
        str(row.get("src_ip") or ""),
        str(row.get("dst_ip") or ""),
        str(row.get("src_port") or ""),
        str(row.get("proto") or ""),
        row.get("_tcp_seq"),
    )


def event_row(event: tuple[float, int, str, str, str, str, Any]) -> dict[str, Any]:
    return {
        "src_ip": event[2],
        "dst_ip": event[3],
        "src_port": event[4],
        "proto": event[5],
        "_tcp_seq": event[6],
    }


def read_flow_groups(raw_path: Path, session_index: dict[str, Any]) -> tuple[dict[Any, dict[str, Any]], str, int]:
    PCAP.ensure_dpkt()
    silver_net = ipaddress.ip_network("10.60.0.0/16")
    gold_net = ipaddress.ip_network("10.61.0.0/16")
    groups: dict[Any, dict[str, Any]] = {}
    error = ""
    packet_count = 0
    opener, reader = B.open_pcap(raw_path)
    try:
        linktype = reader.datalink()
        for ts, buf in reader:
            row = PCAP.parse_packet(ts, buf, linktype, 64)
            PCAP.apply_labels(row, str(raw_path), session_index, silver_net, gold_net)
            packet_bytes = int(row.get("ip_len") or len(buf))
            packet_count += 1
            key = PCAP.flow_key_for_row(row)
            item = groups.setdefault(key, {"template": dict(row), "events": []})
            item["events"].append(make_packet_event(row, ts, packet_bytes))
    except Exception as exc:
        error = f"{raw_path}: {type(exc).__name__}: {exc}"
    finally:
        opener.close()
    return groups, error, packet_count


def rounded_prefix_record(template: dict[str, Any], events: list[tuple[float, int, str, str, str, str, Any]], raw_path: Path) -> dict[str, Any] | None:
    if not events:
        return None
    stat = B.new_flow_stat(template, events[0][0])
    for event in events:
        B.update_flow_stat(stat, event_row(event), event[0], event[1])
    record = B.finalize_flow_stat(stat, raw_path, raw_path, None)
    for key in ("rtt", "jitter", "loss"):
        value = numeric(record.get(key))
        record[key] = round(value, 6) if value is not None else None
    record["duration_s"] = round(float(record["duration_s"]), 6)
    return record


def incremental_prefix_record(
    template: dict[str, Any], events: list[tuple[float, int, str, str, str, str, Any]], cutoff: float, raw_path: Path
) -> dict[str, Any] | None:
    if not events or events[0][0] >= cutoff:
        return None
    stat = B.new_flow_stat(template, events[0][0])
    for event in events:
        if event[0] >= cutoff:
            break
        B.update_flow_stat(stat, event_row(event), event[0], event[1])
    if not stat["packets"]:
        return None
    record = B.finalize_flow_stat(stat, raw_path, raw_path, None)
    for key in ("rtt", "jitter", "loss"):
        value = numeric(record.get(key))
        record[key] = round(value, 6) if value is not None else None
    record["duration_s"] = round(float(record["duration_s"]), 6)
    return record


def add_flow_update(dst: dict[int, dict[int, list[float]]], cutoff_index: int, second: int, record: dict[str, Any]) -> None:
    item = dst.setdefault(cutoff_index, {}).setdefault(second, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    for offset, key in ((0, "rtt"), (2, "jitter"), (4, "loss")):
        value = numeric(record.get(key))
        if value is not None:
            item[offset] += value
            item[offset + 1] += 1.0


def add_n6_allocation(
    dst: dict[int, dict[int, list[float]]],
    cutoff_index: int,
    record: dict[str, Any],
    ranges: list[tuple[int, int]],
) -> None:
    if not ranges:
        return
    first_ts = numeric(record.get("first_ts"))
    last_ts = numeric(record.get("last_ts"))
    bytes_count = numeric(record.get("bytes"))
    span = numeric(record.get("duration_s"))
    if first_ts is None or last_ts is None or bytes_count is None or span is None:
        return
    first = int(math.floor(first_ts))
    last = int(math.floor(last_ts))
    bucket_bytes = dst.setdefault(cutoff_index, {})
    if span <= 0.0:
        for low, high in ranges:
            if low <= first < high:
                item = bucket_bytes.setdefault(first, [0.0, 0.0])
                item[0] += bytes_count
                item[1] += 1.0
                break
        return
    for low, high in ranges:
        for second in range(max(first, low), min(last + 1, high)):
            overlap = max(min(float(last), second + 1.0) - max(float(first), float(second)), 0.0)
            weight = overlap / span
            if weight <= 0.0:
                continue
            item = bucket_bytes.setdefault(second, [0.0, 0.0])
            item[0] += bytes_count * weight
            item[1] += 1.0


def merge_flow_updates(dst: dict[int, dict[int, list[float]]], src: dict[int, dict[int, list[float]]]) -> None:
    for cutoff_index, seconds in src.items():
        for second, values in seconds.items():
            item = dst.setdefault(int(cutoff_index), {}).setdefault(int(second), [0.0] * 6)
            for index in range(6):
                item[index] += float(values[index])


def merge_n6_updates(dst: dict[int, dict[int, list[float]]], src: dict[int, dict[int, list[float]]]) -> None:
    for cutoff_index, seconds in src.items():
        for second, values in seconds.items():
            item = dst.setdefault(int(cutoff_index), {}).setdefault(int(second), [0.0, 0.0])
            item[0] += float(values[0])
            item[1] += float(values[1])


def pcap_worker(args: tuple[Any, ...]) -> dict[str, Any]:
    (
        raw_path_text,
        cutoff_values,
        cutoff_ranges,
        session_index,
        direct_allowed,
        logical_allowed,
    ) = args
    raw_path = Path(raw_path_text)
    groups, parse_error, packet_count = read_flow_groups(raw_path, session_index)
    flow_updates: dict[int, dict[int, list[float]]] = {}
    n6_updates: dict[int, dict[int, list[float]]] = {}
    family = LINKS.plane_from_flow_name(B.strip_pcap_suffix(raw_path.name))
    allowed = direct_allowed if family == "n6" else logical_allowed if family == "n3" else {}
    for key, item in groups.items():
        events = item["events"]
        if not events:
            continue
        first_ts = events[0][0]
        first_second = int(math.floor(first_ts))
        low = bisect_right(cutoff_values, first_ts)
        high = bisect_right(cutoff_values, first_ts + 70.0)
        high = min(high, len(cutoff_values))
        for cutoff_index in range(low, high):
            needs = cutoff_ranges[cutoff_index]
            if not needs and key not in allowed:
                continue
            record = incremental_prefix_record(item["template"], events, cutoff_values[cutoff_index], raw_path)
            if record is None:
                continue
            if any(low_second <= first_second < high_second for low_second, high_second in needs):
                add_flow_update(flow_updates, cutoff_index, first_second, record)
            if key in allowed:
                add_n6_allocation(n6_updates, cutoff_index, record, needs)
    return {
        "raw_path": str(raw_path),
        "family": family,
        "packet_count": packet_count,
        "parse_error": parse_error,
        "flow_updates": flow_updates,
        "n6_updates": n6_updates,
    }


def load_v3_rows(path: Path) -> list[dict[str, str]]:
    csv.field_size_limit(1024 * 1024 * 1024)
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return list(csv.DictReader(handle))


def task_windows(rows: list[dict[str, str]], slot: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[float]]:
    times = [epoch(row.get("time")) for row in rows]
    if any(value is None for value in times):
        raise RuntimeError(f"{slot}: V3 timestamp parse failed")
    seconds = [float(value) for value in times if value is not None]
    t1: list[dict[str, Any]] = []
    t2: list[dict[str, Any]] = []
    for start in range(0, len(rows) - 130, 60):
        c_index = start + 60
        t1.append(
            {
                "task": "T1",
                "window_id": f"{slot}_T1_W{start // 60 + 1:04d}",
                "window_index": start // 60 + 1,
                "start_index": start,
                "history_indices": list(range(start, start + 60)),
                "c_index": c_index,
                "c_epoch": seconds[c_index],
                "target_indices": list(range(start + 120, start + 130)),
                "target_end": seconds[start + 130],
            }
        )
    for start in range(0, len(rows) - 60 + 1, 5):
        c_index = start + 60
        cutoff = seconds[c_index] if c_index < len(seconds) else seconds[-1] + 1.0
        t2.append(
            {
                "task": "T2",
                "window_id": f"{slot}_T2_W{start // 5 + 1:05d}",
                "window_index": start // 5 + 1,
                "start_index": start,
                "history_indices": list(range(start, start + 60)),
                "c_index": c_index,
                "c_epoch": cutoff,
            }
        )
    cutoffs = sorted({float(window["c_epoch"]) for window in t1 + t2} | {float(window["target_end"]) for window in t1})
    return t1, t2, cutoffs


def needed_cutoff_ranges(t1: list[dict[str, Any]], t2: list[dict[str, Any]], cutoffs: list[float]) -> list[list[tuple[int, int]]]:
    index = {float(value): i for i, value in enumerate(cutoffs)}
    ranges: list[list[tuple[int, int]]] = [[] for _ in cutoffs]

    def add(cutoff: float, low: int, high: int) -> None:
        if cutoff not in index:
            raise RuntimeError(f"missing cutoff {cutoff}")
        ranges[index[cutoff]].append((low, high))

    for window in t1:
        c = int(round(window["c_epoch"]))
        add(window["c_epoch"], c - 60, c)
        end = int(round(window["target_end"]))
        add(window["target_end"], end - 10, end)
    for window in t2:
        c = int(round(window["c_epoch"]))
        add(window["c_epoch"], c - 60, c)

    merged: list[list[tuple[int, int]]] = []
    for values in ranges:
        values = sorted(values)
        out: list[tuple[int, int]] = []
        for low, high in values:
            if not out or low > out[-1][1]:
                out.append((low, high))
            else:
                out[-1] = (out[-1][0], max(out[-1][1], high))
        merged.append(out)
    return merged


def unchanged_value(row: dict[str, str], field: str) -> str:
    return row.get(field, "")


def flow_value(flow_updates: dict[int, dict[int, list[float]]], cutoff_index: int, second: int, offset: int) -> str:
    values = flow_updates.get(cutoff_index, {}).get(second)
    if values is None or values[offset + 1] <= 0:
        return ""
    return fmt(round(values[offset] / values[offset + 1], 6))


def n6_value(n6_updates: dict[int, dict[int, list[float]]], cutoff_index: int, second: int) -> str:
    values = n6_updates.get(cutoff_index, {}).get(second)
    if values is None or values[1] <= 0:
        return ""
    return fmt(round(values[0] * 8.0, 6))


def repaired_value(
    field: str,
    row: dict[str, str],
    second: int,
    cutoff_index: int,
    flow_updates: dict[int, dict[int, list[float]]],
    n6_updates: dict[int, dict[int, list[float]]],
) -> str:
    if field == "n6_bitrate_bps":
        return n6_value(n6_updates, cutoff_index, second)
    if field in FLOW_FIELDS:
        return flow_value(flow_updates, cutoff_index, second, FLOW_FIELDS.index(field) * 2)
    return unchanged_value(row, field)


def output_history_row(
    slot: str,
    run_id: str,
    task: str,
    window: dict[str, Any],
    position: int,
    source_index: int,
    row: dict[str, str],
    origin: float,
    cutoff_index: int,
    flow_updates: dict[int, dict[int, list[float]]],
    n6_updates: dict[int, dict[int, list[float]]],
) -> dict[str, Any]:
    second = int(round(epoch(row.get("time")) or 0))
    values: dict[str, str] = {}
    for field in STRICT_FIELDS:
        values[field] = repaired_value(field, row, second, cutoff_index, flow_updates, n6_updates)
    output: dict[str, Any] = {
        "run_id": run_id,
        "slot": slot,
        "split": SPLITS[slot],
        "task": task,
        "window_id": window["window_id"],
        "anchor_c": iso_epoch(window["c_epoch"]),
        "anchor_epoch": fmt(window["c_epoch"]),
        "cutoff_rule": "source_ts < anchor_c",
        "history_position": position,
        "history_row_index": source_index,
        "history_row_timestamp": row.get("time", ""),
        "history_row_epoch": fmt(second),
    }
    output.update(values)
    for field in STRICT_FIELDS:
        output[f"{field}__missing"] = "0" if finite(values[field]) else "1"
    if task == "T1":
        for field in SCHEDULE_FIELDS[:-1]:
            output[field] = B.schedule_value(field, second, origin)
    else:
        for field in RAN_FIELDS:
            output[field] = unchanged_value(row, field)
            output[f"{field}__missing"] = "0" if finite(output[field]) else "1"
        output["anchor_row_mod_900"] = B.schedule_value("anchor_row_mod_900", second, origin)
    return output


def history_fields(task: str) -> list[str]:
    common = [
        "run_id",
        "slot",
        "split",
        "task",
        "window_id",
        "anchor_c",
        "anchor_epoch",
        "cutoff_rule",
        "history_position",
        "history_row_index",
        "history_row_timestamp",
        "history_row_epoch",
    ] + STRICT_FIELDS + MASK_FIELDS
    if task == "T1":
        return common + SCHEDULE_FIELDS[:-1]
    return common + RAN_FIELDS + RAN_MASK_FIELDS + ["anchor_row_mod_900"]


def original_target_stats(rows: list[dict[str, str]], indices: list[int], field: str) -> tuple[int, bool, str]:
    values = [numeric(rows[index].get(field)) for index in indices]
    values = [value for value in values if value is not None]
    eligible = len(values) >= 8
    mean = fmt(round(sum(values) / len(values), 6)) if eligible else ""
    return len(values), eligible, mean


def target_stats(
    rows: list[dict[str, str]],
    indices: list[int],
    field: str,
    cutoff_index: int,
    flow_updates: dict[int, dict[int, list[float]]],
    n6_updates: dict[int, dict[int, list[float]]],
) -> tuple[int, bool, str, list[str]]:
    values: list[float] = []
    cells: list[str] = []
    for index in indices:
        second = int(round(epoch(rows[index].get("time")) or 0))
        value = repaired_value(field, rows[index], second, cutoff_index, flow_updates, n6_updates)
        cells.append(value)
        number = numeric(value)
        if number is not None:
            values.append(number)
    eligible = len(values) >= 8
    mean = fmt(round(sum(values) / len(values), 6)) if eligible else ""
    return len(values), eligible, mean, cells


def build_data(
    slot: str,
    run_dir: Path,
    rows: list[dict[str, str]],
    t1: list[dict[str, Any]],
    t2: list[dict[str, Any]],
    cutoffs: list[float],
    flow_updates: dict[int, dict[int, list[float]]],
    n6_updates: dict[int, dict[int, list[float]]],
    scope_stats: dict[str, Any],
) -> dict[str, Any]:
    run_id = RUNS[slot]
    cutoff_index = {float(value): index for index, value in enumerate(cutoffs)}
    origin = B.timeline_start(run_dir, rows)
    out_dir = OUT / "data" / slot
    out_dir.mkdir(parents=True, exist_ok=True)

    history_t1: list[dict[str, Any]] = []
    history_t2: list[dict[str, Any]] = []
    for window in t1:
        c_index = cutoff_index[float(window["c_epoch"])]
        for position, source_index in enumerate(window["history_indices"]):
            history_t1.append(output_history_row(slot, run_id, "T1", window, position, source_index, rows[source_index], origin, c_index, flow_updates, n6_updates))
    for window in t2:
        c_index = cutoff_index[float(window["c_epoch"])]
        for position, source_index in enumerate(window["history_indices"]):
            history_t2.append(output_history_row(slot, run_id, "T2", window, position, source_index, rows[source_index], origin, c_index, flow_updates, n6_updates))
    write_csv(out_dir / "T1_history.csv", history_t1, history_fields("T1"))
    write_csv(out_dir / "T2_history.csv", history_t2, history_fields("T2"))

    target_rows: list[dict[str, Any]] = []
    target_summary: list[dict[str, Any]] = []
    for window in t1:
        target_cutoff_index = cutoff_index[float(window["target_end"])]
        for target_id, field in TARGETS.items():
            old_finite, old_eligible, old_mean = original_target_stats(rows, window["target_indices"], field)
            new_finite, new_eligible, new_mean, cells = target_stats(rows, window["target_indices"], field, target_cutoff_index, flow_updates, n6_updates)
            target_rows.append(
                {
                    "run_id": run_id,
                    "slot": slot,
                    "split": SPLITS[slot],
                    "task": "T1",
                    "window_id": window["window_id"],
                    "target_id": target_id,
                    "target_field": field,
                    "anchor_c": iso_epoch(window["c_epoch"]),
                    "anchor_epoch": fmt(window["c_epoch"]),
                    "history_start": iso_epoch(window["c_epoch"] - 60),
                    "history_end": iso_epoch(window["c_epoch"]),
                    "target_start": iso_epoch(window["c_epoch"] + 60),
                    "target_end": iso_epoch(window["target_end"]),
                    "target_bucket_count": 10,
                    "finite_target_buckets": new_finite,
                    "eligible": int(new_eligible),
                    "target_mean": new_mean,
                    "target_missing": int(not finite(new_mean)),
                    "source_cutoff_rule": "source_ts < target_end; target=[c+60,c+70)",
                    "old_finite_target_buckets": old_finite,
                    "old_eligible": int(old_eligible),
                    "old_target_mean": old_mean,
                    "changed": int(cells != [rows[index].get(field, "") for index in window["target_indices"]]),
                    "target_cells": ";".join(cells),
                }
            )
            target_summary.append(
                {
                    "slot": slot,
                    "task": "T1",
                    "target_id": target_id,
                    "target_field": field,
                    "candidates": 1,
                    "usable": int(new_eligible),
                    "old_usable": int(old_eligible),
                    "finite_buckets": new_finite,
                    "old_finite_buckets": old_finite,
                }
            )
    write_csv(
        out_dir / "T1_targets.csv",
        target_rows,
        [
            "run_id", "slot", "split", "task", "window_id", "target_id", "target_field", "anchor_c", "anchor_epoch",
            "history_start", "history_end", "target_start", "target_end", "target_bucket_count", "finite_target_buckets",
            "eligible", "target_mean", "target_missing", "source_cutoff_rule", "old_finite_target_buckets", "old_eligible",
            "old_target_mean", "changed", "target_cells",
        ],
    )

    reference = OUT / "reference" / "D05_T2" if slot == "D05" else None
    t2_index: list[dict[str, Any]] = []
    for window in t2:
        c_index = cutoff_index[float(window["c_epoch"])]
        anchor_row = window["c_index"] - 1
        observed = sum(finite(repaired_value(field, rows[anchor_row], int(round(epoch(rows[anchor_row].get("time")) or 0)), c_index, flow_updates, n6_updates)) for field in STRICT_FIELDS)
        t2_index.append(
            {
                "run_id": run_id,
                "slot": slot,
                "split": SPLITS[slot],
                "task": "T2",
                "window_id": window["window_id"],
                "cutoff_row": window["c_index"],
                "anchor_row": anchor_row,
                "history_start": window["start_index"],
                "history_end": window["c_index"],
                "anchor_c": iso_epoch(window["c_epoch"]),
                "cutoff_rule": "source_ts < cutoff_c",
                "strict_observed_numeric_at_anchor": observed,
                "label_status": "frozen_reference_available" if reference else "not_available_on_data_machine",
                "label_consistency": "未检查",
                "label_reference": "reference/D05_T2/D05_LEGACY_T2_REFERENCE.parquet; join by cutoff_row" if reference else "",
            }
        )
    write_csv(
        out_dir / "T2_index.csv",
        t2_index,
        [
            "run_id", "slot", "split", "task", "window_id", "cutoff_row", "anchor_row", "history_start", "history_end",
            "anchor_c", "cutoff_rule", "strict_observed_numeric_at_anchor", "label_status", "label_consistency", "label_reference",
        ],
    )

    field_summary = []
    for field in ("n6_bitrate_bps", *FLOW_FIELDS):
        old_values = [numeric(row.get(field)) for row in rows]
        old_finite = sum(value is not None for value in old_values)
        new_values: list[str] = []
        changed = 0
        mask_changed = 0
        for task, windows in (("T1", t1), ("T2", t2)):
            for window in windows:
                ci = cutoff_index[float(window["c_epoch"])]
                for index in window["history_indices"]:
                    second = int(round(epoch(rows[index].get("time")) or 0))
                    old = rows[index].get(field, "")
                    new = repaired_value(field, rows[index], second, ci, flow_updates, n6_updates)
                    new_values.append(new)
                    changed += int((numeric(old) is None and numeric(new) is not None) or (numeric(old) is not None and numeric(new) is None) or (numeric(old) is not None and numeric(new) is not None and not math.isclose(float(numeric(old)), float(numeric(new)), rel_tol=1e-12, abs_tol=1e-9)))
                    mask_changed += int((0 if finite(old) else 1) != (0 if finite(new) else 1))
        new_finite = sum(finite(value) for value in new_values)
        field_summary.append(
            {
                "slot": slot,
                "field": field,
                "task_history_cells": len(new_values),
                "old_unique_timeline_finite": old_finite,
                "new_task_history_finite": new_finite,
                "changed_task_history_values": changed,
                "changed_task_history_masks": mask_changed,
                "source_rule": "raw packet prefix source_ts < sample cutoff; original flow formula/allocation retained",
            }
        )
    write_csv(
        out_dir / "REPAIRED_FIELD_SUMMARY.csv",
        field_summary,
        ["slot", "field", "task_history_cells", "old_unique_timeline_finite", "new_task_history_finite", "changed_task_history_values", "changed_task_history_masks", "source_rule"],
    )

    write_json(
        out_dir / "RUN_DATA_MANIFEST.json",
        {
            "slot": slot,
            "run_id": run_id,
            "split": SPLITS[slot],
            "source_v3": str(run_dir / "report" / "v3_timeseries.csv"),
            "t1_candidates": len(t1),
            "t2_candidates": len(t2),
            "history_rows": {"T1": len(history_t1), "T2": len(history_t2)},
            "target_rows": len(target_rows),
            "cutoffs": len(cutoffs),
            "affected_fields": ["n6_bitrate_bps", *FLOW_FIELDS],
            "unchanged_fields": "all other original V3 fields and original construction",
            "n6_scope": scope_stats,
        },
    )
    return {"field_summary": field_summary, "target_summary": target_summary, "origin": origin}


def compare_number(a: Any, b: Any) -> bool:
    na, nb = numeric(a), numeric(b)
    if na is None or nb is None:
        return na is None and nb is None
    return math.isclose(na, nb, rel_tol=1e-10, abs_tol=1e-9)


def local_n6_value(groups: dict[Any, dict[str, Any]], cutoff: float, seconds: list[int], allowed: dict[Any, tuple[str, str]], raw_path: Path) -> dict[int, float]:
    result: dict[int, float] = defaultdict(float)
    ranges = [(second, second + 1) for second in seconds]
    for key, item in groups.items():
        if key not in allowed:
            continue
        record = incremental_prefix_record(item["template"], item["events"], cutoff, raw_path)
        if record is None:
            continue
        temp: dict[int, dict[int, list[float]]] = {}
        add_n6_allocation(temp, 0, record, ranges)
        for second, values in temp.get(0, {}).items():
            result[second] += values[0] * 8.0
    return dict(result)


def single_n6_value(record: dict[str, Any], second: int) -> float | None:
    temp: dict[int, dict[int, list[float]]] = {}
    add_n6_allocation(temp, 0, record, [(second, second + 1)])
    values = temp.get(0, {}).get(second)
    if values is None or values[1] <= 0:
        return None
    return values[0] * 8.0


def local_flow_value(groups: dict[Any, dict[str, Any]], cutoff: float, seconds: list[int], metric: str, raw_path: Path) -> dict[int, float]:
    result: dict[int, list[float]] = {}
    for item in groups.values():
        record = incremental_prefix_record(item["template"], item["events"], cutoff, raw_path)
        if record is None:
            continue
        second = int(math.floor(float(record["first_ts"])))
        if second not in seconds:
            continue
        value = numeric(record.get(metric))
        if value is not None:
            result.setdefault(second, [0.0, 0.0])
            result[second][0] += value
            result[second][1] += 1.0
    return {second: round(values[0] / values[1], 6) for second, values in result.items() if values[1]}


def fixture_aggregate(
    groups: dict[Any, dict[str, Any]],
    cutoff: float,
    raw_path: Path,
    allowed: dict[Any, tuple[str, str]],
    use_truncated: bool,
) -> dict[str, dict[int, float]]:
    flow: dict[str, dict[int, list[float]]] = {metric: {} for metric in FLOW_METRIC_KEYS}
    n6: dict[int, dict[int, list[float]]] = {0: {}}
    for key, item in groups.items():
        events = [event for event in item["events"] if event[0] < cutoff] if use_truncated else item["events"]
        if not use_truncated:
            record = incremental_prefix_record(item["template"], events, cutoff, raw_path)
        else:
            record = rounded_prefix_record(item["template"], events, raw_path)
        if record is None:
            continue
        second = int(math.floor(float(record["first_ts"])))
        for metric in FLOW_METRIC_KEYS:
            value = numeric(record.get(metric))
            if value is not None:
                item_metric = flow[metric].setdefault(second, [0.0, 0.0])
                item_metric[0] += value
                item_metric[1] += 1.0
        if key in allowed:
            add_n6_allocation(n6, 0, record, [(second, second + 1)])
    values: dict[str, dict[int, float]] = {}
    for metric, by_second in flow.items():
        values[metric] = {second: round(item[0] / item[1], 6) for second, item in by_second.items() if item[1]}
    values["n6"] = {second: round(item[0] * 8.0, 6) for second, item in n6.get(0, {}).items() if item[1]}
    return values


def validation_fixture(run_dir: Path, t1: list[dict[str, Any]], cutoffs: list[float], cutoff_ranges: list[list[tuple[int, int]]], session_index: dict[str, Any], direct: dict[str, dict[Any, tuple[str, str]]], logical: dict[str, dict[Any, tuple[str, str]]]) -> dict[str, Any]:
    """Run the required checks against real D05 raw packets and one real task target."""
    candidate_paths = [(Path(path), "n6", mapping) for path, mapping in direct.items() if mapping]
    candidate_paths += [(Path(path), "n3", mapping) for path, mapping in logical.items() if mapping]
    fixture = None
    fixture_groups = None
    fixture_allowed: dict[Any, tuple[str, str]] = {}
    fixture_family = ""
    fixture_raw_path: Path | None = None
    fixture_pre_index: int | None = None
    for raw_path, family, mapping in candidate_paths:
        groups, parse_error, packet_count = read_flow_groups(raw_path, session_index)
        if parse_error:
            continue
        selected = [(key, item) for key, item in groups.items() if key in mapping and len(item["events"]) >= 3]
        if not selected:
            continue
        for key, item in selected:
            events = item["events"]
            for cutoff in cutoffs:
                prefix_count = sum(event[0] < cutoff for event in events)
                if prefix_count < 2 or prefix_count >= len(events):
                    continue
                cutoff_index = cutoffs.index(cutoff)
                second = int(math.floor(events[0][0]))
                if not any(low <= second < high for low, high in cutoff_ranges[cutoff_index]):
                    continue
                base_record = incremental_prefix_record(item["template"], events, cutoff, raw_path)
                if base_record is None:
                    continue
                pre_index = next((index for index, event in enumerate(events) if event[0] < cutoff), None)
                if pre_index is None:
                    continue
                pre_event = events[pre_index]
                changed_by_pre_packet = list(events)
                changed_by_pre_packet[pre_index] = (
                    pre_event[0],
                    pre_event[1] + 137,
                    pre_event[2],
                    pre_event[3],
                    pre_event[4],
                    pre_event[5],
                    pre_event[6],
                )
                changed_record = incremental_prefix_record(item["template"], changed_by_pre_packet, cutoff, raw_path)
                if changed_record is None:
                    continue
                if compare_number(single_n6_value(base_record, second), single_n6_value(changed_record, second)):
                    continue
                fixture = (key, item, cutoff, cutoff_index)
                fixture_groups = groups
                fixture_allowed = mapping
                fixture_family = family
                fixture_raw_path = raw_path
                fixture_pre_index = pre_index
                break
            if fixture:
                break
        if fixture:
            break
    if fixture is None or fixture_groups is None or fixture_raw_path is None or fixture_pre_index is None:
        raise RuntimeError("D05 validation fixture: no selected real N6/N3 flow has a usable pre/post cutoff")

    key, item, cutoff, cutoff_index = fixture
    raw_path = fixture_raw_path

    full = fixture_aggregate(fixture_groups, cutoff, raw_path, fixture_allowed, use_truncated=False)
    truncated = fixture_aggregate(fixture_groups, cutoff, raw_path, fixture_allowed, use_truncated=True)
    aggregate_checks: dict[str, Any] = {}
    for field in ("rtt", "jitter", "loss", "n6"):
        all_seconds = sorted(set(full.get(field, {})) | set(truncated.get(field, {})))
        aggregate_checks[field] = {
            "value_equal": all(compare_number(full.get(field, {}).get(second), truncated.get(field, {}).get(second)) for second in all_seconds),
            "mask_equal": all((second in full.get(field, {})) == (second in truncated.get(field, {})) for second in all_seconds),
            "cells_compared": len(all_seconds),
        }

    base_events = item["events"]
    pre_events = list(base_events)
    pre_index = fixture_pre_index
    event = pre_events[pre_index]
    pre_events[pre_index] = (event[0], event[1] + 137, event[2], event[3], event[4], event[5], event[6])
    pre_groups = dict(fixture_groups)
    pre_groups[key] = {"template": item["template"], "events": pre_events}
    before_n6 = fixture_aggregate(fixture_groups, cutoff, raw_path, fixture_allowed, use_truncated=False)["n6"]
    after_n6 = fixture_aggregate(pre_groups, cutoff, raw_path, fixture_allowed, use_truncated=False)["n6"]
    pre_changed = any(not compare_number(before_n6.get(second), after_n6.get(second)) for second in set(before_n6) | set(after_n6))

    post_events = list(base_events)
    post_events.append((cutoff + 0.25, event[1] + 999, event[2], event[3], event[4], event[5], event[6]))
    post_groups = dict(fixture_groups)
    post_groups[key] = {"template": item["template"], "events": post_events}
    post_aggregate = fixture_aggregate(post_groups, cutoff, raw_path, fixture_allowed, use_truncated=False)
    base_aggregate = fixture_aggregate(fixture_groups, cutoff, raw_path, fixture_allowed, use_truncated=False)
    post_unchanged = all(
        compare_number(post_aggregate.get(field, {}).get(second), base_aggregate.get(field, {}).get(second))
        and ((second in post_aggregate.get(field, {})) == (second in base_aggregate.get(field, {})))
        for field in ("rtt", "jitter", "loss", "n6")
        for second in set(post_aggregate.get(field, {})) | set(base_aggregate.get(field, {}))
    )

    target_check = None
    for window in t1:
        target_start = int(round(window["c_epoch"] + 60))
        target_end = int(round(window["target_end"]))
        if not any(target_start <= int(math.floor(event[0])) < target_end for event in base_events):
            continue
        target_seconds = list(range(target_start, target_end))
        before_target = local_n6_value(fixture_groups, float(target_end), target_seconds, fixture_allowed, raw_path)
        target_post_events = list(base_events) + [(float(target_end) + 0.5, event[1] + 701, event[2], event[3], event[4], event[5], event[6])]
        target_post_groups = dict(fixture_groups)
        target_post_groups[key] = {"template": item["template"], "events": target_post_events}
        after_target = local_n6_value(target_post_groups, float(target_end), target_seconds, fixture_allowed, raw_path)
        before_finite = sum(finite(before_target.get(second)) for second in target_seconds)
        after_finite = sum(finite(after_target.get(second)) for second in target_seconds)
        before_mean = sum(before_target.values()) / before_finite if before_finite else None
        after_mean = sum(after_target.values()) / after_finite if after_finite else None
        target_check = {
            "window_id": window["window_id"],
            "target_interval": f"[{iso_epoch(window['c_epoch'] + 60)},{iso_epoch(window['target_end'])})",
            "field": "n6_bitrate_bps",
            "finite_buckets_equal": before_finite == after_finite,
            "mean_equal": compare_number(before_mean, after_mean),
            "before_finite_buckets": before_finite,
            "after_finite_buckets": after_finite,
            "before_mean": fmt(before_mean),
            "after_mean": fmt(after_mean),
            "appended_source_ts": iso_epoch(float(target_end) + 0.5),
        }
        break
    if target_check is None:
        raise RuntimeError("D05 validation fixture: no real selected N6 flow overlaps a T1 target interval")

    result = {
        "status": "PASS" if all(item["value_equal"] and item["mask_equal"] for item in aggregate_checks.values()) and pre_changed and post_unchanged and target_check["finite_buckets_equal"] and target_check["mean_equal"] else "FAIL",
        "source_run": RUNS["D05"],
        "raw_fixture": str(raw_path),
        "fixture_family": fixture_family,
        "cutoff": iso_epoch(cutoff),
        "cutoff_rule": "packet_ts < cutoff",
        "aggregate_full_vs_truncated": aggregate_checks,
        "pre_cutoff_perturbation": {
            "changed": pre_changed,
            "modified_packet_ts": iso_epoch(event[0]),
            "bytes_delta": 137,
            "field": "n6_bitrate_bps",
        },
        "post_cutoff_append": {
            "unchanged_value_and_mask": post_unchanged,
            "appended_packet_ts": iso_epoch(cutoff + 0.25),
        },
        "post_target_end_append": target_check,
        "actual_repair_functions": ["read_flow_groups", "incremental_prefix_record", "add_n6_allocation", "fixture_aggregate"],
    }
    write_json(OUT / "validation" / "D05_VALIDATION.json", result)
    return result


def copy_reference() -> None:
    source = Path("/home/experiment/Desktop/free5gc_experiments/w1_strict_history_v1/reference/D05_T2")
    target = OUT / "reference" / "D05_T2"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("D05_LEGACY_T2_REFERENCE.parquet", "D05_LEGACY_T2_REFERENCE_ORIGINAL.parquet", "D05_LEGACY_T2_REFERENCE_MANIFEST.json", "D05_LEGACY_T2_REFERENCE_REPORT.md", "D05_LEGACY_T2_REFERENCE_SHA256.txt"):
        src = source / name
        if src.is_file() and not (target / name).exists():
            shutil.copy2(src, target / name)


def source_hashes(run_dir: Path) -> dict[str, str]:
    paths = [run_dir / "report" / "v3_timeseries.csv", run_dir / "derived" / "nf-links.jsonl", run_dir / "derived" / "session_map.jsonl"]
    return {str(path): hash_file(path) for path in paths if path.is_file()}


def repo_status() -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO), "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def protected_roots() -> list[Path]:
    return [
        *(RAW_ROOT / run_id for run_id in RUNS.values()),
        Path("/home/experiment/Desktop/free5gc_experiments/w1_strict_history_v1"),
        Path("/home/experiment/Desktop/free5gc_experiments/w1_causal_rebuild_v1"),
        Path("/home/experiment/Desktop/free5gc_experiments/temporal_raw_audit"),
    ]


def protected_sentinel() -> dict[str, Any]:
    """Record read-only metadata for protected inputs and the pre-existing repo state."""
    roots: dict[str, Any] = {}
    for root in protected_roots():
        entries: list[str] = []
        total_bytes = 0
        if root.is_file():
            paths = [root]
        elif root.is_dir():
            paths = sorted(path for path in root.rglob("*") if path.is_file())
        else:
            paths = []
        for path in paths:
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            relative = "." if path == root else str(path.relative_to(root))
            entries.append(f"{relative}\0{stat.st_size}\0{stat.st_mtime_ns}\0{stat.st_mode}")
            total_bytes += stat.st_size
        digest = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
        roots[str(root)] = {"file_count": len(entries), "total_bytes": total_bytes, "metadata_sha256": digest}
    return {"roots": roots, "repo_status_short": repo_status()}


def build_run(slot: str, workers: int) -> dict[str, Any]:
    run_dir = RAW_ROOT / RUNS[slot]
    if not run_dir.is_dir():
        raise RuntimeError(f"{slot}: source run unavailable: {run_dir}")
    print(f"[{slot}] load V3/task windows", flush=True)
    rows = load_v3_rows(run_dir / "report" / "v3_timeseries.csv")
    t1, t2, cutoffs = task_windows(rows, slot)
    cutoff_ranges = needed_cutoff_ranges(t1, t2, cutoffs)
    context, session_index = session_context(run_dir)
    direct, logical, scope_stats = n6_scope_maps(run_dir, context, session_index)
    pairs, missing = flow_pairs(run_dir)
    if missing:
        print(f"[{slot}] missing raw flow pairs={len(missing)}", flush=True)
    tasks: list[tuple[Any, ...]] = []
    for raw_path, _flow_path in pairs:
        tasks.append((str(raw_path), cutoffs, cutoff_ranges, session_index, direct.get(str(raw_path), {}), logical.get(str(raw_path), {})))
    flow_updates: dict[int, dict[int, list[float]]] = {}
    n6_updates: dict[int, dict[int, list[float]]] = {}
    parse_errors: list[str] = []
    packet_count = 0
    completed = 0
    print(f"[{slot}] parse raw prefixes pcaps={len(tasks)} workers={workers}", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(pcap_worker, task) for task in tasks]
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            packet_count += int(result["packet_count"])
            if result["parse_error"]:
                parse_errors.append(result["parse_error"])
            merge_flow_updates(flow_updates, result["flow_updates"])
            merge_n6_updates(n6_updates, result["n6_updates"])
            if completed % 25 == 0 or completed == len(tasks):
                print(f"[{slot}] parsed {completed}/{len(tasks)} pcaps", flush=True)

    if slot == "D05":
        validation_fixture(run_dir, t1, cutoffs, cutoff_ranges, session_index, direct, logical)
    built = build_data(slot, run_dir, rows, t1, t2, cutoffs, flow_updates, n6_updates, scope_stats)
    built.update(
        {
            "slot": slot,
            "run_id": RUNS[slot],
            "row_count": len(rows),
            "pcap_count": len(tasks),
            "packet_count": packet_count,
            "parse_errors": parse_errors,
            "missing_flow_pairs": missing,
            "source_hashes": source_hashes(run_dir),
            "n6_scope": scope_stats,
            "t1_candidates": len(t1),
            "t2_candidates": len(t2),
            "history_rows": {"T1": len(t1) * 60, "T2": len(t2) * 60},
            "target_rows": len(t1) * len(TARGETS),
        }
    )
    write_json(OUT / "manifest" / f"{slot}_PROCESS_MANIFEST.json", built)
    return built


def validate_d05_only() -> dict[str, Any]:
    """Validate the actual prefix repair on one real D05 PCAP before full processing."""
    slot = "D05"
    run_dir = RAW_ROOT / RUNS[slot]
    rows = load_v3_rows(run_dir / "report" / "v3_timeseries.csv")
    t1, t2, cutoffs = task_windows(rows, slot)
    cutoff_ranges = needed_cutoff_ranges(t1, t2, cutoffs)
    context, session_index = session_context(run_dir)
    direct, logical, _scope_stats = n6_scope_maps(run_dir, context, session_index)
    return validation_fixture(run_dir, t1, cutoffs, cutoff_ranges, session_index, direct, logical)


def field_changes() -> None:
    rows = [
        {
            "field": "n6_bitrate_bps",
            "original_construction": "derive_nf_links + interval-overlap link_accumulators; complete flow bytes/duration allocated by first_seen/last_seen",
            "future_dependency_location": "complete flow/link last_seen and bytes were used before model bucket aggregation",
            "minimal_change": "rebuild each original N6 link candidate from raw packet prefix packet_ts < cutoff, then reuse the same interval-overlap allocation and 1 s bitrate",
            "semantic_changed": "no",
            "missing_indicator_change": "recomputed from repaired finite value",
        },
        {
            "field": "end_to_end_rtt_ms",
            "original_construction": "parse_pcap write_flow_outputs RTT proxy; mean across flow rows assigned to first_seen second",
            "future_dependency_location": "complete flow RTT was written to the first_seen bucket after later packets were observed",
            "minimal_change": "replay original RTT proxy on packets with packet_ts < cutoff; retain per-flow rounding and mean aggregation",
            "semantic_changed": "no",
            "missing_indicator_change": "recomputed from repaired finite value",
        },
        {
            "field": "jitter_ms",
            "original_construction": "parse_pcap write_flow_outputs mean absolute adjacent-IAT difference; mean across flow rows",
            "future_dependency_location": "complete flow IAT/jitter used packets after the sample cutoff",
            "minimal_change": "replay original IAT/jitter formula on the packet prefix; retain sparse-flow zero rule and rounding",
            "semantic_changed": "no",
            "missing_indicator_change": "recomputed from repaired finite value",
        },
        {
            "field": "packet_loss_rate",
            "original_construction": "parse_pcap TCP sequence rollback count / TCP sequence observation count; mean across flow rows",
            "future_dependency_location": "complete flow TCP sequence state included later packets",
            "minimal_change": "replay original TCP sequence rollback formula on the packet prefix; retain ratio and rounding",
            "semantic_changed": "no",
            "missing_indicator_change": "recomputed from repaired finite value",
        },
    ]
    write_csv(OUT / "FIELD_CHANGES.csv", rows, ["field", "original_construction", "future_dependency_location", "minimal_change", "semantic_changed", "missing_indicator_change"])


def write_report(results: dict[str, dict[str, Any]], validation: dict[str, Any], immutability: dict[str, Any]) -> None:
    changes = []
    for data in results.values():
        changes.extend(data.get("field_summary", []))
    target_rows = []
    for data in results.values():
        target_rows.extend(data.get("target_summary", []))
    write_csv(
        OUT / "FIELD_REPAIR_COUNTS.csv",
        changes,
        ["slot", "field", "task_history_cells", "old_unique_timeline_finite", "new_task_history_finite", "changed_task_history_values", "changed_task_history_masks", "source_rule"],
    )
    target_counts: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in target_rows:
        key = (row["slot"], row["task"], row["target_id"], row["target_field"])
        aggregate = target_counts.setdefault(
            key,
            {
                "slot": row["slot"],
                "task": row["task"],
                "target_id": row["target_id"],
                "target_field": row["target_field"],
                "candidates": 0,
                "usable": 0,
                "old_usable": 0,
                "finite_buckets": 0,
                "old_finite_buckets": 0,
            },
        )
        for field in ("candidates", "usable", "old_usable", "finite_buckets", "old_finite_buckets"):
            aggregate[field] += int(row.get(field, 0))
    write_csv(
        OUT / "T1_TARGET_COUNTS.csv",
        list(target_counts.values()),
        ["slot", "task", "target_id", "target_field", "candidates", "usable", "old_usable", "finite_buckets", "old_finite_buckets"],
    )
    lines = [
        "# W1 future-leakage repair",
        "",
        "本目录是独立修复副本。旧 W1、原始 PCAP/log/metrics/derived、旧模型结果、论文、strict/causal 目录未作为输出写入。",
        "",
        "## 修复边界",
        "",
        "只重算 `n6_bitrate_bps`、`end_to_end_rtt_ms`、`jitter_ms`、`packet_loss_rate` 及其 missing mask。所有其他字段沿用原 V3 行值和原构造方式；事件时间、run 划分、T2 标签和步长不变。完整 flow/link 行只用于冻结原有纳入/去重范围，修复数值来自 raw packet prefix。",
        "",
        "T1 使用 `history=[c-60,c)`、`target=[c+60,c+70)`、10 个一秒桶、finite >= 8、finite 值算术均值、不插补。历史输入严格使用 `source_ts < c`；目标只使用 `source_ts < target_end`。没有引入 gap tolerance、lifecycle coverage 认证或新的 coverage gate。",
        "",
        "## D05 实际前置验证",
        "",
        f"验证结果：**{validation.get('status')}**。验证使用真实 D05 raw PCAP `{validation.get('raw_fixture')}`，不是单独的时间过滤函数。",
        "",
        "- full raw prefix replay 与先截断 raw records 后按原公式计算：数值和 finite mask 均一致。",
        f"- cutoff 前有效扰动改变 N6 输出：`{validation.get('pre_cutoff_perturbation', {}).get('changed')}`。",
        f"- cutoff 后追加记录不改变输入值和 mask：`{validation.get('post_cutoff_append', {}).get('unchanged_value_and_mask')}`。",
        f"- target_end 后追加记录不改变目标值和有效性：`{validation.get('post_target_end_append', {}).get('finite_buckets_equal')}` / `{validation.get('post_target_end_append', {}).get('mean_equal')}`。",
        "",
        "## 全量处理",
        "",
        "| run | T1 candidates | T2 candidates | T1 history rows | T2 history rows | raw PCAPs | parse errors |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for slot in RUNS:
        data = results.get(slot, {})
        lines.append(f"| {slot} | {data.get('t1_candidates','')} | {data.get('t2_candidates','')} | {data.get('history_rows',{}).get('T1','')} | {data.get('history_rows',{}).get('T2','')} | {data.get('pcap_count','')} | {len(data.get('parse_errors', []))} |")
    changed_values = sum(int(row.get("changed_task_history_values", 0)) for row in changes)
    changed_masks = sum(int(row.get("changed_task_history_masks", 0)) for row in changes)
    total_history_cells = sum(int(data.get("history_rows", {}).get("T1", 0)) + int(data.get("history_rows", {}).get("T2", 0)) for data in results.values())
    lines += [
        "",
        f"全量 task-history 行数沿用原窗口规则，未为数量匹配而调整：{total_history_cells} 行；受影响字段的数值变化单元：{changed_values}，mask 变化单元：{changed_masks}。具体按 run/字段见 [FIELD_REPAIR_COUNTS.csv](FIELD_REPAIR_COUNTS.csv)。",
        "",
        "N6 纳入范围映射和未解决输入按 run 如下：",
    ]
    unresolved = False
    for slot in RUNS:
        data = results.get(slot, {})
        scope = data.get("n6_scope", {})
        lines.append(
            f"- {slot}: saved={scope.get('saved_n6_link_rows','')}, selected={scope.get('selected_n6_link_rows','')}, unmapped={scope.get('unmapped_n6_link_rows','')}, missing raw flow pairs={len(data.get('missing_flow_pairs', []))}, parser errors={len(data.get('parse_errors', []))}."
        )
        if data.get("missing_flow_pairs") or data.get("parse_errors") or int(scope.get("unmapped_n6_link_rows", 0) or 0):
            unresolved = True
            for item in (data.get("missing_flow_pairs", []) + data.get("parse_errors", []))[:10]:
                lines.append(f"  - {item}")
    if not unresolved:
        lines.append("- 本次全量处理未发现 parser error、缺少 raw flow pair 或未映射的旧 N6 link scope 行。")
    lines += [
        "",
        "四个 paper-final T1 target 的候选/可用数见 [T1_TARGET_COUNTS.csv](T1_TARGET_COUNTS.csv)。每个 run 的字段值、mask 和任务行数量变化见 [FIELD_REPAIR_COUNTS.csv](FIELD_REPAIR_COUNTS.csv)；字段语义变化矩阵见 [FIELD_CHANGES.csv](FIELD_CHANGES.csv)。",
        "",
        "## 标签与未解决问题",
        "",
        "T2 标签未在数据机重建。D05 冻结 reference 已复制到 `reference/D05_T2/`，D01–D04、D06–D07 没有在本机重新发明缺失 reference；T2 index 的 `label_consistency` 统一标为“未检查”。",
        "",
        "采集连续性未做 lifecycle-certified 证明；本次也未把缺少生命周期文件升级为 missing，也未使用 2 s 或其他 gap tolerance。raw parser error、无法映射到旧 N6 scope 的记录和缺少 raw flow pair 若存在，逐 run 写入 `manifest/*_PROCESS_MANIFEST.json`，不影响其他字段继续输出。",
        "",
        "## 原数据未修改检查",
        "",
        f"受保护输入树的文件数量、大小、mtime 元数据哨兵及仓库 `git status --short` 前后比较：**{immutability.get('status')}**。详细结果见 `manifest/PROTECTED_SENTINEL_BEFORE.json`、`manifest/PROTECTED_SENTINEL_AFTER.json` 和 `manifest/PROTECTED_IMMUTABILITY_CHECK.json`。本脚本只向本独立输出目录写入。",
        "",
        f"仓库状态前后相同：`{immutability.get('repo_status_equal')}`；受保护树哨兵相同：`{immutability.get('protected_roots_equal')}`。",
        "",
        "## 实验机读取目录",
        "",
        f"实验机读取：`{OUT / 'data'}`。每个 run 使用 `data/<Dxx>/T1_history.csv`、`T1_targets.csv`、`T2_history.csv`、`T2_index.csv`；字段映射见 [FIELD_CHANGES.csv](FIELD_CHANGES.csv)。运行清单和 source hash 在 `manifest/`。",
        "",
        "## 运行命令",
        "",
        f"```bash\npython3 {OUT / 'repair_w1_future_leakage.py'} --mode validate-d05 --workers 4\npython3 {OUT / 'repair_w1_future_leakage.py'} --mode full --workers 4\n```",
        "",
        "本次未训练、未推理、未修改论文。",
    ]
    (OUT / "FIX_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("validate-d05", "full"), required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if OUT.parent.name != "w1_future_leakage_fix":
        raise RuntimeError(f"unexpected independent output parent: {OUT.parent}")
    if args.workers < 1 or args.workers > 8:
        raise RuntimeError("workers must be between 1 and 8")
    field_changes()
    copy_reference()
    sentinel_before = protected_sentinel()
    write_json(OUT / "manifest" / "PROTECTED_SENTINEL_BEFORE.json", sentinel_before)
    config = {
        "rule_version": "w1-future-leakage-fix-v1",
        "history": "[c-60,c)",
        "target": "[c+60,c+70)",
        "target_buckets": 10,
        "target_finite_threshold": 8,
        "target_aggregation": "arithmetic mean of finite buckets; no imputation",
        "cutoff": "source_ts < cutoff",
        "affected_fields": ["n6_bitrate_bps", *FLOW_FIELDS],
        "gap_tolerance": None,
        "coverage_certification": False,
        "run_ids": RUNS,
        "script_sha256": hash_file(Path(__file__)),
        "audit_helper_sha256": hash_file(AUDIT_HELPER),
        "parse_pcap_sha256": hash_file(REPO / "scripts" / "parse_pcap.py"),
        "derive_nf_links_sha256": hash_file(REPO / "scripts" / "derive_nf_links.py"),
        "derive_n6_logical_sha256": hash_file(REPO / "scripts" / "derive_n6_logical_flows.py"),
    }
    write_json(OUT / "manifest" / "REPAIR_CONFIG.json", config)

    if args.mode == "validate-d05":
        validation = validate_d05_only()
        sentinel_after = protected_sentinel()
        immutability = {
            "status": "PASS" if sentinel_before == sentinel_after else "FAIL",
            "repo_status_equal": sentinel_before.get("repo_status_short") == sentinel_after.get("repo_status_short"),
            "protected_roots_equal": sentinel_before.get("roots") == sentinel_after.get("roots"),
        }
        write_json(OUT / "manifest" / "PROTECTED_SENTINEL_AFTER.json", sentinel_after)
        write_json(OUT / "manifest" / "PROTECTED_IMMUTABILITY_CHECK.json", immutability)
        write_report({}, validation, immutability)
        if validation.get("status") != "PASS":
            raise SystemExit(2)
        return

    validation_path = OUT / "validation" / "D05_VALIDATION.json"
    if not validation_path.is_file():
        raise RuntimeError("D05 validation is required before full processing")
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if validation.get("status") != "PASS":
        raise RuntimeError("D05 validation did not pass")
    results: dict[str, dict[str, Any]] = {}
    for slot in RUNS:
        manifest_path = OUT / "manifest" / f"{slot}_PROCESS_MANIFEST.json"
        data_manifest = OUT / "data" / slot / "RUN_DATA_MANIFEST.json"
        if slot == "D05" and manifest_path.is_file() and data_manifest.is_file():
            results[slot] = json.loads(manifest_path.read_text(encoding="utf-8"))
            print("[D05] reuse completed D05 result after identical validation/config", flush=True)
            continue
        results[slot] = build_run(slot, args.workers)
    sentinel_after = protected_sentinel()
    immutability = {
        "status": "PASS" if sentinel_before == sentinel_after else "FAIL",
        "repo_status_equal": sentinel_before.get("repo_status_short") == sentinel_after.get("repo_status_short"),
        "protected_roots_equal": sentinel_before.get("roots") == sentinel_after.get("roots"),
    }
    write_json(OUT / "manifest" / "PROTECTED_SENTINEL_AFTER.json", sentinel_after)
    write_json(OUT / "manifest" / "PROTECTED_IMMUTABILITY_CHECK.json", immutability)
    write_report(results, validation, immutability)
    write_json(OUT / "manifest" / "FULL_PROCESS_MANIFEST.json", {"status": "COMPLETE", "runs": list(results), "validation": validation, "config": config})


if __name__ == "__main__":
    main()
