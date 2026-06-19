from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    group: Mapped[str] = mapped_column(String(96), default="Жизнь")
    carry_rule: Mapped[str] = mapped_column(String(64), default="normal_reduce_by_overspend")
    debt_catchup_percent: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    aliases: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    budget_lines: Mapped[list["BudgetLine"]] = relationship(back_populates="category")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")


class MonthlyPlan(Base):
    __tablename__ = "monthly_plans"
    __table_args__ = (UniqueConstraint("month", name="uq_monthly_plan_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[date] = mapped_column(Date, unique=True, index=True)  # first day of month
    planned_income: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    guaranteed_income: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    reserve_percent: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.10"))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lines: Mapped[list["BudgetLine"]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class BudgetLine(Base):
    __tablename__ = "budget_lines"
    __table_args__ = (UniqueConstraint("plan_id", "category_id", name="uq_budget_line_plan_category"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("monthly_plans.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    rule_value: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("0"))
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    source: Mapped[str] = mapped_column(String(64), default="auto")

    plan: Mapped[MonthlyPlan] = relationship(back_populates="lines")
    category: Mapped[Category] = relationship(back_populates="budget_lines")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tx_date: Mapped[date] = mapped_column(Date, index=True)
    tx_type: Mapped[str] = mapped_column(String(16), index=True)  # expense|income
    person: Mapped[str] = mapped_column(String(64), default="Общее")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Optional[Category]] = relationship(back_populates="transactions")
