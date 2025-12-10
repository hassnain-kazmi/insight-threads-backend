import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app

from app.models import IngestEvent, User

logger = logging.getLogger(__name__)


class IngestService:
    """Service for handling ingestion operations."""

    @staticmethod
    async def create_and_enqueue_ingestion(
        user: User,
        db: AsyncSession,
    ) -> tuple[IngestEvent, str]:
        """
        Create an ingestion event and enqueue the processing task.
        
        Args:
            user: The user initiating the ingestion
            db: Database session
            
        Returns:
            Tuple of (IngestEvent, task_id)
            
        Raises:
            Exception: If task enqueue fails (e.g., Celery unavailable) or database operation fails
        """
        ingest_event = IngestEvent(
            user_id=user.id,
            status="pending",
        )
        db.add(ingest_event)
        await db.flush()
        
        try:
            task = celery_app.send_task(
                "app.tasks.ingest.process_ingestion",
                args=[str(ingest_event.id), str(user.id)],
            )
        except Exception as celery_error:
            await db.rollback()
            logger.error(f"Failed to enqueue Celery task: {celery_error}", exc_info=True)
            raise
        
        await db.commit()
        await db.refresh(ingest_event)
        
        logger.info(
            f"Created ingestion event {ingest_event.id} for user {user.id}, "
            f"task_id: {task.id}"
        )
        
        return ingest_event, task.id

