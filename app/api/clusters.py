import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User
from app.schemas.cluster import ClusterDetailResponse, ClusterResponse, ClustersListResponse
from app.services.cluster_service import get_cluster_detail, get_clusters
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.get("", status_code=status.HTTP_200_OK, response_model=ClustersListResponse)
async def get_clusters_endpoint(
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
        clusters, total = await get_clusters(
            user_id=current_user.id,
            db=db,
            limit=limit,
            offset=offset,
        )
        
        cluster_responses = [ClusterResponse.model_validate(cluster) for cluster in clusters]
        
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


@router.get("/{cluster_id}", status_code=status.HTTP_200_OK, response_model=ClusterDetailResponse)
async def get_cluster_detail_endpoint(
    cluster_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ClusterDetailResponse:
    """
    Get detailed information about a specific cluster.
    
    Returns cluster details including keywords and timeseries summaries.
    Only returns clusters owned by the authenticated user.
    
    Args:
        cluster_id: Cluster unique identifier (UUID)
        current_user: Authenticated user from JWT token
        db: Database session
        
    Returns:
        ClusterDetailResponse with cluster details and related data
        
    Raises:
        HTTPException: 404 if cluster not found or not owned by user
    """
    try:
        try:
            cluster_uuid = UUID(cluster_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cluster ID format",
            )
        
        cluster = await get_cluster_detail(
            cluster_id=cluster_uuid,
            user_id=current_user.id,
            db=db,
        )
        
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cluster not found",
            )
        
        return ClusterDetailResponse.model_validate(cluster)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving cluster {cluster_id} for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve cluster details",
        )

