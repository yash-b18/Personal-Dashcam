"""
Anomaly endpoints.

Implemented in feature/api-backend.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("")
def list_anomalies() -> dict:
    """List all detected anomalies. Implemented in feature/api-backend."""
    return {"detail": "Not yet implemented"}


@router.get("/{anomaly_id}")
def get_anomaly(anomaly_id: str) -> dict:
    """Get anomaly details with AI explanation. Implemented in feature/api-backend."""
    return {"detail": "Not yet implemented"}
