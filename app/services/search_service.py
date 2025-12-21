import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.embeddings import DEFAULT_MODEL_NAME, compute_embedding
from app.models import Document
from app.utils.vector_search import search_similar_documents_async

logger = logging.getLogger(__name__)


async def search_documents(
    query_text: str,
    user_id: UUID,
    db: AsyncSession,
    limit: int = 10,
    similarity_threshold: float | None = None,
) -> list[tuple[Document, float]]:
    """
    Search documents using semantic similarity.
    
    Converts the query text to an embedding and searches for similar documents
    using vector similarity search. Only returns documents owned by the specified user.
    
    Args:
        query_text: Search query text
        user_id: User unique identifier
        db: Database session
        limit: Maximum number of results (default: 10)
        similarity_threshold: Optional maximum cosine distance threshold (0-2 range)
                             Lower values = more strict similarity requirement
                             
    Returns:
        List of tuples (Document, distance) ordered by similarity
        
    Raises:
        ValueError: If query text is invalid
        RuntimeError: If embedding computation fails
    """
    if not query_text or not query_text.strip():
        raise ValueError("Query text cannot be empty")
    
    logger.info(f"Computing embedding for search query: {query_text[:100]}...")
    query_vector = compute_embedding(query_text.strip(), model_name=DEFAULT_MODEL_NAME)
    
    logger.info(f"Searching for similar documents for user {user_id}")
    document_results = await search_similar_documents_async(
        session=db,
        query_vector=query_vector,
        model_name=DEFAULT_MODEL_NAME,
        limit=limit,
        user_id=user_id,
        similarity_threshold=similarity_threshold,
    )
    
    logger.info(
        f"Found {len(document_results)} results for query '{query_text[:50]}...' "
        f"for user {user_id}"
    )
    
    return document_results

