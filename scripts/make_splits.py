"""
Create a locked train/test split for model evaluation.

Stratifies on the binary `is_anomaly` label so both splits see the same anomaly
rate. Saves the clip-id lists to data/splits.json so every model variant
(classical-19, classical+YOLO, LSTM+YOLO) is trained and evaluated on exactly
the same partitions.

Reproducibility:
  - random_state=42 (persisted into splits.json)
  - Split is only regenerated when --force is passed; otherwise the existing
    file is preserved so metric comparisons stay apples-to-apples.

Usage:
    python scripts/make_splits.py                    # create or verify
    python scripts/make_splits.py --force            # rebuild
    python scripts/make_splits.py --test-size 0.2    # override default 0.2
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

SPLITS_PATH = Path("data/splits.json")
DEFAULT_TEST_SIZE = 0.2
DEFAULT_RANDOM_STATE = 42


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--test-size", type=float, default=DEFAULT_TEST_SIZE)
    p.add_argument("--random-state", type=int, default=DEFAULT_RANDOM_STATE)
    p.add_argument(
        "--force", action="store_true", help="Overwrite existing splits.json"
    )
    return p.parse_args()


def build_splits(test_size: float, random_state: int) -> dict:
    """Pull labeled clips from the DB and produce a stratified split."""
    from api.database import SessionLocal
    from api.models.db_models import Clip, Label

    db = SessionLocal()
    try:
        rows = db.query(Clip, Label).join(Label, Clip.id == Label.clip_id).all()
    finally:
        db.close()

    if not rows:
        raise RuntimeError("No labeled clips in DB. Label via admin UI first.")

    clip_ids = [str(c.id) for c, _ in rows]
    is_anom = [int(lbl.is_anomaly) for _, lbl in rows]
    type_lists = [lbl.anomaly_types or [] for _, lbl in rows]

    train_ids, test_ids, train_y, test_y = train_test_split(
        clip_ids,
        is_anom,
        test_size=test_size,
        stratify=is_anom,
        random_state=random_state,
    )

    # Also emit per-clip type lists keyed by id, so training scripts don't have
    # to re-query the DB for labels.
    type_map = {cid: tl for cid, tl in zip(clip_ids, type_lists)}

    return {
        "random_state": random_state,
        "test_size": test_size,
        "train": train_ids,
        "test": test_ids,
        "labels": {
            "is_anomaly": dict(zip(clip_ids, is_anom)),
            "anomaly_types": type_map,
        },
        "counts": {
            "n_total": len(clip_ids),
            "n_train": len(train_ids),
            "n_test": len(test_ids),
            "n_train_positive": int(sum(train_y)),
            "n_test_positive": int(sum(test_y)),
        },
    }


def main() -> None:
    args = parse_args()

    if SPLITS_PATH.exists() and not args.force:
        existing = json.loads(SPLITS_PATH.read_text())
        logger.info("Split already exists at %s (use --force to rebuild).", SPLITS_PATH)
        logger.info("  counts: %s", existing.get("counts"))
        return

    splits = build_splits(args.test_size, args.random_state)
    SPLITS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPLITS_PATH.write_text(json.dumps(splits, indent=2))

    c = splits["counts"]
    logger.info("Saved %s", SPLITS_PATH)
    logger.info("  total:    %d clips", c["n_total"])
    logger.info("  train:    %d (%d positive)", c["n_train"], c["n_train_positive"])
    logger.info("  test:     %d (%d positive)", c["n_test"], c["n_test_positive"])


if __name__ == "__main__":
    main()
