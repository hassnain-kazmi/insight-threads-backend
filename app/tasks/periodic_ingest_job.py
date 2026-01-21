import logging
from typing import Any

from sqlalchemy import select

from app.celery_app import celery_app
from app.db import get_sync_db
from app.models import IngestEvent, User, UserIngestionPreference

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.periodic_ingest_job.trigger_periodic_ingestion")
def trigger_periodic_ingestion() -> dict[str, Any]:
    """
    Periodic task to trigger ingestion for all users every 24 hours.
    
    For each user, it uses their saved ingestion preferences to determine
    what sources to ingest. Each preference represents a source type and
    its parameters that the user has successfully ingested from before.
    
    Returns:
        dict: Summary of triggered ingestions
    """
    logger.info("Starting periodic ingestion for all users")
    
    triggered_count = 0
    skipped_count = 0
    error_count = 0
    errors = []
    
    try:
        with get_sync_db() as db:
            users_result = db.execute(select(User))
            users = users_result.scalars().all()
            
            logger.info(f"Found {len(users)} users for periodic ingestion")
            
            for user in users:
                try:
                    preferences_result = db.execute(
                        select(UserIngestionPreference).where(
                            UserIngestionPreference.user_id == user.id
                        )
                    )
                    preferences = preferences_result.scalars().all()
                    
                    if not preferences:
                        logger.debug(
                            f"No ingestion preferences found for user {user.id}, skipping"
                        )
                        skipped_count += 1
                        continue
                    
                    user_triggered = 0
                    for preference in preferences:
                        try:
                            new_event = IngestEvent(
                                user_id=user.id,
                                source=preference.source,
                                status="pending",
                            )
                            db.add(new_event)
                            db.flush()
                            
                            task = celery_app.send_task(
                                "app.tasks.ingest_job.process_ingestion",
                                args=[
                                    str(new_event.id),
                                    str(user.id),
                                    preference.source,
                                    preference.source_params,
                                ],
                            )
                            
                            db.commit()
                            
                            logger.info(
                                f"Triggered periodic ingestion for user {user.id}, "
                                f"event: {new_event.id}, task: {task.id}, source: {preference.source}"
                            )
                            user_triggered += 1
                            triggered_count += 1
                            
                        except Exception as preference_error:
                            db.rollback()
                            error_msg = (
                                f"Error triggering ingestion for user {user.id}, "
                                f"source: {preference.source}: {str(preference_error)}"
                            )
                            logger.error(error_msg, exc_info=True)
                            errors.append(error_msg)
                            error_count += 1
                    
                    if user_triggered == 0:
                        skipped_count += 1
                    
                except Exception as user_error:
                    db.rollback()
                    error_msg = f"Error processing user {user.id}: {str(user_error)}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)
                    error_count += 1
            
            summary = {
                "status": "completed",
                "total_users": len(users),
                "triggered": triggered_count,
                "skipped": skipped_count,
                "errors": error_count,
                "error_details": errors if errors else None,
            }
            
            logger.info(
                f"Periodic ingestion completed: {triggered_count} triggered, "
                f"{skipped_count} skipped, {error_count} errors"
            )
            
            return summary
            
    except Exception as e:
        logger.error(f"Fatal error in periodic ingestion: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
            "triggered": triggered_count,
            "skipped": skipped_count,
            "errors": error_count,
        }
