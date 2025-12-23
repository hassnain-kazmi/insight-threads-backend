import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ClusterMember, Document, DocumentSentiment, IngestEvent

logger = logging.getLogger(__name__)


async def get_documents(
    user_id: UUID,
    db: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    processed: bool | None = None,
    ingest_event_id: UUID | None = None,
    cluster_id: UUID | None = None,
    source_type: str | None = None,
    sentiment_min: float | None = None,
    sentiment_max: float | None = None,
) -> tuple[list[Document], int]:
    """
    Get documents for a user with optional filters.

    Args:
        user_id: User unique identifier
        db: Database session
        limit: Maximum number of documents to return (default: 100)
        offset: Number of documents to skip (default: 0)
        processed: Optional filter by processed status
        ingest_event_id: Optional filter by ingest event ID
        cluster_id: Optional filter by cluster ID
        source_type: Optional filter by source type (rss, hackernews, github) - filters via ingest_event.source
        sentiment_min: Optional minimum sentiment score filter
        sentiment_max: Optional maximum sentiment score filter

    Returns:
        Tuple of (list of documents, total count)
    """
    query = select(Document).where(Document.user_id == user_id)
    count_query = select(func.count(Document.id)).where(Document.user_id == user_id)

    if processed is not None:
        query = query.where(Document.processed == processed)
        count_query = count_query.where(Document.processed == processed)

    if ingest_event_id:
        query = query.where(Document.ingest_event_id == ingest_event_id)
        count_query = count_query.where(Document.ingest_event_id == ingest_event_id)

    if cluster_id:
        query = query.join(
            ClusterMember, Document.id == ClusterMember.document_id
        ).where(ClusterMember.cluster_id == cluster_id)
        count_query = count_query.join(
            ClusterMember, Document.id == ClusterMember.document_id
        ).where(ClusterMember.cluster_id == cluster_id)

    if source_type:
        query = query.join(
            IngestEvent, Document.ingest_event_id == IngestEvent.id
        ).where(IngestEvent.source == source_type.lower())
        count_query = count_query.join(
            IngestEvent, Document.ingest_event_id == IngestEvent.id
        ).where(IngestEvent.source == source_type.lower())

    if sentiment_min is not None or sentiment_max is not None:
        query = query.join(
            DocumentSentiment, Document.id == DocumentSentiment.document_id
        )
        count_query = count_query.join(
            DocumentSentiment, Document.id == DocumentSentiment.document_id
        )

        if sentiment_min is not None:
            query = query.where(DocumentSentiment.combined_score >= sentiment_min)
            count_query = count_query.where(
                DocumentSentiment.combined_score >= sentiment_min
            )

        if sentiment_max is not None:
            query = query.where(DocumentSentiment.combined_score <= sentiment_max)
            count_query = count_query.where(
                DocumentSentiment.combined_score <= sentiment_max
            )

    count_result = await db.execute(count_query)
    total = count_result.scalar_one() or 0

    data_query = query.order_by(Document.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(data_query)
    documents = result.scalars().all()

    logger.info(
        f"Retrieved {len(documents)} documents for user {user_id} "
        f"(offset: {offset}, limit: {limit})"
    )

    return documents, total


async def get_document(
    document_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Document | None:
    """
    Get document by ID.

    Returns document details. Only returns documents owned by the specified user.

    Args:
        document_id: Document unique identifier
        user_id: User unique identifier (for authorization)
        db: Database session

    Returns:
        Document object, or None if not found or not owned by user
    """
    query = select(Document).where(
        Document.id == document_id, Document.user_id == user_id
    )

    result = await db.execute(query)
    document = result.scalar_one_or_none()

    if document:
        logger.info(f"Retrieved document {document_id} for user {user_id}")
    else:
        logger.debug(f"Document {document_id} not found or not owned by user {user_id}")

    return document


async def get_document_detail(
    document_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> Document | None:
    """
    Get document detail with relationships loaded.

    Returns document details with sentiment and cluster memberships loaded.
    Only returns documents owned by the specified user.

    Args:
        document_id: Document unique identifier
        user_id: User unique identifier (for authorization)
        db: Database session

    Returns:
        Document object with relationships loaded, or None if not found or not owned by user
    """
    query = (
        select(Document)
        .options(
            selectinload(Document.sentiments),
            selectinload(Document.cluster_memberships),
        )
        .where(Document.id == document_id, Document.user_id == user_id)
    )

    result = await db.execute(query)
    document = result.scalar_one_or_none()

    if document:
        logger.info(f"Retrieved document detail {document_id} for user {user_id}")
    else:
        logger.debug(f"Document {document_id} not found or not owned by user {user_id}")

    return document
