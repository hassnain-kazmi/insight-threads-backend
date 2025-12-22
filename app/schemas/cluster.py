from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.anomaly import AnomalyResponse
from app.schemas.insight import InsightResponse


class ClusterResponse(BaseModel):
    """Response model for cluster."""
    
    id: UUID = Field(..., description="Cluster unique identifier")
    user_id: UUID = Field(..., description="User unique identifier")
    document_count: int = Field(..., description="Number of documents in cluster")
    avg_sentiment: float | None = Field(None, description="Average sentiment score")
    trending_score: float | None = Field(None, description="Trending score (0.0 to 1.0)")
    created_at: datetime = Field(..., description="Cluster creation timestamp")
    updated_at: datetime = Field(..., description="Cluster last update timestamp")
    
    model_config = {"from_attributes": True}


class ClustersListResponse(BaseModel):
    """Response model for clusters list."""
    
    clusters: list[ClusterResponse] = Field(..., description="List of clusters ordered by trending score")
    total: int = Field(..., description="Total number of clusters")


class KeywordResponse(BaseModel):
    """Response model for keyword."""
    
    id: UUID = Field(..., description="Keyword unique identifier")
    keyword: str = Field(..., description="Keyword text")
    weight: float | None = Field(None, description="Keyword weight/importance")
    created_at: datetime = Field(..., description="Keyword creation timestamp")
    
    model_config = {"from_attributes": True}


class TimeseriesSummaryResponse(BaseModel):
    """Response model for timeseries summary."""
    
    id: UUID = Field(..., description="Timeseries summary unique identifier")
    summary_date: date = Field(..., description="Date of the summary")
    mention_count: int = Field(..., description="Number of mentions on this date")
    avg_sentiment: float | None = Field(None, description="Average sentiment for this date")
    momentum: float | None = Field(None, description="Momentum value")
    forecast_lower: float | None = Field(None, description="Forecast lower bound")
    forecast_upper: float | None = Field(None, description="Forecast upper bound")
    created_at: datetime = Field(..., description="Timeseries summary creation timestamp")
    
    model_config = {"from_attributes": True}


class ClusterDetailResponse(BaseModel):
    """Response model for cluster detail with related data."""
    
    id: UUID = Field(..., description="Cluster unique identifier")
    user_id: UUID = Field(..., description="User unique identifier")
    document_count: int = Field(..., description="Number of documents in cluster")
    avg_sentiment: float | None = Field(None, description="Average sentiment score")
    trending_score: float | None = Field(None, description="Trending score (0.0 to 1.0)")
    created_at: datetime = Field(..., description="Cluster creation timestamp")
    updated_at: datetime = Field(..., description="Cluster last update timestamp")
    keywords: list[KeywordResponse] = Field(default_factory=list, description="Keywords associated with cluster")
    timeseries: list[TimeseriesSummaryResponse] = Field(default_factory=list, description="Timeseries summaries for cluster")
    insights: list[InsightResponse] = Field(default_factory=list, description="AI-generated insights for cluster")
    anomalies: list[AnomalyResponse] = Field(default_factory=list, description="Anomalies detected for cluster")
    
    model_config = {"from_attributes": True}

