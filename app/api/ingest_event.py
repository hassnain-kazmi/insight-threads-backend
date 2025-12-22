import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.schemas.ingest import IngestEventResponse, IngestEventsListResponse
from app.services.ingest_event_service import get_ingest_event, get_ingest_events
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest/events", tags=["ingest"])


@router.get("", status_code=status.HTTP_200_OK, response_model=IngestEventsListResponse)
async def get_ingest_events_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
    event_status: str | None = Query(None, description="Filter by ingestion status", alias="status"),
) -> IngestEventsListResponse:
    """
    Get ingest events for the authenticated user.
    
    Returns ingest events with optional status filter.
    Only returns events owned by the authenticated user.
    
    Args:
        current_user: Authenticated user from JWT token
        db: Database session
        limit: Maximum number of results (default: 100)
        offset: Number of results to skip (default: 0)
        status: Optional filter by ingestion status
        
    Returns:
        IngestEventsListResponse with filtered ingest events
    """
    try:
        events, total = await get_ingest_events(
            user_id=current_user.id,
            db=db,
            limit=limit,
            offset=offset,
            status=event_status,
        )
        
        event_responses = [IngestEventResponse.model_validate(event) for event in events]
        
        return IngestEventsListResponse(
            events=event_responses,
            total=total,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving ingest events for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve ingest events",
        )


@router.get("/{event_id}", status_code=status.HTTP_200_OK, response_model=IngestEventResponse)
async def get_ingest_event_endpoint(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IngestEventResponse:
    """
    Get ingest event by ID.
    
    Returns ingest event details including status and error messages.
    Only returns events owned by the authenticated user.
    
    Args:
        event_id: Ingest event unique identifier (UUID)
        current_user: Authenticated user from JWT token
        db: Database session
        
    Returns:
        IngestEventResponse with event details
        
    Raises:
        HTTPException: 404 if event not found or not owned by user
    """
    try:
        try:
            event_uuid = UUID(event_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid event ID format",
            )
        
        event = await get_ingest_event(
            event_id=event_uuid,
            user_id=current_user.id,
            db=db,
        )
        
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ingest event not found",
            )
        
        return IngestEventResponse.model_validate(event)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving ingest event {event_id} for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve ingest event",
        )

