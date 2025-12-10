from pydantic import BaseModel, Field


class TriggerIngestionRequest(BaseModel):
    """Request model for triggering ingestion."""
    
    source: str = Field(..., description="Data source type (e.g., 'reddit')")
    source_params: dict = Field(default_factory=dict, description="Source-specific parameters")


class TriggerIngestionResponse(BaseModel):
    """Response model for ingestion trigger."""
    
    ingest_event_id: str = Field(..., description="UUID of the created ingestion event")
    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(..., description="Initial status of the ingestion event")

