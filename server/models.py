from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db import Base, utc_now


def uuid_str() -> str:
    return str(uuid.uuid4())


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    nickname: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    user_uid: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    cookies: Mapped[str] = mapped_column(Text, nullable=False)
    cookie_preview: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    group_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    remark: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_use_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bound_device_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    usage_tags: Mapped[list["AccountUsageTag"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class AccountUsageTag(Base):
    __tablename__ = "account_usage_tags"
    __table_args__ = (UniqueConstraint("account_id", "usage_tag", name="uq_account_usage_tag"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    usage_tag: Mapped[str] = mapped_column(String(50), nullable=False)

    account: Mapped[Account] = relationship(back_populates="usage_tags")


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("device_id", "app_instance_id", name="uq_device_instance"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    device_id: Mapped[str] = mapped_column(String(100), nullable=False)
    app_instance_id: Mapped[str] = mapped_column(String(100), nullable=False)
    device_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    app_version: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="online", nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_ip: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class PublishTask(Base):
    __tablename__ = "publish_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    topics_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    location: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    media_urls_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    cover_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    task_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by_device_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retry: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    published_post_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    published_post_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), default="web", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class SearchTask(Base):
    __tablename__ = "search_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    keyword: Mapped[str] = mapped_column(String(200), nullable=False)
    group_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    require_num: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    sort_type: Mapped[str] = mapped_column(String(30), default="general", nullable=False)
    note_type: Mapped[str] = mapped_column(String(30), default="all", nullable=False)
    time_range: Mapped[str] = mapped_column(String(30), default="all", nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    task_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    claimed_by_device_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    assigned_worker_account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retry: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class SearchResult(Base):
    __tablename__ = "search_results"
    __table_args__ = (
        UniqueConstraint("search_task_id", "post_id", name="uq_search_task_post"),
        UniqueConstraint("search_task_id", "result_id", "post_id", name="uq_search_task_result_post"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    search_task_id: Mapped[str] = mapped_column(String(36), ForeignKey("search_tasks.id"), nullable=False)
    result_id: Mapped[str] = mapped_column(String(100), nullable=False)
    worker_account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=True)
    post_id: Mapped[str] = mapped_column(String(100), nullable=False)
    post_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    content_preview: Mapped[str] = mapped_column(Text, default="", nullable=False)
    author_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    author_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    collect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    review_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AnalyticsTask(Base):
    __tablename__ = "analytics_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False)
    group_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=360, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    task_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    claimed_by_device_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    assigned_worker_account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retry: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (UniqueConstraint("analytics_task_id", "result_id", name="uq_analytics_task_result"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    analytics_task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("analytics_tasks.id"), nullable=True)
    result_id: Mapped[str] = mapped_column(String(100), nullable=False)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False)
    worker_account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=True)
    nickname: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    follower_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    liked_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    post_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    collected_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    posts: Mapped[list["AnalyticsSnapshotPost"]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")


class AnalyticsSnapshotPost(Base):
    __tablename__ = "analytics_snapshot_posts"
    __table_args__ = (UniqueConstraint("snapshot_id", "post_id", name="uq_snapshot_post"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    snapshot_id: Mapped[str] = mapped_column(String(36), ForeignKey("analytics_snapshots.id", ondelete="CASCADE"), nullable=False)
    post_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    post_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    collect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    snapshot: Mapped[AnalyticsSnapshot] = relationship(back_populates="posts")


class TaskResult(Base):
    __tablename__ = "task_results"
    __table_args__ = (UniqueConstraint("task_id", "result_id", name="uq_task_result"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    result_id: Mapped[str] = mapped_column(String(100), nullable=False)
    device_id: Mapped[str] = mapped_column(String(100), nullable=False)
    app_instance_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    log_type: Mapped[str] = mapped_column(String(50), nullable=False)
    operator_type: Mapped[str] = mapped_column(String(20), nullable=False)
    operator_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
