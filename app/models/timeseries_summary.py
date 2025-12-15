from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base, generate_uuid


class TimeseriesSummary(Base):
    __tablename__ = "timeseries_summary"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=generate_uuid
    )
    cluster_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False
    )
    summary_date: Mapped[Date] = mapped_column(Date, nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum: Mapped[float | None] = mapped_column(Float, nullable=True)
    forecast_lower: Mapped[float | None] = mapped_column(Float, nullable=True)
    forecast_upper: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cluster = relationship("Cluster", back_populates="timeseries")

