import logging

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIM = 384


_model_cache: dict[str, SentenceTransformer] = {}


def get_embedding_model(model_name: str = DEFAULT_MODEL_NAME) -> SentenceTransformer:
    """
    Get or initialize the SentenceTransformer model instance.

    Args:
        model_name: Name of the SentenceTransformer model to use

    Returns:
        SentenceTransformer: The model instance
    """
    global _model_cache

    if model_name not in _model_cache:
        logger.info(f"Loading embedding model: {model_name}")
        try:
            _model_cache[model_name] = SentenceTransformer(model_name)
            logger.info(f"Successfully loaded embedding model: {model_name}")
        except Exception as e:
            logger.error(
                f"Failed to load embedding model {model_name}: {e}", exc_info=True
            )
            raise

    return _model_cache[model_name]


def compute_embedding(text: str, model_name: str = DEFAULT_MODEL_NAME) -> list[float]:
    """
    Compute embedding vector for a given text using SentenceTransformers.

    Args:
        text: Text to embed
        model_name: Name of the SentenceTransformer model to use

    Returns:
        List of floats representing the embedding vector (384 dimensions)

    Raises:
        ValueError: If text is empty or None
        RuntimeError: If model fails to generate embedding
    """
    if not text or not text.strip():
        raise ValueError("Text cannot be empty or None")

    try:
        model = get_embedding_model(model_name)
        embedding = model.encode(
            text, normalize_embeddings=True, show_progress_bar=False
        )

        embedding_list = embedding.tolist()

        if len(embedding_list) != DEFAULT_EMBEDDING_DIM:
            logger.warning(
                f"Embedding dimension mismatch: expected {DEFAULT_EMBEDDING_DIM}, "
                f"got {len(embedding_list)}"
            )

        return embedding_list

    except Exception as e:
        logger.error(f"Failed to compute embedding: {e}", exc_info=True)
        raise RuntimeError(f"Failed to compute embedding: {e}") from e
