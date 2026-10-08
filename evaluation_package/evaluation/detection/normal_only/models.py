"""Verified model identities and task adapters.

The three FD names are not aliases for generic classifiers:

* ``AE`` reuses the previously executed dense sequence autoencoder topology.
* ``TranAD_adapted_v2`` extracts the pinned official TranAD classes and retains
  its two-decoder self-conditioning mechanism; the bounded adversarial adapter
  is the already-audited v2 implementation, not an exact-paper reproduction.
* ``KAN-AD`` extracts the pinned ICML 2025 author ``KANADModel`` and applies the
  previously used shared-univariate, first-difference next-anchor adapter.

All FD scores are current-cutoff scores.  No point adjustment exists here.
"""
from __future__ import annotations

import ast
import copy
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import math
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F


HERE = Path(__file__).resolve().parent
TRANAD_VENDOR = HERE / "vendor" / "TranAD"
KANAD_VENDOR = HERE / "vendor" / "KANAD"
TRANAD_COMMIT = "7ffb98d0c18189cc3d9ab732b4cb0278200a0af0"
KANAD_COMMIT = "7c3a0d96b77e0d609660a240c2b11db084ba523f"


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class RelativePosition(nn.Module):
    def __init__(self, width, history, dropout):
        super().__init__()
        pos = torch.arange(history).float()[:, None]
        rates = torch.exp(torch.arange(0, width, 2).float() * (-math.log(10000.0) / width))
        pe = torch.zeros(history, width)
        pe[:, 0::2] = torch.sin(pos * rates)
        pe[:, 1::2] = torch.cos(pos * rates[:pe[:, 1::2].shape[1]])
        self.register_buffer("pe", pe[None])
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        return self.dropout(x + self.pe[:, :x.shape[1]])


class CausalConv(nn.Module):
    def __init__(self, in_dim, out_dim, dilation=1):
        super().__init__()
        self.padding = 2 * dilation
        self.conv = nn.Conv1d(in_dim, out_dim, 3, dilation=dilation)

    def forward(self, x):
        return self.conv(F.pad(x, (self.padding, 0)))


class CausalBlock(nn.Module):
    def __init__(self, in_dim, width, dilation, dropout):
        super().__init__()
        self.path = nn.Sequential(
            CausalConv(in_dim, width, dilation), nn.ReLU(), nn.Dropout(dropout),
            CausalConv(width, width, dilation), nn.ReLU(), nn.Dropout(dropout),
        )
        self.skip = nn.Identity() if in_dim == width else nn.Conv1d(in_dim, width, 1)

    def forward(self, x):
        return F.relu(self.path(x) + self.skip(x))


class SequenceClassifier(nn.Module):
    """Frozen width-64, two-layer LSTM/TCN/small-Transformer classifier."""

    def __init__(self, name, input_dim, output_dim, history=12, width=64, dropout=0.1):
        super().__init__()
        self.name, self.history = name, history
        if name == "LSTM":
            self.encoder = nn.LSTM(input_dim, width, 2, batch_first=True, dropout=dropout)
        elif name == "TCN":
            self.encoder = nn.Sequential(
                CausalBlock(input_dim, width, 1, dropout),
                CausalBlock(width, width, 2, dropout),
            )
        elif name == "small_Transformer":
            self.input_projection = nn.Linear(input_dim, width)
            self.position = RelativePosition(width, history, dropout)
            layer = nn.TransformerEncoderLayer(
                width, 4, 128, dropout, batch_first=True, activation="gelu")
            self.encoder = nn.TransformerEncoder(layer, 2, enable_nested_tensor=False)
        else:
            raise ValueError(name)
        self.head = nn.Linear(width, output_dim)

    def forward(self, x):
        if x.ndim != 3 or x.shape[1] != self.history:
            raise ValueError("Classifier requires complete Bx12xD windows")
        if self.name == "LSTM":
            state = self.encoder(x)[0][:, -1]
        elif self.name == "TCN":
            state = self.encoder(x.transpose(1, 2))[:, :, -1]
        else:
            state = self.position(self.input_projection(x))
            causal = torch.triu(torch.ones(
                x.shape[1], x.shape[1], device=x.device, dtype=torch.bool), diagonal=1)
            state = self.encoder(state, mask=causal)[:, -1]
        return self.head(state)


