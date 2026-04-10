"""
Celery tasks for async video processing.

Full task implementations are added in feature/api-backend and
feature/deep-learning. Stubs are defined here to register task names.
"""

from api.tasks.celery_app import celery_app


@celery_app.task(name="api.tasks.video_tasks.process_clip", bind=True, max_retries=3)
def process_clip(self, clip_id: str) -> dict:
    """
    Full async pipeline for a single clip.

    Steps (implemented in feature/api-backend):
      1. Download front + rear video from R2
      2. Extract frames with OpenCV
      3. Run inference (baseline → classical → deep learning)
      4. Compute per-clip score
      5. Generate AI explanation via Claude API
      6. Persist results to PostgreSQL
      7. Update clip processing_status

    Args:
        clip_id: UUID string of the Clip record to process.

    Returns:
        Dict with clip_id and processing summary.
    """
    raise NotImplementedError("Implemented in feature/api-backend")


@celery_app.task(name="api.tasks.video_tasks.process_all_pending")
def process_all_pending() -> dict:
    """
    Enqueue process_clip tasks for all clips with PENDING status.

    Returns:
        Dict with count of clips enqueued.
    """
    raise NotImplementedError("Implemented in feature/api-backend")
