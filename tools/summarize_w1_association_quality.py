#!/usr/bin/env python3
"""Offline W1 provenance-route counts; no collection, control, or re-attribution.

Default/--check consumes only the de-identified evidence bundled beside the
summary. --extract reads an explicitly supplied accepted-run registry and its
retained artifacts (all session rows and capture summaries; a systematic
capture-file sample for flow routes), and writes compact projections to
--evidence-dir. NF-link counts come from retained producer summary JSON. It never
changes the source run directories and does not perform content-hash checks.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

FIELDS = ("supi", "pdu_session_id", "ue_ip", "dnn", "upf_id", "selected_amf",
          "selected_smf", "teid_ul", "teid_dl", "pfcp_session_established")
FLOW_FIELDS = ("ue_ip", "dnn", "upf_id", "supi", "pdu_session_id")


def present(value):
    return value not in (None, "")


def read_jsonl(path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def presence(row, fields):
    return "".join("1" if present(row.get(field)) else "0" for field in fields)


def family(name):
    if name == "n6-uplink-logical_flows.jsonl":
        return "n6-logical-derived"
    for value in ("gtp-gold", "gtp-silver", "n3-gtpu", "n4-pfcp", "n6-uplink", "sbi-http"):
        if name.startswith(value):
            return value
    raise ValueError(f"Unsupported capture family: {name}")


def ip_status(value, identities):
    if not present(value):
        return "empty"
    count = len(identities.get(value, ()))
    return "multi_identity" if count > 1 else "single_identity" if count == 1 else "not_in_session_map"


def extract(registry_path, evidence_dir, sample_every):
    registry = json.loads(registry_path.read_text())
    accepted = set(registry["accepted"])
    runs = sorted((row for row in registry["attempts"] if row["run_id"] in accepted), key=lambda row: row["slot"])
    if len(runs) != 7 or {row["slot"] for row in runs} != {f"D{i:02d}" for i in range(1, 8)}:
        raise ValueError("Expected the seven W1 accepted slots D01-D07")
    session_rows, flow_rows, inventory, capture_summary_rows = [], [], [], []
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for run in runs:
        slot = "W1-" + run["slot"]
        root = Path(run["run_dir"])
        sessions = list(read_jsonl(root / "derived/session_map.jsonl"))
        supis = sorted({str(row.get("supi")) for row in sessions if present(row.get("supi"))})
        ips = sorted({str(row.get("ue_ip")) for row in sessions if present(row.get("ue_ip"))})
        ue_alias = {value: f"UE{i:03d}" for i, value in enumerate(supis, 1)}
        ip_alias = {value: f"IP{i:03d}" for i, value in enumerate(ips, 1)}
        identities = defaultdict(set)
        for row in sessions:
            if present(row.get("ue_ip")):
                identities[row["ue_ip"]].add((row.get("supi"), row.get("pdu_session_id")))
        for number, row in enumerate(sessions, 1):
            session_rows.append({
                "run": slot, "row_number": number,
                "timestamp": row.get("timestamp", ""),
                "ue_key": ue_alias.get(str(row.get("supi")), ""),
                "pdu_session_id": row.get("pdu_session_id", ""),
                "ue_ip_key": ip_alias.get(str(row.get("ue_ip")), ""),
                "label_source": row.get("label_source") or "<empty>",
                "presence_bits": presence(row, FIELDS),
                "selected_amf": row.get("selected_amf") or "",
                "selected_smf": row.get("selected_smf") or "",
                "upf_id": row.get("upf_id") or "",
            })
        derived = sorted(root.glob("derived/*_flows.jsonl"))
        derived_names = {path.name for path in derived}
        compatible = sorted(path for path in root.glob("pcap/*_flows.jsonl") if path.name not in derived_names)
        candidates = sorted(derived + compatible, key=lambda path: path.name)
        counters = defaultdict(Counter)
        file_counts = Counter()
        family_ordinals = Counter()
        family_totals = Counter(family(path.name) for path in candidates)
        flow_input_bytes = 0
        for file_number, path in enumerate(candidates, 1):
            capture = family(path.name)
            if capture == "n6-logical-derived":
                continue
            file_counts[capture] += 1
            ordinal = family_ordinals[capture]
            family_ordinals[capture] += 1
            selected = ordinal % sample_every == 0 or ordinal == family_totals[capture] - 1
            summary_path = path.with_name(path.name.replace("_flows.jsonl", "_summary.txt"))
            summary_text = summary_path.read_text() if summary_path.is_file() else ""
            total_match = re.search(r"^\s*Flow records\s*:\s*(\d+)", summary_text, re.M)
            labeled_match = re.search(r"^\s*Labeled flow records\s*:\s*(\d+)", summary_text, re.M)
            if not total_match or not labeled_match:
                raise ValueError(f"Missing retained capture row-count summary: {summary_path}")
            capture_summary_rows.append({"run": slot, "file_number": file_number, "capture_family": capture,
                                         "family_file_ordinal": ordinal + 1, "sample_selected": int(selected),
                                         "sample_every_files": sample_every, "retained_flow_record_count": int(total_match[1]),
                                         "retained_labeled_flow_record_count": int(labeled_match[1])})
            if not selected:
                continue
            csv_path = path.with_suffix(".csv")
            if not csv_path.is_file():
                raise ValueError(f"Missing canonical CSV representation: {csv_path}")
            flow_input_bytes += csv_path.stat().st_size
            with csv_path.open(newline="", encoding="utf-8") as handle:
                csv_rows = csv.DictReader(handle)
                row_count = 0
                first = next(csv_rows, None)
                first_json = next(read_jsonl(path), None)
                if (first is None) != (first_json is None):
                    raise ValueError(f"CSV/JSONL first-record presence mismatch: {csv_path}")
                if first is not None and any(str(first.get(key) or "") != str(first_json.get(key) or "") for key in FLOW_FIELDS + ("label_source",)):
                    raise ValueError(f"CSV/JSONL first-record label/identity projection mismatch: {csv_path}")
                def projected_csv_rows():
                    if first is not None:
                        yield first
                    yield from csv_rows
                for row in projected_csv_rows():
                    row_count += 1
                    source = str(row.get("label_source") or "<empty>")
                    secondary = str(row.get("source") or "<empty>")
                    key = (slot, file_number, capture, path.parent.name, source, secondary,
                           ip_status(row.get("ue_ip"), identities), presence(row, FLOW_FIELDS))
                    counters[capture][key] += 1
                if row_count != int(total_match[1]):
                    raise ValueError(f"CSV count does not match retained capture summary: {csv_path}")
        for capture in sorted(counters):
            for key, count in sorted(counters[capture].items()):
                flow_rows.append(dict(zip(("run", "file_number", "capture_family", "source_directory", "label_source", "secondary_source", "ue_ip_lookup_status", "presence_bits"), key), record_count=count))
        nf_path = root / "derived/nf-links.jsonl"
        retained_summary = json.loads((root / "derived/nf-links.latest.json").read_text())
        inventory.append({"run": slot, "session_rows": len(sessions), "capture_file_counts": dict(sorted(file_counts.items())),
                          "compatibility_files_excluded_same_basename": sum(1 for path in root.glob("pcap/*_flows.jsonl") if path.name in derived_names),
                          "sampling_stride_files_within_run_capture_family": sample_every,
                          "sampled_flow_csv_input_bytes": flow_input_bytes,
                          "retained_nf_link_file_bytes_not_scanned": nf_path.stat().st_size,
                          "retained_nf_summary": {key: retained_summary[key] for key in ("record_count", "plane_counts")}})
        print(f"Extracted {slot}: {len(sessions)} session rows; {sum(sum(c.values()) for c in counters.values())} sampled flow rows; retained NF summary only", file=sys.stderr, flush=True)
    write_csv(evidence_dir / "session_record_projection.csv", ("run", "row_number", "timestamp", "ue_key", "pdu_session_id", "ue_ip_key", "label_source", "presence_bits", "selected_amf", "selected_smf", "upf_id"), session_rows)
    write_csv(evidence_dir / "flow_file_provenance_counts.csv", ("run", "file_number", "capture_family", "source_directory", "label_source", "secondary_source", "ue_ip_lookup_status", "presence_bits", "record_count"), flow_rows)
    write_csv(evidence_dir / "capture_summary_projection.csv", ("run", "file_number", "capture_family", "family_file_ordinal", "sample_selected", "sample_every_files", "retained_flow_record_count", "retained_labeled_flow_record_count"), capture_summary_rows)
    dump(evidence_dir / "source_inventory.json", inventory)


def safe_ratio(numerator, denominator):
    return round(numerator / denominator, 9) if denominator else None


def route_table(result):
    columns = ("run", "capture_family", "label_source", "sample_record_count", "sample_denominator", "sample_share",
               "sample_capture_file_count", "all_capture_file_count", "all_capture_record_count_from_summaries", "all_capture_labeled_count_from_summaries")
    rows = []
    for entry in result["runs"] + [result["totals"]]:
        for capture, item in sorted(entry["flow_artifacts_by_capture_family"].items()):
            for label, count in sorted(item["producer_route_counts"].items()):
                rows.append(dict(zip(columns, (entry["run"], capture, label, count,
                    item["sampled_flow_artifact_record_count"], item["producer_route_shares"][label],
                    item["sampled_capture_file_count"], item["all_capture_file_count"],
                    item["all_retained_flow_record_count"], item["all_retained_labeled_flow_record_count"]))))
    return columns, rows


def summarize(evidence_dir):
    sessions = read_csv(evidence_dir / "session_record_projection.csv")
    flows = read_csv(evidence_dir / "flow_file_provenance_counts.csv")
    capture_summaries = read_csv(evidence_dir / "capture_summary_projection.csv")
    inventory = json.loads((evidence_dir / "source_inventory.json").read_text())
    result = {"scope": "Seven accepted W1 runs; retained producer routes, not accuracy", "session_presence_bit_order": list(FIELDS),
              "flow_presence_bit_order": list(FLOW_FIELDS), "runs": [], "totals": {}}
    result["independent_association_precision"] = None
    result["independent_association_recall"] = None
    result["independent_misassociation_rate"] = None
    for run in [f"W1-D{i:02d}" for i in range(1, 8)] + ["ALL"]:
        sr = [row for row in sessions if run == "ALL" or row["run"] == run]
        fr = [row for row in flows if run == "ALL" or row["run"] == run]
        cr = [row for row in capture_summaries if run == "ALL" or row["run"] == run]
        pairs = Counter((row["run"], row["ue_key"], row["pdu_session_id"]) for row in sr)
        exact = Counter((row["run"], row["ue_key"], row["pdu_session_id"], row["timestamp"], row["ue_ip_key"], row["upf_id"]) for row in sr)
        ips = defaultdict(set)
        ip_supis = defaultdict(set)
        for row in sr:
            ips[(row["run"], row["ue_ip_key"])].add((row["ue_key"], row["pdu_session_id"]))
            ip_supis[(row["run"], row["ue_ip_key"])].add(row["ue_key"])
        sources = Counter(row["label_source"] for row in sr)
        session = {"row_count": len(sr), "producer_route_counts": dict(sorted(sources.items())),
                   "control_plane_log_route_rows": sources["control-plane-log"],
                   "explicit_ran_n3_fallback_route_rows": sources["ran-ue-map+n3-gtpu-fallback"],
                   "empty_or_unrecognized_route_rows": sum(value for key, value in sources.items() if key not in {"control-plane-log", "ran-ue-map+n3-gtpu-fallback"}),
                   "field_level_direct_versus_fallback_counts": None,
                   "producer_route_shares": {key: safe_ratio(value, len(sr)) for key, value in sorted(sources.items())},
                   "unique_run_supi_keys": len({(row["run"], row["ue_key"]) for row in sr}),
                   "unique_run_supi_pdu_keys": len(pairs), "supi_pdu_keys_with_multiple_records": sum(value > 1 for value in pairs.values()),
                   "records_beyond_first_per_supi_pdu_key": sum(value - 1 for value in pairs.values()),
                   "exact_lifecycle_key_duplicate_records": sum(value - 1 for value in exact.values()),
                   "ue_ip_keys": len(ips), "ue_ip_keys_with_multiple_supi_pdu_identities": sum(len(value) > 1 for value in ips.values()),
                   "ue_ip_keys_with_multiple_supis": sum(len(value) > 1 for value in ip_supis.values()),
                   "supi_identity_count_distribution_by_ue_ip_key": dict(sorted(Counter(str(len(value)) for value in ip_supis.values()).items())),
                   "nonempty_field_counts": {field: sum(row["presence_bits"][index] == "1" for row in sr) for index, field in enumerate(FIELDS)}}
        captures = {}
        for capture in sorted({row["capture_family"] for row in fr}):
            rows = [row for row in fr if row["capture_family"] == capture]
            total = sum(int(row["record_count"]) for row in rows)
            capture_inventory = [row for row in cr if row["capture_family"] == capture]
            routes, exposure = Counter(), Counter()
            for row in rows:
                routes[row["label_source"]] += int(row["record_count"])
                exposure[row["ue_ip_lookup_status"]] += int(row["record_count"])
            for item in capture_inventory:
                ordinal = int(item["family_file_ordinal"]) - 1
                expected = ordinal % int(item["sample_every_files"]) == 0 or ordinal == len([entry for entry in capture_inventory if entry["run"] == item["run"]]) - 1
                if bool(int(item["sample_selected"])) != expected:
                    raise ValueError(f"Sample inclusion mismatch for {run}/{capture}/{ordinal}")
                if not expected:
                    continue
                file_rows = [row for row in rows if row["run"] == item["run"] and row["file_number"] == item["file_number"]]
                sampled_count = sum(int(row["record_count"]) for row in file_rows)
                labeled_count = sum(int(row["record_count"]) for row in file_rows if row["presence_bits"][1] == "1" or row["presence_bits"][2] == "1")
                if sampled_count != int(item["retained_flow_record_count"]) or labeled_count != int(item["retained_labeled_flow_record_count"]):
                    raise ValueError(f"Sample projection/count-summary mismatch for {run}/{capture}/{ordinal}")
            captures[capture] = {"sampled_flow_artifact_record_count": total,
                                 "all_capture_file_count": len(capture_inventory),
                                 "sampled_capture_file_count": sum(int(row["sample_selected"]) for row in capture_inventory),
                                 "all_retained_flow_record_count": sum(int(row["retained_flow_record_count"]) for row in capture_inventory),
                                 "all_retained_labeled_flow_record_count": sum(int(row["retained_labeled_flow_record_count"]) for row in capture_inventory),
                                 "sample_scope": "Every Nth file per run/capture family from sorted canonical filenames, starting with the first file and including the final file; N is recorded in source_inventory.json. Shares apply only to sampled rows; no population accuracy estimate.",
                                 "producer_route_counts": dict(sorted(routes.items())),
                                 "producer_route_shares": {key: safe_ratio(value, total) for key, value in sorted(routes.items())},
                                 "ue_ip_lookup_counts": dict(sorted(exposure.items())),
                                 "run_wide_multi_identity_ip_exposure_share_all_rows": safe_ratio(exposure["multi_identity"], total),
                                 "run_wide_multi_identity_ip_exposure_share_session_map_hits": safe_ratio(exposure["multi_identity"], exposure["multi_identity"] + exposure["single_identity"]),
                                 "nonempty_field_counts": {field: sum(int(row["record_count"]) for row in rows if row["presence_bits"][index] == "1") for index, field in enumerate(FLOW_FIELDS)}}
        nf_planes = Counter()
        nf_count = 0
        for item in inventory:
            if run == "ALL" or item["run"] == run:
                nf_count += item["retained_nf_summary"]["record_count"]
                nf_planes.update(item["retained_nf_summary"]["plane_counts"])
        nf = {"record_count": nf_count, "count_source": "retained nf-links.latest.json producer summary; full NF-link records not rescanned",
              "observation_source_counts": None, "plane_counts": dict(sorted(nf_planes.items())),
              "field_level_direct_fallback_ambiguous_unmapped_counts": None,
              "reason": "Producer output omits per-field route, rejected candidate, ambiguity and unmatched inventories."}
        entry = {"run": run, "session_map": session, "flow_artifacts_by_capture_family": captures, "nf_links": nf}
        if run == "ALL":
            result["totals"] = entry
        else:
            inv = next(row for row in inventory if row["run"] == run)
            if inv["session_rows"] != len(sr):
                raise ValueError(f"Session row count inconsistent for {run}")
            if sum(nf["plane_counts"].values()) != nf["record_count"]:
                raise ValueError(f"Retained NF summary plane totals inconsistent for {run}")
            result["runs"].append(entry)
    result["limits"] = [
        "Source-route shares are producer metadata counts, not independent association precision or recall.",
        "control-plane-log includes temporal and configuration/path-based inference; its field-level direct fraction is unknown.",
        "authoritative:session-map is a static whole-run IP/TEID lookup; it has no lifecycle bounds or candidate-conflict output.",
        "Flow label_source is initialized from the first packet in a flow aggregate; the aggregation key does not include label_source. These are flow-record label shares, not packet-level attribution fractions.",
        "Run-wide UE-IP reuse exposure is potential lifecycle ambiguity, not simultaneous conflict or observed misassociation.",
        "TEID integers are not evaluated as globally unique keys: UPF, peer and direction scopes are required.",
        "Each capture family has its own artifact-row denominator; capture points, rotations and logical derivatives are not pooled into unique connections.",
        "Flow producer-route and reuse-exposure shares use a deterministic systematic file sample, not all retained flow rows. All-capture row/labeled totals are copied from retained per-capture summaries. The logical N6 derivative is excluded from capture denominators.",
        "Empty flow label_source is an unlabelled UE/session route and may be inapplicable for control/management traffic; it is not by itself an association failure.",
        "NF links omit discarded/unmapped candidates and field-level provenance, so their complete success/failure/ambiguous denominator is unavailable.",
        "Independent precision/recall and actual misassociation rate remain unmeasured without ground-truth labels.",
    ]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_dir = Path(__file__).resolve().parents[1] / "platform_data/quality/association"
    parser.add_argument("--evidence-dir", type=Path, default=default_dir)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--sample-every", type=int, default=12, help="Read every Nth canonical capture CSV in each run/family (default 12)")
    parser.add_argument("--check", action="store_true", help="Read compact evidence and compare the deterministic summary; no raw runs needed")
    args = parser.parse_args()
    if args.extract:
        if not args.registry or args.check:
            parser.error("--extract requires --registry and cannot be combined with --check")
        if args.sample_every < 1:
            parser.error("--sample-every must be positive")
        extract(args.registry, args.evidence_dir, args.sample_every)
    result = summarize(args.evidence_dir)
    target = args.evidence_dir / "association_summary.json"
    route_target = args.evidence_dir / "flow_route_summary.csv"
    route_columns, route_rows = route_table(result)
    if args.check:
        if json.loads(target.read_text()) != result:
            raise SystemExit("Association summary mismatch")
        expected_csv = [{key: "" if value is None else str(value) for key, value in row.items()} for row in route_rows]
        if read_csv(route_target) != expected_csv:
            raise SystemExit("Flow route summary CSV mismatch")
        print("PASS: association JSON and flow route CSV match compact evidence; retained NF plane totals are internally consistent")
    else:
        dump(target, result)
        write_csv(route_target, route_columns, route_rows)
        print(f"Wrote {target}")


if __name__ == "__main__":
    main()
