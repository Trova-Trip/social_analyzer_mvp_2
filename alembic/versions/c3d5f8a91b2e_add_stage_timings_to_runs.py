"""Add stage_timings to runs table

Revision ID: c3d5f8a91b2e
Revises: 84c3bf335c1d
Create Date: 2026-03-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d5f8a91b2e'
down_revision: Union[str, Sequence[str], None] = 'a7e1d3f52b09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add stage_timings JSON column to runs."""
    op.add_column('runs', sa.Column('stage_timings', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove stage_timings column."""
    op.drop_column('runs', 'stage_timings')
