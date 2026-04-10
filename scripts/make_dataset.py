"""
Dataset ingestion script — pulls clip metadata from Cloudflare R2.

Scans the R2 bucket for front/rear clip pairs, extracts metadata
(duration, file size, recorded_at from filename), and writes records
to the PostgreSQL clips table.

Implemented in: feature/data-pipeline

Usage:
    python scripts/make_dataset.py [--dry-run] [--limit N]
"""

import argparse


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Ingest dashcam clips from Cloudflare R2")
    parser.add_argument("--dry-run", action="store_true", help="Print clips without writing to DB")
    parser.add_argument("--limit", type=int, default=None, help="Max number of clips to ingest")
    return parser.parse_args()


def main() -> None:
    """Run R2 ingestion. Implemented in feature/data-pipeline."""
    args = parse_args()
    raise NotImplementedError(
        "Implemented in feature/data-pipeline. "
        f"Args: dry_run={args.dry_run}, limit={args.limit}"
    )


if __name__ == "__main__":
    main()
