import logging
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Anomaly, Cluster

logger = logging.getLogger(__name__)


async def get_anomalies(
    user_id: UUID,
    db: AsyncSession,
    cluster_id: UUID | None = None,
    anomaly_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Anomaly], int]:
    """
    Get anomalies for a user with optional filters.

    Returns anomalies filtered by cluster, type, and date range.
    Only returns anomalies for clusters owned by the specified user.

    Args:
        user_id: User unique identifier
        db: Database session
        cluster_id: Optional cluster ID filter
        anomaly_type: Optional anomaly type filter
        start_date: Optional start date filter
        end_date: Optional end date filter
        limit: Maximum number of results (default: 100)
        offset: Number of results to skip (default: 0)

    Returns:
        Tuple of (list of anomalies, total count)
    """

    def apply_filters(query):
        """Apply optional filters to a query."""
        if cluster_id:
            query = query.where(Anomaly.cluster_id == cluster_id)
        if anomaly_type:
            query = query.where(Anomaly.type == anomaly_type)
        if start_date:
            query = query.where(Anomaly.anomaly_date >= start_date)
        if end_date:
            query = query.where(Anomaly.anomaly_date <= end_date)
        return query

    base_query = (
        select(Anomaly)
        .join(Cluster, Anomaly.cluster_id == Cluster.id)
        .where(Cluster.user_id == user_id)
    )
    base_query = apply_filters(base_query)

    count_query = (
        select(func.count(Anomaly.id))
        .join(Cluster, Anomaly.cluster_id == Cluster.id)
        .where(Cluster.user_id == user_id)
    )
    count_query = apply_filters(count_query)

    count_result = await db.execute(count_query)
    total = count_result.scalar_one() or 0

    data_query = (
        base_query.order_by(Anomaly.anomaly_date.desc(), Anomaly.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(data_query)
    anomalies = result.scalars().all()

    logger.info(
        f"Retrieved {len(anomalies)} anomalies for user {user_id} "
        f"(offset: {offset}, limit: {limit})"
    )

    return anomalies, total
