import logging
from uuid import UUID

from celery import Task
from sqlalchemy import select

from app.celery_app import celery_app

from app.db import get_sync_db
from app.models import IngestEvent

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.ingest.process_ingestion")
def process_ingestion(self: Task, ingest_event_id: str, user_id: str) -> dict:
    """
    Celery task to process ingestion event.
    
    Args:
        ingest_event_id: UUID of the ingestion event
        user_id: UUID of the user initiating the ingestion
        
    Returns:
        dict: Task result with status and ingest_event_id
    """
    ingest_uuid = UUID(ingest_event_id)
    user_uuid = UUID(user_id)
    
    logger.info(f"Processing ingestion event {ingest_uuid} for user {user_uuid}")
    
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
            
            # TODO: Implement actual ingestion logic (Reddit, etc.)
            
            return {
                "status": "processing",
                "ingest_event_id": str(ingest_uuid),
                "task_id": self.request.id,
            }
            
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
            logger.error(f"Failed to update event status to failed: {db_error}")
        
        raise
