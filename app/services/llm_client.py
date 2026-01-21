import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from requests.exceptions import ConnectionError, ReadTimeout, RequestException

from app.config import settings

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "ml" / "prompts"


class OllamaError(Exception):
    """Base exception for Ollama client errors."""

    pass


class OllamaConnectionError(OllamaError):
    """Raised when connection to Ollama fails."""

    pass


class OllamaTimeoutError(OllamaError):
    """Raised when Ollama request times out."""

    pass


class OllamaGenerationError(OllamaError):
    """Raised when Ollama fails to generate a response."""

    pass


@dataclass
class LLMResponse:
    """Response from LLM generation."""

    content: str
    model: str
    total_duration_ms: int | None = None
    eval_count: int | None = None
    metadata: dict[str, Any] | None = None


def load_prompt_template(template_name: str) -> str:
    """
    Load a prompt template from the prompts directory.

    Args:
        template_name: Name of the template file (without .md extension)

    Returns:
        Template content as string

    Raises:
        FileNotFoundError: If template does not exist
    """
    template_path = PROMPTS_DIR / f"{template_name}.md"
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")

    return template_path.read_text(encoding="utf-8")


def format_prompt(
    template_name: str,
    **kwargs: Any,
) -> str:
    """
    Load and format a prompt template with provided variables.

    Args:
        template_name: Name of the template file (without .md extension)
        **kwargs: Variables to substitute in the template

    Returns:
        Formatted prompt string
    """
    template = load_prompt_template(template_name)
    return template.format(**kwargs)