class DenseSequenceAutoencoder(nn.Module):
    """Previously executed AE topology, adapted from 60 to 12 grid steps.

    The topology is the exact DenseAutoencoder family used in the prior code:
    flattened sequence -> hidden 256 -> latent 64 -> hidden 256 -> flattened
    sequence.  Its full 48-channel output preserves that identity; only the 24
    numeric channels participate in loss and scoring, as required here.
    """

    def __init__(self, input_dim, history=12, hidden=256, latent=64):
        super().__init__()
        self.name, self.history = "AE", history
        width = history * input_dim
        self.input_dim = input_dim
        self.encoder = nn.Sequential(nn.Linear(width, hidden), nn.GELU(), nn.Linear(hidden, latent))
        self.decoder = nn.Sequential(nn.Linear(latent, hidden), nn.GELU(), nn.Linear(hidden, width))

    def forward(self, x):
        if x.ndim != 3 or x.shape[1:] != (self.history, self.input_dim):
            raise ValueError("AE input shape mismatch")
        flat = x.flatten(1)
        return self.decoder(self.encoder(flat)).view(-1, self.history, self.input_dim)


class _EncoderStack(nn.Module):
    def __init__(self, layer, num_layers):
        super().__init__()
        self.layers = nn.ModuleList(copy.deepcopy(layer) for _ in range(num_layers))

    def forward(self, src):
        for layer in self.layers:
            src = layer(src)
        return src


class _DecoderStack(nn.Module):
    def __init__(self, layer, num_layers):
        super().__init__()
        self.layers = nn.ModuleList(copy.deepcopy(layer) for _ in range(num_layers))

    def forward(self, tgt, memory):
        for layer in self.layers:
            tgt = layer(tgt, memory)
        return tgt


@lru_cache(maxsize=1)
def official_tranad_classes():
    """Extract selected official classes without importing legacy drivers."""
    namespace = {
        "nn": nn, "torch": torch, "math": math, "lr": 1e-3,
        "TransformerEncoder": _EncoderStack, "TransformerDecoder": _DecoderStack,
    }
    selections = [
        ("src/dlutils.py", {"PositionalEncoding", "TransformerEncoderLayer", "TransformerDecoderLayer"}),
        ("src/models.py", {"TranAD"}),
    ]
    for relative, wanted in selections:
        path = TRANAD_VENDOR / relative
        tree = ast.parse(path.read_text(), filename=str(path))
        nodes = [node for node in tree.body
                 if isinstance(node, ast.ClassDef) and node.name in wanted]
        if {node.name for node in nodes} != wanted:
            raise RuntimeError(f"Pinned TranAD source identity mismatch: {path}")
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["TranAD"], namespace["PositionalEncoding"]


@dataclass
class TranADOutput:
    phase1: torch.Tensor
    phase2: torch.Tensor
    decoder2_unconditioned: torch.Tensor
    focus: torch.Tensor
    representation: str = "bounded_logistic_v2"


def tranad_bounded_values(values, observed):
    mask = observed.bool() & torch.isfinite(values)
    clean = torch.where(mask, values, torch.zeros_like(values))
    return torch.where(mask, torch.sigmoid(clean), torch.zeros_like(clean))


