"""
Model training and inference orchestration script.

Supports all three model tiers:
  - baseline     : Optical flow thresholding (no training, predict only)
  - classical    : XGBoost classifier                   (feature/classical-ml)
  - deep_learning: YOLOv8 + LSTM temporal classifier    (feature/deep-learning)

Usage:
    python scripts/model.py --predict --model baseline
    python scripts/model.py --predict --model baseline --video path/to/clip.mp4
    python scripts/model.py --evaluate --model baseline
    python scripts/model.py --train --model classical
    python scripts/model.py --train --model deep_learning
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Train or run inference for DashcamIQ models"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--train", action="store_true", help="Train the specified model")
    mode.add_argument("--predict", action="store_true", help="Run inference")
    mode.add_argument("--evaluate", action="store_true", help="Evaluate against labels")
    parser.add_argument(
        "--model",
        choices=["baseline", "classical", "deep_learning", "all"],
        default="baseline",
    )
    parser.add_argument(
        "--video", type=str, default=None, help="Single video file path"
    )
    parser.add_argument("--output", type=str, default="data/outputs")
    parser.add_argument(
        "--extract-dl-features",
        action="store_true",
        help="Extract DL feature sequences for all labeled clips (deep_learning only)",
    )
    parser.add_argument(
        "--features-dir",
        type=str,
        default="data/processed",
        help="Directory for feature .npz files",
    )
    parser.add_argument(
        "--arch",
        choices=["lstm", "transformer"],
        default="lstm",
        help="DL architecture: lstm or transformer (deep_learning only)",
    )
    return parser.parse_args()


def run_baseline_predict(video_path: str | None, output_dir: Path) -> None:
    """Run optical flow baseline on a single video or all pending DB clips."""
    from scripts.models.baseline import OpticalFlowBaseline

    detector = OpticalFlowBaseline()
    output_dir.mkdir(parents=True, exist_ok=True)

    if video_path:
        logger.info("Running baseline on: %s", video_path)
        result = detector.predict(video_path)
        output = {
            "clip_path": result.clip_path,
            "is_anomaly": result.is_anomaly,
            "severity": result.severity,
            "anomaly_windows": [
                {
                    "start_second": w.start_second,
                    "end_second": w.end_second,
                    "peak_magnitude": w.peak_magnitude,
                    "severity": w.severity,
                }
                for w in result.anomaly_windows
            ],
            "total_frames": result.total_frames,
            "fps": result.fps,
            "error": result.error,
        }
        out_file = output_dir / "baseline_single.json"
        out_file.write_text(json.dumps(output, indent=2))
        print(f"\nResult: anomaly={result.is_anomaly}  severity={result.severity:.3f}")
        print(f"Windows: {len(result.anomaly_windows)}")
        print(f"Saved:   {out_file}")
    else:
        from api.database import SessionLocal
        from api.models.db_models import Clip, ProcessingStatus
        from api.storage.r2_client import R2Client

        r2 = R2Client()
        db = SessionLocal()
        results = []
        try:
            clips = (
                db.query(Clip)
                .filter(Clip.processing_status == ProcessingStatus.PENDING)
                .all()
            )
            logger.info("Running baseline on %d pending clips", len(clips))
            for clip in clips:
                tmp_path = None
                try:
                    tmp_path = r2.download_to_temp(clip.r2_key_front)
                    result = detector.predict(tmp_path)
                    results.append(
                        {
                            "clip_id": str(clip.id),
                            "filename_prefix": clip.filename_prefix,
                            "is_anomaly": result.is_anomaly,
                            "severity": result.severity,
                            "window_count": len(result.anomaly_windows),
                            "error": result.error,
                        }
                    )
                    logger.info(
                        "[%s] anomaly=%s severity=%.2f",
                        clip.filename_prefix,
                        result.is_anomaly,
                        result.severity,
                    )
                except Exception as exc:
                    logger.error("Failed on %s: %s", clip.filename_prefix, exc)
                    results.append({"clip_id": str(clip.id), "error": str(exc)})
                finally:
                    if tmp_path and Path(tmp_path).exists():
                        Path(tmp_path).unlink()
        finally:
            db.close()

        out_file = output_dir / "baseline_results.json"
        out_file.write_text(json.dumps(results, indent=2))
        flagged = sum(1 for r in results if r.get("is_anomaly"))
        print(f"\nProcessed: {len(results)}  Flagged: {flagged}  Output: {out_file}")


def run_baseline_evaluate(output_dir: Path) -> None:
    """Evaluate baseline F1/AUC against human-labeled clips in DB."""
    from api.database import SessionLocal
    from api.models.db_models import Clip, Label
    from api.storage.r2_client import R2Client
    from scripts.models.baseline import OpticalFlowBaseline

    try:
        from sklearn.metrics import (
            classification_report,
            f1_score,
            precision_score,
            recall_score,
            roc_auc_score,
        )
    except ImportError:
        logger.error("scikit-learn not installed. Run: pip install scikit-learn")
        sys.exit(1)

    db = SessionLocal()
    r2 = R2Client()
    detector = OpticalFlowBaseline()
    output_dir.mkdir(parents=True, exist_ok=True)
    y_true, y_pred, y_scores = [], [], []

    try:
        labeled = db.query(Clip, Label).join(Label, Clip.id == Label.clip_id).all()
        if not labeled:
            logger.warning("No labeled clips found. Use the admin labeling UI first.")
            sys.exit(0)

        logger.info("Evaluating on %d labeled clips", len(labeled))
        for clip, label in labeled:
            tmp_path = None
            try:
                tmp_path = r2.download_to_temp(clip.r2_key_front)
                result = detector.predict(tmp_path)
                y_true.append(int(label.is_anomaly))
                y_pred.append(int(result.is_anomaly))
                y_scores.append(result.severity)
            except Exception as exc:
                logger.warning("Skipping %s: %s", clip.filename_prefix, exc)
            finally:
                if tmp_path and Path(tmp_path).exists():
                    Path(tmp_path).unlink()
    finally:
        db.close()

    if not y_true:
        logger.error("No clips could be evaluated.")
        sys.exit(1)

    metrics = {
        "model": "baseline",
        "n_samples": len(y_true),
        "n_positive": sum(y_true),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "auc_roc": roc_auc_score(y_true, y_scores) if len(set(y_true)) > 1 else None,
    }

    out_file = output_dir / "baseline_eval.json"
    out_file.write_text(json.dumps(metrics, indent=2))

    print("\n── Baseline Evaluation ───────────────────")
    for k, v in metrics.items():
        print(f"  {k:<28} {f'{v:.4f}' if isinstance(v, float) else v}")
    print(
        f"\nReport:\n{classification_report(y_true, y_pred, target_names=['normal','anomaly'])}"
    )
    print(f"Saved: {out_file}")


def run_classical_train(output_dir: Path) -> None:
    """Train XGBoost + Random Forest on labeled clip features."""
    from scripts.models.classical import ClassicalAnomalyClassifier

    clf = ClassicalAnomalyClassifier()
    logger.info("Training classical models (XGBoost + Random Forest)...")
    metrics = clf.train()
    print("\n── Classical ML Results ──────────────────")
    for k, v in metrics.items():
        print(f"  {k:<28} {f'{v:.4f}' if isinstance(v, float) else v}")
    print("\nModels saved to models/  |  Eval: data/outputs/classical_eval.json")


def run_classical_predict(clip_id: str | None, output_dir: Path) -> None:
    """Run XGBoost inference on a single clip or all DB clips."""
    from scripts.models.classical import ClassicalAnomalyClassifier

    output_dir.mkdir(parents=True, exist_ok=True)
    clf = ClassicalAnomalyClassifier()
    clf.load()

    if clip_id:
        result = clf.predict(clip_id)
        print(f"\nClip: {clip_id}")
        print(f"Anomaly:     {result.is_anomaly}")
        print(f"Probability: {result.anomaly_probability:.4f}")
    else:
        from api.database import SessionLocal
        from api.models.db_models import Clip

        db = SessionLocal()
        try:
            clip_ids = [str(c.id) for c in db.query(Clip).all()]
        finally:
            db.close()

        results = []
        for cid in clip_ids:
            try:
                r = clf.predict(cid)
                results.append(
                    {
                        "clip_id": cid,
                        "is_anomaly": r.is_anomaly,
                        "probability": r.anomaly_probability,
                    }
                )
            except FileNotFoundError:
                results.append({"clip_id": cid, "error": "no features"})

        out_file = output_dir / "classical_results.json"
        out_file.write_text(json.dumps(results, indent=2))
        flagged = sum(1 for r in results if r.get("is_anomaly"))
        print(f"\nProcessed: {len(results)}  Flagged: {flagged}  Output: {out_file}")


def run_dl_extract_features(video_path: str | None, features_dir: Path) -> None:
    """Extract DL feature sequences for a single video or all labeled DB clips."""
    from api.video.sequence_builder import SequenceBuilder, save_dl_features

    builder = SequenceBuilder()
    features_dir.mkdir(parents=True, exist_ok=True)

    if video_path:
        clip_id = Path(video_path).stem
        logger.info("Extracting DL features from %s", video_path)
        sequences = builder.build_sequences(video_path)
        out = save_dl_features(clip_id, sequences, output_dir=features_dir)
        print(f"Saved {len(sequences)} windows → {out}")
        return

    from api.database import SessionLocal
    from api.models.db_models import Clip, Label
    from api.storage.r2_client import R2Client

    r2 = R2Client()
    db = SessionLocal()
    try:
        labeled = db.query(Clip, Label).join(Label, Clip.id == Label.clip_id).all()
        logger.info("Extracting DL features for %d labeled clips", len(labeled))
        skipped = 0
        for clip, _label in labeled:
            out_path = features_dir / f"{clip.id}_dl_features.npz"
            if out_path.exists():
                skipped += 1
                continue
            tmp_path = None
            try:
                tmp_path = r2.download_to_temp(clip.r2_key_front)
                seqs = builder.build_sequences(tmp_path)
                save_dl_features(str(clip.id), seqs, output_dir=features_dir)
                logger.info("[%s] %d windows saved", clip.filename_prefix, len(seqs))
            except Exception as exc:
                logger.error("Failed on %s: %s", clip.filename_prefix, exc)
            finally:
                if tmp_path and Path(tmp_path).exists():
                    Path(tmp_path).unlink()
        print(f"Done. Skipped (already cached): {skipped}")
    finally:
        db.close()


def run_dl_train(features_dir: Path, output_dir: Path, arch: str = "lstm") -> None:
    """Train a DL model (LSTM or Transformer) on pre-extracted feature sequences."""
    from scripts.models.deep_learning import LSTMAnomalyClassifier

    output_dir.mkdir(parents=True, exist_ok=True)
    clf = LSTMAnomalyClassifier(arch=arch)
    logger.info("Training %s model on sequences in %s ...", arch.upper(), features_dir)
    history = clf.train(features_dir=features_dir)
    best_f1 = max(history["val_f1"]) if history["val_f1"] else 0.0
    best_auc = max(history["val_auc"]) if history["val_auc"] else 0.0
    print(f"\n── Deep Learning {arch.upper()} Results ────────────")
    print(f"  Best val F1:          {best_f1:.4f}")
    print(f"  Best val AUC-ROC:     {best_auc:.4f}")
    print(f"  Epochs trained:       {len(history['val_f1'])}")
    print(f"  Model saved:          {clf.model_path}")
    print(f"  Eval saved:           {clf.eval_output_path}")


def run_dl_predict(
    video_path: str | None, features_dir: Path, output_dir: Path
) -> None:
    """Run LSTM inference on a single video or all clips with pre-extracted features."""
    from scripts.models.deep_learning import LSTMAnomalyClassifier

    output_dir.mkdir(parents=True, exist_ok=True)
    clf = LSTMAnomalyClassifier()

    if video_path:
        clip_id = Path(video_path).stem
        logger.info("Running DL inference on: %s", video_path)
        result = clf.predict_from_video(video_path, clip_id)
        print(f"\nClip:         {clip_id}")
        print(f"Anomaly:      {result.is_anomaly}")
        print(f"Probability:  {result.anomaly_probability:.4f}")
        print(f"Windows:      {len(result.anomaly_windows)}")
        if result.error:
            print(f"Error:        {result.error}")
        return

    import json as _json

    feature_files = list(features_dir.glob("*_dl_features.npz"))
    if not feature_files:
        print("No DL feature files found. Run --extract-dl-features first.")
        return

    results = []
    for f in feature_files:
        clip_id = f.name.replace("_dl_features.npz", "")
        try:
            clf.load()
            r = clf.predict(clip_id, features_dir=features_dir)
            results.append(
                {
                    "clip_id": clip_id,
                    "is_anomaly": r.is_anomaly,
                    "probability": r.anomaly_probability,
                    "n_anomaly_windows": len(r.anomaly_windows),
                }
            )
        except Exception as exc:
            results.append({"clip_id": clip_id, "error": str(exc)})

    out_file = output_dir / "dl_results.json"
    out_file.write_text(_json.dumps(results, indent=2))
    flagged = sum(1 for r in results if r.get("is_anomaly"))
    print(f"\nProcessed: {len(results)}  Flagged: {flagged}  Output: {out_file}")


def main() -> None:
    """Dispatch to the appropriate model handler."""
    args = parse_args()
    output_dir = Path(args.output)

    if args.model == "baseline":
        if args.train:
            print("Baseline is rule-based — no training needed.")
            print(
                "Edit MAGNITUDE_THRESHOLD / VARIANCE_THRESHOLD in scripts/models/baseline.py."
            )
        elif args.predict:
            run_baseline_predict(args.video, output_dir)
        elif args.evaluate:
            run_baseline_evaluate(output_dir)

    elif args.model == "classical":
        if args.train:
            run_classical_train(output_dir)
        elif args.predict:
            run_classical_predict(args.video, output_dir)
        elif args.evaluate:
            logger.info(
                "Classical evaluation runs automatically during --train via k-fold CV."
            )
            run_classical_train(output_dir)

    elif args.model == "deep_learning":
        if args.extract_dl_features:
            run_dl_extract_features(args.video, Path(args.features_dir))
        elif args.train:
            run_dl_train(Path(args.features_dir), output_dir, arch=args.arch)
        elif args.predict:
            run_dl_predict(args.video, Path(args.features_dir), output_dir)
        elif args.evaluate:
            logger.info(
                "DL evaluation runs automatically during --train (loss/F1/AUC history saved)."
            )
            run_dl_train(Path(args.features_dir), output_dir, arch=args.arch)

    else:
        raise NotImplementedError(f"Unknown model: {args.model}")


if __name__ == "__main__":
    main()
