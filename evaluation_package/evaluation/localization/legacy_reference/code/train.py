"""Training, checkpointing, and row-level prediction for the frozen tasks."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pickle
import random
import sys
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import torch
from torch import nn
from torch.utils.data import DataLoader

from .data import (CLASS_NAMES, PackageData, Preprocessor, WindowDataset,
                   digest_strings, write_json)
from .models import (build_classifier, build_fd, fd_backward, fd_current_score,
                     fd_forward, fd_validation_loss, model_provenance,
                     parameter_count, KANADAdapted, TranADAdaptedV2)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def json_safe(value):
    """Make estimator metadata serializable without changing the estimator."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    return repr(value)


def seed_all(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def move(batch, device):
    return {key: value.to(device, non_blocking=True) if torch.is_tensor(value) else value
            for key, value in batch.items()}


def loader(dataset, shuffle, seed, batch_size=128):
    generator = torch.Generator().manual_seed(seed)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle,
                      generator=generator, num_workers=0,
                      pin_memory=torch.cuda.is_available(), drop_last=False)


def source_identity(package_root):
    package_root = Path(package_root)
    environment_spec = Path(__file__).resolve().parents[1] / "configs" / "env-spec.json"
    return {
        "package_root": str(package_root.resolve()),
        "package_protocol_sha256": sha256_file(package_root / "metadata" / "protocol.json"),
        "package_sealed_manifest_sha256": sha256_file(package_root / "SHA256SUMS.txt"),
        "package_metadata_sha256": {
            name: sha256_file(package_root / "metadata" / name)
            for name in (
                "feature_sets.json", "runs.csv", "ALL_CORE_EPISODES.csv",
                "EVENT_EVALUABILITY.csv",
            )
        },
        "package_index_sha256": {
            task: sha256_file(package_root / "tasks" / task / "index.parquet")
            for task in ("FD_detection", "FL_localization", "FP_forewarning")
        },
        "training_source_sha256": {
            name: sha256_file(Path(__file__).with_name(name))
            for name in ("data.py", "models.py", "train.py")
        },
        "execution_environment_spec": str(environment_spec),
        "execution_environment_spec_sha256": sha256_file(environment_spec),
    }


def _selection_index(data, task, feature_set):
    index = data.index(task, split="validation", feature_set=feature_set)
    if task == "FD_detection":
        # D05 current-normal observations select the reconstruction checkpoint;
        # all D05 rows remain available later for threshold calibration.
        index = index.loc[index.y.eq(0)].reset_index(drop=True)
    return index


def _task_loss(task, output, y, pos_weight=None):
    if task == "FL_localization":
        return nn.functional.cross_entropy(output, y.long())
    if task == "FP_forewarning":
        return nn.functional.binary_cross_entropy_with_logits(
            output.squeeze(-1), y.float(), pos_weight=pos_weight)
    raise ValueError(task)


def _validation(model, dataset, task, device, epoch, pos_weight=None):
    model.eval()
    total, weight = 0.0, 0
    with torch.inference_mode():
        for raw in loader(dataset, False, 0):
            batch = move(raw, device)
            if task == "FD_detection":
                output = fd_forward(model, batch)
                loss = fd_validation_loss(model, output, batch["values"], batch["mask"], epoch)
            else:
                output = model(batch["x"])
                loss = _task_loss(task, output, batch["y"], pos_weight)
            total += float(loss) * len(batch["x"])
            weight += len(batch["x"])
    return total / max(weight, 1)


