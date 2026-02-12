import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ml.embeddings import DEFAULT_EMBEDDING_DIM
from app.models import Document, DocumentEmbedding

logger = logging.getLogger(__name__)


def _format_vector_for_query(vector: list[float]) -> str:
    """
    Format a Python list of floats as a PostgreSQL vector literal.

    Args:
        vector: List of float values

    Returns:
        String representation suitable for PostgreSQL vector type casting
    """
    return "[" + ",".join(str(v) for v in vector) + "]"


def _build_vector_search_query(
    vector_literal: str,
    user_id: UUID | None = None,
    similarity_threshold: float | None = None,
) -> str:
    """
    Build the SQL query for vector similarity search.

    Args:
        vector_literal: Formatted vector literal string (e.g., "[1,2,3]")
        user_id: Optional user ID filter
        similarity_threshold: Optional distance threshold

    Returns:
        SQL query string with placeholders for parameters
    """

    vector_literal_quoted = f"'{vector_literal}'"

    query_parts = [
        f"SELECT de.id, de.embedding <=> {vector_literal_quoted}::vector AS distance",
        "FROM document_embeddings de",
    ]

    if user_id:
        query_parts.append("INNER JOIN documents d ON de.document_id = d.id")

    query_parts.append("WHERE de.model_name = :model_name")

    if user_id:
        query_parts.append("AND d.user_id = :user_id")

    if similarity_threshold is not None:
        query_parts.append(
            f"AND (de.embedding <=> {vector_literal_quoted}::vector) <= :threshold"
        )

    query_parts.append("ORDER BY distance ASC")
    query_parts.append("LIMIT :limit")

    return " ".join(query_parts)


def search_similar_embeddings_sync(
    session: Session,
    query_vector: list[float],
    model_name: str,
    limit: int = 10,
    user_id: UUID | None = None,
    similarity_threshold: float | None = None,
) -> list[tuple[DocumentEmbedding, float]]:
    """
    Search for similar document embeddings using approximate nearest neighbor search.

    Uses IVFFlat index for efficient vector similarity search. Returns embeddings
    ordered by cosine distance (smaller is more similar).

    Args:
        session: SQLAlchemy synchronous session
        query_vector: Query embedding vector (expected 384 dimensions)
        model_name: Filter embeddings by model name
        limit: Maximum number of results to return
        user_id: Optional user ID to filter documents by owner
        similarity_threshold: Optional maximum cosine distance threshold (0-2 range)
                             Lower values = more strict similarity requirement

    Returns:
        List of tuples (DocumentEmbedding, distance) ordered by similarity
        (most similar first). Distance is cosine distance (0 = identical, 2 = opposite)
    """
    if len(query_vector) != DEFAULT_EMBEDDING_DIM:
        raise ValueError(
            f"Query vector must be {DEFAULT_EMBEDDING_DIM} dimensions, got {len(query_vector)}"
        )

    vector_literal = _format_vector_for_query(query_vector)

    params: dict[str, Any] = {
        "model_name": model_name,
        "limit": limit,
    }

    if user_id:
        params["user_id"] = str(user_id)

    if similarity_threshold is not None:
        params["threshold"] = similarity_threshold

    try:
        id_sql_query = _build_vector_search_query(
            vector_literal, user_id, similarity_threshold
        )

        id_result = session.execute(text(id_sql_query), params)
        id_rows = id_result.fetchall()

        embedding_ids = [UUID(str(row[0])) for row in id_rows]
        distances = [float(row[1]) for row in id_rows]

        if not embedding_ids:
            return []

        embeddings_query = select(DocumentEmbedding).where(
            DocumentEmbedding.id.in_(embedding_ids)
        )
        embeddings_result = session.execute(embeddings_query)
        embeddings_dict = {emb.id: emb for emb in embeddings_result.scalars().all()}

        results: list[tuple[DocumentEmbedding, float]] = []
        for emb_id, distance in zip(embedding_ids, distances):
            embedding = embeddings_dict.get(emb_id)
            if embedding:
                results.append((embedding, distance))

        return results

    except Exception as e:
        logger.error(f"Error performing vector search: {e}", exc_info=True)
        raise