class TranADAdaptedV2(nn.Module):
    """Pinned official TranAD architecture plus audited bounded v2 objective."""

    def __init__(self, input_dim, value_dim, history=12, dropout=0.1):
        super().__init__()
        if input_dim != 2 * value_dim:
            raise ValueError("TranAD requires value+mask input")
        self.name, self.history = "TranAD_adapted_v2", history
        self.value_dim = value_dim
        self.variant = "bounded_logistic_v2"
        self.register_buffer("tranad_variant_version", torch.tensor(2, dtype=torch.int64))
        upstream, position = official_tranad_classes()
        self.core = upstream(input_dim)
        self.core.n_window, self.core.n = history, input_dim * history
        self.core.pos_encoder = position(2 * input_dim, dropout, history)

    def forward(self, x):
        if x.ndim != 3 or x.shape[1] != self.history or x.shape[2] != 2 * self.value_dim:
            raise ValueError("TranAD requires Bx12x(Dvalue+Dmask)")
        observed = x[:, :, self.value_dim:]
        bounded = tranad_bounded_values(x[:, :, :self.value_dim], observed)
        src = torch.cat((bounded, observed), dim=-1).transpose(0, 1)
        tgt, zero = src[-1:], torch.zeros_like(src)
        query, memory = self.core.encode(src, zero, tgt)
        phase1 = self.core.fcn(self.core.transformer_decoder1(query, memory))
        base2 = self.core.fcn(self.core.transformer_decoder2(query, memory))
        value_mask = src[:, :, self.value_dim:]
        focus_values = (phase1[:, :, :self.value_dim] - src[:, :, :self.value_dim]).square() * value_mask
        focus = torch.cat((focus_values, torch.zeros_like(value_mask)), dim=-1)
        phase2 = self.core.fcn(self.core.transformer_decoder2(*self.core.encode(src, focus, tgt)))
        take = lambda z: z[:, :, :self.value_dim].transpose(0, 1)
        return TranADOutput(take(phase1), take(phase2), take(base2), focus)

    def adversarial_parameter_groups(self):
        discriminator = list(self.core.transformer_decoder2.parameters())
        ids = {id(p) for p in discriminator}
        generator = [p for p in self.parameters() if id(p) not in ids]
        return generator, discriminator


@lru_cache(maxsize=1)
def official_kanad_class():
    path = KANAD_VENDOR / "kanad" / "kanad.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    nodes = [node for node in tree.body
             if isinstance(node, ast.ClassDef) and node.name == "KANADModel"]
    if len(nodes) != 1:
        raise RuntimeError("Pinned KAN-AD source identity mismatch")
    namespace = {"th": torch, "torch": torch, "nn": nn}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["KANADModel"]


class KANADAdapted(nn.Module):
    """Author KAN-AD backbone with shared univariate next-anchor adaptation.

    For a 12-step window, the first 11 steps are history; first differencing
    yields the 10-element native KAN-AD input.  The native forecast is added to
    step 11 to predict the current (12th) value.  Channels share one author
    backbone exactly as in the prior verified adapter.
    """

    def __init__(self, value_dim, history=12, order=2):
        super().__init__()
        self.name, self.history = "KAN-AD", history
        self.value_dim, self.order = value_dim, order
        self.native_window = history - 2
        self.native = official_kanad_class()(window=self.native_window, order=order)

    def forward(self, values):
        if values.ndim != 3 or values.shape[1:] != (self.history, self.value_dim):
            raise ValueError("KAN-AD values input shape mismatch")
        history = values[:, :-1].transpose(1, 2)
        delta = history[..., 1:] - history[..., :-1]
        forecast_delta = self.native(delta.reshape(-1, self.native_window)).reshape(
            len(values), self.value_dim)
        return (forecast_delta + values[:, -2]).unsqueeze(1)


def build_classifier(name, input_dim, output_dim):
    return SequenceClassifier(name, input_dim, output_dim, history=12, width=64, dropout=0.1)


def build_fd(name, input_dim, value_dim):
    if name == "AE":
        return DenseSequenceAutoencoder(input_dim, history=12, hidden=256, latent=64)
    if name == "TranAD_adapted_v2":
        return TranADAdaptedV2(input_dim, value_dim, history=12, dropout=0.1)
    if name == "KAN-AD":
        return KANADAdapted(value_dim, history=12, order=2)
    raise ValueError(name)


