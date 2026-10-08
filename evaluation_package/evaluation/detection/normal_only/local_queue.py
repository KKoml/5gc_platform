"""Minimal persistent local single-GPU queue for this frozen experiment.

The installed experiment-queue package lacks its referenced helper scripts and
targets SSH hosts.  This local adapter keeps the relevant guarantees: explicit
manifest, phase dependencies, one GPU job at a time, per-job logs, durable state,
expected-output validation, and no silent retry of non-OOM failures.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def now():
    return datetime.now(timezone.utc).isoformat()


def write_state(path, state):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def output_ok(root, job):
    expected = root / job["expected_output"]
    if not expected.exists():
        return False
    if expected.suffix == ".json":
        try:
            payload = json.loads(expected.read_text())
        except Exception:
            return False
        if job.get("expected_json_status") is not None:
            return payload.get("status") == job["expected_json_status"]
    return True


def terminal(status):
    return status in ("completed", "stuck")


def run(manifest_path, state_path, log_dir):
    manifest_path, state_path, log_dir = map(Path, (manifest_path, state_path, log_dir))
    manifest = json.loads(manifest_path.read_text())
    root = Path(manifest["cwd"]).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        state = json.loads(state_path.read_text())
        # A queue process cannot still own a job after this state file is
        # reopened by a fresh queue invocation.  Preserve any partial output
        # exactly where it is and fail closed instead of hanging forever or
        # silently moving/overwriting the interrupted result.
        for job in manifest["jobs"]:
            record = state["jobs"][job["id"]]
            if record["status"] != "running":
                continue
            if output_ok(root, job):
                record.update(
                    status="completed",
                    recovered_at=now(),
                    recovery="expected output was complete after queue interruption",
                )
            else:
                record.update(
                    status="stuck",
                    finished_at=now(),
                    error="queue interrupted while running; partial output preserved",
                )
    else:
        state = {
            "project": manifest["project"], "created_at": now(), "updated_at": now(),
            "status": "running", "jobs": {
                job["id"]: {"status": "pending", "attempts": 0, "phase": job["phase"]}
                for job in manifest["jobs"]
            },
        }
        write_state(state_path, state)
    jobs = {job["id"]: job for job in manifest["jobs"]}
    while True:
        pending = []
        for job_id, job in jobs.items():
            record = state["jobs"][job_id]
            if record["status"] == "completed" and not output_ok(root, job):
                record.update(status="stuck", error="expected output disappeared or became invalid")
            if record["status"] != "pending":
                continue
            dependencies = job.get("depends_on", [])
            if any(state["jobs"][dependency]["status"] == "stuck" for dependency in dependencies):
                record.update(status="stuck", error="dependency stuck", finished_at=now())
                continue
            if all(state["jobs"][dependency]["status"] == "completed" for dependency in dependencies):
                pending.append(job)
        state["updated_at"] = now()
        write_state(state_path, state)
        if not pending:
            if all(terminal(value["status"]) for value in state["jobs"].values()):
                break
            time.sleep(1)
            continue
        job = pending[0]
        record = state["jobs"][job["id"]]
        record.update(status="running", started_at=now(), attempts=record["attempts"] + 1)
        state["updated_at"] = now()
        write_state(state_path, state)
        command = [manifest["python"], "-m", "code.pipeline", "run-job",
                   "--manifest", str(manifest_path), "--job-id", job["id"]]
        env = os.environ.copy()
        env.update(manifest["environment"])
        log_path = log_dir / f"{job['id']}.log"
        with log_path.open("a") as log:
            log.write(json.dumps({"event": "launch", "at": now(), "command": command}) + "\n")
            log.flush()
            completed = subprocess.run(command, cwd=root, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, text=True)
        if completed.returncode == 0 and output_ok(root, job):
            record.update(status="completed", finished_at=now(), returncode=0,
                          expected_output=job["expected_output"])
        else:
            text = log_path.read_text(errors="replace")[-20000:]
            oom = "torch.OutOfMemoryError" in text or "CUDA out of memory" in text
            if oom and record["attempts"] < manifest.get("oom_max_attempts", 1):
                record.update(status="pending", last_error="OOM", returncode=completed.returncode)
                if __import__("torch").cuda.is_available():
                    __import__("torch").cuda.empty_cache()
                time.sleep(manifest.get("oom_retry_delay_seconds", 10))
            else:
                record.update(status="stuck", finished_at=now(), returncode=completed.returncode,
                              error="OOM" if oom else "non-OOM failure", log=str(log_path))
        state["updated_at"] = now()
        write_state(state_path, state)
    counts = {}
    for value in state["jobs"].values():
        counts[value["status"]] = counts.get(value["status"], 0) + 1
    state["status"] = "completed" if not counts.get("stuck") else "completed_with_stuck"
    state["finished_at"] = now()
    state["counts"] = counts
    write_state(state_path, state)
    return 0 if not counts.get("stuck") else 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--log-dir", required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.manifest, args.state, args.log_dir))


if __name__ == "__main__":
    main()
