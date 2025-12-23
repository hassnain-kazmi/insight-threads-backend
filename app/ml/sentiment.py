import logging
from typing import Optional, Tuple

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

logger = logging.getLogger(__name__)

DEFAULT_DISTILBERT_MODEL = "distilbert-base-uncased-finetuned-sst-2-english"

_vader_analyzer: Optional[SentimentIntensityAnalyzer] = None
_distilbert_pipelines: dict = {}


def get_vader_analyzer() -> SentimentIntensityAnalyzer:
    """
    Lazily initialize and return a singleton VADER sentiment analyzer.
    """
    global _vader_analyzer
    if _vader_analyzer is None:
        logger.info("Loading VADER SentimentIntensityAnalyzer")
        _vader_analyzer = SentimentIntensityAnalyzer()
    return _vader_analyzer


def get_distilbert_pipeline(model_name: str = DEFAULT_DISTILBERT_MODEL):
    """
    Lazily initialize and cache a HuggingFace pipeline for DistilBERT sentiment.
    """
    global _distilbert_pipelines
    if model_name not in _distilbert_pipelines:
        logger.info(f"Loading DistilBERT sentiment model: {model_name}")
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        _distilbert_pipelines[model_name] = pipeline(
            "sentiment-analysis", model=model, tokenizer=tokenizer
        )
    return _distilbert_pipelines[model_name]


def compute_vader_score(text: str) -> Optional[float]:
    """
    Compute VADER compound sentiment score for text in [-1, 1].
    Returns None if text is empty/whitespace.
    """
    if not text or not text.strip():
        return None

    analyzer = get_vader_analyzer()
    scores = analyzer.polarity_scores(text)
    return float(scores.get("compound", 0.0))


def compute_distilbert_sentiment(
    text: str,
    model_name: str = DEFAULT_DISTILBERT_MODEL,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Run DistilBERT sentiment classifier and return (signed_score, label).

    - Label is typically "POSITIVE" or "NEGATIVE" (and sometimes "NEUTRAL").
    - Signed score is in [-1, 1], with sign based on label.
    """
    if not text or not text.strip():
        return None, None

    try:
        pipe = get_distilbert_pipeline(model_name)
        results = pipe(text[:512])
        if not results:
            return None, None

        result = results[0]
        label = str(result.get("label"))
        score = float(result.get("score", 0.0))

        label_upper = label.upper()
        if "NEG" in label_upper:
            signed = -score
        elif "POS" in label_upper:
            signed = score
        else:
            signed = 0.0

        return signed, label
    except Exception as e:
        logger.error(f"Failed to compute DistilBERT sentiment: {e}", exc_info=True)
        return None, None


def compute_combined_score(
    vader: Optional[float],
    distilbert: Optional[float],
) -> Optional[float]:
    """
    Combine VADER and DistilBERT into a single score.

    - Simple average of available scores.
    - Returns None if both are None.
    """
    values: list[float] = []
    if vader is not None:
        values.append(float(vader))
    if distilbert is not None:
        values.append(float(distilbert))

    if not values:
        return None

    return float(sum(values) / len(values))


def analyze_sentiment(
    text: str,
    distilbert_model_name: str = DEFAULT_DISTILBERT_MODEL,
) -> dict[str, Optional[float | str]]:
    """
    Convenience function to compute VADER, DistilBERT, and combined scores.

    Returns dict with keys:
      - vader (float | None)
      - distilbert_score (float | None)
      - distilbert_label (str | None)
      - combined_score (float | None)
    """
    if not text or not text.strip():
        return {
            "vader": None,
            "distilbert_score": None,
            "distilbert_label": None,
            "combined_score": None,
        }

    vader = compute_vader_score(text)
    distilbert_score, distilbert_label = compute_distilbert_sentiment(
        text, model_name=distilbert_model_name
    )
    combined = compute_combined_score(vader, distilbert_score)

    return {
        "vader": vader,
        "distilbert_score": distilbert_score,
        "distilbert_label": distilbert_label,
        "combined_score": combined,
    }
