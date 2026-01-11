import uuid

from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    @declared_attr.directive
    def __tablename__(cls) -> str:
        return cls.__name__.lower()


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()


from .user import User  # noqa: E402,F401
from .document import Document  # noqa: E402,F401
from .ingest_event import IngestEvent  # noqa: E402,F401
from .cluster import Cluster  # noqa: E402,F401
from .document_embedding import DocumentEmbedding  # noqa: E402,F401
from .document_sentiment import DocumentSentiment  # noqa: E402,F401
from .cluster_member import ClusterMember  # noqa: E402,F401
from .keyword import Keyword  # noqa: E402,F401
from .timeseries_summary import TimeseriesSummary  # noqa: E402,F401
from .anomaly import Anomaly  # noqa: E402,F401
from .insight import Insight  # noqa: E402,F401
from .umap_projection import UMAPProjection  # noqa: E402,F401
from .user_ingestion_preference import UserIngestionPreference  # noqa: E402,F401
