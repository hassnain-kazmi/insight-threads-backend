import logging
from datetime import date
from typing import Any, Dict, List, Tuple
from uuid import UUID

import numpy as np
import sqlalchemy as sa
from pyod.models.iforest import IForest
from pyod.models.lof import LOF
from sqlalchemy.orm import Session

from app.models import TimeseriesSummary

logger = logging.getLogger(__name__)


def _prepare_timeseries_features(
    timeseries_data: List[Dict[str, Any]],
) -> Tuple[np.ndarray, List[date]]:
    """
    Prepare feature matrix from timeseries data for anomaly detection.

    Features:
    - mention_count
    - avg_sentiment
    - momentum

    Returns:
        Tuple of (feature_matrix, dates) where feature_matrix is (n_samples, n_features)
    """
    if not timeseries_data:
        return np.array([]).reshape(0, 3), []

    mention_counts = []
    sentiments = []
    momentums = []
    dates = []

    for row in timeseries_data:
        dates.append(row["summary_date"])
        mention_counts.append(float(row.get("mention_count", 0)))
        sentiment = row.get("avg_sentiment")
        sentiments.append(float(sentiment) if sentiment is not None else 0.0)
        momentum = row.get("momentum")
        momentums.append(float(momentum) if momentum is not None else 0.0)

    features = np.column_stack([mention_counts, sentiments, momentums])

    for i in range(features.shape[1]):
        col = features[:, i]
        if col.std() > 0:
            features[:, i] = (col - col.mean()) / col.std()
        else:
            features[:, i] = 0.0

    return features, dates


def detect_volume_anomalies(
    timeseries_data: List[Dict[str, Any]],
    contamination: float = 0.1,
) -> List[Dict[str, Any]]:
    """
    Detect anomalies in mention_count (volume spikes) using Isolation Forest.

    Args:
        timeseries_data: List of dicts with keys: summary_date, mention_count, avg_sentiment, momentum
        contamination: Expected proportion of anomalies (default 0.1 = 10%, must be between 0 and 0.5)

    Returns:
        List of anomaly dicts with keys: date, score, type, metadata
    """
    if not (0 < contamination <= 0.5):
        logger.warning(
            "Invalid contamination value %f, using default 0.1", contamination
        )
        contamination = 0.1

    if len(timeseries_data) < 3:
        logger.debug(
            "Insufficient timeseries data for volume anomaly detection (need at least 3 points)"
        )
        return []

    features, dates = _prepare_timeseries_features(timeseries_data)
    volume_features = features[:, 0:1]

    try:
        model = IForest(contamination=contamination, random_state=42)
        model.fit(volume_features)
        scores = model.decision_scores_
        labels = model.labels_

        anomalies = []
        for i, (d, score, is_anomaly) in enumerate(zip(dates, scores, labels)):
            if is_anomaly:
                mention_count = timeseries_data[i].get("mention_count", 0)
                anomalies.append(
                    {
                        "date": d,
                        "score": float(score),
                        "type": "volume_spike",
                        "metadata": {
                            "mention_count": mention_count,
                            "model": "IForest",
                            "contamination": contamination,
                        },
                    }
                )

        return anomalies
    except Exception as e:
        logger.error("Error in volume anomaly detection: %s", e, exc_info=True)
        return []


def detect_sentiment_anomalies(
    timeseries_data: List[Dict[str, Any]],
    contamination: float = 0.1,
) -> List[Dict[str, Any]]:
    """
    Detect anomalies in sentiment (sentiment spikes/drops) using LOF.

    Args:
        timeseries_data: List of dicts with keys: summary_date, mention_count, avg_sentiment, momentum
        contamination: Expected proportion of anomalies (default 0.1 = 10%, must be between 0 and 0.5)

    Returns:
        List of anomaly dicts with keys: date, score, type, metadata
    """
    if not (0 < contamination <= 0.5):
        logger.warning(
            "Invalid contamination value %f, using default 0.1", contamination
        )
        contamination = 0.1

    if len(timeseries_data) < 3:
        logger.debug(
            "Insufficient timeseries data for sentiment anomaly detection (need at least 3 points)"
        )
        return []

    features, dates = _prepare_timeseries_features(timeseries_data)
    sentiment_features = features[:, 1:3]

    try:
        n_samples = sentiment_features.shape[0]
        model = LOF(
            contamination=contamination, n_neighbors=min(5, max(1, n_samples - 1))
        )
        model.fit(sentiment_features)
        scores = model.decision_scores_
        labels = model.labels_

        anomalies = []
        for i, (d, score, is_anomaly) in enumerate(zip(dates, scores, labels)):
            if is_anomaly:
                sentiment = timeseries_data[i].get("avg_sentiment")
                momentum = timeseries_data[i].get("momentum")
                anomalies.append(
                    {
                        "date": d,
                        "score": float(score),
                        "type": "sentiment_spike",
                        "metadata": {
                            "avg_sentiment": float(sentiment)
                            if sentiment is not None
                            else None,
                            "momentum": float(momentum)
                            if momentum is not None
                            else None,
                            "model": "LOF",
                            "contamination": contamination,
                        },
                    }
                )

        return anomalies
    except Exception as e:
        logger.error("Error in sentiment anomaly detection: %s", e, exc_info=True)
        return []


def detect_anomalies_for_cluster(
    db: Session,
    cluster_id: UUID,
    contamination: float = 0.1,
) -> List[Dict[str, Any]]:
    """
    Detect both volume and sentiment anomalies for a cluster.

    Fetches timeseries data from the database and runs both anomaly detection methods.

    Args:
        db: Database session
        cluster_id: Cluster UUID
        contamination: Expected proportion of anomalies (default 0.1 = 10%, must be between 0 and 0.5)

    Returns:
        List of anomaly dicts with keys: date, score, type, metadata
    """
    stmt = (
        sa.select(TimeseriesSummary)
        .where(TimeseriesSummary.cluster_id == cluster_id)
        .order_by(TimeseriesSummary.summary_date)
    )

    result = db.execute(stmt)
    timeseries_rows = result.scalars().all()

    if not timeseries_rows:
        logger.debug("No timeseries data found for cluster %s", cluster_id)
        return []

    timeseries_data = [
        {
            "summary_date": row.summary_date,
            "mention_count": row.mention_count,
            "avg_sentiment": row.avg_sentiment,
            "momentum": row.momentum,
        }
        for row in timeseries_rows
    ]

    volume_anomalies = detect_volume_anomalies(
        timeseries_data, contamination=contamination
    )
    sentiment_anomalies = detect_sentiment_anomalies(
        timeseries_data, contamination=contamination
    )

    all_anomalies = volume_anomalies + sentiment_anomalies

    logger.info(
        "Detected %d anomalies for cluster %s (%d volume, %d sentiment)",
        len(all_anomalies),
        cluster_id,
        len(volume_anomalies),
        len(sentiment_anomalies),
    )

    return all_anomalies
