"""
models.deeplearning
===================
PyTorch spatiotemporal members (ARCHITECTURE.md §6.2 #17 ConvLSTM, #21 U-Net).
**Import-guarded**: if ``torch`` is not installed, ``available()`` returns
False and the trainer skips these members with a logged note — the rest of the
ensemble (numpy baselines + ridge + analog + boosting) still trains.

Both nets are deliberately **small and CPU-friendly** (a few epochs, tiny
channel counts) because the demo must run without a GPU.

ConvLSTM (field nowcaster)
--------------------------
A 1-layer ConvLSTM cell over a short input window of the stacked
(rainfall, tmax, tmin) fields predicts the **next-day field** of one target
variable over the whole 14×20 grid. Captures the spatial structure + motion the
per-cell tree/linear members cannot see.

U-Net (spatial field predictor / downscaler)
---------------------------------------------
A tiny encoder-decoder CNN maps the current-day 3-variable field to the
next-day target field. It is the deterministic field-regression / bias-correction
member and the architectural hook for the §6.2 1.0°→0.25° temperature
downscaling deliverable (same net, coarse→fine inputs).

Outputs are returned as full (T, nlat, nlon) prediction cubes aligned to the
dataset's day axis, which the trainer maps onto the shared feature-table rows so
they can be scored and stacked exactly like the other members.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .data import VARS, ClimateDataset

# ---- Import guard ---------------------------------------------------------
_TORCH_OK = True
try:  # pragma: no cover - depends on environment
    import torch  # type: ignore
    import torch.nn as nn  # type: ignore
except Exception:  # pragma: no cover
    _TORCH_OK = False
    torch = None  # type: ignore
    nn = object  # type: ignore


def available() -> bool:
    return _TORCH_OK


# ──────────────────────────────────────────────────────────────────────────
# Normalisation helpers (per variable, train-only stats)
# ──────────────────────────────────────────────────────────────────────────
def _norm_stats(ds: ClimateDataset) -> Dict[str, Tuple[float, float]]:
    stats: Dict[str, Tuple[float, float]] = {}
    train_mask = np.isin(ds.year_of_day, ds.train_years)
    for v in VARS:
        cube = ds.cube(v)[train_mask]
        stats[v] = (float(cube.mean()), float(cube.std() + 1e-6))
    return stats


def _stack_norm(ds: ClimateDataset, stats: Dict[str, Tuple[float, float]]) -> np.ndarray:
    """Return a (T, 3, nlat, nlon) normalised stack of the three variables."""
    chans = []
    for v in VARS:
        mu, sd = stats[v]
        chans.append((ds.cube(v) - mu) / sd)
    return np.stack(chans, axis=1)


if _TORCH_OK:

    class _ConvLSTMCell(nn.Module):
        def __init__(self, in_ch: int, hid_ch: int, k: int = 3):
            super().__init__()
            pad = k // 2
            self.hid_ch = hid_ch
            self.conv = nn.Conv2d(in_ch + hid_ch, 4 * hid_ch, k, padding=pad)

        def forward(self, x, h, c):
            z = self.conv(torch.cat([x, h], dim=1))
            i, f, o, g = torch.chunk(z, 4, dim=1)
            i = torch.sigmoid(i); f = torch.sigmoid(f); o = torch.sigmoid(o); g = torch.tanh(g)
            c = f * c + i * g
            h = o * torch.tanh(c)
            return h, c

    class _ConvLSTMNet(nn.Module):
        """1-layer ConvLSTM over a window → 1-channel next-day field."""

        def __init__(self, in_ch: int = 3, hid_ch: int = 12):
            super().__init__()
            self.cell = _ConvLSTMCell(in_ch, hid_ch)
            self.head = nn.Conv2d(hid_ch, 1, 1)
            self.hid_ch = hid_ch

        def forward(self, seq):  # seq: (B, L, C, H, W)
            B, L, C, H, W = seq.shape
            h = torch.zeros(B, self.hid_ch, H, W, device=seq.device)
            c = torch.zeros(B, self.hid_ch, H, W, device=seq.device)
            for t in range(L):
                h, c = self.cell(seq[:, t], h, c)
            return self.head(h).squeeze(1)  # (B, H, W)

    class _UNet(nn.Module):
        """Tiny 2-level U-Net: 3-ch field → 1-ch next-day field."""

        def __init__(self, in_ch: int = 3, base: int = 16):
            super().__init__()
            self.e1 = nn.Sequential(nn.Conv2d(in_ch, base, 3, padding=1), nn.ReLU(),
                                    nn.Conv2d(base, base, 3, padding=1), nn.ReLU())
            self.pool = nn.MaxPool2d(2)
            self.e2 = nn.Sequential(nn.Conv2d(base, base * 2, 3, padding=1), nn.ReLU(),
                                    nn.Conv2d(base * 2, base * 2, 3, padding=1), nn.ReLU())
            self.up = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False)
            self.d1 = nn.Sequential(nn.Conv2d(base * 3, base, 3, padding=1), nn.ReLU(),
                                    nn.Conv2d(base, base, 3, padding=1), nn.ReLU())
            self.head = nn.Conv2d(base, 1, 1)

        def forward(self, x):  # (B, C, H, W)
            s1 = self.e1(x)
            s2 = self.e2(self.pool(s1))
            u = self.up(s2)
            # Pad to match s1 if odd dims.
            if u.shape[-2:] != s1.shape[-2:]:
                u = u[..., : s1.shape[-2], : s1.shape[-1]]
            d = self.d1(torch.cat([u, s1], dim=1))
            return self.head(d).squeeze(1)


@dataclass
class TorchFieldModel:
    """A fitted torch field model (ConvLSTM or U-Net) for one variable."""

    var: str
    kind: str                      # "convlstm" | "unet"
    net: object
    stats: Dict[str, Tuple[float, float]]
    window: int
    resid_sigma: float = 1.0
    pred_cube: Optional[np.ndarray] = None  # cached (T,nlat,nlon) predictions


def _make_sequences(stack: np.ndarray, target: np.ndarray, days: np.ndarray,
                    window: int, kind: str):
    """Assemble (X, Y) training tensors for the given source days.

    For ConvLSTM X is (N, window, 3, H, W); for U-Net X is (N, 3, H, W).
    Target Y is the normalised next-day target field (N, H, W).
    """
    Xs, Ys, used = [], [], []
    for t in days:
        t = int(t)
        if kind == "convlstm":
            if t - (window - 1) < 0:
                continue
            seq = stack[t - (window - 1): t + 1]  # (window,3,H,W)
            Xs.append(seq)
        else:
            Xs.append(stack[t])                   # (3,H,W)
        Ys.append(target[t + 1])
        used.append(t)
    return np.asarray(Xs), np.asarray(Ys), np.asarray(used)


def fit(var: str, ds: ClimateDataset, kind: str = "convlstm",
        window: int = 3, epochs: int = 8, hid: int = 12,
        lr: float = 5e-3, seed: int = 0) -> Optional[TorchFieldModel]:
    """Train a small torch field model for ``var``. Returns None if torch absent."""
    if not _TORCH_OK:
        return None
    torch.manual_seed(seed)
    np.random.seed(seed)
    nlat, nlon = ds.grid.shape
    stats = _norm_stats(ds)
    stack = _stack_norm(ds, stats)                 # (T,3,H,W)
    tmu, tsd = stats[var]
    target_norm = (ds.cube(var) - tmu) / tsd       # (T,H,W)

    # Source days within each TRAIN year (t+1 in-year).
    train_days: List[int] = []
    for y in ds.train_years:
        idx = np.where(ds.year_of_day == y)[0]
        train_days += list(range(int(idx[0]), int(idx[-1])))
    train_days_arr = np.asarray(train_days)

    X, Y, _ = _make_sequences(stack, target_norm, train_days_arr, window, kind)
    if X.shape[0] == 0:
        return None
    Xt = torch.tensor(X, dtype=torch.float32)
    Yt = torch.tensor(Y, dtype=torch.float32)

    if kind == "convlstm":
        net = _ConvLSTMNet(in_ch=3, hid_ch=hid)
    else:
        net = _UNet(in_ch=3, base=hid)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    loss_fn = nn.SmoothL1Loss()

    n = Xt.shape[0]
    batch = 64
    net.train()
    for ep in range(epochs):
        perm = torch.randperm(n)
        for s in range(0, n, batch):
            bi = perm[s: s + batch]
            opt.zero_grad()
            out = net(Xt[bi])
            loss = loss_fn(out, Yt[bi])
            loss.backward()
            opt.step()

    # Precompute predictions for ALL days (de-normalised) for downstream use.
    net.eval()
    pred_cube = np.full((ds.T, nlat, nlon), np.nan)
    all_days = np.arange(ds.T - 1)
    Xa, _, used = _make_sequences(stack, target_norm, all_days, window, kind)
    if Xa.shape[0] > 0:
        with torch.no_grad():
            preds = []
            Xat = torch.tensor(Xa, dtype=torch.float32)
            for s in range(0, Xat.shape[0], 256):
                preds.append(net(Xat[s: s + 256]).cpu().numpy())
        preds = np.concatenate(preds, axis=0)
        preds = preds * tsd + tmu  # de-normalise
        if var == "rainfall":
            preds = np.maximum(preds, 0.0)
        # used[k] is source day t; prediction is for day t+1.
        for k, t in enumerate(used):
            pred_cube[int(t) + 1] = preds[k]

    model = TorchFieldModel(var=var, kind=kind, net=net, stats=stats,
                            window=window, pred_cube=pred_cube)
    # Residual sigma on validation days.
    val_days = np.isin(ds.year_of_day, ds.val_years)
    vt = np.where(val_days)[0]
    res = []
    for t in vt:
        if np.isfinite(pred_cube[t]).all():
            res.append((ds.cube(var)[t] - pred_cube[t]).reshape(-1))
    model.resid_sigma = float(np.std(np.concatenate(res))) if res else 1.0
    return model


def predict_table(model: TorchFieldModel, ds: ClimateDataset,
                  target_day_index: np.ndarray, cell_index: np.ndarray) -> np.ndarray:
    """Per-sample prediction from the cached cube.

    ``target_day_index`` is the *target* day (t+1) of each feature-table row.
    """
    pred = model.pred_cube
    nlat, nlon = ds.grid.shape
    out = np.empty(target_day_index.shape[0])
    for n in range(target_day_index.shape[0]):
        t1 = int(target_day_index[n])
        c = int(cell_index[n])
        out[n] = pred[t1].reshape(-1)[c]
    return out


__all__ = ["available", "TorchFieldModel", "fit", "predict_table"]
