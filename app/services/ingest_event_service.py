import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, IngestEvent

logger = logging.getLogger(__name__)


async def get_ingest_events(
    user_id: UUID,
    db: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
) -> tuple[list[IngestEvent], int]:
    """
    Get ingest events for a user with optional filters.

    Args:
        user_id: User unique identifier
        db: Database session
        limit: Maximum number of events to return (default: 100)
        offset: Number of events to skip (default: 0)
        status: Optional filter by status

    Returns:
        Tuple of (list of ingest events, total count)
    """
    query = select(IngestEvent).where(IngestEvent.user_id == user_id)

    if status:
        query = query.where(IngestEvent.status == status)

    count_query = select(func.count(IngestEvent.id)).where(
        IngestEvent.user_id == user_id
    )

    if status:
        count_query = count_query.where(IngestEvent.status == status)

    count_result = await db.execute(count_query)
    total = count_result.scalar_one() or 0

    data_query = (
        query.order_by(IngestEvent.started_at.desc()).limit(limit).offset(offset)
    )

    result = await db.execute(data_query)
    events = result.scalars().all()

    logger.info(
        f"Retrieved {len(events)} ingest events for user {user_id} "
        f"(offset: {offset}, limit: {limit})"
    )

    return events, total


async def get_ingest_event(
    event_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> IngestEvent | None:
    """
    Get ingest event by ID.

    Returns ingest event details. Only returns events owned by the specified user.

    Args:
        event_id: Ingest event unique identifier
        user_id: User unique identifier (for authorization)
        db: Database session

    Returns:
        IngestEvent object, or None if not found or not owned by user
    """
    query = select(IngestEvent).where(
        IngestEvent.id == event_id, IngestEvent.user_id == user_id
    )

    result = await db.execute(query)
    event = result.scalar_one_or_none()

    if event:
        logger.info(f"Retrieved ingest event {event_id} for user {user_id}")
    else:
        logger.debug(
            f"Ingest event {event_id} not found or not owned by user {user_id}"
        )

    return event


async def get_ingest_event_with_document_count(
    event_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> tuple[IngestEvent | None, int]:
    """
    Get ingest event by ID with document count.

    Returns ingest event details and the number of documents created.
    Only returns events owned by the specified user.

    Args:
        event_id: Ingest event unique identifier
        user_id: User unique identifier (for authorization)
        db: Database session

    Returns:
        Tuple of (IngestEvent object or None, document_count)
    """
    event = await get_ingest_event(event_id, user_id, db)
    
    if not event:
        return None, 0
    
    count_query = select(func.count(Document.id)).where(
        Document.ingest_event_id == event_id
    )
    count_result = await db.execute(count_query)
    document_count = count_result.scalar_one() or 0
    
    return event, document_count
