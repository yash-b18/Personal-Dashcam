"""
API route tests using FastAPI TestClient.

Environment variables are set before any app modules are imported,
so no PostgreSQL or Redis connection is needed.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ── Shared app fixture ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def app_client():
    from fastapi.testclient import TestClient
    from app import app
    from api.database import get_db

    def _null_db():
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        db.query.return_value.filter.return_value.count.return_value = 0
        db.query.return_value.count.return_value = 0
        db.query.return_value.filter.return_value.subquery.return_value = MagicMock()
        (
            db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value
        ) = []
        (
            db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value
        ) = []
        yield db

    app.dependency_overrides[get_db] = _null_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


# ── Schemas (no DB needed) ─────────────────────────────────────────────────────


class TestSchemas:
    def test_clip_summary_required_fields(self) -> None:
        from api.schemas import ClipSummary

        uid = uuid.uuid4()
        obj = ClipSummary(
            id=uid,
            filename_prefix="20240101_120000",
            processing_status="done",
            score=85.5,
            grade="B",
            anomaly_count=2,
        )
        assert obj.id == uid
        assert obj.grade == "B"

    def test_clip_summary_optional_fields_default_none(self) -> None:
        from api.schemas import ClipSummary

        obj = ClipSummary(
            id=uuid.uuid4(),
            filename_prefix="clip",
            processing_status="pending",
        )
        assert obj.score is None
        assert obj.grade is None
        assert obj.front_url is None
        assert obj.duration_seconds is None
        assert obj.recorded_at is None

    def test_label_submit_full(self) -> None:
        from api.schemas import LabelSubmit

        ls = LabelSubmit(
            is_anomaly=True,
            anomaly_types=["hard_braking", "near_miss"],
            reason="Sudden stop",
        )
        assert ls.is_anomaly is True
        assert len(ls.anomaly_types) == 2

    def test_label_submit_minimal(self) -> None:
        from api.schemas import LabelSubmit

        ls = LabelSubmit(is_anomaly=False)
        assert ls.anomaly_types is None
        assert ls.reason is None

    def test_overall_score_response(self) -> None:
        from api.schemas import OverallScoreResponse

        r = OverallScoreResponse(
            score=78.5,
            grade="C",
            clips_analyzed=42,
            breakdown={"hard_braking": 15.0},
        )
        assert r.score == 78.5

    def test_anomaly_breakdown_schema(self) -> None:
        from api.schemas import AnomalyBreakdown

        ab = AnomalyBreakdown(
            anomaly_type="near_miss", count=3, total_score_impact=75.0
        )
        assert ab.count == 3

    def test_process_response_defaults(self) -> None:
        from api.schemas import ProcessResponse

        pr = ProcessResponse(task_id="abc-123", clip_id=uuid.uuid4())
        assert pr.status == "queued"

    def test_clip_list_response(self) -> None:
        from api.schemas import ClipListResponse

        r = ClipListResponse(clips=[], total=0, page=1, page_size=20)
        assert r.total == 0

    def test_anomaly_list_response_empty(self) -> None:
        from api.schemas import AnomalyListResponse

        r = AnomalyListResponse(anomalies=[], total=0, page=1, page_size=20)
        assert r.anomalies == []

    def test_label_queue_response(self) -> None:
        from api.schemas import LabelQueueResponse

        r = LabelQueueResponse(clips=[], total_unlabeled=100)
        assert r.total_unlabeled == 100

    def test_score_history_response(self) -> None:
        from api.schemas import ScoreHistoryResponse

        r = ScoreHistoryResponse(history=[], total=0)
        assert r.total == 0

    def test_anomaly_summary_schema(self) -> None:
        from api.schemas import AnomalySummary

        a = AnomalySummary(
            id=uuid.uuid4(),
            clip_id=uuid.uuid4(),
            model_type="baseline",
            anomaly_type="hard_braking",
            severity=0.7,
            confidence=0.8,
            timestamp_start=5.0,
            timestamp_end=7.0,
            score_impact=12.5,
            detected_at=datetime.now(timezone.utc),
        )
        assert a.anomaly_type == "hard_braking"
        assert a.ai_explanation is None

    def test_dashboard_response(self) -> None:
        from api.schemas import DashboardResponse

        r = DashboardResponse(
            overall_score=82.0,
            grade="B",
            clips_analyzed=15,
            recent_anomaly_count=3,
            clips_with_anomalies=2,
            anomaly_breakdown=[],
            score_trend=[],
        )
        assert r.overall_score == 82.0

    def test_process_all_response(self) -> None:
        from api.schemas import ProcessAllResponse

        r = ProcessAllResponse(enqueued=5)
        assert r.enqueued == 5
        assert r.status == "queued"


# ── Health endpoint ────────────────────────────────────────────────────────────


class TestHealthEndpoint:
    def test_health_returns_ok(self, app_client) -> None:
        response = app_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_contains_service(self, app_client) -> None:
        response = app_client.get("/health")
        assert "service" in response.json()


# ── Video routes ───────────────────────────────────────────────────────────────


class TestVideoRoutes:
    def test_list_clips_empty(self, app_client) -> None:
        response = app_client.get("/api/v1/videos")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["clips"] == []

    def test_list_clips_invalid_status(self, app_client) -> None:
        response = app_client.get("/api/v1/videos?status=not_a_real_status")
        assert response.status_code == 400

    def test_get_clip_not_found(self, app_client) -> None:
        response = app_client.get(f"/api/v1/videos/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_get_clip_invalid_uuid(self, app_client) -> None:
        response = app_client.get("/api/v1/videos/not-a-uuid")
        assert response.status_code == 422


# ── Anomaly routes ─────────────────────────────────────────────────────────────


class TestAnomalyRoutes:
    def test_list_anomalies_empty(self, app_client) -> None:
        response = app_client.get("/api/v1/anomalies")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["anomalies"] == []

    def test_get_anomaly_not_found(self, app_client) -> None:
        response = app_client.get(f"/api/v1/anomalies/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_list_anomalies_pagination_params(self, app_client) -> None:
        response = app_client.get("/api/v1/anomalies?page=2&page_size=10")
        assert response.status_code == 200
        assert response.json()["page"] == 2


# ── Label routes ───────────────────────────────────────────────────────────────


class TestLabelRoutes:
    def test_get_label_not_found(self, app_client) -> None:
        response = app_client.get(f"/api/v1/labels/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_submit_label_clip_not_found(self, app_client) -> None:
        response = app_client.post(
            f"/api/v1/labels/{uuid.uuid4()}",
            json={"is_anomaly": True, "reason": "hard stop"},
        )
        assert response.status_code == 404

    def test_submit_label_invalid_body(self, app_client) -> None:
        response = app_client.post(
            f"/api/v1/labels/{uuid.uuid4()}",
            json={"not_a_field": "value"},
        )
        assert response.status_code == 422

    def test_delete_label_not_found(self, app_client) -> None:
        response = app_client.delete(f"/api/v1/labels/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_get_label_queue(self, app_client) -> None:
        response = app_client.get("/api/v1/labels/queue")
        assert response.status_code == 200
        data = response.json()
        assert "total_unlabeled" in data
        assert "clips" in data
