import logging
from typing import Any
from uuid import UUID

import requests
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Document
from app.services.ingest.common import check_duplicate
from app.utils.storage import upload_snapshot, sanitize_filename

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_LIMIT = 50
DEFAULT_PER_PAGE = 100


def _get_github_headers() -> dict[str, str]:
    """
    Get headers for GitHub API requests with authentication if available.
    
    Returns:
        Dictionary with headers including Authorization if token is configured
    """
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "InsightThreads-Backend/1.0",
    }
    
    github_token = getattr(settings, "GITHUB_TOKEN", None)
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    
    return headers


def _fetch_commits(
    owner: str,
    repo: str,
    limit: int = DEFAULT_LIMIT,
    since: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch commits from a GitHub repository.
    
    Args:
        owner: Repository owner (username or organization)
        repo: Repository name
        limit: Maximum number of commits to fetch
        since: ISO 8601 timestamp to fetch commits since (optional)
        
    Returns:
        List of commit dictionaries
    """
    try:
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits"
        params: dict[str, Any] = {"per_page": min(limit, DEFAULT_PER_PAGE)}
        if since:
            params["since"] = since
        
        commits: list[dict[str, Any]] = []
        page = 1
        
        while len(commits) < limit:
            params["page"] = page
            response = requests.get(url, headers=_get_github_headers(), params=params, timeout=30.0)
            
            if response.status_code == 404:
                logger.warning(f"Repository {owner}/{repo} not found")
                break
            if response.status_code == 403:
                logger.warning(f"Rate limit or access denied for {owner}/{repo}")
                break
            
            response.raise_for_status()
            page_commits = response.json()
            
            if not isinstance(page_commits, list) or not page_commits:
                break
            
            commits.extend(page_commits)
            
            if len(page_commits) < DEFAULT_PER_PAGE:
                break
            
            page += 1
        
        return commits[:limit]
    except Exception as e:
        logger.error(f"Failed to fetch commits from {owner}/{repo}: {e}", exc_info=True)
        return []


def _fetch_issues(
    owner: str,
    repo: str,
    limit: int = DEFAULT_LIMIT,
    state: str = "all",
) -> list[dict[str, Any]]:
    """
    Fetch issues from a GitHub repository.
    
    Args:
        owner: Repository owner (username or organization)
        repo: Repository name
        limit: Maximum number of issues to fetch
        state: Issue state ('open', 'closed', 'all')
        
    Returns:
        List of issue dictionaries
    """
    try:
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues"
        params: dict[str, Any] = {
            "per_page": min(limit, DEFAULT_PER_PAGE),
            "state": state,
        }
        
        issues: list[dict[str, Any]] = []
        page = 1
        
        while len(issues) < limit:
            params["page"] = page
            response = requests.get(url, headers=_get_github_headers(), params=params, timeout=30.0)
            
            if response.status_code == 404:
                logger.warning(f"Repository {owner}/{repo} not found")
                break
            if response.status_code == 403:
                logger.warning(f"Rate limit or access denied for {owner}/{repo}")
                break
            
            response.raise_for_status()
            page_issues = response.json()
            
            if not isinstance(page_issues, list) or not page_issues:
                break
            
            for issue in page_issues:
                if "pull_request" not in issue:
                    issues.append(issue)
                    if len(issues) >= limit:
                        break
            
            if len(page_issues) < DEFAULT_PER_PAGE:
                break
            
            page += 1
        
        return issues[:limit]
    except Exception as e:
        logger.error(f"Failed to fetch issues from {owner}/{repo}: {e}", exc_info=True)
        return []


def _fetch_pull_requests(
    owner: str,
    repo: str,
    limit: int = DEFAULT_LIMIT,
    state: str = "all",
) -> list[dict[str, Any]]:
    """
    Fetch pull requests from a GitHub repository.
    
    Args:
        owner: Repository owner (username or organization)
        repo: Repository name
        limit: Maximum number of PRs to fetch
        state: PR state ('open', 'closed', 'all')
        
    Returns:
        List of pull request dictionaries
    """
    try:
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls"
        params: dict[str, Any] = {
            "per_page": min(limit, DEFAULT_PER_PAGE),
            "state": state,
        }
        
        prs: list[dict[str, Any]] = []
        page = 1
        
        while len(prs) < limit:
            params["page"] = page
            response = requests.get(url, headers=_get_github_headers(), params=params, timeout=30.0)
            
            if response.status_code == 404:
                logger.warning(f"Repository {owner}/{repo} not found")
                break
            if response.status_code == 403:
                logger.warning(f"Rate limit or access denied for {owner}/{repo}")
                break
            
            response.raise_for_status()
            page_prs = response.json()
            
            if not isinstance(page_prs, list) or not page_prs:
                break
            
            prs.extend(page_prs)
            
            if len(page_prs) < DEFAULT_PER_PAGE:
                break
            
            page += 1
        
        return prs[:limit]
    except Exception as e:
        logger.error(f"Failed to fetch pull requests from {owner}/{repo}: {e}", exc_info=True)
        return []


def _fetch_releases(
    owner: str,
    repo: str,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """
    Fetch releases from a GitHub repository.
    
    Args:
        owner: Repository owner (username or organization)
        repo: Repository name
        limit: Maximum number of releases to fetch
        
    Returns:
        List of release dictionaries
    """
    try:
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/releases"
        params: dict[str, Any] = {"per_page": min(limit, DEFAULT_PER_PAGE)}
        
        releases: list[dict[str, Any]] = []
        page = 1
        
        while len(releases) < limit:
            params["page"] = page
            response = requests.get(url, headers=_get_github_headers(), params=params, timeout=30.0)
            
            if response.status_code == 404:
                logger.warning(f"Repository {owner}/{repo} not found or has no releases")
                break
            if response.status_code == 403:
                logger.warning(f"Rate limit or access denied for {owner}/{repo}")
                break
            
            response.raise_for_status()
            page_releases = response.json()
            
            if not isinstance(page_releases, list) or not page_releases:
                break
            
            releases.extend(page_releases)
            
            if len(page_releases) < DEFAULT_PER_PAGE:
                break
            
            page += 1
        
        return releases[:limit]
    except Exception as e:
        logger.error(f"Failed to fetch releases from {owner}/{repo}: {e}", exc_info=True)
        return []


def _normalize_commit(commit: dict[str, Any], owner: str, repo: str) -> dict[str, Any]:
    """
    Normalize GitHub commit data into document schema.
    
    Args:
        commit: Raw commit data from GitHub API
        owner: Repository owner
        repo: Repository name
        
    Returns:
        Normalized document data
        
    Raises:
        ValueError: If commit SHA is missing
    """
    sha = commit.get("sha")
    commit_data = commit.get("commit", {})
    author = commit_data.get("author", {})
    message = commit_data.get("message", "")
    url = commit.get("html_url", "")
    
    if not sha:
        raise ValueError("Commit SHA is missing from GitHub commit data")
    
    if not url:
        url = f"https://github.com/{owner}/{repo}/commit/{sha}"
    
    full_text_parts = [f"Commit: {sha[:7]}"]
    
    if message:
        full_text_parts.append(message)
    
    author_name = author.get("name", "")
    author_email = author.get("email", "")
    if author_name or author_email:
        author_str = f"{author_name} <{author_email}>" if author_name and author_email else author_name or author_email
        full_text_parts.append(f"\n\nAuthor: {author_str}")
    
    author_date = author.get("date")
    if author_date:
        full_text_parts.append(f"\nDate: {author_date}")
    
    stats = commit.get("stats", {})
    if stats:
        additions = stats.get("additions", 0)
        deletions = stats.get("deletions", 0)
        total = stats.get("total", 0)
        if total > 0:
            full_text_parts.append(f"\nChanges: +{additions} -{deletions} ({total} total)")
    
    files = commit.get("files", [])
    if files:
        file_names = [f.get("filename", "") for f in files[:10]]
        if file_names:
            full_text_parts.append(f"\n\nFiles changed: {', '.join(file_names)}")
            if len(files) > 10:
                full_text_parts.append(f" (and {len(files) - 10} more)")
    
    full_text = "\n\n".join(full_text_parts)
    
    return {
        "title": f"Commit {sha[:7]}: {message.split(chr(10))[0][:100] if message else 'No message'}",
        "raw_text": full_text,
        "url": url,
        "sha": sha,
    }


def _normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize GitHub issue data into document schema.
    
    Args:
        issue: Raw issue data from GitHub API
        
    Returns:
        Normalized document data
        
    Raises:
        ValueError: If issue number or URL is missing
    """
    number = issue.get("number")
    title = issue.get("title", "")
    body = issue.get("body", "")
    url = issue.get("html_url", "")
    state = issue.get("state", "")
    user = issue.get("user", {})
    labels = issue.get("labels", [])
    created_at = issue.get("created_at", "")
    updated_at = issue.get("updated_at", "")
    closed_at = issue.get("closed_at")
    
    if number is None:
        raise ValueError("Issue number is missing from GitHub issue data")
    
    if not url:
        raise ValueError("Issue URL is missing from GitHub issue data")
    
    full_text_parts = [f"Issue #{number}: {title}"]
    
    if body:
        full_text_parts.append(body)
    
    if user:
        user_login = user.get("login", "")
        if user_login:
            full_text_parts.append(f"\n\nOpened by: {user_login}")
    
    if state:
        full_text_parts.append(f"\nState: {state}")
    
    if labels:
        label_names = [label.get("name", "") for label in labels if isinstance(label, dict)]
        if label_names:
            full_text_parts.append(f"\nLabels: {', '.join(label_names)}")
    
    if created_at:
        full_text_parts.append(f"\nCreated: {created_at}")
    if updated_at:
        full_text_parts.append(f"\nUpdated: {updated_at}")
    if closed_at:
        full_text_parts.append(f"\nClosed: {closed_at}")
    
    full_text = "\n\n".join(full_text_parts)
    
    return {
        "title": f"Issue #{number}: {title[:512] if title else 'Untitled'}",
        "raw_text": full_text,
        "url": url,
        "issue_number": number,
    }


def _normalize_pull_request(pr: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize GitHub pull request data into document schema.
    
    Args:
        pr: Raw pull request data from GitHub API
        
    Returns:
        Normalized document data
        
    Raises:
        ValueError: If PR number or URL is missing
    """
    number = pr.get("number")
    title = pr.get("title", "")
    body = pr.get("body", "")
    url = pr.get("html_url", "")
    state = pr.get("state", "")
    user = pr.get("user", {})
    labels = pr.get("labels", [])
    created_at = pr.get("created_at", "")
    updated_at = pr.get("updated_at", "")
    merged_at = pr.get("merged_at")
    base = pr.get("base", {})
    head = pr.get("head", {})
    mergeable = pr.get("mergeable")
    
    if number is None:
        raise ValueError("Pull request number is missing from GitHub PR data")
    
    if not url:
        raise ValueError("Pull request URL is missing from GitHub PR data")
    
    full_text_parts = [f"Pull Request #{number}: {title}"]
    
    if body:
        full_text_parts.append(body)
    
    if user:
        user_login = user.get("login", "")
        if user_login:
            full_text_parts.append(f"\n\nOpened by: {user_login}")
    
    if state:
        full_text_parts.append(f"\nState: {state}")
    
    if merged_at:
        full_text_parts.append(f"\nMerged: {merged_at}")
    elif mergeable is not None:
        full_text_parts.append(f"\nMergeable: {mergeable}")
    
    if base and head:
        base_ref = base.get("ref", "")
        head_ref = head.get("ref", "")
        if base_ref and head_ref:
            full_text_parts.append(f"\n\nBase: {base_ref} ← Head: {head_ref}")
    
    if labels:
        label_names = [label.get("name", "") for label in labels if isinstance(label, dict)]
        if label_names:
            full_text_parts.append(f"\nLabels: {', '.join(label_names)}")
    
    if created_at:
        full_text_parts.append(f"\nCreated: {created_at}")
    if updated_at:
        full_text_parts.append(f"\nUpdated: {updated_at}")
    
    full_text = "\n\n".join(full_text_parts)
    
    return {
        "title": f"PR #{number}: {title[:512] if title else 'Untitled'}",
        "raw_text": full_text,
        "url": url,
        "pr_number": number,
    }


def _normalize_release(release: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize GitHub release data into document schema.
    
    Args:
        release: Raw release data from GitHub API
        
    Returns:
        Normalized document data
        
    Raises:
        ValueError: If release ID or URL is missing
    """
    release_id = release.get("id")
    tag_name = release.get("tag_name", "")
    name = release.get("name", "")
    body = release.get("body", "")
    url = release.get("html_url", "")
    author = release.get("author", {})
    created_at = release.get("created_at", "")
    published_at = release.get("published_at", "")
    prerelease = release.get("prerelease", False)
    draft = release.get("draft", False)
    
    if release_id is None:
        raise ValueError("Release ID is missing from GitHub release data")
    
    if not url:
        raise ValueError("Release URL is missing from GitHub release data")
    
    title = name or tag_name or f"Release {release_id}"
    
    full_text_parts = [f"Release: {title}"]
    
    if tag_name:
        full_text_parts.append(f"\nTag: {tag_name}")
    
    if body:
        full_text_parts.append(body)
    
    if author:
        author_login = author.get("login", "")
        if author_login:
            full_text_parts.append(f"\n\nPublished by: {author_login}")
    
    if prerelease:
        full_text_parts.append("\nType: Pre-release")
    elif draft:
        full_text_parts.append("\nType: Draft")
    else:
        full_text_parts.append("\nType: Release")
    
    if created_at:
        full_text_parts.append(f"\nCreated: {created_at}")
    if published_at:
        full_text_parts.append(f"\nPublished: {published_at}")
    
    full_text = "\n\n".join(full_text_parts)
    
    return {
        "title": title[:512] if title else "Untitled Release",
        "raw_text": full_text,
        "url": url,
        "release_id": release_id,
    }


def ingest_repository(
    db: Session,
    ingest_event_id: UUID,
    user_id: UUID,
    owner: str,
    repo: str,
    include_commits: bool = True,
    include_issues: bool = True,
    include_prs: bool = True,
    include_releases: bool = True,
    limit_per_type: int = DEFAULT_LIMIT,
    commit_since: str | None = None,
    issue_state: str = "all",
    pr_state: str = "all",
) -> dict[str, int]:
    """
    Ingest GitHub repository activity and create documents.
    
    Args:
        db: Database session
        ingest_event_id: UUID of the ingestion event
        user_id: UUID of the user
        owner: Repository owner (username or organization)
        repo: Repository name
        include_commits: Whether to fetch commits
        include_issues: Whether to fetch issues
        include_prs: Whether to fetch pull requests
        include_releases: Whether to fetch releases
        limit_per_type: Maximum number of items to fetch per type
        commit_since: ISO 8601 timestamp to fetch commits since (optional)
        issue_state: Issue state filter ('open', 'closed', 'all')
        pr_state: PR state filter ('open', 'closed', 'all')
        
    Returns:
        Dictionary with ingestion statistics (total_fetched, new_documents, 
        duplicates, errors)
    """
    logger.info(
        f"Starting GitHub ingestion for {owner}/{repo}, "
        f"event={ingest_event_id}, "
        f"commits={include_commits}, issues={include_issues}, "
        f"prs={include_prs}, releases={include_releases}"
    )
    
    all_items: list[tuple[str, dict[str, Any]]] = []
    
    if include_commits:
        commits = _fetch_commits(owner, repo, limit_per_type, commit_since)
        for commit in commits:
            all_items.append(("commit", commit))
        logger.info(f"Fetched {len(commits)} commits from {owner}/{repo}")
    
    if include_issues:
        issues = _fetch_issues(owner, repo, limit_per_type, issue_state)
        for issue in issues:
            all_items.append(("issue", issue))
        logger.info(f"Fetched {len(issues)} issues from {owner}/{repo}")
    
    if include_prs:
        prs = _fetch_pull_requests(owner, repo, limit_per_type, pr_state)
        for pr in prs:
            all_items.append(("pr", pr))
        logger.info(f"Fetched {len(prs)} pull requests from {owner}/{repo}")
    
    if include_releases:
        releases = _fetch_releases(owner, repo, limit_per_type)
        for release in releases:
            all_items.append(("release", release))
        logger.info(f"Fetched {len(releases)} releases from {owner}/{repo}")
    
    if not all_items:
        logger.warning(f"No items fetched from {owner}/{repo}")
        return {
            "total_fetched": 0,
            "new_documents": 0,
            "duplicates": 0,
            "errors": 0,
        }
    
    logger.info(f"Fetched {len(all_items)} total items from {owner}/{repo}")
    
    new_documents = 0
    duplicates = 0
    errors = 0
    
    try:
        for item_type, item_data in all_items:
            try:
                if item_type == "commit":
                    normalized = _normalize_commit(item_data, owner, repo)
                    dedupe_key = normalized["sha"]
                    item_id = normalized["sha"]
                elif item_type == "issue":
                    normalized = _normalize_issue(item_data)
                    dedupe_key = normalized["url"]
                    item_id = str(normalized["issue_number"])
                elif item_type == "pr":
                    normalized = _normalize_pull_request(item_data)
                    dedupe_key = normalized["url"]
                    item_id = str(normalized["pr_number"])
                elif item_type == "release":
                    normalized = _normalize_release(item_data)
                    dedupe_key = normalized["url"]
                    item_id = str(normalized["release_id"])
                else:
                    errors += 1
                    logger.warning(f"Unknown item type: {item_type}")
                    continue
                
                existing = check_duplicate(db, dedupe_key)
                if existing:
                    duplicates += 1
                    logger.debug(f"Duplicate found: {dedupe_key}")
                    continue
                
                item_id_sanitized = sanitize_filename(item_id, max_length=100)
                snapshot_path = f"github/{user_id}/{ingest_event_id}/{item_type}/{item_id_sanitized}.json"
                upload_snapshot(item_data, snapshot_path)
                
                document = Document(
                    user_id=user_id,
                    ingest_event_id=ingest_event_id,
                    source_path=dedupe_key,
                    title=normalized["title"],
                    raw_text=normalized["raw_text"],
                    processed=False,
                )
                db.add(document)
                new_documents += 1
                
            except Exception as e:
                errors += 1
                item_id = item_data.get("id", item_data.get("sha", item_data.get("number", "unknown")))
                logger.error(f"Error processing {item_type} {item_id}: {e}", exc_info=True)
        
        db.commit()
        logger.info(f"Committed {new_documents} new documents to database")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Critical error during GitHub ingestion, rolling back transaction: {e}", exc_info=True)
        raise
    
    stats = {
        "total_fetched": len(all_items),
        "new_documents": new_documents,
        "duplicates": duplicates,
        "errors": errors,
    }
    
    logger.info(
        f"GitHub ingestion completed for {owner}/{repo}: "
        f"{new_documents} new documents, {duplicates} duplicates, {errors} errors"
    )
    
    return stats

