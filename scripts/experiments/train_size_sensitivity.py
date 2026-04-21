"""
Training-set-size sensitivity experiment.

Motivation
----------
We collected 626 dashcam clips and hand-labeled each as anomalous vs normal
using the in-app labeling UI. Only 16 of those clips ended up flagged as
anomalous (2.6% positive rate). A natural question is: was 626 enough? If
performance on our held-out test set plateaus well before we reach 100% of
the training data, further labeling effort was low-value. If it's still
climbing at 100%, doubling our labeling budget would have paid off.

This experiment trains the deployed classical ML model (XGBoost on 19
hand-engineered motion features) on increasing fractions of the training
split [10%, 25%, 50%, 75%, 100%] and evaluates each on the fixed, held-out
test set defined in data/splits.json. Multiple seeds per fraction let us
plot mean ± std and distinguish "the curve plateaued" from "one unlucky
subsample."

Outputs
-------
  data/outputs/experiment/train_size.json  — raw per-run metrics
  data/outputs/experiment/train_size.png   — F1 and AUC vs train fraction

Usage
-----
    python scripts/experiments/train_size_sensitivity.py
    python scripts/experiments/train_size_sensitivity.py --include-lstm
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

SPLITS_PATH = Path("data/splits.json")
FEATURES_DIR = Path("data/processed")
OUTPUT_DIR = Path("data/outputs/experiment")
TRAIN_FRACTIONS = [0.10, 0.25, 0.50, 0.75, 1.00]
SEEDS = [0, 1, 2, 3, 4]


def _load_split_features() -> dict:
    """Load 19-dim classical features + labels, keyed by split."""
    splits = json.loads(SPLITS_PATH.read_text())
    labels = splits["labels"]["is_anomaly"]

    def _load(ids: list[str]) -> tuple[np.ndarray, np.ndarray, list[str]]:
        X, y, kept = [], [], []
        for cid in ids:
            p = FEATURES_DIR / f"{cid}_features.npz"
            if not p.exists():
                continue
            with np.load(p) as d:
                X.append(d["features"])
            y.append(int(labels[cid]))
            kept.append(cid)
        return np.stack(X), np.array(y, dtype=np.int32), kept

    X_tr, y_tr, train_ids = _load(splits["train"])
    X_te, y_te, test_ids = _load(splits["test"])
    logger.info(
        "Train: %d (%d pos)  Test: %d (%d pos)",
        len(y_tr),
        y_tr.sum(),
        len(y_te),
        y_te.sum(),
    )
    return {
        "X_train": X_tr,
        "y_train": y_tr,
        "train_ids": train_ids,
        "X_test": X_te,
        "y_test": y_te,
        "test_ids": test_ids,
    }


def _stratified_subsample(
    X: np.ndarray, y: np.ndarray, frac: float, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    """Subsample preserving positive/negative ratio. Always keeps ≥1 positive."""
    rng = np.random.default_rng(seed)
    pos_idx = np.where(y == 1)[0]
    neg_idx = np.where(y == 0)[0]
    n_pos = max(1, int(round(len(pos_idx) * frac)))
    n_neg = max(1, int(round(len(neg_idx) * frac)))
    pos_sel = rng.choice(pos_idx, size=n_pos, replace=False)
    neg_sel = rng.choice(neg_idx, size=n_neg, replace=False)
    idx = np.concatenate([pos_sel, neg_sel])
    rng.shuffle(idx)
    return X[idx], y[idx]


def _train_classical(X_tr, y_tr, X_te, y_te, seed: int) -> dict:
    """Train XGBoost and evaluate on held-out test set."""
    import xgboost as xgb
    from sklearn.metrics import (
        f1_score,
        roc_auc_score,
        precision_score,
        recall_score,
    )
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(X_tr)
    X_tr_s = scaler.transform(X_tr)
    X_te_s = scaler.transform(X_te)

    n_pos = max(int(y_tr.sum()), 1)
    n_neg = max(len(y_tr) - n_pos, 1)
    clf = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=n_neg / n_pos,
        eval_metric="logloss",
        random_state=seed,
        n_jobs=-1,
    )
    clf.fit(X_tr_s, y_tr)
    probs = clf.predict_proba(X_te_s)[:, 1]
    preds = (probs >= 0.5).astype(int)

    return {
        "f1": float(f1_score(y_te, preds, zero_division=0)),
        "auc": float(roc_auc_score(y_te, probs))
        if len(set(y_te)) > 1
        else float("nan"),
        "precision": float(precision_score(y_te, preds, zero_division=0)),
        "recall": float(recall_score(y_te, preds, zero_division=0)),
        "n_train": int(len(y_tr)),
        "n_train_pos": int(y_tr.sum()),
    }


def run_classical_sensitivity(data: dict) -> list[dict]:
    runs = []
    for frac in TRAIN_FRACTIONS:
        for seed in SEEDS:
            X_sub, y_sub = _stratified_subsample(
                data["X_train"],
                data["y_train"],
                frac,
                seed,
            )
            m = _train_classical(X_sub, y_sub, data["X_test"], data["y_test"], seed)
            m.update(fraction=frac, seed=seed, model="classical_xgb")
            logger.info(
                "classical frac=%.2f seed=%d n_train=%d pos=%d f1=%.3f auc=%.3f",
                frac,
                seed,
                m["n_train"],
                m["n_train_pos"],
                m["f1"],
                m["auc"],
            )
            runs.append(m)
    return runs


# ── LSTM (optional second curve) ──────────────────────────────────────────────


def _load_lstm_data(
    train_ids: list[str], test_ids: list[str], labels: dict[str, int]
) -> dict:
    """Load sequence windows from *_dl_features.npz, tag each with clip label."""

    def _load(ids):
        X_windows, y_windows, clip_of_window = [], [], []
        for cid in ids:
            p = FEATURES_DIR / f"{cid}_dl_features.npz"
            if not p.exists():
                continue
            with np.load(p) as d:
                seqs = d["sequences"]
            if seqs.shape[0] == 0:
                continue
            lbl = int(labels[cid])
            X_windows.append(seqs)
            y_windows.append(np.full(seqs.shape[0], lbl, dtype=np.int32))
            clip_of_window.extend([cid] * seqs.shape[0])
        if not X_windows:
            return None, None, []
        return (
            np.concatenate(X_windows, axis=0),
            np.concatenate(y_windows, axis=0),
            clip_of_window,
        )

    X_tr, y_tr, tr_clip = _load(train_ids)
    X_te, y_te, te_clip = _load(test_ids)
    logger.info(
        "LSTM train windows: %d (%d pos)  test windows: %d (%d pos)",
        len(y_tr),
        int(y_tr.sum()),
        len(y_te),
        int(y_te.sum()),
    )
    return {
        "X_train": X_tr,
        "y_train": y_tr,
        "train_clip": tr_clip,
        "X_test": X_te,
        "y_test": y_te,
        "test_clip": te_clip,
    }


def _train_lstm(X_tr, y_tr, X_te, y_te, test_clip, seed: int, epochs: int = 10) -> dict:
    """Train a small LSTM and evaluate clip-level (max-pool windows per clip)."""
    import torch
    import torch.nn as nn
    from sklearn.metrics import (
        f1_score,
        roc_auc_score,
        precision_score,
        recall_score,
    )

    torch.manual_seed(seed)
    np.random.seed(seed)

    device = (
        "cuda"
        if torch.cuda.is_available()
        else (
            "mps"
            if getattr(torch.backends, "mps", None)
            and torch.backends.mps.is_available()
            else "cpu"
        )
    )

    class TinyLSTM(nn.Module):
        def __init__(self, input_dim=13, hidden=64):
            super().__init__()
            self.lstm = nn.LSTM(
                input_dim, hidden, num_layers=1, batch_first=True, bidirectional=True
            )
            self.head = nn.Sequential(
                nn.Linear(2 * hidden, 32),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(32, 1),
            )

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out.mean(dim=1)).squeeze(-1)

    model = TinyLSTM().to(device)
    pos_weight = torch.tensor(
        [max(1, (len(y_tr) - y_tr.sum()) / max(y_tr.sum(), 1))],
        dtype=torch.float32,
    ).to(device)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optim = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)

    Xt = torch.tensor(X_tr, dtype=torch.float32)
    yt = torch.tensor(y_tr, dtype=torch.float32)
    idx = np.arange(len(y_tr))
    batch = 128
    for ep in range(epochs):
        np.random.shuffle(idx)
        model.train()
        for i in range(0, len(idx), batch):
            b = idx[i : i + batch]
            xb = Xt[b].to(device)
            yb = yt[b].to(device)
            logits = model(xb)
            loss = loss_fn(logits, yb)
            optim.zero_grad()
            loss.backward()
            optim.step()

    model.eval()
    Xe = torch.tensor(X_te, dtype=torch.float32).to(device)
    with torch.no_grad():
        win_probs = torch.sigmoid(model(Xe)).cpu().numpy()

    clip_probs: dict[str, float] = {}
    clip_truth: dict[str, int] = {}
    for cid, p, y in zip(test_clip, win_probs, y_te):
        clip_probs[cid] = max(clip_probs.get(cid, 0.0), float(p))
        clip_truth[cid] = int(y)
    y_true = np.array([clip_truth[c] for c in clip_probs], dtype=np.int32)
    p_arr = np.array([clip_probs[c] for c in clip_probs], dtype=np.float32)
    preds = (p_arr >= 0.5).astype(int)

    return {
        "f1": float(f1_score(y_true, preds, zero_division=0)),
        "auc": float(roc_auc_score(y_true, p_arr))
        if len(set(y_true)) > 1
        else float("nan"),
        "precision": float(precision_score(y_true, preds, zero_division=0)),
        "recall": float(recall_score(y_true, preds, zero_division=0)),
        "n_train": int(len(y_tr)),
        "n_train_pos": int(y_tr.sum()),
    }


def run_lstm_sensitivity(train_ids, test_ids, labels, seeds=(0, 1)) -> list[dict]:
    data = _load_lstm_data(train_ids, test_ids, labels)
    if data["X_train"] is None:
        logger.warning("No DL feature sequences — skipping LSTM curve.")
        return []

    # Subsample at the CLIP level, not the window level, so the "train size"
    # axis means "number of labeled clips" for both curves.
    clip_list = sorted(set(data["train_clip"]))
    clip_label = {
        c: int(data["y_train"][data["train_clip"].index(c)]) for c in clip_list
    }
    pos_clips = [c for c in clip_list if clip_label[c] == 1]
    neg_clips = [c for c in clip_list if clip_label[c] == 0]

    runs = []
    for frac in TRAIN_FRACTIONS:
        for seed in seeds:
            rng = np.random.default_rng(1000 + seed)
            n_pos = max(1, int(round(len(pos_clips) * frac)))
            n_neg = max(1, int(round(len(neg_clips) * frac)))
            keep = set(rng.choice(pos_clips, size=n_pos, replace=False)) | set(
                rng.choice(neg_clips, size=n_neg, replace=False)
            )
            mask = np.array([c in keep for c in data["train_clip"]])
            X_sub = data["X_train"][mask]
            y_sub = data["y_train"][mask]
            m = _train_lstm(
                X_sub,
                y_sub,
                data["X_test"],
                data["y_test"],
                data["test_clip"],
                seed=seed,
            )
            m.update(fraction=frac, seed=seed, model="lstm", n_train_clips=len(keep))
            logger.info(
                "lstm frac=%.2f seed=%d n_clips=%d pos_clips=%d f1=%.3f auc=%.3f",
                frac,
                seed,
                len(keep),
                n_pos,
                m["f1"],
                m["auc"],
            )
            runs.append(m)
    return runs


# ── Plot + save ───────────────────────────────────────────────────────────────


def _plot(runs: list[dict], out_path: Path) -> None:
    import matplotlib.pyplot as plt

    models = sorted({r["model"] for r in runs})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))

    for ax, metric, title in [
        (axes[0], "f1", "F1 on held-out test"),
        (axes[1], "auc", "AUC on held-out test"),
    ]:
        for m in models:
            rows = [r for r in runs if r["model"] == m]
            fracs = sorted({r["fraction"] for r in rows})
            means = [
                np.nanmean([r[metric] for r in rows if r["fraction"] == f])
                for f in fracs
            ]
            stds = [
                np.nanstd([r[metric] for r in rows if r["fraction"] == f])
                for f in fracs
            ]
            ax.errorbar(fracs, means, yerr=stds, marker="o", capsize=3, label=m)
        ax.set_xlabel("Fraction of training set")
        ax.set_ylabel(metric.upper())
        ax.set_title(title)
        ax.set_ylim(0, 1.05)
        ax.grid(True, alpha=0.3)
        ax.legend()

    fig.suptitle("Training-set-size sensitivity (held-out test split, stratified)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    logger.info("Saved plot to %s", out_path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--include-lstm",
        action="store_true",
        help="Also run the LSTM curve (slower — ~10 min on CPU).",
    )
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = _load_split_features()

    runs = run_classical_sensitivity(data)

    if args.include_lstm:
        splits = json.loads(SPLITS_PATH.read_text())
        labels = splits["labels"]["is_anomaly"]
        runs.extend(run_lstm_sensitivity(splits["train"], splits["test"], labels))

    out_json = OUTPUT_DIR / "train_size.json"
    out_plot = OUTPUT_DIR / "train_size.png"
    out_json.write_text(
        json.dumps(
            {
                "fractions": TRAIN_FRACTIONS,
                "seeds": SEEDS,
                "n_test": int(len(data["y_test"])),
                "n_test_positive": int(data["y_test"].sum()),
                "runs": runs,
            },
            indent=2,
        )
    )
    logger.info("Saved raw results to %s", out_json)

    _plot(runs, out_plot)


if __name__ == "__main__":
    main()