def fit_deep(package_root, task, model_name, seed, feature_set, preprocessor_path,
             output, device="cuda", max_epochs=50, patience=8):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    data = PackageData(package_root)
    pp = Preprocessor.load(preprocessor_path)
    if pp.task != task or pp.feature_set != feature_set:
        raise ValueError("Preprocessor identity mismatch")
    train_index = data.index(task, fit=True, feature_set=feature_set)
    if digest_strings(train_index.sample_id.astype(str)) != pp.fit_sample_id_sha256:
        raise RuntimeError("Fit sample IDs do not match frozen preprocessor")
    validation_index = _selection_index(data, task, feature_set)
    mode = "values_only" if task == "FD_detection" and model_name == "KAN-AD" else "full"
    train_data = WindowDataset(data, task, train_index, pp, mode=mode)
    validation_data = WindowDataset(data, task, validation_index, pp, mode=mode)
    input_dim = train_data.input_dim
    output_dim = 2 if task == "FL_localization" else 1
    seed_all(seed)
    model = (build_fd(model_name, pp.full_input_dim, pp.value_dim)
             if task == "FD_detection" else build_classifier(model_name, input_dim, output_dim))
    model = model.to(device)
    if task == "FD_detection" and model_name == "KAN-AD":
        optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
        scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.75)
        lr = 0.003
        optimizer_name = "Adam + StepLR(5,0.75), author mechanism"
    else:
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
        scheduler = None
        lr = 1e-3
        optimizer_name = "AdamW"
    pos_weight = None
    if task == "FP_forewarning":
        negatives = int(train_index.y.eq(0).sum())
        positives = int(train_index.y.eq(1).sum())
        pos_weight = torch.tensor(negatives / positives, device=device, dtype=torch.float32)
    actual_input = {
        "value_channels_consumed": pp.value_dim,
        "mask_channels_consumed": 0 if isinstance(model, KANADAdapted) else pp.value_dim,
        "mask_channels_used_for_loss_and_score_validity": (
            pp.value_dim if task == "FD_detection" else 0
        ),
        "sequence_steps": 12,
    }
    config = {
        **source_identity(package_root),
        "task": task, "model": model_name, "seed": seed,
        "feature_set": feature_set, "feature_columns": pp.columns,
        "feature_column_sha256": digest_strings(pp.columns),
        "actual_input": actual_input,
        "fit_sample_count": len(train_index),
        "fit_sample_id_sha256": digest_strings(train_index.sample_id.astype(str)),
        "selection_sample_count": len(validation_index),
        "selection_sample_id_sha256": digest_strings(validation_index.sample_id.astype(str)),
        "selection_split": "D05 validation only",
        "test_or_external_used_for_selection": False,
        "history_steps": 12, "grid_seconds": 5,
        "physical_batch_size": 128, "effective_batch_size": 128,
        "gradient_accumulation": 1,
        "max_epochs": int(max_epochs), "early_stopping_patience": int(patience),
        "optimizer": optimizer_name, "learning_rate": lr,
        "weight_decay": 0.0 if model_name == "KAN-AD" else 1e-4,
        "classifier_defaults": ({"width": 64, "layers": 2, "dropout": 0.1}
                                if task != "FD_detection" else None),
        "fp_training_pos_weight": float(pos_weight) if pos_weight is not None else None,
        "checkpoint_selection": ("minimum D05 current-normal reconstruction/forecast loss"
                                 if task == "FD_detection" else "minimum D05 classification loss"),
        "point_adjustment": False,
        "created_at": now(), "status": "training",
        "device": device, "parameter_count": parameter_count(model),
        "preprocessor_sha256": sha256_file(preprocessor_path),
    }
    write_json(output / "experiment_config.json", config)
    pp.save(output / "preprocessing.json")
    write_json(output / "implementation_provenance.json", model_provenance(model))
    train_index[["sample_id", "run_id", "slot"]].to_csv(
        output / "fit_sample_ids.csv.gz", index=False)

    train_loader = loader(train_data, True, seed)
    logs = []
    best = float("inf")
    stale = 0
    started = time.perf_counter()
    if device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()
    minimum_epoch = 2 if isinstance(model, TranADAdaptedV2) else 1
    for epoch in range(max_epochs):
        epoch_started = time.perf_counter()
        model.train()
        loss_total = generator_total = discriminator_total = 0.0
        weight = adversarial_weight = 0
        for raw in train_loader:
            batch = move(raw, device)
            optimizer.zero_grad(set_to_none=True)
            if task == "FD_detection":
                output_tensor = fd_forward(model, batch)
                receipt = fd_backward(model, output_tensor, batch["values"], batch["mask"], epoch)
                loss = receipt["loss"]
                if "generator_loss" in receipt:
                    generator_total += receipt["generator_loss"] * len(batch["x"])
                    discriminator_total += receipt["discriminator_loss"] * len(batch["x"])
                    adversarial_weight += len(batch["x"])
            else:
                output_tensor = model(batch["x"])
                loss_tensor = _task_loss(task, output_tensor, batch["y"], pos_weight)
                if not torch.isfinite(loss_tensor):
                    raise FloatingPointError("Non-finite classification loss")
                loss_tensor.backward()
                loss = float(loss_tensor.detach())
            gradients = [p.grad for p in model.parameters() if p.grad is not None]
            if not gradients or not all(torch.isfinite(g).all() for g in gradients):
                raise FloatingPointError("Missing or non-finite gradients")
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0, error_if_nonfinite=True)
            optimizer.step()
            loss_total += float(loss) * len(batch["x"])
            weight += len(batch["x"])
        if scheduler is not None:
            scheduler.step()
        selection = _validation(model, validation_data, task, device, epoch, pos_weight)
        admissible = epoch + 1 >= minimum_epoch
        improved = admissible and selection < best
        if improved:
            best, stale = selection, 0
            torch.save({
                "model_state": model.state_dict(), "task": task, "model": model_name,
                "seed": seed, "feature_set": feature_set,
                "input_dim": input_dim, "value_dim": pp.value_dim,
                "selected_epoch": epoch + 1, "selection_metric": selection,
            }, output / "checkpoint.pt")
        elif admissible:
            stale += 1
        if device.startswith("cuda"):
            torch.cuda.synchronize()
        row = {
            "epoch": epoch + 1,
            "train_loss": loss_total / weight,
            "train_generator_loss": generator_total / adversarial_weight if adversarial_weight else np.nan,
            "train_discriminator_loss": discriminator_total / adversarial_weight if adversarial_weight else np.nan,
            "validation_selection_loss": selection,
            "checkpoint_admissible": admissible,
            "checkpoint_selected": improved,
            "epoch_seconds": time.perf_counter() - epoch_started,
            "elapsed_seconds": time.perf_counter() - started,
            "learning_rate": optimizer.param_groups[0]["lr"],
            "peak_gpu_allocated_bytes": (torch.cuda.max_memory_allocated()
                                         if device.startswith("cuda") else 0),
        }
        logs.append(row)
        pd.DataFrame(logs).to_csv(output / "training_log.csv", index=False)
        print(json.dumps({"event": "epoch", "job": output.name, **row}, default=float), flush=True)
        if stale >= patience:
            break
    checkpoint = torch.load(output / "checkpoint.pt", map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state"])
    elapsed = time.perf_counter() - started
    timing = {
        "fit_seconds": elapsed,
        "epochs_executed": len(logs),
        "selected_epoch": checkpoint["selected_epoch"],
        "seconds_per_executed_epoch": elapsed / len(logs),
        "peak_gpu_allocated_bytes": (torch.cuda.max_memory_allocated()
                                     if device.startswith("cuda") else 0),
        "device_name": torch.cuda.get_device_name(0) if device.startswith("cuda") else "CPU",
        "upper_50epoch_gpu_hours_from_observed_mean": (elapsed / len(logs) * 50 / 3600
                                                        if device.startswith("cuda") else 0),
        "measurement_scope": "real fit including D05 checkpoint validation; excludes later split inference",
    }
    write_json(output / "timing.json", timing)
    config.update({
        "status": "trained", "completed_at": now(), "fit_seconds": elapsed,
        "epochs_executed": len(logs), "selected_epoch": checkpoint["selected_epoch"],
        "checkpoint_sha256": sha256_file(output / "checkpoint.pt"),
    })
    write_json(output / "experiment_config.json", config)
    return config


def _matrix(dataset):
    return np.stack([dataset[i]["x"].numpy().reshape(-1) for i in range(len(dataset))])


def _timing_matrix(index, origins=None):
    times = pd.to_datetime(index.anchor_time, utc=True, format="mixed").astype("int64").to_numpy() / 1e9
    if origins is None:
        origins = {run: float(times[index.run_id.to_numpy() == run].min())
                   for run in index.run_id.unique()}
    elapsed = times - np.asarray([origins[run] for run in index.run_id])
    return (elapsed / 3600.0).reshape(-1, 1), origins


def fit_classical(package_root, task, model_name, seed, feature_set, preprocessor_path,
                  output, mode="full"):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    data = PackageData(package_root)
    pp = Preprocessor.load(preprocessor_path)
    train_index = data.index(task, fit=True, feature_set=feature_set)
    if digest_strings(train_index.sample_id.astype(str)) != pp.fit_sample_id_sha256:
        raise RuntimeError("Classical fit scope differs from preprocessing scope")
    timing_origins = None
    started = time.perf_counter()
    if model_name == "Constant":
        estimator = {"score": float(train_index.y.mean())}
        input_description = "training prevalence only"
    elif model_name == "TimingLR":
        matrix, timing_origins = _timing_matrix(train_index)
        estimator = make_pipeline(StandardScaler(), LogisticRegression(
            C=1, max_iter=2000, class_weight="balanced", solver="lbfgs", random_state=seed))
        estimator.fit(matrix, train_index.y.astype(int))
        input_description = "diagnostic elapsed hours from own-run origin only"
    else:
        dataset = WindowDataset(data, task, train_index, pp, mode=mode)
        matrix = _matrix(dataset)
        if model_name in ("IsolationForest", "MaskOnlyIF", "ReadyMaskIF"):
            estimator = IsolationForest(n_estimators=200, max_samples=min(256, len(matrix)),
                                        random_state=seed, n_jobs=4)
            estimator.fit(matrix)
        elif model_name in ("RF", "ReadyMaskRF"):
            estimator = RandomForestClassifier(
                n_estimators=200, max_depth=8, min_samples_leaf=5,
                class_weight=None, random_state=seed, n_jobs=4)
            estimator.fit(matrix, train_index.y)
        elif model_name in ("LR", "MaskOnlyLR"):
            estimator = LogisticRegression(
                C=1, max_iter=2000, class_weight="balanced", solver="lbfgs", random_state=seed)
            estimator.fit(matrix, train_index.y.astype(int))
        else:
            raise ValueError(model_name)
        input_description = f"12-step flattened mode={mode}, width={matrix.shape[1]}"
    with open(output / "checkpoint.pkl", "wb") as handle:
        pickle.dump({"estimator": estimator, "timing_origins": timing_origins}, handle)
    elapsed = time.perf_counter() - started
    if model_name in ("Constant", "TimingLR"):
        actual_input = {
            "value_channels_consumed": 0,
            "mask_channels_consumed": 0,
            "metadata_control_channels_consumed": 0 if model_name == "Constant" else 1,
            "sequence_steps": 0 if model_name == "Constant" else 1,
        }
    elif mode == "full":
        actual_input = {
            "value_channels_consumed": pp.value_dim,
            "mask_channels_consumed": pp.value_dim,
            "metadata_control_channels_consumed": 0,
            "sequence_steps": 12,
        }
    elif mode == "values_only":
        actual_input = {
            "value_channels_consumed": pp.value_dim,
            "mask_channels_consumed": 0,
            "metadata_control_channels_consumed": 0,
            "sequence_steps": 12,
        }
    elif mode == "mask_only":
        actual_input = {
            "value_channels_consumed": 0,
            "mask_channels_consumed": pp.value_dim,
            "metadata_control_channels_consumed": 0,
            "sequence_steps": 12,
        }
    else:
        actual_input = {
            "value_channels_consumed": int(pp.ready.sum()),
            "mask_channels_consumed": pp.value_dim,
            "metadata_control_channels_consumed": 0,
            "sequence_steps": 12,
        }
    config = {
        **source_identity(package_root),
        "task": task, "model": model_name, "seed": seed,
        "feature_set": feature_set, "feature_columns": pp.columns,
        "mode": mode, "input_description": input_description,
        "actual_input": actual_input,
        "fit_sample_count": len(train_index),
        "fit_sample_id_sha256": digest_strings(train_index.sample_id.astype(str)),
        "preprocessor_sha256": sha256_file(preprocessor_path),
        "fit_seconds": elapsed, "device": "CPU", "peak_gpu_allocated_bytes": 0,
        "test_or_external_used_for_selection": False,
        "point_adjustment": False, "created_at": now(), "status": "trained",
        "checkpoint_sha256": sha256_file(output / "checkpoint.pkl"),
        "implementation": f"scikit-learn {sklearn.__version__}",
    }
    write_json(output / "experiment_config.json", config)
    pp.save(output / "preprocessing.json")
    write_json(output / "implementation_provenance.json", {
        "python": sys.version, "numpy": np.__version__, "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__, "model": model_name,
        "hyperparameters": json_safe(
            estimator.get_params(deep=True)
            if hasattr(estimator, "get_params") else estimator
        ),
        "point_adjustment": False,
    })
    pd.DataFrame([{
        "epoch": 0, "train_loss": np.nan, "validation_selection_loss": np.nan,
        "checkpoint_selected": True, "elapsed_seconds": elapsed,
        "peak_gpu_allocated_bytes": 0,
    }]).to_csv(output / "training_log.csv", index=False)
    train_index[["sample_id", "run_id", "slot"]].to_csv(
        output / "fit_sample_ids.csv.gz", index=False)
    return config


def _load_deep(config, checkpoint, device):
    pp = Preprocessor.load(Path(checkpoint).with_name("preprocessing.json"))
    if config["task"] == "FD_detection":
        model = build_fd(config["model"], pp.full_input_dim, pp.value_dim)
    else:
        model = build_classifier(config["model"],
                                 config["actual_input"]["value_channels_consumed"]
                                 + config["actual_input"]["mask_channels_consumed"],
                                 2 if config["task"] == "FL_localization" else 1)
    saved = torch.load(checkpoint, map_location=device, weights_only=False)
    model.load_state_dict(saved["model_state"])
    return model.to(device).eval(), pp


def predict_job(job_dir, split, device="cuda"):
    job_dir = Path(job_dir)
    config = json.loads((job_dir / "experiment_config.json").read_text())
    data = PackageData(config["package_root"])
    pp = Preprocessor.load(job_dir / "preprocessing.json")
    index = data.index(config["task"], split=split, feature_set=config["feature_set"])
    frame = index.copy()
    frame["model"] = config["model"]
    frame["seed"] = config["seed"]
    started = time.perf_counter()
    checkpoint_pt = job_dir / "checkpoint.pt"
    if checkpoint_pt.exists():
        model, _ = _load_deep(config, checkpoint_pt, device)
        mode = "values_only" if config["task"] == "FD_detection" and config["model"] == "KAN-AD" else "full"
        dataset = WindowDataset(data, config["task"], index, pp, mode=mode)
        scores, valid, predictions, probabilities = [], [], [], []
        with torch.inference_mode():
            for raw in loader(dataset, False, 0):
                batch = move(raw, device)
                if config["task"] == "FD_detection":
                    output = fd_forward(model, batch)
                    score, okay = fd_current_score(model, output, batch["values"], batch["mask"])
                    scores.extend(score.cpu().numpy())
                    valid.extend(okay.cpu().numpy())
                else:
                    logits = model(batch["x"])
                    if config["task"] == "FP_forewarning":
                        prob = torch.sigmoid(logits.squeeze(-1))
                        scores.extend(prob.cpu().numpy())
                        valid.extend(np.ones(len(prob), dtype=bool))
                    else:
                        prob = torch.softmax(logits, dim=-1)
                        label = prob.argmax(-1).cpu().numpy()
                        predictions.extend(CLASS_NAMES[i] for i in label)
                        probabilities.extend(prob.cpu().numpy().tolist())
                        valid.extend(np.ones(len(label), dtype=bool))
        del model
        if device.startswith("cuda"):
            torch.cuda.empty_cache()
    else:
        with open(job_dir / "checkpoint.pkl", "rb") as handle:
            saved = pickle.load(handle)
        estimator, origins = saved["estimator"], saved["timing_origins"]
        mode = config.get("mode", "full")
        if config["model"] == "Constant":
            scores = np.repeat(estimator["score"], len(index))
        elif config["model"] == "TimingLR":
            # The timing-only diagnostic is expressed relative to the first
            # eligible cutoff of each *own* run.  Reusing training-run origins
            # would be undefined for D05/held-out run IDs and would leak an
            # unrelated absolute-clock offset into this control.
            matrix, _ = _timing_matrix(index, origins=None)
            scores = estimator.predict_proba(matrix)[:, 1]
        else:
            dataset = WindowDataset(data, config["task"], index, pp, mode=mode)
            matrix = _matrix(dataset)
            if config["model"] in ("IsolationForest", "MaskOnlyIF", "ReadyMaskIF"):
                scores = -estimator.score_samples(matrix)
            elif config["task"] == "FL_localization":
                predictions = estimator.predict(matrix).astype(str)
                probabilities = estimator.predict_proba(matrix).tolist()
            else:
                scores = estimator.predict_proba(matrix)[:, 1]
        valid = np.ones(len(index), dtype=bool)
    frame["prediction_valid"] = np.asarray(valid, dtype=bool)
    frame["y_true"] = frame.y
    if config["task"] == "FL_localization":
        frame["y_pred"] = list(predictions)
        frame["class_probabilities"] = list(probabilities)
    else:
        frame["score"] = np.asarray(scores, dtype=float)
    elapsed = time.perf_counter() - started
    frame["inference_seconds_per_sample"] = elapsed / max(len(frame), 1)
    destination = job_dir / "predictions" / f"{split}.parquet"
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(destination, index=False)
    write_json(destination.with_suffix(".json"), {
        "task": config["task"], "model": config["model"], "seed": config["seed"],
        "split": split, "sample_count": len(frame),
        "sample_id_sha256": digest_strings(frame.sample_id.astype(str)),
        "prediction_file_sha256": sha256_file(destination),
        "inference_seconds": elapsed,
        "point_adjustment": False,
        "metadata_columns_are_output_only": True,
    })
    return destination
