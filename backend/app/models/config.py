from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import APP_SCHEMA, Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class SystemConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "system_configs"
    __table_args__ = (
        Index("ix_system_configs_key", "config_key", unique=True),
        Index("ix_system_configs_group", "config_group"),
        {"schema": APP_SCHEMA},
    )

    config_key: Mapped[str] = mapped_column(String(200), nullable=False)
    config_value: Mapped[str] = mapped_column(Text, nullable=False)
    config_group: Mapped[str] = mapped_column(String(100), nullable=False)
