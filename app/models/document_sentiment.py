from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base, generate_uuid


class DocumentSentiment(Base):
    __tablename__ = "document_sentiments"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    document_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))
    vader: Mapped[float | None] = mapped_column(Float, nullable=True)
    distilbert_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    distilbert_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    combined_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document = relationship("Document", back_populates="sentiments")