def masked_mse(prediction, target, observed):
    mask = observed.bool() & torch.isfinite(target)
    clean = torch.where(mask, target, torch.zeros_like(target))
    residual = torch.where(mask, prediction - clean, torch.zeros_like(prediction))
    count = mask.sum()
    if int(count) == 0:
        raise ValueError("No observed targets in batch")
    return residual.square().sum() / count


def tranad_adversarial_losses(output, target_values, observed_mask, epoch_index):
    target, mask = target_values[:, -1:], observed_mask[:, -1:].bool()
    target = tranad_bounded_values(target, mask)
    a = 1.0 / (epoch_index + 1)
    err1 = masked_mse(output.phase1, target, mask)
    err2 = masked_mse(output.decoder2_unconditioned, target, mask)
    focused = masked_mse(output.phase2, target, mask)
    return a * err1 + (1 - a) * focused, a * err2 - (1 - a) * focused


def fd_backward(model, output, values, observed, epoch_index, loss_scale=1.0):
    """Backpropagate the model's real reconstruction/forecast objective."""
    if isinstance(model, DenseSequenceAutoencoder):
        loss = masked_mse(output[:, :, :values.shape[-1]], values, observed)
        (loss * loss_scale).backward()
        return {"loss": float(loss.detach())}
    if isinstance(model, KANADAdapted):
        loss = masked_mse(output, values[:, -1:], observed[:, -1:])
        (loss * loss_scale).backward()
        return {"loss": float(loss.detach())}
    if isinstance(model, TranADAdaptedV2):
        generator_loss, discriminator_loss = tranad_adversarial_losses(
            output, values, observed, epoch_index)
        generator, discriminator = model.adversarial_parameter_groups()
        gg = torch.autograd.grad(generator_loss * loss_scale, generator,
                                 retain_graph=True, allow_unused=True)
        gd = torch.autograd.grad(discriminator_loss * loss_scale, discriminator,
                                 allow_unused=True)
        for parameter, gradient in zip(generator + discriminator, list(gg) + list(gd)):
            if gradient is not None:
                parameter.grad = (gradient.detach() if parameter.grad is None
                                  else parameter.grad.add_(gradient.detach()))
        return {
            "loss": float(generator_loss.detach()),
            "generator_loss": float(generator_loss.detach()),
            "discriminator_loss": float(discriminator_loss.detach()),
        }
    raise TypeError(type(model).__name__)


def fd_validation_loss(model, output, values, observed, epoch_index):
    if isinstance(model, DenseSequenceAutoencoder):
        return masked_mse(output[:, :, :values.shape[-1]], values, observed)
    if isinstance(model, KANADAdapted):
        return masked_mse(output, values[:, -1:], observed[:, -1:])
    if isinstance(model, TranADAdaptedV2):
        return tranad_adversarial_losses(output, values, observed, epoch_index)[0]
    raise TypeError(type(model).__name__)


def fd_forward(model, batch):
    if isinstance(model, KANADAdapted):
        return model(batch["values"])
    return model(batch["x"])


def fd_current_score(model, output, values, observed):
    """Return score and validity for the current final grid point only."""
    target, mask = values[:, -1], observed[:, -1].bool()
    clean = torch.where(mask, target, torch.zeros_like(target))
    if isinstance(model, DenseSequenceAutoencoder):
        # Contracted AE score: mean squared standardized value residual.
        residual = (output[:, -1, :values.shape[-1]] - clean).square()
    elif isinstance(model, TranADAdaptedV2):
        bounded = tranad_bounded_values(target, mask)
        residual = 0.5 * ((output.phase1[:, -1] - bounded).square()
                          + (output.phase2[:, -1] - bounded).square())
    elif isinstance(model, KANADAdapted):
        # Author evaluation uses absolute forecast residual at the anchor.
        residual = (output[:, -1] - clean).abs()
    else:
        raise TypeError(type(model).__name__)
    count = mask.sum(-1)
    score = torch.where(mask, residual, torch.zeros_like(residual)).sum(-1) / count.clamp_min(1)
    valid = (count > 0) & torch.isfinite(score)
    score = torch.where(valid, score, torch.full_like(score, float("nan")))
    return score, valid


