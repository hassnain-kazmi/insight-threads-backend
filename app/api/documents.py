import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.schemas.document import (
    ClusterMembershipResponse,
    DocumentDetailResponse,
    DocumentResponse,
    DocumentSentimentResponse,
    DocumentsListResponse,
)
from app.services.document_service import get_document_detail, get_documents
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", status_code=status.HTTP_200_OK, response_model=DocumentsListResponse)
async def get_documents_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
    processed: bool | None = Query(None, description="Filter by processed status"),
    ingest_event_id: str | None = Query(None, description="Filter by ingest event ID"),
    cluster_id: str | None = Query(None, description="Filter by cluster ID"),
    source_type: str | None = Query(None, description="Filter by source type (rss, hackernews, github)"),
    sentiment_min: float | None = Query(None, description="Minimum sentiment score (-1 to 1)"),
    sentiment_max: float | None = Query(None, description="Maximum sentiment score (-1 to 1)"),
) -> DocumentsListResponse:
    """
    Get documents for the authenticated user.
    
    Returns documents with optional filters by processed status, ingest event, cluster,
    source type, and sentiment range. Only returns documents owned by the authenticated user.
    
    Args:
        current_user: Authenticated user from JWT token
        db: Database session
        limit: Maximum number of results (default: 100)
        offset: Number of results to skip (default: 0)
        processed: Optional filter by processed status
        ingest_event_id: Optional filter by ingest event ID (UUID)
        cluster_id: Optional filter by cluster ID (UUID)
        source_type: Optional filter by source type (rss, hackernews, github)
        sentiment_min: Optional minimum sentiment score filter (-1 to 1)
        sentiment_max: Optional maximum sentiment score filter (-1 to 1)
        
    Returns:
        DocumentsListResponse with filtered documents
    """
    try:
        ingest_event_uuid = None
        if ingest_event_id:
            try:
                ingest_event_uuid = UUID(ingest_event_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid ingest event ID format",
                )
        
        cluster_uuid = None
        if cluster_id:
            try:
                cluster_uuid = UUID(cluster_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid cluster ID format",
                )
        
        if sentiment_min is not None and (sentiment_min < -1 or sentiment_min > 1):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="sentiment_min must be between -1 and 1",
            )
        
        if sentiment_max is not None and (sentiment_max < -1 or sentiment_max > 1):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="sentiment_max must be between -1 and 1",
            )
        
        if sentiment_min is not None and sentiment_max is not None and sentiment_min > sentiment_max:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="sentiment_min must be less than or equal to sentiment_max",
            )
        
        documents, total = await get_documents(
            user_id=current_user.id,
            db=db,
            limit=limit,
            offset=offset,
            processed=processed,
            ingest_event_id=ingest_event_uuid,
            cluster_id=cluster_uuid,
            source_type=source_type,
            sentiment_min=sentiment_min,
            sentiment_max=sentiment_max,
        )
        
        document_responses = [DocumentResponse.model_validate(doc) for doc in documents]
        
        return DocumentsListResponse(
            documents=document_responses,
            total=total,
        )
        
    except Exception as e:
        logger.error(f"Error retrieving documents for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve documents",
        )


@router.get("/{document_id}", status_code=status.HTTP_200_OK, response_model=DocumentDetailResponse)
async def get_document_endpoint(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentDetailResponse:
    """
    Get document by ID with full details.
    
    Returns document details including raw text, sentiment, and cluster memberships.
    Only returns documents owned by the authenticated user.
    
    Args:
        document_id: Document unique identifier (UUID)
        current_user: Authenticated user from JWT token
        db: Database session
        
    Returns:
        DocumentDetailResponse with document details including relationships
        
    Raises:
        HTTPException: 404 if document not found or not owned by user
    """
    try:
        try:
            document_uuid = UUID(document_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid document ID format",
            )
        
        document = await get_document_detail(
            document_id=document_uuid,
            user_id=current_user.id,
            db=db,
        )
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        
        sentiment_data = None
        if document.sentiments:
            sentiment = document.sentiments[0]
            sentiment_data = DocumentSentimentResponse.model_validate(sentiment)
        
        cluster_memberships_data = [
            ClusterMembershipResponse.model_validate(membership)
            for membership in document.cluster_memberships
        ]
        
        return DocumentDetailResponse(
            id=document.id,
            user_id=document.user_id,
            ingest_event_id=document.ingest_event_id,
            source_path=document.source_path,
            title=document.title,
            raw_text=document.raw_text,
            processed=document.processed,
            processed_at=document.processed_at,
            created_at=document.created_at,
            updated_at=document.updated_at,
            sentiment=sentiment_data,
            cluster_memberships=cluster_memberships_data,
        )
        
    except Exception as e:
        logger.error(f"Error retrieving document {document_id} for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document",
        )

