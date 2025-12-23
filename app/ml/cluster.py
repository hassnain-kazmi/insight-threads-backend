import logging
from typing import Any

import numpy as np
import hdbscan
from keybert import KeyBERT
from sklearn.feature_extraction.text import TfidfVectorizer

logger = logging.getLogger(__name__)

DEFAULT_MIN_CLUSTER_SIZE = 3
DEFAULT_MIN_SAMPLES = 2
DEFAULT_CLUSTER_SELECTION_EPSILON = 0.0

_keybert_model_cache: dict[str, KeyBERT] = {}


def compute_hdbscan_clusters(
    embeddings: list[list[float]],
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    cluster_selection_epsilon: float = DEFAULT_CLUSTER_SELECTION_EPSILON,
    metric: str = "euclidean",
) -> tuple[np.ndarray, hdbscan.HDBSCAN]:
    """
    Compute HDBSCAN clusters from embedding vectors.

    Args:
        embeddings: List of embedding vectors (each is a list of floats)
        min_cluster_size: Minimum size of clusters (default: 3)
        min_samples: Minimum samples in neighborhood (default: 2)
        cluster_selection_epsilon: Epsilon for cluster selection (default: 0.0)
        metric: Distance metric to use (default: "euclidean")

    Returns:
        Tuple of (cluster_labels, hdbscan_model)
        - cluster_labels: numpy array with cluster labels (-1 for noise)
        - hdbscan_model: The fitted HDBSCAN model (never None)

    Raises:
        RuntimeError: If clustering fails
    """
    if not embeddings:
        raise ValueError("Embeddings list cannot be empty")

    try:
        embeddings_array = np.array(embeddings, dtype=np.float32)

        if len(embeddings_array.shape) != 2:
            raise ValueError(
                f"Expected 2D array of embeddings, got shape {embeddings_array.shape}"
            )

        logger.info(
            f"Computing HDBSCAN clusters for {len(embeddings)} embeddings "
            f"(min_cluster_size={min_cluster_size}, min_samples={min_samples})"
        )

        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            cluster_selection_epsilon=cluster_selection_epsilon,
            metric=metric,
            prediction_data=True,
        )

        cluster_labels = clusterer.fit_predict(embeddings_array)

        n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
        n_noise = list(cluster_labels).count(-1)

        logger.info(
            f"HDBSCAN clustering completed: {n_clusters} clusters found, "
            f"{n_noise} points marked as noise"
        )

        return cluster_labels, clusterer

    except Exception as e:
        logger.error(f"Failed to compute HDBSCAN clusters: {e}", exc_info=True)
        raise RuntimeError(f"Failed to compute HDBSCAN clusters: {e}") from e


def compute_cluster_centroid(embeddings: list[list[float]]) -> list[float]:
    """
    Compute centroid (mean) of embeddings in a cluster.

    Args:
        embeddings: List of embedding vectors for cluster members

    Returns:
        List of floats representing the centroid vector (384 dimensions)

    Raises:
        ValueError: If embeddings list is empty
    """
    if not embeddings:
        raise ValueError("Embeddings list cannot be empty for centroid computation")

    embeddings_array = np.array(embeddings, dtype=np.float32)
    centroid = np.mean(embeddings_array, axis=0)

    return centroid.tolist()


