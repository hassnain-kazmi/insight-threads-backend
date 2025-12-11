import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document

logger = logging.getLogger(__name__)


def check_duplicate(db: Session, url: str) -> Optional[Document]:
    """
    Check if a document with the same URL already exists.
    
    This is a shared utility function used by all ingestion sources for URL-based deduplication.
    
    Args:
        db: Database session
        url: Document URL to check
        
    Returns:
        Existing Document if found, None otherwise
    """
    if not url:
        return None
    
    try:
        result = db.execute(
            select(Document).where(Document.source_path == url)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error checking duplicate for URL {url}: {e}", exc_info=True)
        return None

