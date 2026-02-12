import logging
from typing import Any
from uuid import UUID

from celery import Task
from sqlalchemy import select

from app.celery_app import celery_app
from app.db import get_sync_db
from app.ml.embeddings import DEFAULT_MODEL_NAME
from app.ml.umap import compute_umap_projection
from app.models import Document, DocumentEmbedding, UMAPProjection

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.umap_job.compute_umap_projections")
def compute_umap_projections(
    self: Task,
    user_id: str | None = None,
    model_name: str = DEFAULT_MODEL_NAME,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    random_state: int | None = None,
) -> dict[str, Any]:
    """
    Celery task to compute and save 2D UMAP projections for document embeddings.

    This task:
    1. Retrieves all document embeddings for the specified model (optionally filtered by user)
    2. Computes 2D UMAP projection
    3. Saves projections to umap_projections table

    Args:
        user_id: Optional UUID of user to filter embeddings by. If None, processes all embeddings.
        model_name: Name of the embedding model to use (default: DEFAULT_MODEL_NAME)
        n_neighbors: Number of neighbors for UMAP (default: 15)
        min_dist: Minimum distance for UMAP (default: 0.1)
        random_state: Random seed for reproducibility (default: None)

    Returns:
        dict: Task result with status, counts, and metadata.
              Status can be "completed" or "skipped" (when no embeddings found).

    Raises:
        RuntimeError: If UMAP computation or database operations fail
    """
    logger.info(
        f"Starting UMAP projection job for model {model_name}"
        f"{f' (user_id: {user_id})' if user_id else ' (all users)'}"
    )

    try:
        with get_sync_db() as db:
            user_uuid: UUID | None = None
            if user_id:
                try:
                    user_uuid = UUID(user_id)
                except (ValueError, TypeError) as e:
                    logger.error("Invalid user_id for UMAP job: %r (%s)", user_id, e)
                    raise ValueError(f"Invalid user_id format: {user_id}") from e

            query = select(DocumentEmbedding).where(
                DocumentEmbedding.model_name == model_name
            )

            if user_uuid:
                query = query.join(Document).where(Document.user_id == user_uuid)

            result = db.execute(query)
            embeddings = result.scalars().all()

            if not embeddings:
                error_msg = (
                    f"No embeddings found for model {model_name}"
                    f"{f' and user {user_uuid}' if user_uuid else ''}"
                )
                logger.warning(error_msg)
                return {
                    "status": "skipped",
                    "message": error_msg,
                    "model_name": model_name,
                    "user_id": user_id,
                    "projections_created": 0,
                }

            logger.info(f"Found {len(embeddings)} embeddings to project")

            embedding_vectors = [emb.embedding for emb in embeddings]
            document_ids = [emb.document_id for emb in embeddings]

            try:
                logger.info("Computing UMAP projection...")
                coordinates = compute_umap_projection(
                    embedding_vectors,
                    n_neighbors=n_neighbors,
                    min_dist=min_dist,
                    random_state=random_state,
                )

                logger.info(
                    f"Computed {len(coordinates)} projections, saving to database..."
                )

                if len(coordinates) != len(document_ids):
                    raise RuntimeError(
                        f"Mismatch between coordinates ({len(coordinates)}) "
                        f"and document_ids ({len(document_ids)})"
                    )

                existing_projections_query = select(UMAPProjection).where(
                    UMAPProjection.document_id.in_(document_ids),
                    UMAPProjection.model_name == model_name,
                )
                existing_projections_result = db.execute(existing_projections_query)
                existing_projections = existing_projections_result.scalars().all()
                existing_by_doc_id = {
                    proj.document_id: proj for proj in existing_projections
                }

                projections_created = 0
                projections_updated = 0

                for doc_id, (x, y) in zip(document_ids, coordinates):
                    existing = existing_by_doc_id.get(doc_id)

                    if existing:
                        existing.x = x
                        existing.y = y
                        projections_updated += 1
                    else:
                        projection = UMAPProjection(
                            document_id=doc_id,
                            model_name=model_name,
                            x=x,
                            y=y,
                        )
                        db.add(projection)
                        projections_created += 1

                db.commit()

                logger.info(
                    f"Successfully saved UMAP projections: "
                    f"{projections_created} created, {projections_updated} updated"
                )

                return {
                    "status": "completed",
                    "model_name": model_name,
                    "user_id": user_id,
                    "embeddings_processed": len(embeddings),
                    "projections_created": projections_created,
                    "projections_updated": projections_updated,
                    "task_id": self.request.id,
                }

            except Exception:
                db.rollback()
                raise

    except ValueError as e:
        logger.error(f"Value error in UMAP projection job: {e}")
        raise
    except Exception as e:
        logger.error(
            f"Error in UMAP projection job: {e}",
            exc_info=True,
        )
        raise RuntimeError(f"Failed to compute UMAP projections: {e}") from e
