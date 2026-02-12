from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentSentimentResponse(BaseModel):
    """Response model for document sentiment."""

    vader: float | None = Field(None, description="VADER sentiment score")
    distilbert_score: float | None = Field(
        None, description="DistilBERT sentiment score"
    )
    distilbert_label: str | None = Field(None, description="DistilBERT sentiment label")
    combined_score: float | None = Field(None, description="Combined sentiment score")

    model_config = {"from_attributes": True}


class ClusterMembershipResponse(BaseModel):
    """Response model for cluster membership."""

    cluster_id: UUID = Field(..., description="Cluster unique identifier")
    membership_strength: float | None = Field(
        None, description="Membership strength score"
    )

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    """Response model for document."""

    id: UUID = Field(..., description="Document unique identifier")
    user_id: UUID | None = Field(None, description="User unique identifier")
    ingest_event_id: UUID | None = Field(
        None, description="Ingest event unique identifier"
    )
    source_path: str | None = Field(None, description="Document source path")
    title: str | None = Field(None, description="Document title")
    processed: bool = Field(..., description="Whether document has been processed")
    processed_at: datetime | None = Field(
        None, description="Document processing timestamp"
    )
    created_at: datetime = Field(..., description="Document creation timestamp")
    updated_at: datetime = Field(..., description="Document last update timestamp")

    model_config = {"from_attributes": True}


class DocumentDetailResponse(BaseModel):
    """Response model for document detail with full content and relationships."""

    id: UUID = Field(..., description="Document unique identifier")
    user_id: UUID | None = Field(None, description="User unique identifier")
    ingest_event_id: UUID | None = Field(
        None, description="Ingest event unique identifier"
    )
    source_path: str | None = Field(None, description="Document source path")
    title: str | None = Field(None, description="Document title")
    raw_text: str | None = Field(None, description="Document raw text content")
    processed: bool = Field(..., description="Whether document has been processed")
    processed_at: datetime | None = Field(
        None, description="Document processing timestamp"
    )
    created_at: datetime = Field(..., description="Document creation timestamp")
    updated_at: datetime = Field(..., description="Document last update timestamp")
    sentiment: DocumentSentimentResponse | None = Field(
        None, description="Document sentiment analysis"
    )
    cluster_memberships: list[ClusterMembershipResponse] = Field(
        default_factory=list, description="Cluster memberships"
    )

    model_config = {"from_attributes": True}


class DocumentsListResponse(BaseModel):
    """Response model for documents list."""

    documents: list[DocumentResponse] = Field(..., description="List of documents")
    total: int = Field(..., description="Total number of documents")
