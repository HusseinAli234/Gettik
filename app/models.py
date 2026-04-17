from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    direction: Mapped[str] = mapped_column(String(80), nullable=False)
    people_count: Mapped[int] = mapped_column(Integer, nullable=False)

    transport: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    food: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    activities: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    total_price: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
