import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import requests
from sqlalchemy.orm import Session

from app.models import Document
from app.services.ingest.common import check_duplicate
from app.utils.storage import upload_snapshot, sanitize_filename

logger = logging.getLogger(__name__)

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
DEFAULT_LIMIT = 50


def _fetch_story_ids(
    endpoint: str = "topstories", limit: int = DEFAULT_LIMIT
) -> list[int]:
    """
    Fetch story IDs from Hacker News API.

    Args:
        endpoint: API endpoint ('topstories', 'newstories', 'beststories', etc.)
        limit: Maximum number of story IDs to return

    Returns:
        List of story IDs
    """
    try:
        url = f"{HN_API_BASE}/{endpoint}.json"
        response = requests.get(url, timeout=10.0)
        response.raise_for_status()
        story_ids = response.json()

        if not isinstance(story_ids, list):
            logger.warning(
                f"Unexpected response format from {endpoint}: {type(story_ids)}"
            )
            return []

        return story_ids[:limit]
    except Exception as e:
        logger.error(
            f"Failed to fetch {endpoint} from Hacker News API: {e}", exc_info=True
        )
        return []


def _fetch_item(item_id: int) -> dict[str, Any] | None:
    """
    Fetch a single item from Hacker News API.

    Args:
        item_id: Hacker News item ID

    Returns:
        Item data dictionary or None if fetch fails
    """
    try:
        url = f"{HN_API_BASE}/item/{item_id}.json"
        response = requests.get(url, timeout=10.0)
        response.raise_for_status()
        item = response.json()

        if not isinstance(item, dict):
            logger.warning(
                f"Unexpected response format for item {item_id}: {type(item)}"
            )
            return None

        return item
    except Exception as e:
        logger.error(
            f"Failed to fetch item {item_id} from Hacker News API: {e}", exc_info=True
        )
        return None


def _fetch_posts(
    endpoint: str = "topstories", limit: int = DEFAULT_LIMIT
) -> list[dict[str, Any]]:
    """
    Fetch posts from Hacker News API.

    Args:
        endpoint: API endpoint ('topstories', 'newstories', 'beststories', etc.)
        limit: Maximum number of posts to fetch

    Returns:
        List of post dictionaries
    """
    story_ids = _fetch_story_ids(endpoint, limit)

    if not story_ids:
        logger.warning(f"No story IDs fetched from {endpoint}")
        return []

    logger.info(f"Fetched {len(story_ids)} story IDs from {endpoint}")

    posts: list[dict[str, Any]] = []
    for story_id in story_ids:
        item = _fetch_item(story_id)

        if not item:
            continue

        item_type = item.get("type", "")
        if item_type != "story":
            logger.debug(f"Skipping item {story_id} with type '{item_type}'")
            continue

        if item.get("deleted") or item.get("dead"):
            logger.debug(f"Skipping deleted/dead item {story_id}")
            continue

        posts.append(item)

    logger.info(f"Fetched {len(posts)} valid story posts from {len(story_ids)} IDs")
    return posts


def _normalize_post(post: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize Hacker News post data into document schema.

    Args:
        post: Raw post data from Hacker News API

    Returns:
        Normalized document data

    Raises:
        ValueError: If post ID is missing from item data
    """
    post_id = post.get("id")
    title = post.get("title", "")
    url = post.get("url", "")
    text = post.get("text", "")
    author = post.get("by", "")
    score = post.get("score", 0)
    time = post.get("time", 0)
    descendants = post.get("descendants", 0)

    if post_id is None:
        raise ValueError("Post ID is missing from Hacker News item data")

    if not url:
        url = f"https://news.ycombinator.com/item?id={post_id}"

    full_text_parts = [title]

    if text:
        full_text_parts.append(text)
    elif url and url.startswith("http") and "news.ycombinator.com" not in url:
        full_text_parts.append(f"\n\nLink: {url}")

    if author:
        full_text_parts.append(f"\n\nAuthor: {author}")
    if score is not None:
        full_text_parts.append(f"\nScore: {score}")
    if descendants is not None:
        full_text_parts.append(f"\nComments: {descendants}")
    if time:
        try:
            dt = datetime.fromtimestamp(time, tz=timezone.utc)
            full_text_parts.append(f"\nPublished: {dt.isoformat()}")
        except (ValueError, OSError):
            pass

    full_text = "\n\n".join(full_text_parts)

    return {
        "title": title[:512] if title else "Untitled",
        "raw_text": full_text,
        "url": url,
        "post_id": post_id,
    }


def ingest_posts(
    db: Session,
    ingest_event_id: UUID,
    user_id: UUID,
    endpoint: str = "topstories",
    limit: int = DEFAULT_LIMIT,
) -> dict[str, int]:
    """
    Ingest Hacker News posts and create documents.

    Args:
        db: Database session
        ingest_event_id: UUID of the ingestion event
        user_id: UUID of the user
        endpoint: Hacker News API endpoint ('topstories', 'newstories', 'beststories', etc.)
        limit: Maximum number of posts to fetch

    Returns:
        Dictionary with ingestion statistics (total_fetched, new_documents,
        duplicates, errors). Returns zeros if no posts fetched.
    """
    logger.info(
        f"Starting Hacker News ingestion from {endpoint}, "
        f"limit={limit}, event={ingest_event_id}"
    )

    posts = _fetch_posts(endpoint, limit)

    if not posts:
        logger.warning("No posts fetched from Hacker News API")
        return {
            "total_fetched": 0,
            "new_documents": 0,
            "duplicates": 0,
            "errors": 0,
        }

    logger.info(f"Fetched {len(posts)} posts from Hacker News API")

    new_documents = 0
    duplicates = 0
    errors = 0

    try:
        for post in posts:
            try:
                normalized = _normalize_post(post)

                existing = check_duplicate(db, normalized["url"], user_id)
                if existing:
                    duplicates += 1
                    logger.debug(f"Duplicate found: {normalized['url']}")
                    continue

                post_id = normalized["post_id"]
                post_id_str = sanitize_filename(str(post_id), max_length=100)
                snapshot_path = (
                    f"hackernews/{user_id}/{ingest_event_id}/{post_id_str}.json"
                )
                storage_path = upload_snapshot(post, snapshot_path)

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
                post_id = post.get("id", "unknown")
                logger.error(f"Error processing post {post_id}: {e}", exc_info=True)

        db.commit()
        logger.info(f"Committed {new_documents} new documents to database")

    except Exception as e:
        db.rollback()
        logger.error(
            f"Critical error during Hacker News ingestion, rolling back transaction: {e}",
            exc_info=True,
        )
        raise

    stats = {
        "total_fetched": len(posts),
        "new_documents": new_documents,
        "duplicates": duplicates,
        "errors": errors,
    }

    logger.info(
        f"Hacker News ingestion completed: {new_documents} new documents, "
        f"{duplicates} duplicates, {errors} errors"
    )

    return stats
