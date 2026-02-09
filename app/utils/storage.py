import json
import logging
from pathlib import Path
from typing import Any, Optional

from supabase import create_client

from app.config import settings

logger = logging.getLogger(__name__)

_INVALID_FILENAME_CHARS = ["<", ">", ":", '"', "/", "\\", "|", "?", "*"]


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """
    Sanitize a filename for cross-platform compatibility (especially Windows).

    Args:
        filename: Original filename
        max_length: Maximum length of sanitized filename

    Returns:
        Sanitized filename safe for all platforms
    """
    sanitized = filename
    for char in _INVALID_FILENAME_CHARS:
        sanitized = sanitized.replace(char, "_")
    return sanitized[:max_length] or "unknown"


_use_supabase = (
    hasattr(settings, "SUPABASE_SERVICE_KEY") and settings.SUPABASE_SERVICE_KEY
)
_local_storage_path = Path(__file__).parent.parent.parent / "storage"
_supabase_client: Optional[Any] = None

if _use_supabase:
    try:
        _supabase_client = create_client(
            settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY
        )
        logger.info(
            f"Initialized Supabase Storage client with bucket: {settings.SUPABASE_STORAGE_BUCKET}"
        )
    except Exception as e:
        logger.warning(
            "Failed to initialize Supabase client, falling back to local storage: %s",
            e,
        )
        _use_supabase = False
        _supabase_client = None
else:
    _local_storage_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Using local storage at {_local_storage_path}")


def upload_snapshot(content: bytes | str | dict[str, Any], file_path: str) -> str:
    """
    Upload a snapshot to storage.

    Args:
        content: Content to upload (bytes or JSON-serializable object)
        file_path: Path within storage bucket/folder

    Returns:
        Storage path/URL of uploaded file
    """
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    elif isinstance(content, dict):
        content_bytes = json.dumps(content, indent=2).encode("utf-8")
    else:
        content_bytes = content

    if _use_supabase and _supabase_client:
        try:
            bucket_name = settings.SUPABASE_STORAGE_BUCKET
            _supabase_client.storage.from_(bucket_name).upload(
                file_path,
                content_bytes,
                file_options={"content-type": "application/json"},
            )
            storage_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/{bucket_name}/{file_path}"
            logger.info(f"Uploaded snapshot to Supabase: {file_path}")
            return storage_url
        except Exception as e:
            error_str = str(e).lower()
            if "409" in error_str or "duplicate" in error_str:
                storage_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/{bucket_name}/{file_path}"
                logger.info(f"Snapshot already exists in Supabase: {file_path}")
                return storage_url
            logger.error(
                f"Failed to upload to Supabase: {e}, falling back to local storage"
            )

    local_file = _local_storage_path / file_path
    local_file.parent.mkdir(parents=True, exist_ok=True)
    local_file.write_bytes(content_bytes)
    logger.info(f"Saved snapshot to local storage: {local_file}")
    return str(local_file.relative_to(_local_storage_path.parent))
