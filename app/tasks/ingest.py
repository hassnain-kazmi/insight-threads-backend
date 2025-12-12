import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from celery import Task
from sqlalchemy import select

from app.celery_app import celery_app

from app.db import get_sync_db
from app.models import IngestEvent
from app.services.ingest.hackernews import DEFAULT_LIMIT as HN_DEFAULT_LIMIT, ingest_posts
from app.services.ingest.rss import DEFAULT_LIMIT, ingest_feeds

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.ingest.process_ingestion")
def process_ingestion(
    self: Task,
    ingest_event_id: str,
    user_id: str,
    source: str = "rss",
    source_params: dict | None = None,
) -> dict[str, Any]:
    """
    Celery task to process ingestion event.
    
    Args:
        ingest_event_id: UUID of the ingestion event
        user_id: UUID of the user initiating the ingestion
        source: Source type (e.g., 'rss')
        source_params: Source-specific parameters
        
    Returns:
        dict: Task result with status and ingest_event_id
    """
    ingest_uuid = UUID(ingest_event_id)
    user_uuid = UUID(user_id)
    source_params = source_params or {}
    
    logger.info(
        f"Processing ingestion event {ingest_uuid} for user {user_uuid}, "
        f"source: {source}, params: {source_params}"
    )
    
    try:
        with get_sync_db() as db:
            result = db.execute(
                select(IngestEvent).where(
                    IngestEvent.id == ingest_uuid,
                    IngestEvent.user_id == user_uuid,
                )
            )
            event = result.scalar_one_or_none()
            
            if not event:
                logger.error(f"Ingest event {ingest_uuid} not found for user {user_uuid}")
                raise ValueError(f"Ingest event {ingest_uuid} not found or access denied")
            
            event.status = "processing"
            db.commit()
            
            logger.info(f"Ingestion event {ingest_uuid} marked as processing")
            
            try:
                if source == "rss":
                    feed_urls = source_params.get("feed_urls", [])
                    if isinstance(feed_urls, str):
                        feed_urls = [feed_urls]
                    limit = source_params.get("limit", DEFAULT_LIMIT)
                    
                    stats = ingest_feeds(
                        db=db,
                        ingest_event_id=ingest_uuid,
                        user_id=user_uuid,
                        feed_urls=feed_urls,
                        limit=limit,
                    )
                elif source == "hackernews":
                    endpoint = source_params.get("endpoint", "topstories")
                    limit = source_params.get("limit", HN_DEFAULT_LIMIT)
                    
                    stats = ingest_posts(
                        db=db,
                        ingest_event_id=ingest_uuid,
                        user_id=user_uuid,
                        endpoint=endpoint,
                        limit=limit,
                    )
                else:
                    raise ValueError(f"Unsupported source type: {source}")
                
                db.refresh(event)
                event.status = "completed"
                event.completed_at = datetime.now(timezone.utc)
                
                logger.info(
                    f"Ingestion event {ingest_uuid} completed: "
                    f"{stats['new_documents']} new documents created"
                )
                
                return {
                    "status": "completed",
                    "ingest_event_id": str(ingest_uuid),
                    "task_id": self.request.id,
                    "stats": stats,
                }
                    
            except Exception:
                db.rollback()
                raise
            
    except Exception as e:
        logger.error(f"Error processing ingestion event {ingest_uuid}: {e}", exc_info=True)
        
        try:
            with get_sync_db() as db:
                result = db.execute(
                    select(IngestEvent).where(IngestEvent.id == ingest_uuid)
                )
                event = result.scalar_one_or_none()
                if event:
                    event.status = "failed"
                    event.error_message = str(e)
                    db.commit()
        except Exception as db_error:
            logger.error(f"Failed to update event status to failed: {db_error}", exc_info=True)
        
        raise