async def search_similar_embeddings_async(
    session: AsyncSession,
    query_vector: list[float],
    model_name: str,
    limit: int = 10,
    user_id: UUID | None = None,
    similarity_threshold: float | None = None,
) -> list[tuple[DocumentEmbedding, float]]:
    """
    Async version of search_similar_embeddings_sync.

    Search for similar document embeddings using approximate nearest neighbor search.

    Args:
        session: SQLAlchemy async session
        query_vector: Query embedding vector (expected 384 dimensions)
        model_name: Filter embeddings by model name
        limit: Maximum number of results to return
        user_id: Optional user ID to filter documents by owner
        similarity_threshold: Optional maximum cosine distance threshold (0-2 range)

    Returns:
        List of tuples (DocumentEmbedding, distance) ordered by similarity
    """
    if len(query_vector) != DEFAULT_EMBEDDING_DIM:
        raise ValueError(
            f"Query vector must be {DEFAULT_EMBEDDING_DIM} dimensions, got {len(query_vector)}"
        )

    vector_literal = _format_vector_for_query(query_vector)

    params: dict[str, Any] = {
        "model_name": model_name,
        "limit": limit,
    }

    if user_id:
        params["user_id"] = str(user_id)

    if similarity_threshold is not None:
        params["threshold"] = similarity_threshold

    try:
        id_sql_query = _build_vector_search_query(
            vector_literal, user_id, similarity_threshold
        )

        id_result = await session.execute(text(id_sql_query), params)
        id_rows = id_result.fetchall()

        embedding_ids = [UUID(str(row[0])) for row in id_rows]
        distances = [float(row[1]) for row in id_rows]

        if not embedding_ids:
            return []

        embeddings_query = select(DocumentEmbedding).where(
            DocumentEmbedding.id.in_(embedding_ids)
        )
        embeddings_result = await session.execute(embeddings_query)
        embeddings_dict = {emb.id: emb for emb in embeddings_result.scalars().all()}

        results: list[tuple[DocumentEmbedding, float]] = []
        for emb_id, distance in zip(embedding_ids, distances):
            embedding = embeddings_dict.get(emb_id)
            if embedding:
                results.append((embedding, distance))

        return results

    except Exception as e:
        logger.error(f"Error performing vector search: {e}", exc_info=True)
        raise


def search_similar_documents_sync(
    session: Session,
    query_vector: list[float],
    model_name: str,
    limit: int = 10,
    user_id: UUID | None = None,
    similarity_threshold: float | None = None,
) -> list[tuple[Document, float]]:
    """
    Search for similar documents using vector similarity.

    Returns Document objects with their similarity distances.

    Args:
        session: SQLAlchemy synchronous session
        query_vector: Query embedding vector (expected 384 dimensions)
        model_name: Filter embeddings by model name
        limit: Maximum number of results to return
        user_id: Optional user ID to filter documents by owner
        similarity_threshold: Optional maximum cosine distance threshold

    Returns:
        List of tuples (Document, distance) ordered by similarity
    """
    embedding_results = search_similar_embeddings_sync(
        session=session,
        query_vector=query_vector,
        model_name=model_name,
        limit=limit,
        user_id=user_id,
        similarity_threshold=similarity_threshold,
    )

    if not embedding_results:
        return []

    document_ids = [emb.document_id for emb, _ in embedding_results]
    documents_query = select(Document).where(Document.id.in_(document_ids))
    documents_result = session.execute(documents_query)
    documents_dict = {doc.id: doc for doc in documents_result.scalars().all()}

    results: list[tuple[Document, float]] = []
    for embedding, distance in embedding_results:
        document = documents_dict.get(embedding.document_id)
        if document:
            results.append((document, distance))

    return results


async def search_similar_documents_async(
    session: AsyncSession,
    query_vector: list[float],
    model_name: str,
    limit: int = 10,
    user_id: UUID | None = None,
    similarity_threshold: float | None = None,
) -> list[tuple[Document, float]]:
    """
    Async version of search_similar_documents_sync.

    Search for similar documents using vector similarity.

    Args:
        session: SQLAlchemy async session
        query_vector: Query embedding vector (expected 384 dimensions)
        model_name: Filter embeddings by model name
        limit: Maximum number of results to return
        user_id: Optional user ID to filter documents by owner
        similarity_threshold: Optional maximum cosine distance threshold

    Returns:
        List of tuples (Document, distance) ordered by similarity
    """
    embedding_results = await search_similar_embeddings_async(
        session=session,
        query_vector=query_vector,
        model_name=model_name,
        limit=limit,
        user_id=user_id,
        similarity_threshold=similarity_threshold,
    )

    if not embedding_results:
        return []

    document_ids = [emb.document_id for emb, _ in embedding_results]
    documents_query = select(Document).where(Document.id.in_(document_ids))
    documents_result = await session.execute(documents_query)
    documents_dict = {doc.id: doc for doc in documents_result.scalars().all()}

    results: list[tuple[Document, float]] = []
    for embedding, distance in embedding_results:
        document = documents_dict.get(embedding.document_id)
        if document:
            results.append((document, distance))

    return results
