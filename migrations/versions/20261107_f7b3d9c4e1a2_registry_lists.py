"""demo_registry.description and .list_name: an operator's description and the list a record belongs to (Axis item 5).

Revision ID: f7b3d9c4e1a2
Revises: e5a1c9d2b7f3
Create Date: 2026-11-07 08:40:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7b3d9c4e1a2"
down_revision: str | Sequence[str] | None = "e5a1c9d2b7f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("demo_registry", sa.Column("description", sa.String(length=200), nullable=True))
    op.add_column("demo_registry", sa.Column("list_name", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("demo_registry", "list_name")
    op.drop_column("demo_registry", "description")
