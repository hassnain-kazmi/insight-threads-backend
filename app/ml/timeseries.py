from datetime import date
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import pandas as pd
import sqlalchemy as sa
from prophet import Prophet
from sqlalchemy.orm import Session

from app.models import ClusterMember, Document, DocumentSentiment

logger = logging.getLogger(__name__)


def _compute_daily_aggregates_for_cluster(
    db: Session,
    cluster_id: UUID,
) -> List[Dict[str, Any]]:
    """
    Compute per-day mention counts and average sentiment for a given cluster.

    The date is derived from Document.created_at (UTC date component).
    """
    summary_date = sa.func.date(Document.created_at)

    stmt = (
        sa.select(
            summary_date.label("summary_date"),
            sa.func.count(Document.id).label("mention_count"),
            sa.func.avg(DocumentSentiment.combined_score).label("sentiment_avg"),
        )
        .select_from(ClusterMember)
        .join(Document, ClusterMember.document_id == Document.id)
        .join(
            DocumentSentiment,
            DocumentSentiment.document_id == Document.id,
        )
        .where(ClusterMember.cluster_id == cluster_id)
        .group_by(summary_date)
        .order_by(summary_date)
    )

    result = db.execute(stmt)
    rows = result.all()

    aggregates: List[Dict[str, Any]] = []
    for row in rows:
        aggregates.append(
            {
                "summary_date": row.summary_date,
                "mention_count": int(row.mention_count or 0),
                "sentiment_avg": float(row.sentiment_avg) if row.sentiment_avg is not None else None,
            }
        )

    return aggregates


def _add_momentum(
    aggregates: List[Dict[str, Any]],
) -> None:
    """
    Add simple momentum field in-place: day-over-day change in average sentiment.

    momentum[t] = sentiment_avg[t] - sentiment_avg[t-1]
    """
    prev_sentiment: Optional[float] = None

    for row in aggregates:
        current = row.get("sentiment_avg")
        if current is None or prev_sentiment is None:
            row["momentum"] = None
        else:
            row["momentum"] = float(current - prev_sentiment)
        if current is not None:
            prev_sentiment = current


def _compute_prophet_forecast(
    aggregates: List[Dict[str, Any]],
    forecast_days: int = 7,
) -> Dict[date, Dict[str, Optional[float]]]:
    """
    Use Prophet to compute forecast ranges on daily mention counts.

    Returns a mapping from date -> {forecast_lower, forecast_upper}.
    """

    if len(aggregates) < 2:
        return {}

    records = []
    for row in aggregates:
        ds = row.get("summary_date")
        y = row.get("mention_count", 0)
        if not isinstance(ds, date):
            continue
        records.append({"ds": ds, "y": float(y or 0)})

    if len(records) < 2:
        return {}

    df = pd.DataFrame.from_records(records)

    try:
        model = Prophet()
        model.fit(df)

        future = model.make_future_dataframe(periods=forecast_days, freq="D")
        forecast_df = model.predict(future)
    except Exception as e:
        logger.error("Failed to compute Prophet forecast: %s", e, exc_info=True)
        return {}

    forecasts: Dict[date, Dict[str, Optional[float]]] = {}

    for _, row in forecast_df.iterrows():
        ds = row.get("ds")
        if isinstance(ds, pd.Timestamp):
            ds_date = ds.date()
        elif isinstance(ds, date):
            ds_date = ds
        else:
            continue

        lower = row.get("yhat_lower")
        upper = row.get("yhat_upper")

        forecasts[ds_date] = {
            "forecast_lower": float(lower) if lower is not None else None,
            "forecast_upper": float(upper) if upper is not None else None,
        }

    return forecasts


def build_timeseries_for_cluster(
    db: Session,
    cluster_id: UUID,
    forecast_days: int = 7,
) -> List[Dict[str, Any]]:
    """
    Compute daily aggregates and Prophet forecast for a single cluster.

    Returns a list of dictionaries ready to be written to the
    `timeseries_summary` table with fields:
      - cluster_id (UUID)
      - summary_date (date)
      - mention_count (int)
      - avg_sentiment (float | None)
      - momentum (float | None)
      - forecast_lower (float | None)
      - forecast_upper (float | None)
    """
    aggregates = _compute_daily_aggregates_for_cluster(db, cluster_id)

    if not aggregates:
        return []

    _add_momentum(aggregates)
    forecasts = _compute_prophet_forecast(aggregates, forecast_days=forecast_days)

    result: List[Dict[str, Any]] = []
    seen_dates: set[date] = set()

    for row in aggregates:
        d = row["summary_date"]
        seen_dates.add(d)
        forecast = forecasts.get(d, {})
        result.append(
            {
                "cluster_id": cluster_id,
                "summary_date": d,
                "mention_count": row.get("mention_count", 0),
                "avg_sentiment": row.get("sentiment_avg"),
                "momentum": row.get("momentum"),
                "forecast_lower": forecast.get("forecast_lower"),
                "forecast_upper": forecast.get("forecast_upper"),
            }
        )

    for d, forecast in forecasts.items():
        if d in seen_dates:
            continue
        result.append(
            {
                "cluster_id": cluster_id,
                "summary_date": d,
                "mention_count": 0,
                "avg_sentiment": None,
                "momentum": None,
                "forecast_lower": forecast.get("forecast_lower"),
                "forecast_upper": forecast.get("forecast_upper"),
            }
        )

    result.sort(key=lambda r: r["summary_date"])
    return result


