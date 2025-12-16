import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Cluster, User
from app.schemas.cluster import ClusterResponse, ClustersListResponse
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.get("", status_code=status.HTTP_200_OK, response_model=ClustersListResponse)
async def get_clusters(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
) -> ClustersListResponse:
    """
    Get clusters for the authenticated user, ordered by trending score (descending).
    
    Returns clusters sorted by trending_score in descending order, with highest
    trending clusters first.
    
    Args:
        current_user: Authenticated user from JWT token
        db: Database session
        limit: Maximum number of clusters to return (default: 100)
        offset: Number of clusters to skip (default: 0)
        
    Returns:
        ClustersListResponse with clusters ordered by trending_score
    """
    try:
        query = (
            select(Cluster)
            .where(Cluster.user_id == current_user.id)
            .order_by(Cluster.trending_score.desc().nulls_last())
            .limit(limit)
            .offset(offset)
        )
        
        result = await db.execute(query)
        clusters = result.scalars().all()
        
        count_query = select(func.count(Cluster.id)).where(Cluster.user_id == current_user.id)
        count_result = await db.execute(count_query)
        total = count_result.scalar_one() or 0
        
        cluster_responses = [ClusterResponse.model_validate(cluster) for cluster in clusters]
        
        logger.info(
            f"Retrieved {len(cluster_responses)} clusters for user {current_user.id} "
            f"(offset: {offset}, limit: {limit})"
        )
        
        return ClustersListResponse(
            clusters=cluster_responses,
            total=total,
        )
        
    except Exception as e:
        logger.error(f"Error retrieving clusters for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve clusters",
        )