class OllamaClient:
    """
    Synchronous client for Ollama HTTP API.

    Used primarily in Celery tasks for insight generation.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        context_size: int | None = None,
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout or settings.OLLAMA_TIMEOUT
        self.max_retries = max_retries or settings.OLLAMA_MAX_RETRIES
        self.context_size = context_size or settings.OLLAMA_CONTEXT_SIZE

    def _make_request(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Make HTTP request to Ollama with retry logic.

        Args:
            endpoint: API endpoint (e.g., "/api/generate")
            payload: Request payload

        Returns:
            Response JSON as dict

        Raises:
            OllamaConnectionError: Connection failed
            OllamaTimeoutError: Request timed out
            OllamaGenerationError: Generation failed
        """
        url = f"{self.base_url}{endpoint}"
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "Ollama request attempt %d/%d to %s",
                    attempt,
                    self.max_retries,
                    url,
                )

                logger.info("Sending request to Ollama (timeout=%ds)...", self.timeout)

                response = requests.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"},
                )

                logger.info(
                    "Received response from Ollama (status=%d)", response.status_code
                )

                if response.status_code != 200:
                    error_text = response.text[:500]
                    raise OllamaGenerationError(
                        f"Ollama returned status {response.status_code}: {error_text}"
                    )

                return response.json()

            except ConnectionError as e:
                last_error = OllamaConnectionError(
                    f"Failed to connect to Ollama at {self.base_url}: {e}"
                )
                logger.warning(
                    "Connection error on attempt %d: %s",
                    attempt,
                    e,
                )

            except ReadTimeout as e:
                last_error = OllamaTimeoutError(
                    f"Ollama request timed out after {self.timeout}s: {e}"
                )
                logger.warning(
                    "Timeout on attempt %d after %ds",
                    attempt,
                    self.timeout,
                )

            except RequestException as e:
                last_error = OllamaGenerationError(f"Request failed: {e}")
                logger.warning(
                    "Request error on attempt %d: %s",
                    attempt,
                    e,
                )

        logger.error(
            "All %d Ollama request attempts failed",
            self.max_retries,
        )
        raise last_error  # type: ignore[misc]

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Generate text completion from Ollama.

        Args:
            prompt: The prompt to send
            model: Model to use (defaults to configured model)
            system: Optional system prompt
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate (None = model default)

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            OllamaError: If generation fails
        """
        payload: dict[str, Any] = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": self.context_size,
            },
        }

        if system:
            payload["system"] = system

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        logger.info(
            "Generating with model=%s, prompt_len=%d, context_size=%d, max_tokens=%s",
            payload["model"],
            len(prompt),
            self.context_size,
            max_tokens or "default",
        )

        response = self._make_request("/api/generate", payload)

        return LLMResponse(
            content=response.get("response", ""),
            model=response.get("model", payload["model"]),
            total_duration_ms=(
                response.get("total_duration", 0) // 1_000_000
                if response.get("total_duration")
                else None
            ),
            eval_count=response.get("eval_count"),
            metadata={
                "prompt_eval_count": response.get("prompt_eval_count"),
                "context": response.get("context"),
            },
        )

    def generate_insight(
        self,
        cluster_keywords: list[str],
        document_samples: list[str],
        avg_sentiment: float | None = None,
        document_count: int | None = None,
        anomaly_info: str | None = None,
        template_name: str = "insight_template_brief",
    ) -> LLMResponse:
        """
        Generate an insight for a cluster using the insight template.

        Args:
            cluster_keywords: Top keywords for the cluster
            document_samples: Sample document texts from the cluster
            avg_sentiment: Average sentiment score (-1 to 1)
            document_count: Total documents in cluster
            anomaly_info: Optional description of detected anomalies
            template_name: Prompt template to use

        Returns:
            LLMResponse with generated insight
        """
        sentiment_label = _sentiment_to_label(avg_sentiment)
        keywords_str = ", ".join(cluster_keywords[:10])
        samples_str = "\n---\n".join(
            [
                _truncate_text(doc, 300) for doc in document_samples[:4]
            ]
        )
        anomaly_section = anomaly_info or "No anomalies detected."

        prompt = format_prompt(
            template_name,
            keywords=keywords_str,
            document_samples=samples_str,
            sentiment_label=sentiment_label,
            sentiment_score=f"{avg_sentiment:.2f}"
            if avg_sentiment is not None
            else "N/A",
            document_count=document_count or "Unknown",
            anomaly_info=anomaly_section,
        )

        return self.generate(
            prompt=prompt,
            temperature=0.5,
            max_tokens=256,
        )

    def generate_cluster_name(
        self,
        cluster_keywords: list[str],
        document_samples: list[str],
        avg_sentiment: float | None = None,
        document_count: int | None = None,
    ) -> LLMResponse:
        """
        Generate a concise name for a cluster (2-4 words).

        Args:
            cluster_keywords: Top keywords for the cluster
            document_samples: Sample document texts from the cluster
            avg_sentiment: Average sentiment score (-1 to 1)
            document_count: Total documents in cluster

        Returns:
            LLMResponse with generated cluster name
        """
        sentiment_label = _sentiment_to_label(avg_sentiment)
        keywords_str = ", ".join(cluster_keywords[:10])
        samples_str = "\n---\n".join(
            [
                _truncate_text(doc, 200) for doc in document_samples[:3]
            ]
        )

        prompt = format_prompt(
            "cluster_name_template",
            keywords=keywords_str,
            document_samples=samples_str,
            sentiment_label=sentiment_label,
            document_count=document_count or "Unknown",
        )

        return self.generate(
            prompt=prompt,
            temperature=0.3,
            max_tokens=20, 
        )

    def health_check(self) -> bool:
        """
        Check if Ollama service is available.

        Returns:
            True if service is responding, False otherwise
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5,
            )
            return response.status_code == 200
        except RequestException:
            return False


def _sentiment_to_label(score: float | None) -> str:
    """Convert sentiment score to human-readable label."""
    if score is None:
        return "unknown"
    if score >= 0.3:
        return "positive"
    if score <= -0.3:
        return "negative"
    return "neutral"


def _truncate_text(text: str, max_length: int) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


_client: OllamaClient | None = None


def get_ollama_client() -> OllamaClient:
    """Get or create the default Ollama client instance."""
    global _client
    if _client is None:
        _client = OllamaClient()
    return _client
