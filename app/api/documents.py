import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.schemas.document import DocumentResponse, DocumentsListResponse
from app.services.document_service import get_document, get_documents
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
) -> DocumentsListResponse:
    """
    Get documents for the authenticated user.
    
    Returns documents with optional filters by processed status and ingest event.
    Only returns documents owned by the authenticated user.
    
    Args:
        current_user: Authenticated user from JWT token
        db: Database session
        limit: Maximum number of results (default: 100)
        offset: Number of results to skip (default: 0)
        processed: Optional filter by processed status
        ingest_event_id: Optional filter by ingest event ID (UUID)
        
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
        
        documents, total = await get_documents(
            user_id=current_user.id,
            db=db,
            limit=limit,
            offset=offset,
            processed=processed,
            ingest_event_id=ingest_event_uuid,
        )
        
        document_responses = [DocumentResponse.model_validate(doc) for doc in documents]
        
        return DocumentsListResponse(
            documents=document_responses,
            total=total,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving documents for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve documents",
        )


@router.get("/{document_id}", status_code=status.HTTP_200_OK, response_model=DocumentResponse)
async def get_document_endpoint(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Get document by ID.
    
    Returns document details. Only returns documents owned by the authenticated user.
    
    Args:
        document_id: Document unique identifier (UUID)
        current_user: Authenticated user from JWT token
        db: Database session
        
    Returns:
        DocumentResponse with document details
        
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
        
        document = await get_document(
            document_id=document_uuid,
            user_id=current_user.id,
            db=db,
        )
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        
        return DocumentResponse.model_validate(document)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving document {document_id} for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document",
        )

