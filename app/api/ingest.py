import logging

from celery.exceptions import OperationalError as CeleryOperationalError
from fastapi import APIRouter, Depends, HTTPException, status
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.schemas.ingest import TriggerIngestionRequest, TriggerIngestionResponse
from app.services.ingest_service import create_and_enqueue_ingestion
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post(
    "/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TriggerIngestionResponse,
)
async def trigger_ingestion(
    request: TriggerIngestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TriggerIngestionResponse:
    """
    Trigger an ingestion task for the authenticated user.

    Enqueues a Celery task to process ingestion from the specified source.

    Args:
        request: Ingestion request with source type and parameters
        current_user: Authenticated user from JWT token
        db: Database session

    Returns:
        TriggerIngestionResponse with ingest_event_id and task_id
    """
    try:
        ingest_event, task_id = await create_and_enqueue_ingestion(
            user=current_user,
            db=db,
            source=request.source,
            source_params=request.source_params,
        )

        logger.info(
            f"Ingestion triggered for user {current_user.id}, "
            f"source: {request.source}, event: {ingest_event.id}, task: {task_id}"
        )

        return TriggerIngestionResponse(
            ingest_event_id=str(ingest_event.id),
            task_id=task_id,
            status=ingest_event.status,
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Ingestion validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except (
        CeleryOperationalError,
        RedisConnectionError,
        RedisTimeoutError,
    ) as e:
        logger.error(f"Task enqueue failed (broker/backend): {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue ingestion task. Service may be unavailable.",
        )
    except Exception as e:
        error_msg = str(e).lower()
        if (
            "enqueue" in error_msg
            or "connection" in error_msg
            or "redis" in error_msg
            or "celery" in error_msg
        ):
            logger.error(f"Task enqueue failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to enqueue ingestion task. Service may be unavailable.",
            )

        logger.error(f"Error triggering ingestion: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger ingestion",
        )
