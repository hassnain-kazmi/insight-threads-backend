import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from celery import Task, chord, group
from sqlalchemy import select

from app.celery_app import celery_app

from app.db import get_sync_db
from app.models import (
    Document,
    DocumentEmbedding,
    DocumentSentiment,
    IngestEvent,
    UserIngestionPreference,
)
from app.ml.embeddings import DEFAULT_MODEL_NAME
from app.services.ingest.rss import DEFAULT_LIMIT as RSS_DEFAULT_LIMIT, ingest_feeds
from app.services.ingest.hackernews import (
    DEFAULT_LIMIT as HN_DEFAULT_LIMIT,
    ingest_posts,
)
from app.services.ingest.github import (
    DEFAULT_LIMIT as GITHUB_DEFAULT_LIMIT,
    ingest_repositories,
)

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.ingest_job.process_ingestion")
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
        dict: Task result with status, ingest_event_id, stats, and embedding_tasks_enqueued
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
                logger.error(
                    f"Ingest event {ingest_uuid} not found for user {user_uuid}"
                )
                raise ValueError(
                    f"Ingest event {ingest_uuid} not found or access denied"
                )

            event.status = "processing"
            db.commit()

            logger.info(f"Ingestion event {ingest_uuid} marked as processing")

            try:
                if source == "rss":
                    feed_urls = source_params.get("feed_urls", [])
                    if isinstance(feed_urls, str):
                        feed_urls = [feed_urls]
                    limit = source_params.get("limit", RSS_DEFAULT_LIMIT)

                    stats = ingest_feeds(
                        db=db,
                        ingest_event_id=ingest_uuid,
                        user_id=user_uuid,
                        feed_urls=feed_urls,
                        limit=limit,
                    )
                elif source == "hackernews":
                    endpoints = source_params.get("endpoints") or source_params.get("endpoint")
                    if endpoints is None:
                        endpoints = ["topstories"]
                    elif isinstance(endpoints, str):
                        endpoints = [endpoints]
                    
                    limit = source_params.get("limit_per_endpoint") or source_params.get(
                        "limit", HN_DEFAULT_LIMIT
                    )

                    stats = ingest_posts(
                        db=db,
                        ingest_event_id=ingest_uuid,
                        user_id=user_uuid,
                        endpoints=endpoints,
                        limit=limit,
                    )
                elif source == "github":
                    repos = source_params.get("repos")
                    
                    logger.info(f"GitHub repos parameter: {repos}, type: {type(repos)}")
                    
                    if repos is not None:
                        if not isinstance(repos, list):
                            try:
                                repos = list(repos) if hasattr(repos, '__iter__') and not isinstance(repos, str) else None
                                logger.info(f"Converted repos to list: {repos}")
                            except (TypeError, ValueError) as e:
                                logger.warning(f"Could not convert repos to list: {e}, repos={repos}")
                                repos = None
                    
                    if repos is None:
                        owner = source_params.get("owner") or ""
                        repo = source_params.get("repo") or ""
                        if not owner or not owner.strip() or not repo or not repo.strip():
                            raise ValueError(
                                "GitHub ingestion requires 'owner' and 'repo' parameters "
                                "(both non-empty), or 'repos' array"
                            )
                        repos = [{"owner": owner.strip(), "repo": repo.strip()}]
                    elif isinstance(repos, list):
                        if not repos:
                            raise ValueError("GitHub ingestion 'repos' array cannot be empty")
                        for repo_item in repos:
                            if not isinstance(repo_item, dict):
                                raise ValueError(
                                    "Each item in 'repos' array must be an object with 'owner' and 'repo'"
                                )
                            if "owner" not in repo_item or "repo" not in repo_item:
                                raise ValueError(
                                    "Each item in 'repos' array must have 'owner' and 'repo' fields"
                                )
                    else:
                        raise ValueError("GitHub ingestion 'repos' must be an array")

                    include_commits = source_params.get("include_commits", True)
                    include_issues = source_params.get("include_issues", True)
                    include_prs = source_params.get("include_prs", True)
                    include_releases = source_params.get("include_releases", True)
                    limit_per_type = source_params.get(
                        "limit_per_type", GITHUB_DEFAULT_LIMIT
                    )
                    commit_since = source_params.get("commit_since")
                    issue_state = source_params.get("issue_state", "all")
                    pr_state = source_params.get("pr_state", "all")

                    stats = ingest_repositories(
                        db=db,
                        ingest_event_id=ingest_uuid,
                        user_id=user_uuid,
                        repos=repos,
                        include_commits=include_commits,
                        include_issues=include_issues,
                        include_prs=include_prs,
                        include_releases=include_releases,
                        limit_per_type=limit_per_type,
                        commit_since=commit_since,
                        issue_state=issue_state,
                        pr_state=pr_state,
                    )
                else:
                    raise ValueError(f"Unsupported source type: {source}")

                db.refresh(event)
                event.status = "completed"
                event.completed_at = datetime.now(timezone.utc)
                
                # Save/update user ingestion preference for periodic ingestion
                preference_result = db.execute(
                    select(UserIngestionPreference).where(
                        UserIngestionPreference.user_id == user_uuid,
                        UserIngestionPreference.source == source,
                    )
                )
                preference = preference_result.scalar_one_or_none()
                
                if preference:
                    # Update existing preference
                    preference.source_params = source_params
                    # updated_at is automatically updated by onupdate=func.now()
                else:
                    # Create new preference
                    preference = UserIngestionPreference(
                        user_id=user_uuid,
                        source=source,
                        source_params=source_params,
                    )
                    db.add(preference)
                
                db.commit()

                logger.info(
                    f"Ingestion event {ingest_uuid} completed: "
                    f"{stats['new_documents']} new documents created"
                )

                documents_result = db.execute(
                    select(Document).where(Document.ingest_event_id == ingest_uuid)
                )
                documents = documents_result.scalars().all()

                embedding_tasks_enqueued = 0
                sentiment_tasks_enqueued = 0
                pipeline_enqueued = False

                if not documents:
                    logger.info(f"No documents found for ingestion event {ingest_uuid}")
                else:
                    document_ids = [doc.id for doc in documents]

                    existing_embeddings_result = db.execute(
                        select(DocumentEmbedding.document_id).where(
                            DocumentEmbedding.document_id.in_(document_ids),
                            DocumentEmbedding.model_name == DEFAULT_MODEL_NAME,
                        )
                    )
                    embedded_document_ids = set(
                        existing_embeddings_result.scalars().all()
                    )

                    existing_sentiments_result = db.execute(
                        select(DocumentSentiment.document_id).where(
                            DocumentSentiment.document_id.in_(document_ids),
                        )
                    )
                    sentiment_document_ids = set(
                        existing_sentiments_result.scalars().all()
                    )

                    embed_tasks = []
                    sentiment_tasks = []

                    for document in documents:
                        if not document.raw_text or not document.raw_text.strip():
                            logger.warning(
                                f"Skipping embedding/sentiment for document {document.id}: no text content"
                            )
                            continue

                        if document.id not in embedded_document_ids:
                            embed_tasks.append(
                                celery_app.signature(
                                    "app.tasks.embed_job.compute_document_embedding",
                                    args=[str(document.id), DEFAULT_MODEL_NAME],
                                )
                            )
                            embedding_tasks_enqueued += 1

                        if document.id not in sentiment_document_ids:
                            sentiment_tasks.append(
                                celery_app.signature(
                                    "app.tasks.sentiment_job.compute_document_sentiment",
                                    args=[str(document.id)],
                                )
                            )
                            sentiment_tasks_enqueued += 1

                    all_processing_tasks = embed_tasks + sentiment_tasks

                    if all_processing_tasks:
                        cluster_task = celery_app.signature(
                            "app.tasks.cluster_job.run_clustering_job",
                            kwargs={
                                "user_id": str(user_uuid),
                                "model_name": DEFAULT_MODEL_NAME,
                                "process_recent_only": False,
                            },
                            immutable=True,
                        )

                        try:
                            chord(group(all_processing_tasks))(cluster_task)
                            pipeline_enqueued = True
                            logger.info(
                                f"Enqueued pipeline: {len(all_processing_tasks)} embed/sentiment tasks → clustering"
                            )
                        except Exception as chord_error:
                            logger.error(
                                f"Failed to enqueue chord pipeline: {chord_error}",
                                exc_info=True,
                            )
                            for task in all_processing_tasks:
                                try:
                                    task.apply_async()
                                except Exception as task_error:
                                    logger.error(
                                        f"Failed to enqueue fallback task: {task_error}",
                                        exc_info=True,
                                    )

                return {
                    "status": "completed",
                    "ingest_event_id": str(ingest_uuid),
                    "task_id": self.request.id,
                    "stats": stats,
                    "embedding_tasks_enqueued": embedding_tasks_enqueued,
                    "sentiment_tasks_enqueued": sentiment_tasks_enqueued,
                    "pipeline_enqueued": pipeline_enqueued,
                }

            except Exception:
                db.rollback()
                raise

    except Exception as e:
        logger.error(
            f"Error processing ingestion event {ingest_uuid}: {e}", exc_info=True
        )

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
            logger.error(
                f"Failed to update event status to failed: {db_error}", exc_info=True
            )

        raise
