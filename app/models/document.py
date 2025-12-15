from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base, generate_uuid


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    user_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    ingest_event_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingest_events.id", ondelete="SET NULL")
    )
    source_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    processed: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    processed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="documents", foreign_keys=[user_id])
    ingest_event = relationship("IngestEvent", back_populates="documents", foreign_keys=[ingest_event_id])
    embeddings = relationship("DocumentEmbedding", back_populates="document", cascade="all, delete-orphan")
    sentiments = relationship("DocumentSentiment", back_populates="document", cascade="all, delete-orphan")
    cluster_memberships = relationship("ClusterMember", back_populates="document", cascade="all, delete-orphan")
    umap_projections = relationship("UMAPProjection", back_populates="document", cascade="all, delete-orphan")

