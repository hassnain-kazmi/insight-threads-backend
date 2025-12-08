from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base, generate_uuid


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    cluster_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clusters.id", ondelete="CASCADE"))
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    cluster = relationship("Cluster", back_populates="keywords")

