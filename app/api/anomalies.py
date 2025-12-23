import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.schemas.anomaly import AnomaliesListResponse, AnomalyResponse
from app.services.anomaly_service import get_anomalies
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("", status_code=status.HTTP_200_OK, response_model=AnomaliesListResponse)
async def get_anomalies_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cluster_id: str | None = Query(None, description="Filter by cluster ID"),
    anomaly_type: str | None = Query(None, description="Filter by anomaly type"),
    start_date: date | None = Query(
        None, description="Filter anomalies from this date"
    ),
    end_date: date | None = Query(None, description="Filter anomalies until this date"),
    limit: int = 100,
    offset: int = 0,
) -> AnomaliesListResponse:
    """
    Get anomalies for the authenticated user.

    Returns anomalies filtered by cluster, type, and date range.
    Only returns anomalies for clusters owned by the authenticated user.

    Args:
        current_user: Authenticated user from JWT token
        db: Database session
        cluster_id: Optional cluster ID filter (UUID)
        anomaly_type: Optional anomaly type filter
        start_date: Optional start date filter
        end_date: Optional end date filter
        limit: Maximum number of results (default: 100)
        offset: Number of results to skip (default: 0)

    Returns:
        AnomaliesListResponse with filtered anomalies
    """
    try:
        cluster_uuid = None
        if cluster_id:
            try:
                cluster_uuid = UUID(cluster_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid cluster ID format",
                )

        anomalies, total = await get_anomalies(
            user_id=current_user.id,
            db=db,
            cluster_id=cluster_uuid,
            anomaly_type=anomaly_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        anomaly_responses = [
            AnomalyResponse.model_validate(anomaly) for anomaly in anomalies
        ]

        return AnomaliesListResponse(
            anomalies=anomaly_responses,
            total=total,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving anomalies for user {current_user.id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve anomalies",
        )
