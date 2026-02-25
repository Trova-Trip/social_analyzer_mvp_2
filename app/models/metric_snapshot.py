"""
MetricSnapshot model — daily aggregate metrics for evaluation benchmarks.
"""
from sqlalchemy import Column, Integer, Text, Float, Date, DateTime, JSON
from sqlalchemy.sql import func

from app.database import Base


class MetricSnapshot(Base):
    __tablename__ = 'metric_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    platform = Column(Text, nullable=False)
    yield_rate = Column(Float, default=0.0)
    avg_score = Column(Float, default=0.0)
    auto_enroll_rate = Column(Float, default=0.0)
    tier_distribution = Column(JSON, default=dict)
    runs_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
