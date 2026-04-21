"""
Video frame extraction and metadata utilities.

Uses OpenCV for frame decoding and ffprobe (via ffmpeg-python) for
accurate duration and FPS metadata without decoding the entire video.

Design decisions:
  - Frames are returned as numpy arrays (BGR, uint8) matching OpenCV convention
  - Extraction is lazy — frames are generated one at a time to avoid loading
    an entire video into memory (important for 1-3 min clips at 1080p)
  - Temporary files downloaded from R2 are NOT deleted here; callers manage
    lifecycle so the same file can be used by multiple extractors
"""

import logging
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import cv2
import ffmpeg
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VideoMetadata:
    """Metadata extracted from a video file via ffprobe."""

    path: str
    duration_seconds: float
    fps: float
    frame_count: int
    width: int
    height: int
    codec: str
    file_size_bytes: int


class FrameExtractor:
    """
    Extracts frames and metadata from a local MP4 video file.

    Typical usage in a Celery task:
        path = r2_client.download_to_temp(clip.r2_key_front)
        extractor = FrameExtractor(path)
        meta = extractor.get_metadata()
        for frame in extractor.extract_frames(target_fps=5):
            # process frame (numpy array, BGR)
            ...
        path.unlink()  # caller cleans up
    """

    def __init__(self, video_path: str | Path) -> None:
        """
        Args:
            video_path: Path to local MP4 file.
        """
        self.video_path = Path(video_path)
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video not found: {self.video_path}")

    # ── Metadata ──────────────────────────────────────────────────────

    def get_metadata(self) -> VideoMetadata:
        """
        Extract video metadata using ffprobe.

        Faster than opening with OpenCV as it reads container metadata
        without decoding frames.

        Returns:
            VideoMetadata dataclass with duration, fps, dimensions, codec.

        Raises:
            ffmpeg.Error: If ffprobe fails to read the file.
        """
        try:
            probe = ffmpeg.probe(str(self.video_path))
        except ffmpeg.Error as exc:
            logger.error("ffprobe failed for %s: %s", self.video_path, exc.stderr)
            raise

        video_stream = next(
            (s for s in probe["streams"] if s["codec_type"] == "video"),
            None,
        )
        if video_stream is None:
            raise ValueError(f"No video stream found in {self.video_path}")

        # FPS is stored as a fraction string e.g. "30000/1001"
        fps_raw = video_stream.get("r_frame_rate", "30/1")
        num, den = (int(x) for x in fps_raw.split("/"))
        fps = num / den if den else 30.0

        duration = float(probe["format"].get("duration", 0))
        frame_count = int(video_stream.get("nb_frames", duration * fps))

        return VideoMetadata(
            path=str(self.video_path),
            duration_seconds=duration,
            fps=fps,
            frame_count=frame_count,
            width=int(video_stream.get("width", 0)),
            height=int(video_stream.get("height", 0)),
            codec=video_stream.get("codec_name", "unknown"),
            file_size_bytes=self.video_path.stat().st_size,
        )

    # ── Frame extraction ──────────────────────────────────────────────

    def extract_frames(
        self,
        target_fps: float = 5.0,
        start_second: float = 0.0,
        end_second: float | None = None,
        resize: tuple[int, int] | None = None,
    ) -> Generator[tuple[int, np.ndarray], None, None]:
        """
        Yield video frames at a specified sample rate.

        Args:
            target_fps: Frames to extract per second of video (default 5 fps).
                        Lower values are much faster for long clips.
            start_second: Start time in seconds (default 0).
            end_second: End time in seconds. None means process to end.
            resize: Optional (width, height) to resize each frame.

        Yields:
            (frame_index, frame) tuples where frame is a BGR numpy array.

        Raises:
            RuntimeError: If the video cannot be opened by OpenCV.
        """
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            raise RuntimeError(f"OpenCV could not open video: {self.video_path}")

        try:
            native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            step = max(1, int(native_fps / target_fps))

            start_frame = int(start_second * native_fps)
            end_frame = int(end_second * native_fps) if end_second else total_frames

            if start_frame > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

            frame_idx = start_frame
            while frame_idx < end_frame:
                ret, frame = cap.read()
                if not ret:
                    break
                if (frame_idx - start_frame) % step == 0:
                    if resize:
                        frame = cv2.resize(frame, resize, interpolation=cv2.INTER_AREA)
                    yield frame_idx, frame
                frame_idx += 1
        finally:
            cap.release()

    def extract_clip_segment(
        self,
        start_second: float,
        end_second: float,
        output_path: str | Path,
    ) -> Path:
        """
        Extract a short clip segment to a new MP4 file using ffmpeg.

        Used to produce the anomaly clip snippets stored back on R2
        for display in the anomaly detail view.

        Args:
            start_second: Segment start time in seconds.
            end_second: Segment end time in seconds.
            output_path: Destination path for the output MP4.

        Returns:
            Path to the written output MP4.

        Raises:
            ffmpeg.Error: If transcoding fails.
        """
        output_path = Path(output_path)
        duration = end_second - start_second
        try:
            (
                ffmpeg.input(str(self.video_path), ss=start_second, t=duration)
                .output(
                    str(output_path),
                    vcodec="libx264",
                    acodec="aac",
                    preset="fast",
                    crf=23,
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            logger.debug(
                "Extracted segment %s–%ss → %s", start_second, end_second, output_path
            )
            return output_path
        except ffmpeg.Error as exc:
            logger.error("Segment extraction failed: %s", exc.stderr)
            raise
