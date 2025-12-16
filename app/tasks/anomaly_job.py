import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from celery import Task

from app.celery_app import celery_app
from app.db import get_sync_db
from app.ml.anomaly import detect_anomalies_for_cluster
from app.models import Anomaly, Cluster

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
                        continue

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

                db.commit()
            except Exception:
                db.rollback()
                raise

            logger.info(
                "Anomaly detection job completed: %d clusters, %d anomalies detected",
                len(cluster_ids),
                total_anomalies,
            )

            return {
                "status": "completed",
                "user_id": user_id,
                "clusters_processed": len(cluster_ids),
                "anomalies_detected": total_anomalies,
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

