from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AnomalyResponse(BaseModel):
    """Response model for anomaly."""
    
    id: UUID = Field(..., description="Anomaly unique identifier")
    cluster_id: UUID = Field(..., description="Cluster unique identifier")
    anomaly_date: date = Field(..., description="Date when anomaly was detected")
    score: float = Field(..., description="Anomaly score")
    type: str | None = Field(None, description="Type of anomaly")
    anomaly_metadata: dict | None = Field(None, description="Additional anomaly metadata")
    created_at: datetime = Field(..., description="Anomaly creation timestamp")
    
    model_config = {"from_attributes": True}


class AnomaliesListResponse(BaseModel):
    """Response model for anomalies list."""
    
    anomalies: list[AnomalyResponse] = Field(..., description="List of anomalies")
    total: int = Field(..., description="Total number of anomalies")