def extract_keywords_tfidf(
    texts: list[str],
    n_keywords: int = 10,
    max_ngram: int = 2,
    min_df: int = 1,
    max_df: float = 0.95,
) -> list[tuple[str, float]]:
    """
    Extract keywords from texts using TF-IDF.

    Args:
        texts: List of text documents
        n_keywords: Number of keywords to extract (default: 10)
        max_ngram: Maximum n-gram size (default: 2 for bigrams)
        min_df: Minimum document frequency (default: 1)
        max_df: Maximum document frequency as fraction (default: 0.95)

    Returns:
        List of (keyword, weight) tuples sorted by weight (descending)

    Raises:
        ValueError: If texts list is empty or contains no valid text
    """
    if not texts:
        raise ValueError("Texts list cannot be empty")

    valid_texts = [text.strip() for text in texts if text and text.strip()]
    if not valid_texts:
        raise ValueError("No valid texts found for keyword extraction")

    try:
        vectorizer = TfidfVectorizer(
            ngram_range=(1, max_ngram),
            min_df=min_df,
            max_df=max_df,
            stop_words="english",
            lowercase=True,
            token_pattern=r"(?u)\b\w+\b",
        )

        tfidf_matrix = vectorizer.fit_transform(valid_texts)

        feature_names = vectorizer.get_feature_names_out()
        tfidf_scores = np.asarray(tfidf_matrix.sum(axis=0)).flatten()

        keyword_scores = list(zip(feature_names, tfidf_scores))
        keyword_scores.sort(key=lambda x: x[1], reverse=True)

        keywords = keyword_scores[:n_keywords]

        logger.debug(f"Extracted {len(keywords)} keywords using TF-IDF")

        return keywords

    except Exception as e:
        logger.error(f"Failed to extract keywords using TF-IDF: {e}", exc_info=True)
        raise RuntimeError(f"Failed to extract keywords: {e}") from e


def extract_keywords_keybert(
    texts: list[str],
    n_keywords: int = 10,
    model_name: str = "all-MiniLM-L6-v2",
    use_mmr: bool = True,
    diversity: float = 0.5,
) -> list[tuple[str, float]]:
    """
    Extract keywords from texts using KeyBERT.

    Args:
        texts: List of text documents
        n_keywords: Number of keywords to extract (default: 10)
        model_name: SentenceTransformer model name (default: "all-MiniLM-L6-v2")
        use_mmr: Whether to use Maximal Marginal Relevance for diversity (default: True)
        diversity: Diversity parameter for MMR (default: 0.5)

    Returns:
        List of (keyword, score) tuples sorted by score (descending)

    Raises:
        ValueError: If texts list is empty or contains no valid text
        RuntimeError: If KeyBERT extraction fails
    """
    if not texts:
        raise ValueError("Texts list cannot be empty")

    valid_texts = [text.strip() for text in texts if text and text.strip()]
    if not valid_texts:
        raise ValueError("No valid texts found for keyword extraction")

    global _keybert_model_cache

    try:
        combined_text = " ".join(valid_texts)

        if model_name not in _keybert_model_cache:
            logger.debug(f"Loading KeyBERT model: {model_name}")
            _keybert_model_cache[model_name] = KeyBERT(model=model_name)
        kw_model = _keybert_model_cache[model_name]

        extract_kwargs = {
            "keyphrase_ngram_range": (1, 2),
            "stop_words": "english",
            "top_n": n_keywords,
        }
        if use_mmr:
            extract_kwargs.update({"use_mmr": True, "diversity": diversity})

        keywords = kw_model.extract_keywords(combined_text, **extract_kwargs)

        logger.debug(f"Extracted {len(keywords)} keywords using KeyBERT")

        return keywords

    except Exception as e:
        logger.error(f"Failed to extract keywords using KeyBERT: {e}", exc_info=True)
        raise RuntimeError(f"Failed to extract keywords using KeyBERT: {e}") from e


def extract_keywords(
    texts: list[str],
    method: str = "tfidf",
    n_keywords: int = 10,
    **kwargs: Any,
) -> list[tuple[str, float]]:
    """
    Extract keywords from texts using specified method.

    Args:
        texts: List of text documents
        method: Extraction method - "tfidf" or "keybert" (default: "tfidf")
        n_keywords: Number of keywords to extract (default: 10)
        **kwargs: Additional arguments passed to extraction method

    Returns:
        List of (keyword, weight/score) tuples sorted by weight (descending)

    Raises:
        ValueError: If method is not "tfidf" or "keybert"
    """
    if method == "tfidf":
        return extract_keywords_tfidf(texts, n_keywords=n_keywords, **kwargs)
    elif method == "keybert":
        return extract_keywords_keybert(texts, n_keywords=n_keywords, **kwargs)
    else:
        raise ValueError(
            f"Unknown keyword extraction method: {method}. Use 'tfidf' or 'keybert'"
        )