def parameter_count(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def model_provenance(model):
    result = {
        "registered_name": model.name,
        "adapter_source_sha256": sha256_file(__file__),
        "trainable_parameters": parameter_count(model),
        "torch_version": torch.__version__,
        "history_steps": model.history,
    }
    if isinstance(model, DenseSequenceAutoencoder):
        prior = Path(__file__).resolve().parent / 'legacy_reference/classic_native.py'
        result.update({
            "identity": "existing DenseAutoencoder topology",
            "prior_source_path": str(prior),
            "prior_source_sha256": sha256_file(prior),
            "architecture": {"hidden": 256, "latent": 64, "activation": "GELU"},
            "adaptation": "sequence length 60->12; input dimension follows FD value+mask; numeric channels alone define loss/score",
            "loss": "observed numeric sequence masked MSE",
            "score": "current valid standardized numeric residual squared mean",
        })
    elif isinstance(model, TranADAdaptedV2):
        files = ["src/models.py", "src/dlutils.py", "main.py", "LICENSE"]
        result.update({
            "identity": "pinned official TranAD classes plus audited bounded_logistic_v2 adapter",
            "official_repository": "https://github.com/imperial-qore/TranAD",
            "official_commit": TRANAD_COMMIT,
            "official_files_sha256": {f: sha256_file(TRANAD_VENDOR / f) for f in files},
            "architecture": {
                "input_features": model.core.n_feats,
                "d_model": 2 * model.core.n_feats,
                "heads": model.core.n_feats,
                "encoder_layers": 1,
                "decoder_layers_each": 1,
                "decoder_count": 2,
            },
            "variant": model.variant,
            "official_output_sigmoid_preserved": True,
            "paper_numerical_reproduction_claimed": False,
            "loss": "two-stage self-conditioned bounded reconstruction with explicit opposing decoder-2 gradients",
            "score": "current valid bounded-space mean of phase1/phase2 squared residuals",
        })
    elif isinstance(model, KANADAdapted):
        files = ["kanad/kanad.py", "SOURCE_COMMIT", "LICENSE"]
        result.update({
            "identity": "pinned author KANADModel",
            "official_repository": "https://github.com/issaccv/KAN-AD",
            "official_commit": KANAD_COMMIT,
            "official_files_sha256": {f: sha256_file(KANAD_VENDOR / f) for f in files},
            "architecture": {"order": model.order, "native_window": model.native_window,
                             "shared_univariate_channels": model.value_dim},
            "adaptation": "12-step multivariate window -> per-channel first-difference length10 -> shared author KANADModel -> current anchor forecast",
            "loss": "current observed numeric forecast MSE",
            "score": "current valid numeric mean absolute forecast residual",
        })
    else:
        if model.name == "LSTM":
            architecture = {
                "family": "LSTM", "hidden_width": 64, "layers": 2,
                "dropout": 0.1, "readout": "last sequence state",
            }
        elif model.name == "TCN":
            architecture = {
                "family": "causal TCN", "width": 64, "blocks": 2,
                "kernel_size": 3, "dilations": [1, 2], "dropout": 0.1,
                "activation": "ReLU", "readout": "last causal state",
            }
        else:
            architecture = {
                "family": "causal Transformer encoder", "d_model": 64,
                "layers": 2, "attention_heads": 4, "feedforward_width": 128,
                "dropout": 0.1, "activation": "GELU",
                "readout": "last causally masked state",
            }
        result.update({
            "architecture": architecture,
            "loss": "BCEWithLogitsLoss" if model.head.out_features == 1 else "CrossEntropyLoss",
        })
    return result
