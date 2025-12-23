import logging

import numpy as np
from umap import UMAP

from app.ml.embeddings import DEFAULT_EMBEDDING_DIM

logger = logging.getLogger(__name__)

DEFAULT_N_NEIGHBORS = 15
DEFAULT_MIN_DIST = 0.1
DEFAULT_N_COMPONENTS = 2
DEFAULT_METRIC = "cosine"


def compute_umap_projection(
    embeddings: list[list[float]],
    n_neighbors: int = DEFAULT_N_NEIGHBORS,
    min_dist: float = DEFAULT_MIN_DIST,
    n_components: int = DEFAULT_N_COMPONENTS,
    metric: str = DEFAULT_METRIC,
    random_state: int | None = None,
) -> list[tuple[float, float]]:
    """
    Compute 2D UMAP projection for a set of embeddings.

    Args:
        embeddings: List of embedding vectors (each is a list of floats)
        n_neighbors: Number of neighbors to consider for UMAP (default: 15)
        min_dist: Minimum distance between points in embedding space (default: 0.1)
        n_components: Number of dimensions in output (default: 2 for 2D)
        metric: Distance metric to use (default: "cosine")
        random_state: Random seed for reproducibility (default: None)

    Returns:
        List of tuples (x, y) representing 2D coordinates for each embedding

    Raises:
        ValueError: If embeddings list is empty or has inconsistent dimensions
        RuntimeError: If UMAP computation fails
    """
    if not embeddings:
        raise ValueError("Embeddings list cannot be empty")

    if n_components != 2:
        raise ValueError(
            f"n_components must be 2 for 2D projections, got {n_components}"
        )

    for i, emb in enumerate(embeddings):
        if not hasattr(emb, "__len__") or len(emb) != DEFAULT_EMBEDDING_DIM:
            raise ValueError(
                f"Embedding at index {i} has invalid length: "
                f"expected {DEFAULT_EMBEDDING_DIM}, got {len(emb) if hasattr(emb, '__len__') else 'unknown'}"
            )

    try:
        logger.info(
            f"Computing UMAP projection for {len(embeddings)} embeddings "
            f"with n_neighbors={n_neighbors}, min_dist={min_dist}"
        )

        embeddings_array = np.array(embeddings, dtype=np.float32)

        umap_model = UMAP(
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            n_components=n_components,
            metric=metric,
            random_state=random_state,
            verbose=False,
        )

        projection = umap_model.fit_transform(embeddings_array)

        if projection.shape[1] != n_components:
            raise RuntimeError(
                f"Expected {n_components} components, got {projection.shape[1]}"
            )

        coordinates = [(float(proj[0]), float(proj[1])) for proj in projection]

        logger.info(
            f"Successfully computed UMAP projection for {len(coordinates)} embeddings"
        )

        return coordinates

    except Exception as e:
        logger.error(f"Failed to compute UMAP projection: {e}", exc_info=True)
        raise RuntimeError(f"Failed to compute UMAP projection: {e}") from e
