"""
Pairs front and rear dashcam clips by matching timestamps in filenames.

Dashcam files are named with an embedded datetime (e.g. 20240101_120000.mp4).
This module extracts that timestamp from each filename and pairs front/rear
clips whose timestamps are within a configurable tolerance window.

Matching strategy:
  1. Parse timestamp from filename using a set of common dashcam patterns
  2. Build a sorted index of (timestamp, key) for each camera
  3. For each front clip, binary-search for the nearest rear timestamp
  4. Accept the pair if |front_ts - rear_ts| <= MATCH_TOLERANCE_SECONDS
  5. Unmatched clips on either side are reported as warnings

Typical dashcam filename formats handled:
  - 20240101_120000.mp4
  - 2024_01_01_12_00_00.mp4
  - dashcam_20240101120000.mp4
  - REC_2024-01-01_12-00-00.mp4
"""

import bisect
import logging
import re
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# Maximum seconds difference to consider a front/rear pair valid
MATCH_TOLERANCE_SECONDS = 5

# Ordered list of (regex, strptime_format) patterns tried in sequence
_TIMESTAMP_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})[-_](\d{2})[-_]?(\d{2})[-_]?(\d{2})"
        ),
        "%Y%m%d%H%M%S",
    ),
    (re.compile(r"(\d{8})_(\d{6})"), "%Y%m%d_%H%M%S"),
    (re.compile(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})"), "%Y-%m-%d_%H-%M-%S"),
]


@dataclass
class ClipPair:
    """A matched pair of front and rear camera clips."""

    front_key: str
    rear_key: str
    timestamp: datetime
    filename_prefix: str  # shared base name used as human-readable ID
    front_size_bytes: int
    rear_size_bytes: int


@dataclass
class PairingResult:
    """Result of pairing all front and rear objects from R2."""

    pairs: list[ClipPair]
    unmatched_front: list[str]  # R2 keys with no rear match
    unmatched_rear: list[str]  # R2 keys with no front match


def extract_timestamp(key: str) -> datetime | None:
    """
    Parse a datetime from an R2 object key using common dashcam patterns.

    Tries each pattern in _TIMESTAMP_PATTERNS in order and returns the
    first successful parse. Returns None if no pattern matches.

    Args:
        key: Full R2 object key (e.g. "dashcam/front/20240101_120000.mp4").

    Returns:
        Parsed datetime or None.
    """
    filename = key.split("/")[-1]

    # Pattern 1: YYYYMMDD_HHMMSS or YYYY_MM_DD_HH_MM_SS variants
    m = re.search(
        r"(\d{4})[_-]?(\d{2})[_-]?(\d{2})[_-](\d{2})[_-]?(\d{2})[_-]?(\d{2})", filename
    )
    if m:
        try:
            return datetime(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
                int(m.group(5)),
                int(m.group(6)),
            )
        except ValueError:
            pass

    # Pattern 2: YYYY-MM-DD_HH-MM-SS
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[_T](\d{2})-(\d{2})-(\d{2})", filename)
    if m:
        try:
            return datetime(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
                int(m.group(5)),
                int(m.group(6)),
            )
        except ValueError:
            pass

    logger.warning("Could not parse timestamp from filename: %s", filename)
    return None


def _filename_prefix(key: str) -> str:
    """
    Derive a human-readable clip identifier from an R2 key.

    Strips the folder prefix and file extension to produce a bare name
    like '20240101_120000' that serves as the clip's display name.

    Args:
        key: Full R2 object key.

    Returns:
        Bare filename without extension (e.g. '20240101_120000').
    """
    return Path(key.split("/")[-1]).stem if "." in key else key.split("/")[-1]


# Avoid importing Path at module level since it's only used here
from pathlib import Path  # noqa: E402


def pair_clips(
    front_objects: list[dict],
    rear_objects: list[dict],
    tolerance_seconds: int = MATCH_TOLERANCE_SECONDS,
) -> PairingResult:
    """
    Match front and rear R2 objects into ClipPair instances.

    Uses binary search on sorted timestamp lists for O(n log n) matching.
    Objects whose filenames contain no parseable timestamp are skipped
    and logged as warnings.

    Args:
        front_objects: List of R2 object metadata dicts from list_front_clips().
        rear_objects:  List of R2 object metadata dicts from list_rear_clips().
        tolerance_seconds: Max allowed timestamp difference to form a pair.

    Returns:
        PairingResult with matched pairs and lists of unmatched keys.
    """

    def _build_index(objects: list[dict]) -> list[tuple[datetime, dict]]:
        indexed = []
        for obj in objects:
            ts = extract_timestamp(obj["Key"])
            if ts is not None:
                indexed.append((ts, obj))
        return sorted(indexed, key=lambda x: x[0])

    front_index = _build_index(front_objects)
    rear_index = _build_index(rear_objects)

    if not front_index:
        logger.warning("No front clips with parseable timestamps found")
    if not rear_index:
        logger.warning("No rear clips with parseable timestamps found")

    rear_timestamps = [ts for ts, _ in rear_index]
    used_rear: set[int] = set()

    pairs: list[ClipPair] = []
    unmatched_front: list[str] = []

    for front_ts, front_obj in front_index:
        # Binary search for nearest rear timestamp
        pos = bisect.bisect_left(rear_timestamps, front_ts)
        best_idx: int | None = None
        best_delta = float("inf")

        for candidate in [pos - 1, pos]:
            if 0 <= candidate < len(rear_timestamps) and candidate not in used_rear:
                delta = abs((rear_timestamps[candidate] - front_ts).total_seconds())
                if delta < best_delta:
                    best_delta = delta
                    best_idx = candidate

        if best_idx is not None and best_delta <= tolerance_seconds:
            _, rear_obj = rear_index[best_idx]
            used_rear.add(best_idx)
            pairs.append(
                ClipPair(
                    front_key=front_obj["Key"],
                    rear_key=rear_obj["Key"],
                    timestamp=front_ts,
                    filename_prefix=_filename_prefix(front_obj["Key"]),
                    front_size_bytes=front_obj.get("Size", 0),
                    rear_size_bytes=rear_obj.get("Size", 0),
                )
            )
        else:
            unmatched_front.append(front_obj["Key"])
            logger.warning("No rear match for front clip: %s", front_obj["Key"])

    unmatched_rear = [
        obj["Key"] for i, (_, obj) in enumerate(rear_index) if i not in used_rear
    ]
    for key in unmatched_rear:
        logger.warning("No front match for rear clip: %s", key)

    logger.info(
        "Pairing complete: %d pairs, %d unmatched front, %d unmatched rear",
        len(pairs),
        len(unmatched_front),
        len(unmatched_rear),
    )
    return PairingResult(
        pairs=pairs, unmatched_front=unmatched_front, unmatched_rear=unmatched_rear
    )
