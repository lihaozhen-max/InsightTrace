"""Create deterministic product catalog demo data.

Revision ID: 0002_catalog_demo
Revises: 0001_core_schema
Create Date: 2026-09-17
"""

from collections.abc import Sequence
from csv import reader
from datetime import date
from decimal import Decimal
from io import StringIO

import sqlalchemy as sa

from alembic import op

revision: str = "0002_catalog_demo"
down_revision: str | Sequence[str] | None = "0001_core_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "demo_catalog"
TABLE = "funnel_metrics"


def _seed_rows() -> list[dict[str, object]]:
    # July is the baseline. August gains mobile traffic but loses carts on app 5.8.0.
    csv_data = """2026-07-01,P100,星云手机,数码,mobile,organic,5.7.0,12000,1440,132,72,71928.00
2026-07-01,P100,星云手机,数码,mobile,paid,5.7.0,8000,880,81,42,41958.00
2026-07-01,P100,星云手机,数码,desktop,organic,web,6000,840,101,60,59940.00
2026-07-01,P100,星云手机,数码,desktop,paid,web,4000,520,62,35,34965.00
2026-07-01,P200,城市跑鞋,运动,mobile,organic,5.7.0,7000,770,71,35,17465.00
2026-07-01,P200,城市跑鞋,运动,mobile,paid,5.7.0,4000,400,37,18,8982.00
2026-07-01,P200,城市跑鞋,运动,desktop,organic,web,3500,420,50,28,13972.00
2026-07-01,P200,城市跑鞋,运动,desktop,paid,web,2500,275,33,17,8483.00
2026-07-01,P300,日常托特包,服饰,mobile,organic,5.7.0,5500,605,56,27,5397.30
2026-07-01,P300,日常托特包,服饰,mobile,paid,5.7.0,3000,315,29,14,2798.60
2026-07-01,P300,日常托特包,服饰,desktop,organic,web,2800,336,40,22,4397.80
2026-07-01,P300,日常托特包,服饰,desktop,paid,web,1800,198,24,13,2598.70
2026-08-01,P100,星云手机,数码,mobile,organic,5.8.0,15000,1800,90,44,43956.00
2026-08-01,P100,星云手机,数码,mobile,paid,5.8.0,10000,1100,50,24,23976.00
2026-08-01,P100,星云手机,数码,desktop,organic,web,6200,868,104,61,60939.00
2026-08-01,P100,星云手机,数码,desktop,paid,web,4200,546,65,36,35964.00
2026-08-01,P200,城市跑鞋,运动,mobile,organic,5.8.0,8000,880,60,29,14471.00
2026-08-01,P200,城市跑鞋,运动,mobile,paid,5.8.0,5000,500,34,16,7984.00
2026-08-01,P200,城市跑鞋,运动,desktop,organic,web,3600,432,52,29,14471.00
2026-08-01,P200,城市跑鞋,运动,desktop,paid,web,2600,286,34,17,8483.00
2026-08-01,P300,日常托特包,服饰,mobile,organic,5.8.0,7000,700,45,21,4197.90
2026-08-01,P300,日常托特包,服饰,mobile,paid,5.8.0,4000,360,23,11,2198.90
2026-08-01,P300,日常托特包,服饰,desktop,organic,web,2900,348,42,23,4597.70
2026-08-01,P300,日常托特包,服饰,desktop,paid,web,1900,209,25,13,2598.70"""
    columns = (
        "period_month",
        "product_id",
        "product_name",
        "category",
        "device",
        "channel",
        "app_version",
        "impressions",
        "clicks",
        "add_to_carts",
        "orders",
        "revenue",
    )
    result: list[dict[str, object]] = []
    for row in reader(StringIO(csv_data)):
        item = dict(zip(columns, row, strict=True))
        item["period_month"] = date.fromisoformat(str(item["period_month"]))
        for key in ("impressions", "clicks", "add_to_carts", "orders"):
            item[key] = int(str(item[key]))
        item["revenue"] = Decimal(str(item["revenue"]))
        result.append(item)
    return result


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    table = op.create_table(
        TABLE,
        sa.Column("period_month", sa.Date(), nullable=False),
        sa.Column("product_id", sa.String(32), nullable=False),
        sa.Column("product_name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("device", sa.String(20), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("app_version", sa.String(20), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.Column("add_to_carts", sa.Integer(), nullable=False),
        sa.Column("orders", sa.Integer(), nullable=False),
        sa.Column("revenue", sa.Numeric(14, 2), nullable=False),
        sa.CheckConstraint(
            "impressions >= clicks AND clicks >= add_to_carts "
            "AND add_to_carts >= orders AND orders >= 0",
            name="ck_catalog_funnel_order",
        ),
        sa.CheckConstraint("revenue >= 0", name="ck_catalog_revenue_non_negative"),
        sa.PrimaryKeyConstraint(
            "period_month", "product_id", "device", "channel", name="pk_catalog_funnel"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_catalog_funnel_period_device",
        TABLE,
        ["period_month", "device"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_catalog_funnel_period_category",
        TABLE,
        ["period_month", "category"],
        schema=SCHEMA,
    )
    op.bulk_insert(table, _seed_rows())


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
