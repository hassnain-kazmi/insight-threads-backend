import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import numpy as np
from celery import Task
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select

from app.celery_app import celery_app
from app.db import get_sync_db
from app.ml.cluster import (
    compute_cluster_centroid,
    compute_hdbscan_clusters,
    extract_keywords,
)
from app.ml.embeddings import DEFAULT_MODEL_NAME
from app.models import (
    Cluster,
    ClusterMember,
    Document,
    DocumentEmbedding,
    DocumentSentiment,
    Keyword,
)

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
EXISTING_CLUSTER_SIMILARITY_THRESHOLD = 0.85


@celery_app.task(bind=True, name="app.tasks.cluster_job.run_clustering_job")
def run_clustering_job(
    self: Task,
    user_id: str | None = None,
    model_name: str = DEFAULT_MODEL_NAME,
    min_cluster_size: int = 3,
    min_samples: int = 2,
    cluster_selection_epsilon: float = 0.0,
    keyword_method: str = "tfidf",
    n_keywords: int = 10,
    process_recent_only: bool = False,
    days_recent: int = 7,
    existing_cluster_similarity_threshold: float = EXISTING_CLUSTER_SIMILARITY_THRESHOLD,
) -> dict[str, Any]:
    """
    Celery task to cluster document embeddings using HDBSCAN and extract keywords.

    This task:
    1. Retrieves document embeddings (optionally filtered by user and recency)
    2. Filters out documents that already have cluster memberships
    3. Assigns unclustered docs to existing clusters when similarity >= threshold
    4. Runs HDBSCAN on remaining unclustered embeddings
    5. Creates new Cluster records and ClusterMember records
    6. Extracts keywords for each new cluster; updates existing cluster centroid/count when assigning
    7. Calculates average sentiment per new cluster

    Args:
        user_id: Optional UUID of user to filter embeddings by. If None, processes all users.
        model_name: Name of the embedding model to use (default: DEFAULT_MODEL_NAME)
        min_cluster_size: Minimum size of clusters for HDBSCAN (default: 3)
        min_samples: Minimum samples in neighborhood for HDBSCAN (default: 2)
        cluster_selection_epsilon: Epsilon for cluster selection (default: 0.0)
        keyword_method: Keyword extraction method - "tfidf" or "keybert" (default: "tfidf")
        n_keywords: Number of keywords to extract per cluster (default: 10)
        process_recent_only: If True, only process documents from recent days (default: False)
        days_recent: Number of days to consider "recent" (default: 7)
        existing_cluster_similarity_threshold: Min cosine similarity to assign a doc to an existing cluster (default: 0.85)

    Returns:
        dict: Task result with status, counts, and metadata.
              Status can be "completed" or "skipped" (when no embeddings found).

    Raises:
        RuntimeError: If clustering or database operations fail
    """
    logger.info(
        f"Starting clustering job for model {model_name}"
        f"{f' (user_id: {user_id})' if user_id else ' (all users)'}"
    )

    try:
        with get_sync_db() as db:
            user_uuid = None
            if user_id is not None:
                try:
                    user_uuid = (
                        UUID(user_id)
                        if isinstance(user_id, str)
                        else UUID(str(user_id))
                    )
                except (ValueError, TypeError) as e:
                    logger.error(
                        "Invalid user_id in clustering job: %r",
                        user_id,
                        exc_info=True,
                    )
                    raise ValueError(f"Invalid user_id {user_id}") from e

            query = (
                select(DocumentEmbedding)
                .join(Document)
                .where(DocumentEmbedding.model_name == model_name)
            )

            if user_uuid:
                query = query.where(Document.user_id == user_uuid)

            if process_recent_only:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_recent)
                query = query.where(Document.created_at >= cutoff_date)

            clustered_docs_subquery = select(ClusterMember.document_id).distinct()
            query = query.where(~Document.id.in_(clustered_docs_subquery))

            result = db.execute(query)
            embeddings = result.unique().scalars().all()

            if not embeddings:
                error_msg = (
                    f"No unclustered embeddings found for model {model_name}"
                    f"{f' and user {user_uuid}' if user_uuid else ''}"
                    f"{f' (recent {days_recent} days)' if process_recent_only else ''}"
                )
                logger.warning(error_msg)
                return {
                    "status": "skipped",
                    "message": error_msg,
                    "model_name": model_name,
                    "user_id": user_id,
                    "clusters_created": 0,
                    "members_assigned_to_existing": 0,
                    "errors": [],
                }

            logger.info(f"Found {len(embeddings)} unclustered embeddings to cluster")

            doc_ids = [emb.document_id for emb in embeddings]
            docs_query = select(Document).where(Document.id.in_(doc_ids))
            docs_result = db.execute(docs_query)
            documents = {doc.id: doc for doc in docs_result.scalars().all()}

            embeddings_by_user: dict[UUID, list[DocumentEmbedding]] = {}
            for emb in embeddings:
                doc = documents.get(emb.document_id)
                if doc and doc.user_id:
                    if doc.user_id not in embeddings_by_user:
                        embeddings_by_user[doc.user_id] = []
                    embeddings_by_user[doc.user_id].append(emb)

            total_clusters_created = 0
            total_members_created = 0
            total_members_assigned_to_existing = 0
            total_keywords_created = 0
            cluster_errors: list[str] = []

            for uid, user_embeddings in embeddings_by_user.items():
                logger.info(
                    f"Processing {len(user_embeddings)} unclustered embeddings for user {uid}"
                )
                existing_clusters_result = db.execute(
                    select(Cluster).where(
                        Cluster.user_id == uid,
                        Cluster.centroid_384.isnot(None),
                    )
                )
                existing_clusters = existing_clusters_result.scalars().all()
                existing_centroids = [
                    (c.id, c.centroid_384, c.document_count) for c in existing_clusters
                ]

                assigned_doc_ids: set[UUID] = set()
                if existing_centroids:
                    for emb in user_embeddings:
                        vec = emb.embedding
                        if vec is None or len(vec) != EMBEDDING_DIM:
                            continue
                        doc_id = emb.document_id
                        best_cluster_id = None
                        best_sim = -1.0
                        for cluster_id, centroid, count in existing_centroids:
                            if centroid is None or len(centroid) != 384:
                                continue
                            sim = float(
                                cosine_similarity(
                                    np.array([centroid]), np.array([vec])
                                )[0][0]
                            )
                            if (
                                sim >= existing_cluster_similarity_threshold
                                and sim > best_sim
                            ):
                                best_sim = sim
                                best_cluster_id = cluster_id
                        if best_cluster_id is not None:
                            cluster = next(
                                c for c in existing_clusters if c.id == best_cluster_id
                            )
                            member = ClusterMember(
                                cluster_id=best_cluster_id,
                                document_id=doc_id,
                                membership_strength=best_sim,
                            )
                            db.add(member)
                            n = cluster.document_count + 1
                            old_c = cluster.centroid_384 or vec
                            new_centroid = [
                                (old_c[i] * (n - 1) + vec[i]) / n
                                for i in range(EMBEDDING_DIM)
                            ]
                            cluster.centroid_384 = new_centroid
                            cluster.document_count = n
                            assigned_doc_ids.add(doc_id)
                            total_members_assigned_to_existing += 1
                    if assigned_doc_ids:
                        logger.info(
                            f"Assigned {len(assigned_doc_ids)} docs to existing clusters for user {uid}"
                        )

                remaining = [
                    e for e in user_embeddings if e.document_id not in assigned_doc_ids
                ]
                if len(remaining) < min_cluster_size:
                    logger.debug(
                        f"User {uid}: {len(remaining)} remaining after assign-to-existing "
                        f"(min_cluster_size={min_cluster_size}), skipping HDBSCAN"
                    )
                    if assigned_doc_ids:
                        db.commit()
                    continue

                embedding_vectors = [emb.embedding for emb in remaining]
                document_ids = [emb.document_id for emb in remaining]

                try:
                    logger.info(
                        f"Computing HDBSCAN on {len(remaining)} remaining embeddings..."
                    )
                    cluster_labels, clusterer = compute_hdbscan_clusters(
                        embedding_vectors,
                        min_cluster_size=min_cluster_size,
                        min_samples=min_samples,
                        cluster_selection_epsilon=cluster_selection_epsilon,
                    )

                    clusters_dict: dict[int, list[tuple[UUID, list[float]]]] = {}
                    for label, doc_id, emb_vec in zip(
                        cluster_labels, document_ids, embedding_vectors
                    ):
                        if label != -1:
                            if label not in clusters_dict:
                                clusters_dict[label] = []
                            clusters_dict[label].append((doc_id, emb_vec))

                    if not clusters_dict:
                        logger.warning(
                            f"No clusters found for user {uid} (all points are noise)"
                        )
                        continue

                    logger.info(f"Found {len(clusters_dict)} clusters for user {uid}")

                    for cluster_label, members in clusters_dict.items():
                        member_doc_ids = [doc_id for doc_id, _ in members]
                        member_embeddings = [emb_vec for _, emb_vec in members]

                        centroid = compute_cluster_centroid(member_embeddings)

                        cluster_documents = [
                            documents[doc_id]
                            for doc_id in member_doc_ids
                            if doc_id in documents
                        ]

                        sentiments_query = select(DocumentSentiment).where(
                            DocumentSentiment.document_id.in_(member_doc_ids)
                        )
                        sentiments_result = db.execute(sentiments_query)
                        sentiments = sentiments_result.scalars().all()

                        avg_sentiment = None
                        if sentiments:
                            combined_scores = [
                                s.combined_score
                                for s in sentiments
                                if s.combined_score is not None
                            ]
                            if combined_scores:
                                avg_sentiment = sum(combined_scores) / len(
                                    combined_scores
                                )

                        cluster = Cluster(
                            user_id=uid,
                            centroid_384=centroid,
                            document_count=len(member_doc_ids),
                            avg_sentiment=avg_sentiment,
                            trending_score=None,
                        )
                        db.add(cluster)
                        db.flush()

                        centroid_array = np.array([centroid])
                        for doc_id, doc_emb in members:
                            doc_emb_array = np.array([doc_emb])
                            similarity = cosine_similarity(
                                centroid_array, doc_emb_array
                            )[0][0]
                            membership_strength = float(similarity)

                            member = ClusterMember(
                                cluster_id=cluster.id,
                                document_id=doc_id,
                                membership_strength=membership_strength,
                            )
                            db.add(member)

                        cluster_texts = [
                            doc.raw_text
                            for doc in cluster_documents
                            if doc.raw_text and doc.raw_text.strip()
                        ]

                        cluster_name = None
                        if cluster_texts:
                            try:
                                keywords = extract_keywords(
                                    cluster_texts,
                                    method=keyword_method,
                                    n_keywords=n_keywords,
                                )

                                for keyword, weight in keywords:
                                    keyword_obj = Keyword(
                                        cluster_id=cluster.id,
                                        keyword=keyword[:255],
                                        weight=float(weight),
                                    )
                                    db.add(keyword_obj)
                                    total_keywords_created += 1

                                if keywords:
                                    top_keywords = [kw[0] for kw in keywords[:3]]
                                    cluster_name = " • ".join(top_keywords)
                                    if len(cluster_name) > 255:
                                        cluster_name = cluster_name[:252] + "..."

                            except Exception as e:
                                logger.warning(
                                    f"Failed to extract keywords for cluster {cluster.id}: {e}",
                                    exc_info=True,
                                )

                        if cluster_name:
                            cluster.name = cluster_name
                            db.flush()

                        total_clusters_created += 1
                        total_members_created += len(member_doc_ids)

                    db.commit()
                    logger.info(
                        f"Successfully created {len(clusters_dict)} clusters for user {uid}"
                    )

                except Exception as e:
                    db.rollback()
                    err_msg = f"{uid}: {e}"
                    cluster_errors.append(err_msg)
                    logger.error(
                        f"Error clustering embeddings for user {uid}: {e}",
                        exc_info=True,
                    )
                    continue

            logger.info(
                f"Clustering job completed: {total_clusters_created} clusters, "
                f"{total_members_created} members, {total_keywords_created} keywords"
            )

            if total_clusters_created == 0 and total_members_assigned_to_existing == 0:
                return {
                    "status": "completed",
                    "model_name": model_name,
                    "user_id": user_id,
                    "embeddings_processed": len(embeddings),
                    "clusters_created": 0,
                    "members_created": 0,
                    "members_assigned_to_existing": 0,
                    "keywords_created": 0,
                    "timeseries_job_enqueued": False,
                    "umap_job_enqueued": False,
                    "task_id": self.request.id,
                    "errors": cluster_errors,
                }

            timeseries_job_enqueued = False
            umap_job_enqueued = False

            try:
                celery_app.send_task(
                    "app.tasks.timeseries_job.compute_timeseries_summaries",
                    kwargs={"user_id": user_id},
                )
                timeseries_job_enqueued = True
                logger.info(
                    f"Enqueued timeseries job {f'for user {user_id}' if user_id else 'for all users'} after clustering"
                )
            except Exception as ts_error:
                logger.error(
                    f"Failed to enqueue timeseries job: {ts_error}",
                    exc_info=True,
                )

            try:
                celery_app.send_task(
                    "app.tasks.umap_job.compute_umap_projections",
                    kwargs={
                        "user_id": user_id,
                        "model_name": model_name,
                    },
                )
                umap_job_enqueued = True
                logger.info(
                    f"Enqueued UMAP job {f'for user {user_id}' if user_id else 'for all users'} after clustering"
                )
            except Exception as umap_error:
                logger.error(
                    f"Failed to enqueue UMAP job: {umap_error}",
                    exc_info=True,
                )

            return {
                "status": "completed",
                "model_name": model_name,
                "user_id": user_id,
                "embeddings_processed": len(embeddings),
                "clusters_created": total_clusters_created,
                "members_created": total_members_created,
                "members_assigned_to_existing": total_members_assigned_to_existing,
                "keywords_created": total_keywords_created,
                "timeseries_job_enqueued": timeseries_job_enqueued,
                "umap_job_enqueued": umap_job_enqueued,
                "task_id": self.request.id,
                "errors": cluster_errors,
            }

    except ValueError as e:
        logger.error(f"Value error in clustering job: {e}")
        raise
    except Exception as e:
        logger.error(
            f"Error in clustering job: {e}",
            exc_info=True,
        )
        raise RuntimeError(f"Failed to run clustering job: {e}") from e
