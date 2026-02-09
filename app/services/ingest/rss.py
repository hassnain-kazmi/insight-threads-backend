import logging
from typing import Any
from uuid import UUID

import feedparser
from sqlalchemy.orm import Session

from app.models import Document
from app.services.ingest.common import check_duplicate
from app.utils.storage import sanitize_filename, upload_snapshot

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50


def _fetch_from_rss(feed_url: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    """
    Fetch entries from RSS feed.

    Args:
        feed_url: RSS feed URL
        limit: Maximum number of entries to fetch

    Returns:
        List of entry dictionaries
    """
    try:
        feed = feedparser.parse(feed_url)

        if feed.bozo and feed.bozo_exception:
            logger.warning(
                f"RSS feed parsing issue for {feed_url}: {feed.bozo_exception}"
            )

        entries: list[dict[str, Any]] = []
        for entry in feed.entries[:limit]:
            content_list = entry.get("content", [])
            content_value = (
                content_list[0].get("value", "")
                if isinstance(content_list, list) and len(content_list) > 0
                else ""
            )

            entries.append(
                {
                    "id": entry.get("id", entry.get("link", "")),
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", ""),
                    "content": content_value,
                    "published": entry.get("published", ""),
                    "published_parsed": entry.get("published_parsed"),
                    "author": entry.get("author", ""),
                    "tags": [tag.get("term", "") for tag in entry.get("tags", [])],
                }
            )

        return entries
    except Exception as e:
        logger.error(f"Failed to fetch RSS feed from {feed_url}: {e}", exc_info=True)
        return []


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize RSS entry data into document schema.

    Args:
        entry: Raw entry data from RSS feed

    Returns:
        Normalized document data

    Raises:
        ValueError: If both entry ID and link are missing
    """
    title = entry.get("title", "")
    summary = entry.get("summary", "")
    content = entry.get("content", "")
    link = entry.get("link", "")
    entry_id = entry.get("id", link)

    if not entry_id:
        raise ValueError("Entry ID and link are both missing from RSS entry data")

    full_text_parts = [title]

    if content:
        full_text_parts.append(content)
    elif summary:
        full_text_parts.append(summary)

    if entry.get("author"):
        full_text_parts.append(f"\n\nAuthor: {entry.get('author')}")
    if entry.get("published"):
        full_text_parts.append(f"\nPublished: {entry.get('published')}")
    if entry.get("tags"):
        tags = ", ".join(entry.get("tags", []))
        if tags:
            full_text_parts.append(f"\nTags: {tags}")

    full_text = "\n\n".join(full_text_parts)

    return {
        "title": title[:512] if title else "Untitled",
        "raw_text": full_text,
        "url": link,
        "entry_id": entry_id,
    }


def ingest_feeds(
    db: Session,
    ingest_event_id: UUID,
    user_id: UUID,
    feed_urls: list[str],
    limit: int = DEFAULT_LIMIT,
) -> dict[str, int]:
    """
    Ingest RSS feed entries and create documents.

    Args:
        db: Database session
        ingest_event_id: UUID of the ingestion event
        user_id: UUID of the user
        feed_urls: List of RSS feed URLs to fetch from
        limit: Maximum number of entries to fetch per feed

    Returns:
        Dictionary with ingestion statistics (total_fetched, new_documents,
        duplicates, errors). Returns zeros if no feeds provided.
    """
    if not feed_urls:
        logger.warning("No RSS feed URLs provided")
        return {
            "total_fetched": 0,
            "new_documents": 0,
            "duplicates": 0,
            "errors": 0,
        }

    logger.info(
        f"Starting RSS ingestion for {len(feed_urls)} feed(s), "
        f"limit={limit} per feed, event={ingest_event_id}"
    )

    all_entries: list[dict[str, Any]] = []
    for feed_url in feed_urls:
        entries = _fetch_from_rss(feed_url, limit)
        all_entries.extend(entries)
        logger.info(f"Fetched {len(entries)} entries from {feed_url}")

    if not all_entries:
        logger.warning("No entries fetched from any RSS feed")
        return {
            "total_fetched": 0,
            "new_documents": 0,
            "duplicates": 0,
            "errors": 0,
        }

    logger.info(
        f"Fetched {len(all_entries)} total entries from {len(feed_urls)} feed(s)"
    )

    new_documents = 0
    duplicates = 0
    errors = 0

    try:
        for entry in all_entries:
            try:
                normalized = _normalize_entry(entry)

                existing = check_duplicate(db, normalized["url"], user_id)
                if existing:
                    duplicates += 1
                    logger.debug(f"Duplicate found: {normalized['url']}")
                    continue

                entry_id = sanitize_filename(normalized["entry_id"], max_length=100)
                snapshot_path = f"rss/{user_id}/{ingest_event_id}/{entry_id}.json"
                storage_path = upload_snapshot(entry, snapshot_path)

                document = Document(
                    user_id=user_id,
                    ingest_event_id=ingest_event_id,
                    source_path=normalized["url"] or storage_path,
                    title=normalized["title"],
                    raw_text=normalized["raw_text"],
                    processed=False,
                )
                db.add(document)
                new_documents += 1

            except Exception as e:
                errors += 1
                logger.error(
                    f"Error processing entry {entry.get('id', 'unknown')}: {e}",
                    exc_info=True,
                )

        db.commit()
        logger.info(f"Committed {new_documents} new documents to database")

    except Exception as e:
        db.rollback()
        logger.error(
            f"Critical error during RSS ingestion, rolling back transaction: {e}",
            exc_info=True,
        )
        raise

    stats = {
        "total_fetched": len(all_entries),
        "new_documents": new_documents,
        "duplicates": duplicates,
        "errors": errors,
    }

    logger.info(
        f"RSS ingestion completed: {new_documents} new documents, "
        f"{duplicates} duplicates, {errors} errors"
    )

    return stats
