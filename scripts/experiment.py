"""
Training Set Size Sensitivity Analysis.

Motivation: DashcamIQ starts with zero labels and accumulates them through the
admin labeling interface. This experiment answers:
  "How many labeled clips do we need before each model becomes reliable?"

Methodology:
  - Load all available labeled clip features (classical 19-dim + DL sequences)
  - Train each model at 10%, 25%, 50%, 75%, and 100% of labeled data
  - At each split: stratified sample → train → evaluate on a fixed held-out test set
  - Metrics collected: F1, AUC-ROC, Precision, Recall
  - Repeat each split N_REPEATS times (different random seeds) to get error bars
  - Save plots to data/outputs/experiment/ and results to experiment_results.json

Usage:
    python scripts/experiment.py                         # both models
    python scripts/experiment.py --model classical       # classical only
    python scripts/experiment.py --model deep_learning   # DL only
    python scripts/experiment.py --n-repeats 5           # fewer repeats (faster)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

TRAIN_FRACTIONS = [0.10, 0.25, 0.50, 0.75, 1.00]
N_REPEATS = 3           # repeats per fraction (averaged for error bars)
TEST_SPLIT = 0.20       # held-out test fraction (constant across all experiments)
OUTPUT_DIR = Path("data/outputs/experiment")

CLASSICAL_FEATURES_DIR = Path("data/processed")
DL_FEATURES_DIR = Path("data/processed")


# ── Classical ML experiment ────────────────────────────────────────────────────

def run_classical_experiment(
    features_dir: Path = CLASSICAL_FEATURES_DIR,
    n_repeats: int = N_REPEATS,
) -> dict:
    """
    Training set size sensitivity for the XGBoost classical model.

    Loads pre-extracted 19-dim features from .npz files + DB labels.
    Trains XGBoost at each fraction, evaluates on a fixed test set.

    Returns:
        dict mapping fraction → list of metric dicts (one per repeat).
    """
    import xgboost as xgb
    from sklearn.metrics import f1_score, roc_auc_score, precision_score, recall_score
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler

    from scripts.build_features import feature_names, load_features
    from api.database import SessionLocal
    from api.models.db_models import Clip, Label

    db = SessionLocal()
    try:
        labeled = db.query(Clip, Label).join(Label, Clip.id == Label.clip_id).all()
    finally:
        db.close()

    if not labeled:
        logger.error("No labeled clips found. Label clips via the admin UI first.")
        return {}

    names = feature_names()
    X_all, y_all = [], []
    for clip, label in labeled:
        feat = load_features(str(clip.id), features_dir=features_dir)
        if feat is None:
            logger.warning("No classical features for %s — skipping", clip.filename_prefix)
            continue
        X_all.append(feat)
        y_all.append(int(label.is_anomaly))

    if len(X_all) < 10:
        logger.error(
            "Only %d clips with features — need at least 10 to run experiment.", len(X_all)
        )
        return {}

    X_all = np.stack(X_all, axis=0)
    y_all = np.array(y_all, dtype=np.int32)
    logger.info(
        "Classical experiment: %d clips total (%d anomaly, %d normal)",
        len(y_all), y_all.sum(), (y_all == 0).sum(),
    )

    # Fixed test set (same across all fractions and repeats)
    X_trainval, X_test, y_trainval, y_test = train_test_split(
        X_all, y_all, test_size=TEST_SPLIT, stratify=y_all, random_state=0,
    )

    results: dict[float, list[dict]] = {}

    for frac in TRAIN_FRACTIONS:
        results[frac] = []
        for repeat in range(n_repeats):
            seed = repeat * 100 + int(frac * 100)

            # Subsample training set at this fraction
            if frac < 1.0:
                n_sample = max(2, int(len(y_trainval) * frac))
                idx = _stratified_sample(y_trainval, n_sample, seed)
                X_tr = X_trainval[idx]
                y_tr = y_trainval[idx]
            else:
                X_tr, y_tr = X_trainval, y_trainval

            pos = y_tr.sum()
            neg = (y_tr == 0).sum()
            scale_pw = float(neg / max(pos, 1))

            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_test_s = scaler.transform(X_test)

            model = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                scale_pos_weight=scale_pw,
                eval_metric="logloss",
                random_state=seed,
                verbosity=0,
            )
            model.fit(X_tr_s, y_tr)

            y_prob = model.predict_proba(X_test_s)[:, 1]
            y_pred = (y_prob >= 0.5).astype(int)

            metrics = _compute_metrics(y_test, y_pred, y_prob)
            metrics["n_train"] = int(len(y_tr))
            metrics["n_anomaly_train"] = int(y_tr.sum())
            results[frac].append(metrics)

            logger.info(
                "  Classical frac=%.2f repeat=%d | n_train=%d F1=%.3f AUC=%.3f",
                frac, repeat, len(y_tr), metrics["f1"], metrics["auc_roc"],
            )

    return results


# ── Deep Learning experiment ───────────────────────────────────────────────────

def run_dl_experiment(
    features_dir: Path = DL_FEATURES_DIR,
    n_repeats: int = N_REPEATS,
) -> dict:
    """
    Training set size sensitivity for the bidirectional LSTM model.

    Loads pre-extracted DL feature sequences from .npz files + DB labels.
    Trains LSTM at each fraction (20 epochs max, early stopping patience=5),
    evaluates on a fixed held-out test set.

    Returns:
        dict mapping fraction → list of metric dicts (one per repeat).
    """
    import torch
    from sklearn.metrics import f1_score, roc_auc_score, precision_score, recall_score
    from sklearn.model_selection import train_test_split
    from torch.utils.data import DataLoader, TensorDataset
    import torch.nn as nn

    from scripts.models.deep_learning import build_lstm_model, DECISION_THRESHOLD
    from api.video.sequence_builder import load_dl_features
    from api.database import SessionLocal
    from api.models.db_models import Clip, Label

    db = SessionLocal()
    try:
        labeled = db.query(Clip, Label).join(Label, Clip.id == Label.clip_id).all()
    finally:
        db.close()

    if not labeled:
        logger.error("No labeled clips found. Label clips via the admin UI first.")
        return {}

    # Build clip-level arrays (clip_id → (sequences, label))
    clip_X, clip_y = [], []
    for clip, label in labeled:
        seqs = load_dl_features(str(clip.id), features_dir)
        if seqs is None or len(seqs) == 0:
            logger.warning("No DL features for %s — skipping", clip.filename_prefix)
            continue
        clip_X.append(seqs)
        clip_y.append(int(label.is_anomaly))

    if len(clip_X) < 10:
        logger.error(
            "Only %d clips with DL features — need at least 10.", len(clip_X)
        )
        return {}

    clip_y_arr = np.array(clip_y, dtype=np.int32)
    logger.info(
        "DL experiment: %d clips total (%d anomaly, %d normal)",
        len(clip_y_arr), clip_y_arr.sum(), (clip_y_arr == 0).sum(),
    )

    # Fixed clip-level split
    n_clips = len(clip_y_arr)
    clip_idx = np.arange(n_clips)
    train_val_idx, test_idx = train_test_split(
        clip_idx, test_size=TEST_SPLIT, stratify=clip_y_arr, random_state=0,
    )

    # Expand test set into window-level arrays
    X_test, y_test = _expand_windows(clip_X, clip_y_arr, test_idx)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    results: dict[float, list[dict]] = {}

    for frac in TRAIN_FRACTIONS:
        results[frac] = []
        for repeat in range(n_repeats):
            seed = repeat * 100 + int(frac * 100)
            torch.manual_seed(seed)
            np.random.seed(seed)

            # Clip-level subsample
            if frac < 1.0:
                n_sample = max(2, int(len(train_val_idx) * frac))
                tv_labels = clip_y_arr[train_val_idx]
                sub_idx = _stratified_sample(tv_labels, n_sample, seed)
                selected = train_val_idx[sub_idx]
            else:
                selected = train_val_idx

            X_tr, y_tr = _expand_windows(clip_X, clip_y_arr, selected)

            pos = y_tr.sum()
            neg = len(y_tr) - pos
            pos_weight = torch.tensor([neg / max(pos, 1)], dtype=torch.float32).to(device)

            model = build_lstm_model().to(device)
            criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
            optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)

            # Quick training loop (fewer epochs for speed in experiment)
            train_ds = TensorDataset(
                torch.tensor(X_tr, dtype=torch.float32),
                torch.tensor(y_tr, dtype=torch.float32),
            )
            train_loader = DataLoader(train_ds, batch_size=32, shuffle=True)

            model.train()
            for _ in range(20):   # 20 epochs max for experiment speed
                for Xb, yb in train_loader:
                    Xb, yb = Xb.to(device), yb.to(device)
                    optimizer.zero_grad()
                    loss = criterion(model(Xb), yb)
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()

            # Evaluate on test set
            model.eval()
            with torch.no_grad():
                Xt = torch.tensor(X_test, dtype=torch.float32).to(device)
                probs = torch.sigmoid(model(Xt)).cpu().numpy()

            y_pred = (probs >= DECISION_THRESHOLD).astype(int)
            metrics = _compute_metrics(y_test, y_pred, probs)
            metrics["n_train_clips"] = int(len(selected))
            metrics["n_train_windows"] = int(len(y_tr))
            results[frac].append(metrics)

            logger.info(
                "  DL frac=%.2f repeat=%d | n_clips=%d F1=%.3f AUC=%.3f",
                frac, repeat, len(selected), metrics["f1"], metrics["auc_roc"],
            )

    return results


# ── Helpers ────────────────────────────────────────────────────────────────────

def _stratified_sample(y: np.ndarray, n: int, seed: int) -> np.ndarray:
    """
    Return indices of a stratified subsample of size n from y.

    Ensures at least one positive and one negative example if possible.
    """
    rng = np.random.default_rng(seed)
    pos_idx = np.where(y == 1)[0]
    neg_idx = np.where(y == 0)[0]

    # proportion of positives
    n_pos = max(1, round(n * len(pos_idx) / max(len(y), 1)))
    n_neg = max(1, n - n_pos)
    n_pos = min(n_pos, len(pos_idx))
    n_neg = min(n_neg, len(neg_idx))

    chosen = np.concatenate([
        rng.choice(pos_idx, size=n_pos, replace=False),
        rng.choice(neg_idx, size=n_neg, replace=False),
    ])
    return chosen


def _expand_windows(
    clip_X: list[np.ndarray],
    clip_y: np.ndarray,
    indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Expand clip-level (sequences, label) into window-level (X, y) arrays.

    All windows of an anomalous clip receive label 1.
    """
    X_parts, y_parts = [], []
    for idx in indices:
        seqs = clip_X[idx]          # (n_windows, seq_len, feat_dim)
        label = clip_y[idx]
        X_parts.append(seqs)
        y_parts.extend([label] * len(seqs))
    return np.concatenate(X_parts, axis=0), np.array(y_parts, dtype=np.float32)


