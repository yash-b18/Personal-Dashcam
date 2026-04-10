"""
Dataset ingestion script — scans Cloudflare R2 and populates the clips table.

Workflow:
  1. List all MP4 objects under the front and rear R2 prefixes
  2. Pair front/rear clips by matching timestamps in filenames
  3. For each pair, fetch video duration via ffprobe
  4. Upsert Clip records into PostgreSQL (idempotent — safe to re-run)
  5. Print a summary of new, updated, and unmatched clips

Usage:
    python scripts/make_dataset.py
    python scripts/make_dataset.py --dry-run        # preview without DB writes
    python scripts/make_dataset.py --limit 50       # ingest first 50 pairs
    python scripts/make_dataset.py --no-metadata    # skip ffprobe (faster)
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.config import get_settings
from api.database import SessionLocal
from api.models.db_models import Clip, ProcessingStatus
from api.storage.clip_pairer import ClipPair, pair_clips
from api.storage.r2_client import R2Client
from api.video.frame_extractor import FrameExtractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Ingest dashcam clip pairs from Cloudflare R2 into the database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be ingested without writing to the database",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of clip pairs to ingest (useful for testing)",
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Skip ffprobe metadata extraction (much faster, omits duration/fps)",
    )
    return parser.parse_args()


def fetch_video_duration(r2_client: R2Client, key: str) -> float | None:
    """
    Download a clip and extract its duration via ffprobe.

    Args:
        r2_client: Authenticated R2 client.
        key: R2 object key for the video.

    Returns:
        Duration in seconds, or None if extraction fails.
    """
    tmp_path = None
    try:
        tmp_path = r2_client.download_to_temp(key)
        meta = FrameExtractor(tmp_path).get_metadata()
        return meta.duration_seconds
    except Exception as exc:
        logger.warning("Could not get duration for %s: %s", key, exc)
        return None
    finally:
        if tmp_path and Path(tmp_path).exists():
            Path(tmp_path).unlink()


def ingest_pairs(
    pairs: list[ClipPair],
    r2_client: R2Client,
    db,
    dry_run: bool,
    fetch_metadata: bool,
) -> dict[str, int]:
    """
    Upsert ClipPair records into the database.

    Clips are identified by filename_prefix. Existing clips are updated;
    new clips are inserted with PENDING status.

    Args:
        pairs: Matched ClipPair list from pair_clips().
        r2_client: Authenticated R2 client for duration fetching.
        db: SQLAlchemy session.
        dry_run: If True, no DB writes are made.
        fetch_metadata: If True, download each clip to get duration.

    Returns:
        Dict with counts: {inserted, updated}.
    """
    counts = {"inserted": 0, "updated": 0}

    for pair in tqdm(pairs, desc="Ingesting clips", unit="pair"):
        existing = db.query(Clip).filter_by(filename_prefix=pair.filename_prefix).first()

        duration = None
        if fetch_metadata:
            duration = fetch_video_duration(r2_client, pair.front_key)

        if dry_run:
            action = "UPDATE" if existing else "INSERT"
            logger.info("[DRY RUN] %s: %s", action, pair.filename_prefix)
            counts["inserted" if not existing else "updated"] += 1
            continue

        if existing:
            existing.r2_key_front = pair.front_key
            existing.r2_key_rear = pair.rear_key
            existing.file_size_bytes_front = pair.front_size_bytes
            existing.file_size_bytes_rear = pair.rear_size_bytes
            if duration is not None:
                existing.duration_seconds = duration
            if pair.timestamp:
                existing.recorded_at = pair.timestamp
            counts["updated"] += 1
        else:
            db.add(Clip(
                r2_key_front=pair.front_key,
                r2_key_rear=pair.rear_key,
                filename_prefix=pair.filename_prefix,
                duration_seconds=duration,
                file_size_bytes_front=pair.front_size_bytes,
                file_size_bytes_rear=pair.rear_size_bytes,
                recorded_at=pair.timestamp,
                processing_status=ProcessingStatus.PENDING,
            ))
            counts["inserted"] += 1

    if not dry_run:
        db.commit()

    return counts


def main() -> None:
    """Run the R2 ingestion pipeline."""
    args = parse_args()
    settings = get_settings()
    r2_client = R2Client(settings)

    logger.info("Listing front clips: %s", settings.r2_front_prefix)
    front_objects = r2_client.list_front_clips()
    logger.info("Found %d front clips", len(front_objects))

    logger.info("Listing rear clips: %s", settings.r2_rear_prefix)
    rear_objects = r2_client.list_rear_clips()
    logger.info("Found %d rear clips", len(rear_objects))

    result = pair_clips(front_objects, rear_objects)
    pairs = result.pairs[:args.limit] if args.limit else result.pairs

    logger.info(
        "Pairing: %d pairs | %d unmatched front | %d unmatched rear",
        len(pairs), len(result.unmatched_front), len(result.unmatched_rear),
    )

    if not pairs:
        logger.warning("No clip pairs found. Check R2 folder structure and filename format.")
        sys.exit(1)

    db = SessionLocal()
    try:
        counts = ingest_pairs(
            pairs=pairs,
            r2_client=r2_client,
            db=db,
            dry_run=args.dry_run,
            fetch_metadata=not args.no_metadata,
        )
    finally:
        db.close()

    print("\n── Ingestion Summary ─────────────────────")
    print(f"  Pairs found:      {len(pairs)}")
    print(f"  Inserted:         {counts['inserted']}")
    print(f"  Updated:          {counts['updated']}")
    print(f"  Unmatched front:  {len(result.unmatched_front)}")
    print(f"  Unmatched rear:   {len(result.unmatched_rear)}")
    if args.dry_run:
        print("  [DRY RUN — no changes written]")
    print("──────────────────────────────────────────")


if __name__ == "__main__":
    main()
