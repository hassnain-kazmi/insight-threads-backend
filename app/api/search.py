import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.schemas.search import DocumentSearchResult, SearchResponse
from app.services.search_service import search_documents
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", status_code=status.HTTP_200_OK, response_model=SearchResponse)
async def search_documents_endpoint(
    query: str = Query(..., description="Search query text", min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 10,
    similarity_threshold: float | None = Query(None, description="Maximum similarity threshold (0-2, lower is stricter)", ge=0.0, le=2.0),
) -> SearchResponse:
    """
    Search documents using semantic similarity.
    
    Converts the query text to an embedding and searches for similar documents
    using vector similarity search. Only returns documents owned by the authenticated user.
    
    Args:
        query: Search query text
        current_user: Authenticated user from JWT token
        db: Database session
        limit: Maximum number of results (default: 10)
        similarity_threshold: Optional maximum cosine distance threshold (0-2 range)
                             Lower values = more strict similarity requirement
                             
    Returns:
        SearchResponse with matching documents and similarity scores
        
    Raises:
        HTTPException: 400 if query is invalid, 500 if search fails
    """
    try:
        document_results = await search_documents(
            query_text=query,
            user_id=current_user.id,
            db=db,
            limit=limit,
            similarity_threshold=similarity_threshold,
        )
 
        search_results = [
            DocumentSearchResult(
                id=document.id,
                title=document.title,
                source_path=document.source_path,
                similarity_score=distance,
                created_at=document.created_at,
            )
            for document, distance in document_results
        ]
        
        return SearchResponse(
            results=search_results,
            total=len(search_results),
            query=query,
        )
        
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as e:
        logger.error(f"Invalid query or embedding computation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid query or failed to process: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Error performing search for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to perform search",
        )
