"""
Celery application configuration.

Tasks are registered in feature/api-backend. This module sets up the
Celery app instance so it can be imported by workers and the API.
"""

from celery import Celery

from api.config import get_settings


def create_celery_app() -> Celery:
    """Create and configure the Celery application."""
    settings = get_settings()
    app = Celery(
        "dashcamiq",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )
    app.config_from_object(
        {
            "task_serializer": "json",
            "result_serializer": "json",
            "accept_content": ["json"],
            "timezone": "UTC",
            "enable_utc": True,
            "task_track_started": True,
            "task_routes": {
                "api.tasks.video_tasks.*": {"queue": "video_processing"},
            },
        }
    )
    return app


celery_app = create_celery_app()
