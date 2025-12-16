from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Anomaly, TimeseriesSummary

ANOMALY_RECENCY_DAYS = 7
MOMENTUM_RECENCY_DAYS = 7
ANOMALY_SCORE_NORMALIZATION_FACTOR = 10.0
GROWTH_RATE_NORMALIZATION_FACTOR = 6.0
SENTIMENT_CHANGE_NORMALIZATION_FACTOR = 4.0
ZERO_START_GROWTH_DIVISOR = 10.0

TRENDING_SCORE_WEIGHTS = {
    "velocity": 0.3,
    "momentum": 0.25,
    "sentiment": 0.25,
    "anomaly": 0.2,
}

DEFAULT_LOOKBACK_DAYS = 14


def calculate_trending_score(
    cluster_id: UUID,
    db: Session,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> float:
    """
    Calculate combined trending score for a cluster.
    
    The score combines:
    - Velocity: Rate of change in mention count (0-1 normalized)
    - Momentum: Momentum from timeseries (0-1 normalized)
    - Sentiment change: Change in sentiment over time (0-1 normalized)
    - Anomaly weight: Weighted sum of recent anomalies (0-1 normalized)
    
    Args:
        cluster_id: UUID of the cluster
        db: Database session
        lookback_days: Number of days to look back for calculations (default: 14)
        
    Returns:
        Combined trending score (0.0 to 1.0, higher = more trending)
    """
    cutoff_date = date.today() - timedelta(days=lookback_days)
    
    timeseries_query = (
        select(TimeseriesSummary)
        .where(
            TimeseriesSummary.cluster_id == cluster_id,
            TimeseriesSummary.summary_date >= cutoff_date,
        )
        .order_by(TimeseriesSummary.summary_date)
    )
    timeseries_result = db.execute(timeseries_query)
    timeseries_data = timeseries_result.scalars().all()

    anomalies_query = (
        select(Anomaly)
        .where(
            Anomaly.cluster_id == cluster_id,
            Anomaly.anomaly_date >= cutoff_date,
        )
        .order_by(Anomaly.anomaly_date.desc())
    )
    anomalies_result = db.execute(anomalies_query)
    anomalies = anomalies_result.scalars().all()
    
    velocity_score = _calculate_velocity(timeseries_data)
    momentum_score = _calculate_momentum(timeseries_data)
    sentiment_score = _calculate_sentiment_change(timeseries_data)
    anomaly_score = _calculate_anomaly_weight(anomalies)
    
    combined_score = (
        velocity_score * TRENDING_SCORE_WEIGHTS["velocity"]
        + momentum_score * TRENDING_SCORE_WEIGHTS["momentum"]
        + sentiment_score * TRENDING_SCORE_WEIGHTS["sentiment"]
        + anomaly_score * TRENDING_SCORE_WEIGHTS["anomaly"]
    )
    
    return max(0.0, min(1.0, combined_score))


def _calculate_velocity(timeseries_data: list[TimeseriesSummary]) -> float:
    """
    Calculate velocity score based on rate of change in mention count.
    
    Returns normalized score (0-1) where higher velocity = higher score.
    """
    if len(timeseries_data) < 2:
        return 0.0
    
    first_count = timeseries_data[0].mention_count
    last_count = timeseries_data[-1].mention_count
    
    if first_count == 0:
        return min(1.0, last_count / ZERO_START_GROWTH_DIVISOR) if last_count > 0 else 0.0
    
    growth_rate = (last_count - first_count) / first_count
    
    return min(1.0, max(0.0, (growth_rate + 1.0) / GROWTH_RATE_NORMALIZATION_FACTOR))


def _calculate_momentum(timeseries_data: list[TimeseriesSummary]) -> float:
    """
    Calculate momentum score from timeseries momentum values.
    
    Returns normalized score (0-1) based on average momentum.
    """
    if not timeseries_data:
        return 0.0
    
    recent_data = (
        timeseries_data[-MOMENTUM_RECENCY_DAYS:]
        if len(timeseries_data) >= MOMENTUM_RECENCY_DAYS
        else timeseries_data
    )
    momentum_values = [
        ts.momentum for ts in recent_data if ts.momentum is not None
    ]
    
    if not momentum_values:
        return 0.0
    
    avg_momentum = sum(momentum_values) / len(momentum_values)
    
    return max(0.0, min(1.0, (avg_momentum + 1.0) / 2.0))


def _calculate_sentiment_change(timeseries_data: list[TimeseriesSummary]) -> float:
    """
    Calculate sentiment change score.
    
    Returns normalized score (0-1) based on sentiment shift.
    Positive sentiment change = higher score.
    """
    if len(timeseries_data) < 2:
        return 0.0

    first_sentiment = timeseries_data[0].avg_sentiment
    last_sentiment = timeseries_data[-1].avg_sentiment
    
    if first_sentiment is None or last_sentiment is None:
        return 0.0

    sentiment_change = last_sentiment - first_sentiment
    
    return max(0.0, min(1.0, (sentiment_change + 2.0) / SENTIMENT_CHANGE_NORMALIZATION_FACTOR))


def _calculate_anomaly_weight(anomalies: list[Anomaly]) -> float:
    """
    Calculate anomaly weight score with recency weighting.
    
    Applies additional recency weighting to anomalies within the last
    ANOMALY_RECENCY_DAYS, giving more weight to very recent anomalies.
    
    Args:
        anomalies: List of anomalies (already filtered by lookback_days in main function)
        
    Returns:
        Normalized anomaly weight score (0.0 to 1.0)
    """
    if not anomalies:
        return 0.0

    recent_cutoff = date.today() - timedelta(days=ANOMALY_RECENCY_DAYS)
    recent_anomalies = [a for a in anomalies if a.anomaly_date >= recent_cutoff]
    
    if not recent_anomalies:
        return 0.0

    total_weight = 0.0
    total_score = 0.0
    
    for anomaly in recent_anomalies:
        days_ago = (date.today() - anomaly.anomaly_date).days
        recency_weight = 1.0 / (1.0 + days_ago)
        weighted_score = anomaly.score * recency_weight
        total_score += weighted_score
        total_weight += recency_weight
    
    if total_weight == 0:
        return 0.0
    
    avg_weighted_score = total_score / total_weight
    return max(0.0, min(1.0, avg_weighted_score / ANOMALY_SCORE_NORMALIZATION_FACTOR))

