import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.schemas.insight import InsightResponse, InsightsListResponse
from app.services.insight_service import get_insight, get_insights
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("", status_code=status.HTTP_200_OK, response_model=InsightsListResponse)
async def get_insights_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cluster_id: str | None = Query(None, description="Filter by cluster ID"),
    limit: int = 100,
    offset: int = 0,
) -> InsightsListResponse:
    """
    Get insights for the authenticated user.

    Returns insights with optional cluster filter.
    Only returns insights for clusters owned by the authenticated user.

    Args:
        current_user: Authenticated user from JWT token
        db: Database session
        cluster_id: Optional cluster ID filter (UUID)
        limit: Maximum number of results (default: 100)
        offset: Number of results to skip (default: 0)

    Returns:
        InsightsListResponse with filtered insights
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

        insights, total = await get_insights(
            user_id=current_user.id,
            db=db,
            cluster_id=cluster_uuid,
            limit=limit,
            offset=offset,
        )

        insight_responses = [
            InsightResponse.model_validate(insight) for insight in insights
        ]

        return InsightsListResponse(
            insights=insight_responses,
            total=total,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving insights for user {current_user.id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve insights",
        )


@router.get(
    "/{insight_id}", status_code=status.HTTP_200_OK, response_model=InsightResponse
)
async def get_insight_endpoint(
    insight_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InsightResponse:
    """
    Get insight by ID.

    Returns insight details. Only returns insights for clusters owned by the authenticated user.

    Args:
        insight_id: Insight unique identifier (UUID)
        current_user: Authenticated user from JWT token
        db: Database session

    Returns:
        InsightResponse with insight details

    Raises:
        HTTPException: 404 if insight not found or cluster not owned by user
    """
    try:
        try:
            insight_uuid = UUID(insight_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid insight ID format",
            )

        insight = await get_insight(
            insight_id=insight_uuid,
            user_id=current_user.id,
            db=db,
        )

        if not insight:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Insight not found",
            )

        return InsightResponse.model_validate(insight)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving insight {insight_id} for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve insight",
        )