def _compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: np.ndarray,
) -> dict:
    """Return a dict with F1, AUC-ROC, precision, recall."""
    from sklearn.metrics import f1_score, roc_auc_score, precision_score, recall_score

    return {
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "auc_roc": float(
            roc_auc_score(y_true, y_prob) if len(set(y_true.tolist())) > 1 else 0.5
        ),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
    }


# ── Aggregation + plotting ─────────────────────────────────────────────────────

def aggregate_results(results: dict[float, list[dict]]) -> dict:
    """
    Average metrics over repeats and compute std dev.

    Returns:
        {fraction: {metric: {mean, std}}}
    """
    aggregated = {}
    for frac, repeat_list in results.items():
        aggregated[frac] = {}
        for metric in ["f1", "auc_roc", "precision", "recall"]:
            values = [r[metric] for r in repeat_list]
            aggregated[frac][metric] = {
                "mean": float(np.mean(values)),
                "std": float(np.std(values)),
            }
    return aggregated


def plot_results(
    classical_agg: dict | None,
    dl_agg: dict | None,
    output_dir: Path,
) -> None:
    """
    Plot learning curves (F1 and AUC-ROC vs training fraction) with error bands.

    Saves:
        experiment_f1.png
        experiment_auc.png
        experiment_combined.png
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not installed — skipping plots. pip install matplotlib")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    fracs_pct = [int(f * 100) for f in TRAIN_FRACTIONS]

    def _extract(agg: dict, metric: str):
        means = [agg[f][metric]["mean"] for f in TRAIN_FRACTIONS]
        stds = [agg[f][metric]["std"] for f in TRAIN_FRACTIONS]
        return np.array(means), np.array(stds)

    for metric, ylabel, filename in [
        ("f1", "F1 Score", "experiment_f1.png"),
        ("auc_roc", "AUC-ROC", "experiment_auc.png"),
    ]:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.set_xlabel("Training Set Size (%)", fontsize=13)
        ax.set_ylabel(ylabel, fontsize=13)
        ax.set_title(f"Training Set Size Sensitivity — {ylabel}", fontsize=14)
        ax.set_xticks(fracs_pct)
        ax.set_ylim(0, 1.05)
        ax.grid(True, alpha=0.3)

        if classical_agg:
            means, stds = _extract(classical_agg, metric)
            ax.plot(fracs_pct, means, "o-", color="#2563EB", label="Classical (XGBoost)", lw=2)
            ax.fill_between(fracs_pct, means - stds, means + stds, alpha=0.15, color="#2563EB")

        if dl_agg:
            means, stds = _extract(dl_agg, metric)
            ax.plot(fracs_pct, means, "s-", color="#DC2626", label="Deep Learning (LSTM)", lw=2)
            ax.fill_between(fracs_pct, means - stds, means + stds, alpha=0.15, color="#DC2626")

        ax.legend(fontsize=11)
        fig.tight_layout()
        fig.savefig(str(output_dir / filename), dpi=150)
        plt.close(fig)
        logger.info("Saved plot: %s", output_dir / filename)

    # Combined 2-panel figure
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, (metric, ylabel) in zip(axes, [("f1", "F1 Score"), ("auc_roc", "AUC-ROC")]):
        ax.set_xlabel("Training Set Size (%)", fontsize=12)
        ax.set_ylabel(ylabel, fontsize=12)
        ax.set_title(ylabel, fontsize=13)
        ax.set_xticks(fracs_pct)
        ax.set_ylim(0, 1.05)
        ax.grid(True, alpha=0.3)

        if classical_agg:
            means, stds = _extract(classical_agg, metric)
            ax.plot(fracs_pct, means, "o-", color="#2563EB", label="Classical (XGBoost)", lw=2)
            ax.fill_between(fracs_pct, means - stds, means + stds, alpha=0.15, color="#2563EB")

        if dl_agg:
            means, stds = _extract(dl_agg, metric)
            ax.plot(fracs_pct, means, "s-", color="#DC2626", label="Deep Learning (LSTM)", lw=2)
            ax.fill_between(fracs_pct, means - stds, means + stds, alpha=0.15, color="#DC2626")

        ax.legend(fontsize=10)

    fig.suptitle(
        "DashcamIQ — Training Set Size Sensitivity Analysis",
        fontsize=15, fontweight="bold",
    )
    fig.tight_layout()
    combined_path = output_dir / "experiment_combined.png"
    fig.savefig(str(combined_path), dpi=150)
    plt.close(fig)
    logger.info("Saved combined plot: %s", combined_path)


def print_summary(
    label: str,
    agg: dict,
) -> None:
    """Print a formatted summary table to stdout."""
    print(f"\n── {label} ─────────────────────────────────────────────")
    print(f"  {'Fraction':>10}  {'N Train':>8}  {'F1':>8}  {'AUC-ROC':>8}  {'Precision':>10}  {'Recall':>8}")
    for frac in TRAIN_FRACTIONS:
        row = agg[frac]
        print(
            f"  {frac*100:>9.0f}%"
            f"  {'—':>8}"
            f"  {row['f1']['mean']:>7.3f}±{row['f1']['std']:.2f}"
            f"  {row['auc_roc']['mean']:>7.3f}±{row['auc_roc']['std']:.2f}"
            f"  {row['precision']['mean']:>9.3f}±{row['precision']['std']:.2f}"
            f"  {row['recall']['mean']:>7.3f}±{row['recall']['std']:.2f}"
        )


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Training set size sensitivity analysis for DashcamIQ models"
    )
    parser.add_argument(
        "--model",
        choices=["classical", "deep_learning", "both"],
        default="both",
        help="Which model(s) to evaluate (default: both)",
    )
    parser.add_argument(
        "--n-repeats", type=int, default=N_REPEATS,
        help=f"Repeats per fraction for error bars (default: {N_REPEATS})",
    )
    parser.add_argument(
        "--features-dir", type=str, default="data/processed",
        help="Directory containing extracted feature .npz files",
    )
    parser.add_argument(
        "--output-dir", type=str, default=str(OUTPUT_DIR),
        help="Where to save plots and results JSON",
    )
    return parser.parse_args()


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    args = parse_args()
    features_dir = Path(args.features_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    classical_raw, dl_raw = None, None
    classical_agg, dl_agg = None, None

    if args.model in ("classical", "both"):
        logger.info("=== Classical ML experiment ===")
        classical_raw = run_classical_experiment(
            features_dir=features_dir,
            n_repeats=args.n_repeats,
        )
        if classical_raw:
            classical_agg = aggregate_results(classical_raw)
            print_summary("Classical ML (XGBoost)", classical_agg)

    if args.model in ("deep_learning", "both"):
        logger.info("=== Deep Learning LSTM experiment ===")
        dl_raw = run_dl_experiment(
            features_dir=features_dir,
            n_repeats=args.n_repeats,
        )
        if dl_raw:
            dl_agg = aggregate_results(dl_raw)
            print_summary("Deep Learning (LSTM)", dl_agg)

    # Save JSON results
    output = {
        "train_fractions": TRAIN_FRACTIONS,
        "n_repeats": args.n_repeats,
        "test_split": TEST_SPLIT,
    }
    if classical_agg:
        output["classical"] = {str(k): v for k, v in classical_agg.items()}
    if dl_agg:
        output["deep_learning"] = {str(k): v for k, v in dl_agg.items()}

    results_path = output_dir / "experiment_results.json"
    results_path.write_text(json.dumps(output, indent=2))
    logger.info("Saved results: %s", results_path)

    plot_results(classical_agg, dl_agg, output_dir)

    print(f"\nResults saved to: {results_path}")
    print(f"Plots saved to:   {output_dir}/")

    # Recommendation
    _print_recommendation(classical_agg, dl_agg)


def _print_recommendation(classical_agg: dict | None, dl_agg: dict | None) -> None:
    """Print a data-driven recommendation on minimum labeling effort."""
    print("\n── Recommendation ────────────────────────────────────────────")
    threshold = 0.70   # F1 threshold for "reliable"

    for label, agg in [("Classical ML", classical_agg), ("Deep Learning", dl_agg)]:
        if agg is None:
            continue
        recommended_frac = None
        for frac in TRAIN_FRACTIONS:
            if agg[frac]["f1"]["mean"] >= threshold:
                recommended_frac = frac
                break
        if recommended_frac is not None:
            print(
                f"  {label}: reaches F1 ≥ {threshold:.0%} at {recommended_frac*100:.0f}% "
                f"of labeled data (F1={agg[recommended_frac]['f1']['mean']:.3f})"
            )
        else:
            best_frac = max(TRAIN_FRACTIONS, key=lambda f: agg[f]["f1"]["mean"])
            print(
                f"  {label}: best F1={agg[best_frac]['f1']['mean']:.3f} at 100% — "
                f"may need more labeled data to reach F1 ≥ {threshold:.0%}"
            )


if __name__ == "__main__":
    main()
