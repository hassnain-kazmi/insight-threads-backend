import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from celery import Task
from sqlalchemy import select

from app.celery_app import celery_app
from app.db import get_sync_db
from app.ml.embeddings import DEFAULT_MODEL_NAME, compute_embedding
from app.models import Document, DocumentEmbedding, DocumentSentiment

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.embed_job.compute_document_embedding")
def compute_document_embedding(
    self: Task,
    document_id: str,
    model_name: str = DEFAULT_MODEL_NAME,
) -> dict[str, Any]:
    """
    Celery task to compute and save embedding for a document.
    
    Args:
        document_id: UUID of the document to embed
        model_name: Name of the embedding model to use
        
    Returns:
        dict: Task result with status, document_id, and embedding_id
        
    Raises:
        ValueError: If document not found or embedding already exists
        RuntimeError: If embedding computation fails
    """
    doc_uuid = UUID(document_id)
    
    logger.info(
        f"Computing embedding for document {doc_uuid} using model {model_name}"
    )
    
    try:
        with get_sync_db() as db:
            result = db.execute(
                select(Document).where(Document.id == doc_uuid)
            )
            document = result.scalar_one_or_none()
            
            if not document:
                error_msg = f"Document {doc_uuid} not found"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            existing_result = db.execute(
                select(DocumentEmbedding).where(
                    DocumentEmbedding.document_id == doc_uuid,
                    DocumentEmbedding.model_name == model_name,
                )
            )
            existing = existing_result.scalar_one_or_none()
            
            if existing:
                logger.warning(
                    f"Embedding already exists for document {doc_uuid} "
                    f"with model {model_name}, skipping"
                )
                return {
                    "status": "skipped",
                    "document_id": document_id,
                    "embedding_id": str(existing.id),
                    "model_name": model_name,
                    "message": "Embedding already exists",
                }
            
            if not document.raw_text or not document.raw_text.strip():
                error_msg = f"Document {doc_uuid} has no text content to embed"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            try:
                logger.info(f"Computing embedding for document {doc_uuid}")
                embedding_vector = compute_embedding(document.raw_text, model_name)
                
                document_embedding = DocumentEmbedding(
                    document_id=doc_uuid,
                    model_name=model_name,
                    embedding=embedding_vector,
                )
                db.add(document_embedding)
                
                if model_name == DEFAULT_MODEL_NAME and not document.processed:
                    sentiment_result = db.execute(
                        select(DocumentSentiment).where(
                            DocumentSentiment.document_id == doc_uuid,
                        )
                    )
                    sentiment_exists = sentiment_result.scalar_one_or_none() is not None
                    
                    if sentiment_exists:
                        document.processed = True
                        document.processed_at = datetime.now(timezone.utc)
                        logger.info(
                            f"Marked document {doc_uuid} as processed "
                            f"(embedding and sentiment both exist)"
                        )
                
                db.commit()
                db.refresh(document_embedding)
                
                logger.info(
                    f"Successfully created embedding {document_embedding.id} "
                    f"for document {doc_uuid} using model {model_name}"
                )
                
                return {
                    "status": "completed",
                    "document_id": document_id,
                    "embedding_id": str(document_embedding.id),
                    "model_name": model_name,
                    "task_id": self.request.id,
                }
            except Exception:
                db.rollback()
                raise
            
    except ValueError as e:
        logger.error(f"Value error computing embedding for document {doc_uuid}: {e}")
        raise
    except Exception as e:
        logger.error(
            f"Error computing embedding for document {doc_uuid}: {e}",
            exc_info=True,
        )
        raise RuntimeError(f"Failed to compute embedding: {e}") from e

