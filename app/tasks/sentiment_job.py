import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from celery import Task
from sqlalchemy import select

from app.celery_app import celery_app
from app.db import get_sync_db
from app.ml.embeddings import DEFAULT_MODEL_NAME
from app.ml.sentiment import DEFAULT_DISTILBERT_MODEL, analyze_sentiment
from app.models import Document, DocumentEmbedding, DocumentSentiment

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.sentiment_job.compute_document_sentiment")
def compute_document_sentiment(
    self: Task,
    document_id: str,
    distilbert_model_name: str = DEFAULT_DISTILBERT_MODEL,
) -> dict[str, Any]:
    """
    Celery task to compute and persist sentiment for a single document.

    Steps:
    - Fetch document by id
    - Skip if sentiment already exists
    - Run VADER + DistilBERT sentiment analysis
    - Store in document_sentiments table
    """
    doc_uuid = UUID(document_id)

    logger.info(
        f"Computing sentiment for document {doc_uuid} "
        f"using DistilBERT model {distilbert_model_name}"
    )

    try:
        with get_sync_db() as db:
            result = db.execute(select(Document).where(Document.id == doc_uuid))
            document = result.scalar_one_or_none()

            if not document:
                error_msg = f"Document {doc_uuid} not found"
                logger.error(error_msg)
                raise ValueError(error_msg)

            if not document.raw_text or not document.raw_text.strip():
                error_msg = (
                    f"Document {doc_uuid} has no text content for sentiment analysis"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

            existing_result = db.execute(
                select(DocumentSentiment).where(
                    DocumentSentiment.document_id == doc_uuid,
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                logger.warning(
                    f"Sentiment already exists for document {doc_uuid}, skipping"
                )
                return {
                    "status": "skipped",
                    "document_id": document_id,
                    "sentiment_id": str(existing.id),
                    "message": "Sentiment already exists",
                }

            try:
                scores = analyze_sentiment(
                    document.raw_text,
                    distilbert_model_name,
                )

                sentiment = DocumentSentiment(
                    document_id=doc_uuid,
                    vader=scores.get("vader"),
                    distilbert_score=scores.get("distilbert_score"),
                    distilbert_label=scores.get("distilbert_label"),
                    combined_score=scores.get("combined_score"),
                )
                db.add(sentiment)

                if not document.processed:
                    embedding_result = db.execute(
                        select(DocumentEmbedding).where(
                            DocumentEmbedding.document_id == doc_uuid,
                            DocumentEmbedding.model_name == DEFAULT_MODEL_NAME,
                        )
                    )
                    embedding_exists = embedding_result.scalar_one_or_none() is not None

                    if embedding_exists:
                        document.processed = True
                        document.processed_at = datetime.now(timezone.utc)
                        logger.info(
                            f"Marked document {doc_uuid} as processed "
                            f"(embedding and sentiment both exist)"
                        )

                db.commit()
                db.refresh(sentiment)

                logger.info(
                    f"Successfully created sentiment {sentiment.id} "
                    f"for document {doc_uuid}"
                )

                return {
                    "status": "completed",
                    "document_id": document_id,
                    "sentiment_id": str(sentiment.id),
                    "vader": sentiment.vader,
                    "distilbert_score": sentiment.distilbert_score,
                    "distilbert_label": sentiment.distilbert_label,
                    "combined_score": sentiment.combined_score,
                    "task_id": self.request.id,
                }
            except Exception:
                db.rollback()
                raise

    except ValueError as e:
        logger.error(f"Value error computing sentiment for document {doc_uuid}: {e}")
        raise
    except Exception as e:
        logger.error(
            f"Error computing sentiment for document {doc_uuid}: {e}",
            exc_info=True,
        )
        raise RuntimeError(f"Failed to compute sentiment: {e}") from e
