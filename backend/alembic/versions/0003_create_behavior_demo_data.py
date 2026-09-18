"""Create deterministic customer behavior demo data.

Revision ID: 0003_behavior_demo
Revises: 0002_catalog_demo
Create Date: 2026-09-18
"""

from collections.abc import Sequence
from csv import reader
from datetime import date
from decimal import Decimal
from io import StringIO

import sqlalchemy as sa

from alembic import op

revision: str = "0003_behavior_demo"
down_revision: str | Sequence[str] | None = "0002_catalog_demo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "demo_behavior"
TABLE = "funnel_metrics"


def _seed_rows() -> list[dict[str, object]]:
    # The second week gains paid-social traffic but loses high-intent behavior.
    csv_data = """2026-08-10,organic_search,华东,new,3000,1800,270,120,30,35940.00
2026-08-10,organic_search,华东,returning,2500,1750,350,180,10,53910.00
2026-08-10,organic_search,华南,new,2000,1200,180,80,20,23960.00
2026-08-10,organic_search,华南,returning,1800,1260,252,126,8,37737.00
2026-08-10,paid_social,华东,new,1800,990,119,48,36,14376.00
2026-08-10,paid_social,华东,returning,1000,650,104,50,10,14975.00
2026-08-10,paid_social,华南,new,1500,825,99,39,30,11680.50
2026-08-10,paid_social,华南,returning,800,520,83,40,8,11980.00
2026-08-17,organic_search,华东,new,3100,1830,270,115,35,34442.50
2026-08-17,organic_search,华东,returning,2600,1810,352,178,12,53311.00
2026-08-17,organic_search,华南,new,2100,1230,180,76,25,22762.00
2026-08-17,organic_search,华南,returning,1850,1280,250,122,9,36539.00
2026-08-17,paid_social,华东,new,3200,1400,112,40,480,11980.00
2026-08-17,paid_social,华东,returning,1100,700,105,49,15,14675.50
2026-08-17,paid_social,华南,new,4500,1500,90,28,1125,8386.00
2026-08-17,paid_social,华南,returning,900,560,80,36,15,10782.00"""
    columns = (
        "period_start",
        "channel",
        "region",
        "visitor_type",
        "visits",
        "product_views",
        "add_to_carts",
        "orders",
        "suspicious_sessions",
        "revenue",
    )
    result: list[dict[str, object]] = []
    for row in reader(StringIO(csv_data)):
        item = dict(zip(columns, row, strict=True))
        item["period_start"] = date.fromisoformat(str(item["period_start"]))
        for key in (
            "visits",
            "product_views",
            "add_to_carts",
            "orders",
            "suspicious_sessions",
        ):
            item[key] = int(str(item[key]))
        item["revenue"] = Decimal(str(item["revenue"]))
        result.append(item)
    return result


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    table = op.create_table(
        TABLE,
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("region", sa.String(30), nullable=False),
        sa.Column("visitor_type", sa.String(20), nullable=False),
        sa.Column("visits", sa.Integer(), nullable=False),
        sa.Column("product_views", sa.Integer(), nullable=False),
        sa.Column("add_to_carts", sa.Integer(), nullable=False),
        sa.Column("orders", sa.Integer(), nullable=False),
        sa.Column("suspicious_sessions", sa.Integer(), nullable=False),
        sa.Column("revenue", sa.Numeric(14, 2), nullable=False),
        sa.CheckConstraint(
            "visits >= product_views AND product_views >= add_to_carts "
            "AND add_to_carts >= orders AND orders >= 0",
            name="ck_behavior_funnel_order",
        ),
        sa.CheckConstraint(
            "suspicious_sessions >= 0 AND suspicious_sessions <= visits",
            name="ck_behavior_suspicious_sessions",
        ),
        sa.CheckConstraint("revenue >= 0", name="ck_behavior_revenue_non_negative"),
        sa.PrimaryKeyConstraint(
            "period_start",
            "channel",
            "region",
            "visitor_type",
            name="pk_behavior_funnel",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_behavior_funnel_period_channel",
        TABLE,
        ["period_start", "channel"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_behavior_funnel_period_segment",
        TABLE,
        ["period_start", "region", "visitor_type"],
        schema=SCHEMA,
    )
    op.bulk_insert(table, _seed_rows())


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
