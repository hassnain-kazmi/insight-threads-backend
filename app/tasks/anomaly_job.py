import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from celery import Task

from app.celery_app import celery_app
from app.db import get_sync_db
from app.ml.anomaly import detect_anomalies_for_cluster
from app.models import Anomaly, Cluster
from app.services.trending import DEFAULT_LOOKBACK_DAYS, calculate_trending_score

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.anomaly_job.detect_cluster_anomalies")
def detect_cluster_anomalies(
    self: Task,
    user_id: str | None = None,
    contamination: float = 0.1,
) -> dict[str, Any]:
    """
    Celery task to detect anomalies in volume and sentiment for clusters.

    This task:
      1. Selects clusters (optionally filtered by user)
      2. For each cluster, fetches timeseries data and runs PyOD anomaly detection
      3. Writes detected anomalies to the `anomalies` table
      4. Replaces existing anomalies for the affected clusters to keep the operation idempotent
      5. Updates trending scores for all processed clusters

    Args:
        user_id: Optional user ID to filter clusters
        contamination: Expected proportion of anomalies (default 0.1 = 10%, must be between 0 and 0.5)

    Returns:
        Dict with status, clusters_processed, anomalies_detected, task_id
    """
    logger.info(
        "Starting anomaly detection job%s",
        f" for user_id={user_id}" if user_id else " for all users",
    )

    try:
        with get_sync_db() as db:
            user_uuid: UUID | None = UUID(user_id) if user_id else None

            query = sa.select(Cluster.id)
            if user_uuid:
                query = query.where(Cluster.user_id == user_uuid)

            result = db.execute(query)
            cluster_ids = [row.id for row in result.all()]

            if not cluster_ids:
                message = "No clusters found for anomaly detection"
                logger.warning(message)
                return {
                    "status": "skipped",
                    "message": message,
                    "user_id": user_id,
                    "clusters_processed": 0,
                    "anomalies_detected": 0,
                }

            logger.info("Found %d clusters to process for anomalies", len(cluster_ids))

            total_anomalies = 0

            try:
                for cluster_id in cluster_ids:
                    anomalies = detect_anomalies_for_cluster(
                        db, cluster_id, contamination=contamination
                    )

                    db.execute(
                        sa.delete(Anomaly).where(Anomaly.cluster_id == cluster_id)
                    )

                    if not anomalies:
                        logger.debug(
                            "No anomalies detected for cluster %s, deleted any existing rows",
                            cluster_id,
                        )
                    else:
                        for anomaly_data in anomalies:
                            db.add(
                                Anomaly(
                                    cluster_id=cluster_id,
                                    anomaly_date=anomaly_data["date"],
                                    score=anomaly_data["score"],
                                    type=anomaly_data["type"],
                                    anomaly_metadata=anomaly_data.get("metadata"),
                                )
                            )

                        total_anomalies += len(anomalies)
                        logger.debug(
                            "Detected %d anomalies for cluster %s",
                            len(anomalies),
                            cluster_id,
                        )

                    try:
                        trending_score = calculate_trending_score(
                            cluster_id=cluster_id,
                            db=db,
                            lookback_days=DEFAULT_LOOKBACK_DAYS,
                        )
                        db.execute(
                            sa.update(Cluster)
                            .where(Cluster.id == cluster_id)
                            .values(trending_score=trending_score)
                        )
                        logger.debug(
                            "Updated trending score for cluster %s: %.4f",
                            cluster_id,
                            trending_score,
                        )
                    except Exception as trending_error:
                        logger.warning(
                            "Failed to calculate trending score for cluster %s: %s",
                            cluster_id,
                            trending_error,
                            exc_info=True,
                        )

                db.commit()
            except Exception:
                db.rollback()
                raise

            logger.info(
                "Anomaly detection job completed: %d clusters, %d anomalies detected",
                len(cluster_ids),
                total_anomalies,
            )

            insight_job_enqueued = False
            if len(cluster_ids) > 0:
                try:
                    celery_app.send_task(
                        "app.tasks.insight_job.generate_cluster_insights",
                        kwargs={"user_id": user_id},
                    )
                    insight_job_enqueued = True
                    logger.info(
                        "Enqueued insight generation job for user %s after anomaly detection",
                        user_id if user_id else "all users",
                    )
                except Exception as insight_error:
                    logger.error(
                        "Failed to enqueue insight generation job: %s",
                        insight_error,
                        exc_info=True,
                    )

            return {
                "status": "completed",
                "user_id": user_id,
                "clusters_processed": len(cluster_ids),
                "anomalies_detected": total_anomalies,
                "insight_job_enqueued": insight_job_enqueued,
                "task_id": self.request.id,
            }

    except ValueError as e:
        logger.error("Value error in anomaly detection job: %s", e)
        raise
    except Exception as e:
        logger.error(
            "Error in anomaly detection job: %s",
            e,
            exc_info=True,
        )
        raise RuntimeError(f"Failed to detect anomalies: {e}") from e

