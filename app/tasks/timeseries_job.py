import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from celery import Task

from app.celery_app import celery_app
from app.db import get_sync_db
from app.ml.timeseries import build_timeseries_for_cluster
from app.models import Cluster, TimeseriesSummary

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.timeseries_job.compute_timeseries_summaries")
def compute_timeseries_summaries(
    self: Task,
    user_id: str | None = None,
    forecast_days: int = 7,
) -> dict[str, Any]:
    """
    Celery task to compute daily timeseries summaries and Prophet forecasts per cluster.

    This task:
      1. Selects clusters (optionally filtered by user)
      2. Computes daily mention_count, avg_sentiment, momentum, and forecast ranges
         using the ML helper in app.ml.timeseries
      3. Writes results into the `timeseries_summary` table, replacing any existing
         rows for the affected clusters to keep the operation idempotent.
    """
    logger.info(
        "Starting timeseries summaries job%s",
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
                message = "No clusters found to compute timeseries summaries"
                logger.warning(message)
                return {
                    "status": "skipped",
                    "message": message,
                    "user_id": user_id,
                    "clusters_processed": 0,
                    "rows_written": 0,
                }

            logger.info("Found %d clusters to process timeseries for", len(cluster_ids))

            total_rows_written = 0

            try:
                for cluster_id in cluster_ids:
                    summaries = build_timeseries_for_cluster(
                        db, cluster_id, forecast_days=forecast_days
                    )

                    db.execute(
                        sa.delete(TimeseriesSummary).where(
                            TimeseriesSummary.cluster_id == cluster_id
                        )
                    )

                    if not summaries:
                        logger.debug(
                            "No timeseries summaries for cluster %s, deleted any existing rows",
                            cluster_id,
                        )
                        continue

                    for row in summaries:
                        db.add(
                            TimeseriesSummary(
                                cluster_id=row["cluster_id"],
                                summary_date=row["summary_date"],
                                mention_count=row.get("mention_count", 0),
                                avg_sentiment=row.get("avg_sentiment"),
                                momentum=row.get("momentum"),
                                forecast_lower=row.get("forecast_lower"),
                                forecast_upper=row.get("forecast_upper"),
                            )
                        )

                    total_rows_written += len(summaries)

                db.commit()
            except Exception:
                db.rollback()
                raise

            logger.info(
                "Timeseries summaries job completed: %d clusters, %d rows written",
                len(cluster_ids),
                total_rows_written,
            )

            anomaly_job_enqueued = False
            if total_rows_written > 0:
                try:
                    celery_app.send_task(
                        "app.tasks.anomaly_job.detect_cluster_anomalies",
                        kwargs={"user_id": user_id},
                    )
                    anomaly_job_enqueued = True
                    logger.info(
                        "Enqueued anomaly detection job for user %s after timeseries job",
                        user_id if user_id else "all users",
                    )
                except Exception as anomaly_error:
                    logger.error(
                        "Failed to enqueue anomaly detection job: %s",
                        anomaly_error,
                        exc_info=True,
                    )

            return {
                "status": "completed",
                "user_id": user_id,
                "clusters_processed": len(cluster_ids),
                "rows_written": total_rows_written,
                "anomaly_job_enqueued": anomaly_job_enqueued,
                "task_id": self.request.id,
            }

    except ValueError as e:
        logger.error("Value error in timeseries summaries job: %s", e)
        raise
    except Exception as e:
        logger.error(
            "Error in timeseries summaries job: %s",
            e,
            exc_info=True,
        )
        raise RuntimeError(f"Failed to compute timeseries summaries: {e}") from e


