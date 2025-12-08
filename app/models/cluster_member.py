from sqlalchemy import DateTime, Float, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base


class ClusterMember(Base):
    __tablename__ = "cluster_members"
    __table_args__ = {"extend_existing": True}

    cluster_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clusters.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    membership_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cluster = relationship("Cluster", back_populates="members")
    document = relationship("Document", back_populates="cluster_memberships")

