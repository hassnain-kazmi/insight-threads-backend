import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document

logger = logging.getLogger(__name__)


def check_duplicate(db: Session, url: str, user_id: UUID | None) -> Document | None:
    """
    Check if a document with the same URL already exists for the given user.

    This avoids cross-user deduplication.

    Args:
        db: Database session
        url: Document URL to check
        user_id: Owner of the document

    Returns:
        Existing Document if found, None otherwise
    """
    if not url:
        return None

    try:
        result = db.execute(
            select(Document).where(
                Document.source_path == url,
                Document.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking duplicate for URL {url}: {e}", exc_info=True)
        return None
