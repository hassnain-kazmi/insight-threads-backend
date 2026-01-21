import json
import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from celery import Task
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db import get_sync_db
from app.models import Anomaly, Cluster, ClusterMember, Document, Insight, Keyword
from app.services.llm_client import OllamaClient, OllamaError, get_ollama_client

logger = logging.getLogger(__name__)

MAX_DOCUMENT_SAMPLES = 5
MAX_KEYWORDS = 10


@celery_app.task(bind=True, name="app.tasks.insight_job.generate_cluster_insights")
def generate_cluster_insights(
    self: Task,
    user_id: str | None = None,
    cluster_id: str | None = None,
    template_name: str = "insight_template_brief",
) -> dict[str, Any]:
    """
    Celery task to generate insights for clusters using Ollama LLM.

    This task:
      1. Selects clusters (optionally filtered by user or specific cluster)
      2. For each cluster, checks if an insight already exists (skips if found)
      3. If no insight exists, gathers keywords, document samples, sentiment, and anomalies
      4. Calls Ollama to generate an insight
      5. Stores the insight in the `insights` table

    Args:
        user_id: Optional user ID to filter clusters
        cluster_id: Optional specific cluster ID to process
        template_name: Prompt template to use (default: "insight_template_brief")

    Returns:
        Dict with status, clusters_processed, insights_generated, task_id
    """
    logger.info(
        "Starting insight generation job%s%s",
        f" for user_id={user_id}" if user_id else "",
        f" for cluster_id={cluster_id}" if cluster_id else "",
    )

    try:
        client = get_ollama_client()

        if not client.health_check():
            logger.error("Ollama service is not available")
            return {
                "status": "error",
                "message": "Ollama service unavailable",
                "task_id": self.request.id,
            }

        with get_sync_db() as db:
            user_uuid: UUID | None = UUID(user_id) if user_id else None
            cluster_uuid: UUID | None = UUID(cluster_id) if cluster_id else None

            query = sa.select(Cluster)
            if cluster_uuid:
                query = query.where(Cluster.id == cluster_uuid)
            elif user_uuid:
                query = query.where(Cluster.user_id == user_uuid)

            result = db.execute(query)
            clusters = result.scalars().all()

            if not clusters:
                message = "No clusters found for insight generation"
                logger.warning(message)
                return {
                    "status": "skipped",
                    "message": message,
                    "user_id": user_id,
                    "cluster_id": cluster_id,
                    "clusters_processed": 0,
                    "insights_generated": 0,
                }

            logger.info("Found %d clusters to process for insights", len(clusters))

            insights_generated = 0
            insights_skipped = 0
            errors = []

            try:
                for cluster in clusters:
                    try:
                        existing_insight = db.execute(
                            sa.select(Insight).where(Insight.cluster_id == cluster.id)
                        ).scalar_one_or_none()

                        if existing_insight:
                            insights_skipped += 1
                            logger.debug(
                                "Insight already exists for cluster %s, skipping generation",
                                cluster.id,
                            )
                            continue

                        insight = _generate_insight_for_cluster(
                            db=db,
                            client=client,
                            cluster=cluster,
                            template_name=template_name,
                        )

                        if insight:
                            db.add(insight)
                            insights_generated += 1
                            logger.debug(
                                "Generated insight for cluster %s",
                                cluster.id,
                            )

                    except OllamaError as e:
                        error_msg = f"Cluster {cluster.id}: {e}"
                        logger.warning("LLM error: %s", error_msg)
                        errors.append(error_msg)

                    except Exception as e:
                        error_msg = f"Cluster {cluster.id}: {e}"
                        logger.error(
                            "Unexpected error generating insight: %s",
                            error_msg,
                            exc_info=True,
                        )
                        errors.append(error_msg)

                db.commit()

            except Exception:
                db.rollback()
                raise

            logger.info(
                "Insight generation job completed: %d clusters, %d insights generated, %d skipped, %d errors",
                len(clusters),
                insights_generated,
                insights_skipped,
                len(errors),
            )

            return {
                "status": "completed",
                "user_id": user_id,
                "cluster_id": cluster_id,
                "clusters_processed": len(clusters),
                "insights_generated": insights_generated,
                "insights_skipped": insights_skipped,
                "errors": errors if errors else None,
                "task_id": self.request.id,
            }

    except ValueError as e:
        logger.error("Value error in insight generation job: %s", e)
        raise

    except Exception as e:
        logger.error(
            "Error in insight generation job: %s",
            e,
            exc_info=True,
        )
        raise RuntimeError(f"Failed to generate insights: {e}") from e


