from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from . import Base, generate_uuid


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    centroid_384: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="clusters")
    members = relationship("ClusterMember", back_populates="cluster", cascade="all, delete-orphan")
    keywords = relationship("Keyword", back_populates="cluster", cascade="all, delete-orphan")
    timeseries = relationship("TimeseriesSummary", back_populates="cluster", cascade="all, delete-orphan")
    anomalies = relationship("Anomaly", back_populates="cluster", cascade="all, delete-orphan")
    insights = relationship("Insight", back_populates="cluster", cascade="all, delete-orphan")

