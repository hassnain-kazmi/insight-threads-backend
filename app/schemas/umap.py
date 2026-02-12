from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UMAPProjectionResponse(BaseModel):
    """Response model for UMAP projection."""

    document_id: UUID = Field(..., description="Document unique identifier")
    x: float = Field(..., description="X coordinate in UMAP space")
    y: float = Field(..., description="Y coordinate in UMAP space")
    model_name: str = Field(..., description="UMAP model name")
    created_at: datetime = Field(..., description="Projection creation timestamp")

    model_config = {"from_attributes": True}


class DocumentUMAPResponse(BaseModel):
    """Response model for document with UMAP projection."""

    document_id: UUID = Field(..., description="Document unique identifier")
    title: str | None = Field(None, description="Document title")
    source_path: str | None = Field(None, description="Document source path")
    cluster_id: UUID | None = Field(
        None, description="Primary cluster ID if document is in a cluster"
    )
    x: float = Field(..., description="X coordinate in UMAP space")
    y: float = Field(..., description="Y coordinate in UMAP space")

    model_config = {"from_attributes": True}


class ClusterUMAPResponse(BaseModel):
    """Response model for cluster UMAP visualization."""

    documents: list[DocumentUMAPResponse] = Field(
        ..., description="Documents with UMAP projections"
    )
    total: int = Field(..., description="Total number of documents")