def _generate_insight_for_cluster(
    db: Session,
    client: OllamaClient,
    cluster: Cluster,
    template_name: str,
) -> Insight | None:
    """
    Generate an insight for a single cluster.

    Args:
        db: Database session
        client: Ollama client
        cluster: Cluster to generate insight for
        template_name: Prompt template name

    Returns:
        Insight model instance or None if generation failed
    """
    keywords_query = (
        sa.select(Keyword.keyword)
        .where(Keyword.cluster_id == cluster.id)
        .order_by(Keyword.weight.desc().nulls_last())
        .limit(MAX_KEYWORDS)
    )
    keywords_result = db.execute(keywords_query)
    keywords = [row[0] for row in keywords_result.all()]

    if not keywords:
        logger.debug("No keywords found for cluster %s, skipping", cluster.id)
        return None

    members_query = (
        sa.select(ClusterMember.document_id)
        .where(ClusterMember.cluster_id == cluster.id)
        .order_by(ClusterMember.membership_strength.desc().nulls_last())
        .limit(MAX_DOCUMENT_SAMPLES)
    )
    members_result = db.execute(members_query)
    document_ids = [row[0] for row in members_result.all()]

    document_samples = []
    if document_ids:
        docs_query = sa.select(Document.raw_text).where(Document.id.in_(document_ids))
        docs_result = db.execute(docs_query)
        document_samples = [row[0] for row in docs_result.all() if row[0]]

    if not document_samples:
        logger.debug("No document samples for cluster %s, skipping", cluster.id)
        return None

    anomalies_query = (
        sa.select(Anomaly)
        .where(Anomaly.cluster_id == cluster.id)
        .order_by(Anomaly.anomaly_date.desc())
        .limit(3)
    )
    anomalies_result = db.execute(anomalies_query)
    anomalies = anomalies_result.scalars().all()

    anomaly_info = None
    if anomalies:
        anomaly_parts = [
            f"{a.type} anomaly on {a.anomaly_date} (score: {a.score:.2f})"
            for a in anomalies
        ]
        anomaly_info = "; ".join(anomaly_parts)

    response = client.generate_insight(
        cluster_keywords=keywords,
        document_samples=document_samples,
        avg_sentiment=cluster.avg_sentiment,
        document_count=cluster.document_count,
        anomaly_info=anomaly_info,
        template_name=template_name,
    )

    metadata = {
        "model": response.model,
        "duration_ms": response.total_duration_ms,
        "eval_count": response.eval_count,
        "template": template_name,
    }

    insight = Insight(
        cluster_id=cluster.id,
        insight_text=response.content.strip(),
        confidence=_calculate_confidence(response),
        llm_metadata=json.dumps(metadata),
    )

    if not cluster.name:
        try:
            name_response = client.generate_cluster_name(
                cluster_keywords=keywords,
                document_samples=document_samples,
                avg_sentiment=cluster.avg_sentiment,
                document_count=cluster.document_count,
            )
            generated_name = name_response.content.strip()
            generated_name = generated_name.strip('"\'')
            generated_name = " ".join(generated_name.split())
            if len(generated_name) > 255:
                generated_name = generated_name[:252] + "..."
            if generated_name:
                cluster.name = generated_name
                logger.debug(
                    "Generated LLM-based name for cluster %s: %s",
                    cluster.id,
                    generated_name,
                )
        except Exception as e:
            logger.warning(
                "Failed to generate cluster name for cluster %s: %s",
                cluster.id,
                e,
                exc_info=True,
            )

    return insight

def _calculate_confidence(response: Any) -> float:
    """
    Calculate confidence score for generated insight.

    Based on response characteristics like token count and generation time.
    """
    base_confidence = 0.7

    if response.eval_count:
        if response.eval_count >= 100:
            base_confidence += 0.1
        elif response.eval_count < 30:
            base_confidence -= 0.1

    return max(0.1, min(1.0, base_confidence))


@celery_app.task(name="app.tasks.insight_job.generate_single_insight")
def generate_single_insight(
    cluster_id: str,
    template_name: str = "insight_template_brief",
) -> dict[str, Any]:
    """
    Generate insight for a single cluster.

    Convenience task for single cluster processing. Directly invokes
    the generation logic rather than delegating to the batch task.

    Args:
        cluster_id: UUID of the cluster
        template_name: Prompt template to use

    Returns:
        Dict with status and generated insight
    """
    logger.info("Generating single insight for cluster_id=%s", cluster_id)

    try:
        client = get_ollama_client()

        if not client.health_check():
            logger.error("Ollama service is not available")
            return {
                "status": "error",
                "message": "Ollama service unavailable",
            }

        with get_sync_db() as db:
            cluster_uuid = UUID(cluster_id)

            result = db.execute(sa.select(Cluster).where(Cluster.id == cluster_uuid))
            cluster = result.scalar_one_or_none()

            if not cluster:
                return {
                    "status": "skipped",
                    "message": f"Cluster {cluster_id} not found",
                    "cluster_id": cluster_id,
                }

            existing_insight = db.execute(
                sa.select(Insight).where(Insight.cluster_id == cluster.id)
            ).scalar_one_or_none()

            if existing_insight:
                logger.info(
                    "Insight already exists for cluster %s, skipping generation",
                    cluster_id,
                )
                return {
                    "status": "skipped",
                    "message": "Insight already exists for this cluster",
                    "cluster_id": cluster_id,
                    "insight_text": existing_insight.insight_text,
                }

            try:
                insight = _generate_insight_for_cluster(
                    db=db,
                    client=client,
                    cluster=cluster,
                    template_name=template_name,
                )

                if insight:
                    db.add(insight)
                    db.commit()

                    return {
                        "status": "completed",
                        "cluster_id": cluster_id,
                        "insight_text": insight.insight_text,
                    }

                return {
                    "status": "skipped",
                    "message": "No keywords or documents to generate insight",
                    "cluster_id": cluster_id,
                }

            except OllamaError as e:
                logger.warning("LLM error for cluster %s: %s", cluster_id, e)
                return {
                    "status": "error",
                    "message": str(e),
                    "cluster_id": cluster_id,
                }
            except Exception as e:
                logger.error(
                    "Unexpected error generating insight for cluster %s: %s",
                    cluster_id,
                    e,
                    exc_info=True,
                )
                raise RuntimeError(f"Failed to generate insight: {e}") from e

    except ValueError as e:
        logger.error("Invalid cluster_id: %s", e)
        raise

    except Exception as e:
        logger.error("Error generating insight: %s", e, exc_info=True)
        raise RuntimeError(f"Failed to generate insight: {e}") from e
