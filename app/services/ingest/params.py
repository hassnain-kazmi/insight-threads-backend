from urllib.parse import urlparse

RSS_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _validate_feed_url(url: str, index: int) -> None:
    """Validate a single feed URL. Raises ValueError if invalid."""
    s = (url or "").strip()
    if not s:
        raise ValueError(f"RSS feed_urls[{index}] must be a non-empty URL")
    parsed = urlparse(s)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"RSS feed_urls[{index}] is not a valid URL: {url!r}")
    if parsed.scheme.lower() not in RSS_ALLOWED_SCHEMES:
        raise ValueError(
            f"RSS feed_urls[{index}] must use http or https, got: {parsed.scheme!r}"
        )


def normalize_github_repos_params(source_params: dict) -> list[dict[str, str]]:
    """
    Normalize and validate GitHub repositories parameters.

    Supports either:
      - repos: list[{"owner": str, "repo": str}]
      - owner: str and repo: str

    Raises ValueError with a clear message when input is invalid.
    """
    repos = source_params.get("repos")

    if repos is not None:
        if isinstance(repos, dict):
            repos = [repos]
        elif not isinstance(repos, list):
            raise ValueError(
                "GitHub ingestion 'repos' must be an array of objects or a single object"
            )

        if not repos:
            raise ValueError("GitHub ingestion 'repos' array cannot be empty")

        normalized_repos: list[dict[str, str]] = []
        for idx, repo_item in enumerate(repos):
            if not isinstance(repo_item, dict):
                raise ValueError(
                    "Each item in 'repos' array must be an object "
                    "with 'owner' and 'repo' string fields"
                )

            owner = (repo_item.get("owner") or "").strip()
            repo = (repo_item.get("repo") or "").strip()

            if not owner or not repo:
                raise ValueError(
                    f"Each item in 'repos' must include non-empty 'owner' and 'repo' "
                    f"fields (invalid at index {idx})"
                )

            normalized_repos.append({"owner": owner, "repo": repo})

        return normalized_repos

    owner = (source_params.get("owner") or "").strip()
    repo = (source_params.get("repo") or "").strip()

    if not owner or not repo:
        raise ValueError(
            "GitHub ingestion requires either:\n"
            "  - 'repos': array of objects with 'owner' and 'repo' fields, or\n"
            "  - both 'owner' and 'repo' parameters (non-empty strings)"
        )

    return [{"owner": owner, "repo": repo}]


HN_ALLOWED_ENDPOINTS = frozenset(
    {
        "topstories",
        "newstories",
        "beststories",
        "askstories",
        "showstories",
        "jobstories",
    }
)
HN_LIMIT_MAX = 500


def _validate_hackernews_params(params: dict) -> None:
    """Validate Hacker News source_params. Raises ValueError if invalid."""
    endpoints = params.get("endpoints") or params.get("endpoint")
    if endpoints is not None:
        if isinstance(endpoints, str):
            endpoints = [endpoints]
        if not isinstance(endpoints, list):
            raise ValueError(
                "Hacker News 'endpoints' (or 'endpoint') must be a string or array of strings"
            )
        for i, ep in enumerate(endpoints):
            if not isinstance(ep, str) or not ep.strip():
                raise ValueError(
                    f"Hacker News endpoint at index {i} must be a non-empty string"
                )
            if ep.strip().lower() not in HN_ALLOWED_ENDPOINTS:
                raise ValueError(
                    f"Hacker News endpoint {ep!r} is not allowed. "
                    f"Use one of: {', '.join(sorted(HN_ALLOWED_ENDPOINTS))}"
                )

    limit_val = params.get("limit_per_endpoint") or params.get("limit")
    if limit_val is not None:
        try:
            limit_int = int(limit_val)
        except (TypeError, ValueError):
            raise ValueError(
                "Hacker News 'limit' / 'limit_per_endpoint' must be a positive integer"
            )
        if limit_int < 1 or limit_int > HN_LIMIT_MAX:
            raise ValueError(
                f"Hacker News limit must be between 1 and {HN_LIMIT_MAX}, got {limit_int}"
            )


def validate_ingestion_params(source: str, source_params: dict | None) -> None:
    """
    Validate source_params for the given source. Raises ValueError if invalid.

    Call this before creating an ingest event so the API can return 400
    instead of enqueueing a task that will fail.
    """
    params = source_params or {}

    if source == "rss":
        feed_urls = params.get("feed_urls", [])
        if isinstance(feed_urls, str):
            feed_urls = [feed_urls]
        if not feed_urls:
            raise ValueError(
                "RSS ingestion requires 'feed_urls' (non-empty string or array of URLs)"
            )
        for i, raw_url in enumerate(feed_urls):
            if not isinstance(raw_url, str):
                raise ValueError(
                    f"RSS feed_urls[{i}] must be a string, got {type(raw_url).__name__}"
                )
            _validate_feed_url(raw_url, i)
        return

    if source == "hackernews":
        _validate_hackernews_params(params)
        return

    if source == "github":
        normalize_github_repos_params(params)
        return

    raise ValueError(
        f"Unsupported source: {source!r}. Use one of: rss, hackernews, github"
    )
