from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from server.db import get_database_url, get_db, init_db
from server.models import (
    Account,
    AccountUsageTag,
    AnalyticsSnapshot,
    AnalyticsSnapshotPost,
    AnalyticsTask,
    AuditLog,
    Device,
    PublishTask,
    SearchResult,
    SearchTask,
    TaskResult,
)


COOKIE_CHECK_TTL_SECONDS = 600
FAILURE_COOLDOWN_THRESHOLD = 3
FAILURE_COOLDOWN_SECONDS = 300
CLAIM_TIMEOUT_MINUTES = 15

ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def mask_cookie(cookies: str) -> str:
    if not cookies:
        return ""
    if len(cookies) <= 16:
        return "*" * len(cookies)
    return f"{cookies[:8]}...{cookies[-8:]}"


def normalize_status(status: str, allowed: set[str], default: str) -> str:
    value = (status or "").strip()
    return value if value in allowed else default


def disable_proxy_for_xhs() -> None:
    if os.getenv("XHS_USE_PROXY", "").lower() in {"1", "true", "yes"}:
        return
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(key, None)


disable_proxy_for_xhs()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Spider XHS Management Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5173",
        "http://localhost:5174",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
class PrimaryAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    cookies: str = Field(min_length=20)
    nickname: str = Field(default="", max_length=100)
    bound_device_id: str = Field(default="", max_length=100)
    remark: str = Field(default="", max_length=500)


class PrimaryCookieSync(BaseModel):
    account_id: str
    cookies: str = Field(min_length=20)
    source: str = Field(default="android_app", max_length=50)


class WorkerCookieCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    cookies: str = Field(min_length=20)
    remark: str = Field(default="", max_length=500)
    usage_tags: list[str] = Field(default_factory=list)
    group_name: str = Field(default="", max_length=100)


class WorkerCookieUpdate(BaseModel):
    status: str | None = Field(default=None, max_length=20)
    remark: str | None = Field(default=None, max_length=500)
    usage_tags: list[str] | None = None
    group_name: str | None = Field(default=None, max_length=100)


class PublishTaskCreate(BaseModel):
    account_id: str
    title: str = Field(min_length=1, max_length=120)
    desc: str = Field(default="", max_length=5000)
    topics: list[str] = Field(default_factory=list)
    location: str = Field(default="", max_length=120)
    media_type: Literal["image", "video"] = "image"
    media_urls: list[str] = Field(default_factory=list)
    cover_url: str = Field(default="", max_length=1000)
    scheduled_at: datetime | None = None
    review_status: Literal["pending", "approved", "rejected"] = "pending"
    max_retry: int = Field(default=1, ge=0, le=5)


class PublishTaskUpdate(BaseModel):
    review_status: Literal["pending", "approved", "rejected"] | None = None
    task_status: Literal["pending", "cancelled"] | None = None
    remark: str = Field(default="", max_length=500)


class SearchTaskCreate(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)
    interval_minutes: int = Field(default=120, ge=5, le=1440)
    require_num: int = Field(default=10, ge=1, le=100)
    sort_type: str = Field(default="general", max_length=30)
    note_type: str = Field(default="all", max_length=30)
    time_range: str = Field(default="all", max_length=30)
    enabled: bool = True
    group_name: str = Field(default="", max_length=100)
    max_retry: int = Field(default=1, ge=0, le=5)


class SearchTaskUpdate(BaseModel):
    enabled: bool | None = None
    group_name: str | None = Field(default=None, max_length=100)
    require_num: int | None = Field(default=None, ge=1, le=100)
    interval_minutes: int | None = Field(default=None, ge=5, le=1440)


class AnalyticsTaskCreate(BaseModel):
    account_id: str
    interval_minutes: int = Field(default=360, ge=360, le=10080)
    enabled: bool = True
    group_name: str = Field(default="", max_length=100)
    max_retry: int = Field(default=1, ge=0, le=5)


class AnalyticsTaskUpdate(BaseModel):
    enabled: bool | None = None
    group_name: str | None = Field(default=None, max_length=100)
    interval_minutes: int | None = Field(default=None, ge=360, le=10080)


class SearchResultUpdate(BaseModel):
    review_status: Literal["pending", "valid", "rejected"] | None = None
    review_note: str | None = Field(default=None, max_length=1000)
    hidden: bool | None = None


class DeviceUpdate(BaseModel):
    status: Literal["online", "offline", "disabled"] | None = None


class AppHeartbeatRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    app_instance_id: str = Field(min_length=1, max_length=100)
    app_version: str = Field(default="", max_length=50)
    device_name: str = Field(default="", max_length=100)


class PublishTaskResultRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    app_instance_id: str = Field(min_length=1, max_length=100)
    result_id: str = Field(min_length=1, max_length=100)
    status: Literal["published", "failed"]
    post_id: str = Field(default="", max_length=100)
    post_url: str = Field(default="", max_length=1000)
    error_message: str = Field(default="", max_length=2000)
    duration_seconds: int = Field(default=0, ge=0)


class SearchItemPayload(BaseModel):
    post_id: str = Field(min_length=1, max_length=100)
    post_url: str = Field(default="", max_length=1000)
    title: str = Field(default="", max_length=300)
    username: str = Field(default="", max_length=100)
    user_id: str = Field(default="", max_length=100)
    content_preview: str = Field(default="", max_length=5000)
    like_count: int = Field(default=0, ge=0)
    comment_count: int = Field(default=0, ge=0)
    collect_count: int = Field(default=0, ge=0)
    publish_time: datetime | None = None


class SearchTaskResultRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    app_instance_id: str = Field(min_length=1, max_length=100)
    result_id: str = Field(min_length=1, max_length=100)
    worker_cookie_id: str = Field(min_length=1, max_length=36)
    partial_success: bool = False
    items: list[SearchItemPayload] = Field(default_factory=list)
    error_message: str = Field(default="", max_length=2000)
    duration_seconds: int = Field(default=0, ge=0)


class AnalyticsPostPayload(BaseModel):
    post_id: str = Field(min_length=1, max_length=100)
    title: str = Field(default="", max_length=300)
    post_url: str = Field(default="", max_length=1000)
    like_count: int = Field(default=0, ge=0)
    comment_count: int = Field(default=0, ge=0)
    collect_count: int = Field(default=0, ge=0)
    publish_time: datetime | None = None


class AnalyticsSnapshotPayload(BaseModel):
    account_id: str
    nickname: str = Field(default="", max_length=100)
    follower_count: int = Field(default=0, ge=0)
    liked_count: int = Field(default=0, ge=0)
    post_count: int = Field(default=0, ge=0)
    collected_total: int | None = Field(default=None, ge=0)
    posts: list[AnalyticsPostPayload] = Field(default_factory=list)


class AnalyticsTaskResultRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    app_instance_id: str = Field(min_length=1, max_length=100)
    result_id: str = Field(min_length=1, max_length=100)
    worker_cookie_id: str = Field(min_length=1, max_length=36)
    snapshot: AnalyticsSnapshotPayload
    error_message: str = Field(default="", max_length=2000)
    duration_seconds: int = Field(default=0, ge=0)


def to_account_public(account: Account) -> dict:
    return {
        "id": account.id,
        "account_type": account.account_type,
        "name": account.name,
        "nickname": account.nickname,
        "cookie_preview": account.cookie_preview,
        "status": account.status,
        "group_name": account.group_name,
        "remark": account.remark,
        "last_check_at": account.last_check_at,
        "last_use_at": account.last_use_at,
        "last_failure_at": account.last_failure_at,
        "failure_count": account.failure_count,
        "cooldown_until": account.cooldown_until,
        "bound_device_id": account.bound_device_id,
        "usage_tags": [tag.usage_tag for tag in account.usage_tags],
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }


def to_publish_task(task: PublishTask) -> dict:
    return {
        "id": task.id,
        "account_id": task.account_id,
        "title": task.title,
        "desc": task.content,
        "topics": task.topics_json,
        "location": task.location,
        "media_type": task.media_type,
        "media_urls": task.media_urls_json,
        "cover_url": task.cover_url,
        "review_status": task.review_status,
        "task_status": task.task_status,
        "scheduled_at": task.scheduled_at,
        "claimed_by_device_id": task.claimed_by_device_id,
        "claim_expires_at": task.claim_expires_at,
        "retry_count": task.retry_count,
        "max_retry": task.max_retry,
        "last_error": task.last_error,
        "published_post_id": task.published_post_id,
        "published_post_url": task.published_post_url,
        "created_by": task.created_by,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def to_search_task(task: SearchTask) -> dict:
    return {
        "id": task.id,
        "keyword": task.keyword,
        "group_name": task.group_name,
        "require_num": task.require_num,
        "sort_type": task.sort_type,
        "note_type": task.note_type,
        "time_range": task.time_range,
        "interval_minutes": task.interval_minutes,
        "enabled": task.enabled,
        "task_status": task.task_status,
        "claimed_by_device_id": task.claimed_by_device_id,
        "assigned_worker_account_id": task.assigned_worker_account_id,
        "claim_expires_at": task.claim_expires_at,
        "last_run_at": task.last_run_at,
        "last_success_at": task.last_success_at,
        "last_error": task.last_error,
        "retry_count": task.retry_count,
        "max_retry": task.max_retry,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def to_analytics_task(task: AnalyticsTask) -> dict:
    return {
        "id": task.id,
        "account_id": task.account_id,
        "group_name": task.group_name,
        "interval_minutes": task.interval_minutes,
        "enabled": task.enabled,
        "task_status": task.task_status,
        "claimed_by_device_id": task.claimed_by_device_id,
        "assigned_worker_account_id": task.assigned_worker_account_id,
        "claim_expires_at": task.claim_expires_at,
        "last_run_at": task.last_run_at,
        "last_success_at": task.last_success_at,
        "last_error": task.last_error,
        "retry_count": task.retry_count,
        "max_retry": task.max_retry,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def to_device_public(device: Device) -> dict:
    return {
        "id": device.id,
        "device_id": device.device_id,
        "app_instance_id": device.app_instance_id,
        "device_name": device.device_name,
        "app_version": device.app_version,
        "status": device.status,
        "last_heartbeat_at": device.last_heartbeat_at,
        "created_at": device.created_at,
        "updated_at": device.updated_at,
    }


def to_search_result_public(item: SearchResult) -> dict:
    return {
        "id": item.id,
        "search_task_id": item.search_task_id,
        "result_id": item.result_id,
        "worker_account_id": item.worker_account_id,
        "post_id": item.post_id,
        "post_url": item.post_url,
        "title": item.title,
        "content_preview": item.content_preview,
        "author_id": item.author_id,
        "author_name": item.author_name,
        "like_count": item.like_count,
        "comment_count": item.comment_count,
        "collect_count": item.collect_count,
        "publish_time": item.publish_time,
        "review_status": item.review_status,
        "review_note": item.review_note,
        "hidden": item.hidden,
        "created_at": item.created_at,
    }


def to_snapshot_public(item: AnalyticsSnapshot) -> dict:
    return {
        "id": item.id,
        "analytics_task_id": item.analytics_task_id,
        "result_id": item.result_id,
        "account_id": item.account_id,
        "worker_account_id": item.worker_account_id,
        "nickname": item.nickname,
        "follower_count": item.follower_count,
        "liked_total": item.liked_total,
        "post_total": item.post_total,
        "collected_total": item.collected_total,
        "posts": [
            {
                "id": post.id,
                "post_id": post.post_id,
                "title": post.title,
                "post_url": post.post_url,
                "like_count": post.like_count,
                "comment_count": post.comment_count,
                "collect_count": post.collect_count,
                "publish_time": post.publish_time,
            }
            for post in item.posts
        ],
        "created_at": item.created_at,
    }


def write_audit_log(
    session: Session,
    *,
    log_type: str,
    operator_type: str,
    operator_id: str,
    target_type: str,
    target_id: str,
    message: str,
    payload: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            log_type=log_type,
            operator_type=operator_type,
            operator_id=operator_id,
            target_type=target_type,
            target_id=target_id,
            message=message,
            payload=payload or {},
        )
    )


def require_account(session: Session, account_id: str, expected_type: str | None = None) -> Account:
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    if expected_type and account.account_type != expected_type:
        raise HTTPException(status_code=400, detail="账号类型不匹配")
    return account


def set_usage_tags(session: Session, account: Account, tags: list[str]) -> None:
    normalized = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
    account.usage_tags.clear()
    for tag in normalized:
        account.usage_tags.append(AccountUsageTag(usage_tag=tag))
    session.flush()


def refresh_account_status(account: Account) -> None:
    now = utc_now()
    if account.status == "cooldown" and account.cooldown_until and account.cooldown_until <= now:
        account.status = "active"
        account.cooldown_until = None


def mark_account_success(account: Account) -> None:
    account.failure_count = 0
    if account.status == "cooldown":
        account.status = "active"
        account.cooldown_until = None


def mark_account_failure(account: Account, message: str = "") -> None:
    account.failure_count += 1
    account.last_failure_at = utc_now()
    lowered = (message or "").lower()
    if "cookie" in lowered or "登录" in message or "invalid" in lowered:
        account.status = "invalid"
        account.cooldown_until = None
        return
    if account.failure_count >= FAILURE_COOLDOWN_THRESHOLD:
        account.status = "cooldown"
        account.cooldown_until = utc_now() + timedelta(seconds=FAILURE_COOLDOWN_SECONDS)


def validate_cookie(account: Account) -> tuple[bool, str]:
    if len((account.cookies or "").strip()) < 20:
        return False, "Cookie 长度不足"
    return True, "Cookie 可用"


def ensure_device(session: Session, payload: AppHeartbeatRequest, request: Request | None = None) -> Device:
    stmt = select(Device).where(Device.device_id == payload.device_id, Device.app_instance_id == payload.app_instance_id)
    device = session.execute(stmt).scalar_one_or_none()
    if device is None:
        device = Device(
            device_id=payload.device_id,
            app_instance_id=payload.app_instance_id,
            device_name=payload.device_name,
            app_version=payload.app_version,
            status="online",
            last_seen_ip=request.client.host if request and request.client else "",
            last_heartbeat_at=utc_now(),
        )
        session.add(device)
    else:
        device.device_name = payload.device_name
        device.app_version = payload.app_version
        if device.status != "disabled":
            device.status = "online"
        device.last_seen_ip = request.client.host if request and request.client else device.last_seen_ip
        device.last_heartbeat_at = utc_now()
    return device


def touch_device_from_query(
    session: Session,
    request: Request | None,
    *,
    device_id: str,
    app_instance_id: str = "",
    app_version: str = "",
    device_name: str = "",
) -> Device | None:
    if not app_instance_id:
        return None
    payload = AppHeartbeatRequest(
        device_id=device_id,
        app_instance_id=app_instance_id,
        app_version=app_version,
        device_name=device_name,
    )
    return ensure_device(session, payload, request)


def reset_task_to_pending(task, *, reset_retry: bool = False) -> None:
    task.task_status = "pending"
    task.claimed_by_device_id = ""
    task.claim_expires_at = None
    task.last_error = ""
    if reset_retry:
        task.retry_count = 0
    if hasattr(task, "assigned_worker_account_id"):
        task.assigned_worker_account_id = None


def reclaim_expired_claims(session: Session) -> None:
    now = utc_now()
    for model in (PublishTask, SearchTask, AnalyticsTask):
        stmt = select(model).where(
            model.task_status == "claimed",
            model.claim_expires_at.is_not(None),
            model.claim_expires_at <= now,
        )
        for task in session.execute(stmt).scalars():
            task.task_status = "pending"
            task.claimed_by_device_id = ""
            task.claim_expires_at = None
            if hasattr(task, "assigned_worker_account_id"):
                task.assigned_worker_account_id = None
            write_audit_log(
                session,
                log_type="task_reclaim",
                operator_type="system",
                operator_id="system",
                target_type=model.__tablename__,
                target_id=task.id,
                message="任务领取超时已回收",
                payload={},
            )
    session.flush()


def device_has_active_task(session: Session, device_id: str) -> bool:
    active_statuses = ("claimed", "running")
    for model in (PublishTask, SearchTask, AnalyticsTask):
        stmt = select(func.count()).select_from(model).where(
            model.claimed_by_device_id == device_id,
            model.task_status.in_(active_statuses),
        )
        if session.execute(stmt).scalar_one() > 0:
            return True
    return False


def account_has_active_publish(session: Session, account_id: str) -> bool:
    stmt = select(func.count()).select_from(PublishTask).where(
        PublishTask.account_id == account_id,
        PublishTask.task_status.in_(("claimed", "running")),
    )
    return session.execute(stmt).scalar_one() > 0


def worker_is_busy(session: Session, worker_id: str) -> bool:
    for model in (SearchTask, AnalyticsTask):
        stmt = select(func.count()).select_from(model).where(
            model.assigned_worker_account_id == worker_id,
            model.task_status.in_(("claimed", "running")),
        )
        if session.execute(stmt).scalar_one() > 0:
            return True
    return False


def choose_worker(session: Session, *, usage_tag: str, group_name: str = "") -> Account | None:
    stmt = (
        select(Account)
        .options(selectinload(Account.usage_tags))
        .where(Account.account_type == "worker")
        .order_by(Account.last_use_at.is_(None).desc(), Account.last_use_at.asc(), Account.created_at.asc())
    )
    workers = session.execute(stmt).scalars().all()
    now = utc_now()
    for worker in workers:
        refresh_account_status(worker)
        if worker.status != "active":
            continue
        if group_name and worker.group_name != group_name:
            continue
        tags = {item.usage_tag for item in worker.usage_tags}
        if usage_tag not in tags and "worker_backup" not in tags:
            continue
        if worker.cooldown_until and worker.cooldown_until > now:
            continue
        if worker_is_busy(session, worker.id):
            continue
        worker.last_use_at = now
        return worker
    return None


def save_task_result(
    session: Session,
    *,
    task_type: str,
    task_id: str,
    result_id: str,
    device_id: str,
    app_instance_id: str,
    status: str,
    duration_seconds: int,
    error_message: str,
    payload: dict,
) -> tuple[TaskResult, bool]:
    stmt = select(TaskResult).where(TaskResult.task_id == task_id, TaskResult.result_id == result_id)
    existing = session.execute(stmt).scalar_one_or_none()
    if existing:
        return existing, False
    item = TaskResult(
        task_type=task_type,
        task_id=task_id,
        result_id=result_id,
        device_id=device_id,
        app_instance_id=app_instance_id,
        status=status,
        duration_seconds=duration_seconds,
        error_message=error_message,
        payload=payload,
    )
    session.add(item)
    session.flush()
    return item, True


def claim_publish_task(session: Session, device_id: str) -> PublishTask | None:
    reclaim_expired_claims(session)
    if device_has_active_task(session, device_id):
        raise HTTPException(status_code=409, detail="当前设备已有运行中任务")
    now = utc_now()
    stmt = (
        select(PublishTask)
        .where(
            PublishTask.review_status == "approved",
            PublishTask.task_status == "pending",
            or_(PublishTask.scheduled_at.is_(None), PublishTask.scheduled_at <= now),
        )
        .order_by(PublishTask.scheduled_at.asc().nullsfirst(), PublishTask.created_at.asc())
    )
    for task in session.execute(stmt).scalars():
        account = require_account(session, task.account_id, "primary")
        refresh_account_status(account)
        if account.status != "active":
            continue
        if account.bound_device_id and account.bound_device_id != device_id:
            continue
        if account_has_active_publish(session, task.account_id):
            continue
        task.task_status = "claimed"
        task.claimed_by_device_id = device_id
        task.claim_expires_at = now + timedelta(minutes=CLAIM_TIMEOUT_MINUTES)
        write_audit_log(
            session,
            log_type="task_claim",
            operator_type="app",
            operator_id=device_id,
            target_type="publish_task",
            target_id=task.id,
            message="发帖任务已领取",
            payload={"account_id": task.account_id},
        )
        return task
    return None


def search_task_due(task: SearchTask) -> bool:
    if not task.enabled or task.task_status != "pending":
        return False
    if task.last_run_at is None:
        return True
    return task.last_run_at <= utc_now() - timedelta(minutes=task.interval_minutes)


def claim_search_task(session: Session, device_id: str) -> tuple[SearchTask, Account] | None:
    reclaim_expired_claims(session)
    if device_has_active_task(session, device_id):
        raise HTTPException(status_code=409, detail="当前设备已有运行中任务")
    stmt = select(SearchTask).order_by(SearchTask.last_run_at.asc().nullsfirst(), SearchTask.created_at.asc())
    for task in session.execute(stmt).scalars():
        if not search_task_due(task):
            continue
        worker = choose_worker(session, usage_tag="worker_search", group_name=task.group_name)
        if not worker:
            continue
        task.task_status = "claimed"
        task.claimed_by_device_id = device_id
        task.assigned_worker_account_id = worker.id
        task.claim_expires_at = utc_now() + timedelta(minutes=CLAIM_TIMEOUT_MINUTES)
        write_audit_log(
            session,
            log_type="cookie_assign",
            operator_type="system",
            operator_id="system",
            target_type="search_task",
            target_id=task.id,
            message="搜索任务已分配小号",
            payload={"worker_account_id": worker.id},
        )
        return task, worker
    return None


def analytics_task_due(task: AnalyticsTask) -> bool:
    if not task.enabled or task.task_status != "pending":
        return False
    if task.last_run_at is None:
        return True
    return task.last_run_at <= utc_now() - timedelta(minutes=task.interval_minutes)


def claim_analytics_task(session: Session, device_id: str) -> tuple[AnalyticsTask, Account] | None:
    reclaim_expired_claims(session)
    if device_has_active_task(session, device_id):
        raise HTTPException(status_code=409, detail="当前设备已有运行中任务")
    stmt = select(AnalyticsTask).order_by(AnalyticsTask.last_run_at.asc().nullsfirst(), AnalyticsTask.created_at.asc())
    for task in session.execute(stmt).scalars():
        if not analytics_task_due(task):
            continue
        worker = choose_worker(session, usage_tag="worker_analytics", group_name=task.group_name)
        if not worker:
            continue
        task.task_status = "claimed"
        task.claimed_by_device_id = device_id
        task.assigned_worker_account_id = worker.id
        task.claim_expires_at = utc_now() + timedelta(minutes=CLAIM_TIMEOUT_MINUTES)
        write_audit_log(
            session,
            log_type="cookie_assign",
            operator_type="system",
            operator_id="system",
            target_type="analytics_task",
            target_id=task.id,
            message="监控任务已分配小号",
            payload={"worker_account_id": worker.id},
        )
        return task, worker
    return None


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "database_url": get_database_url()}


@app.get("/api/accounts")
def list_accounts(session: Session = Depends(get_db)) -> dict:
    stmt = select(Account).options(selectinload(Account.usage_tags)).order_by(Account.created_at.desc())
    accounts = session.execute(stmt).scalars().all()
    return {
        "primary_accounts": [to_account_public(item) for item in accounts if item.account_type == "primary"],
        "worker_cookies": [to_account_public(item) for item in accounts if item.account_type == "worker"],
    }


@app.post("/api/accounts/primary")
def create_primary_account(payload: PrimaryAccountCreate, session: Session = Depends(get_db)) -> dict:
    account = Account(
        account_type="primary",
        name=payload.name.strip(),
        nickname=payload.nickname.strip(),
        cookies=payload.cookies.strip(),
        cookie_preview=mask_cookie(payload.cookies),
        status="active",
        bound_device_id=payload.bound_device_id.strip(),
        remark=payload.remark.strip(),
    )
    session.add(account)
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="account",
        target_id=account.id,
        message="创建主账号",
        payload={"account_type": "primary"},
    )
    session.commit()
    session.refresh(account)
    return {"account": to_account_public(account)}


@app.post("/api/accounts/primary/{account_id}/check")
def check_primary_account(account_id: str, session: Session = Depends(get_db)) -> dict:
    account = require_account(session, account_id, "primary")
    ok, message = validate_cookie(account)
    account.last_check_at = utc_now()
    if ok:
        account.status = "active"
        mark_account_success(account)
    else:
        mark_account_failure(account, message)
    session.commit()
    session.refresh(account)
    return {"success": ok, "message": message, "account": to_account_public(account)}


@app.post("/api/app/auth/sync-cookie")
def sync_primary_cookie(payload: PrimaryCookieSync, session: Session = Depends(get_db)) -> dict:
    account = require_account(session, payload.account_id, "primary")
    account.cookies = payload.cookies.strip()
    account.cookie_preview = mask_cookie(payload.cookies)
    account.status = "active"
    account.last_check_at = utc_now()
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="app",
        operator_id=payload.source,
        target_type="account",
        target_id=account.id,
        message="App 同步主 Cookie",
        payload={},
    )
    session.commit()
    session.refresh(account)
    return {"account": to_account_public(account)}


@app.get("/api/cookie-workers")
def list_cookie_workers(session: Session = Depends(get_db)) -> dict:
    stmt = (
        select(Account)
        .options(selectinload(Account.usage_tags))
        .where(Account.account_type == "worker")
        .order_by(Account.created_at.desc())
    )
    return {"worker_cookies": [to_account_public(item) for item in session.execute(stmt).scalars().all()]}


@app.post("/api/cookie-workers")
def create_cookie_worker(payload: WorkerCookieCreate, session: Session = Depends(get_db)) -> dict:
    worker = Account(
        account_type="worker",
        name=payload.name.strip(),
        cookies=payload.cookies.strip(),
        cookie_preview=mask_cookie(payload.cookies),
        status="active",
        group_name=payload.group_name.strip(),
        remark=payload.remark.strip(),
    )
    session.add(worker)
    session.flush()
    set_usage_tags(session, worker, payload.usage_tags)
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="account",
        target_id=worker.id,
        message="创建小号 Cookie",
        payload={"group_name": worker.group_name},
    )
    session.commit()
    session.refresh(worker)
    return {"worker_cookie": to_account_public(worker)}


@app.patch("/api/cookie-workers/{worker_id}")
def update_cookie_worker(worker_id: str, payload: WorkerCookieUpdate, session: Session = Depends(get_db)) -> dict:
    worker = require_account(session, worker_id, "worker")
    if payload.status is not None:
        worker.status = normalize_status(payload.status, {"active", "cooldown", "invalid", "disabled"}, worker.status)
    if payload.remark is not None:
        worker.remark = payload.remark.strip()
    if payload.group_name is not None:
        worker.group_name = payload.group_name.strip()
    if payload.usage_tags is not None:
        set_usage_tags(session, worker, payload.usage_tags)
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="account",
        target_id=worker.id,
        message="更新小号 Cookie",
        payload={"status": worker.status},
    )
    session.commit()
    session.refresh(worker)
    return {"worker_cookie": to_account_public(worker)}


@app.post("/api/cookie-workers/{worker_id}/check")
def check_cookie_worker(worker_id: str, session: Session = Depends(get_db)) -> dict:
    worker = require_account(session, worker_id, "worker")
    ok, message = validate_cookie(worker)
    worker.last_check_at = utc_now()
    if ok:
        worker.status = "active"
        mark_account_success(worker)
    else:
        mark_account_failure(worker, message)
    session.commit()
    session.refresh(worker)
    return {"success": ok, "message": message, "worker_cookie": to_account_public(worker)}


@app.post("/api/app/heartbeat")
def app_heartbeat(payload: AppHeartbeatRequest, request: Request, session: Session = Depends(get_db)) -> dict:
    device = ensure_device(session, payload, request)
    write_audit_log(
        session,
        log_type="app_result",
        operator_type="app",
        operator_id=payload.device_id,
        target_type="device",
        target_id=device.id,
        message="设备心跳",
        payload={"app_version": payload.app_version},
    )
    session.commit()
    session.refresh(device)
    return {"device": to_device_public(device)}


@app.get("/api/devices")
def list_devices(session: Session = Depends(get_db)) -> dict:
    stmt = select(Device).order_by(Device.last_heartbeat_at.desc().nulls_last(), Device.created_at.desc())
    return {"devices": [to_device_public(item) for item in session.execute(stmt).scalars().all()]}


@app.patch("/api/devices/{device_id}")
def update_device(device_id: str, payload: DeviceUpdate, session: Session = Depends(get_db)) -> dict:
    device = session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    if payload.status is not None:
        device.status = payload.status
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="device",
        target_id=device.id,
        message="更新设备状态",
        payload={"status": device.status},
    )
    session.commit()
    session.refresh(device)
    return {"device": to_device_public(device)}


@app.post("/api/publish-tasks")
def create_publish_task(payload: PublishTaskCreate, session: Session = Depends(get_db)) -> dict:
    require_account(session, payload.account_id, "primary")
    if not payload.media_urls:
        raise HTTPException(status_code=400, detail="至少需要一个媒体 URL")
    task = PublishTask(
        account_id=payload.account_id,
        title=payload.title.strip(),
        content=payload.desc,
        topics_json=[item.strip() for item in payload.topics if item.strip()],
        location=payload.location.strip(),
        media_type=payload.media_type,
        media_urls_json=[item.strip() for item in payload.media_urls if item.strip()],
        cover_url=payload.cover_url.strip(),
        scheduled_at=payload.scheduled_at,
        review_status=payload.review_status,
        task_status="pending",
        max_retry=payload.max_retry,
    )
    session.add(task)
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="publish_task",
        target_id=task.id,
        message="创建发帖任务",
        payload={"review_status": task.review_status},
    )
    session.commit()
    session.refresh(task)
    return {"task": to_publish_task(task)}


@app.get("/api/publish-tasks")
def list_publish_tasks(
    status: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    session: Session = Depends(get_db),
) -> dict:
    stmt = select(PublishTask).order_by(PublishTask.created_at.desc())
    if status:
        stmt = stmt.where(PublishTask.task_status == status)
    if review_status:
        stmt = stmt.where(PublishTask.review_status == review_status)
    return {"tasks": [to_publish_task(item) for item in session.execute(stmt).scalars().all()]}


@app.get("/api/publish-records")
def list_publish_records(session: Session = Depends(get_db)) -> dict:
    stmt = select(PublishTask).where(PublishTask.task_status == "success").order_by(PublishTask.updated_at.desc())
    return {"records": [to_publish_task(item) for item in session.execute(stmt).scalars().all()]}


@app.patch("/api/publish-tasks/{task_id}")
def update_publish_task(task_id: str, payload: PublishTaskUpdate, session: Session = Depends(get_db)) -> dict:
    task = session.get(PublishTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="发帖任务不存在")
    if payload.review_status is not None:
        task.review_status = payload.review_status
    if payload.task_status is not None:
        task.task_status = payload.task_status
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="publish_task",
        target_id=task.id,
        message="更新发帖任务",
        payload={"review_status": task.review_status, "task_status": task.task_status, "remark": payload.remark},
    )
    session.commit()
    session.refresh(task)
    return {"task": to_publish_task(task)}


@app.post("/api/publish-tasks/{task_id}/requeue")
def requeue_publish_task(task_id: str, session: Session = Depends(get_db)) -> dict:
    task = session.get(PublishTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="发帖任务不存在")
    reset_task_to_pending(task, reset_retry=True)
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="publish_task",
        target_id=task.id,
        message="重新入队发帖任务",
        payload={},
    )
    session.commit()
    session.refresh(task)
    return {"task": to_publish_task(task)}


@app.get("/api/app/publish-tasks/next")
def app_next_publish_task(
    request: Request,
    device_id: str,
    app_instance_id: str = Query(default=""),
    app_version: str = Query(default=""),
    device_name: str = Query(default=""),
    session: Session = Depends(get_db),
) -> dict:
    device = touch_device_from_query(
        session,
        request,
        device_id=device_id,
        app_instance_id=app_instance_id,
        app_version=app_version,
        device_name=device_name,
    )
    if device and device.status == "disabled":
        session.commit()
        raise HTTPException(status_code=403, detail="设备已禁用")
    task = claim_publish_task(session, device_id)
    session.commit()
    return {"task": to_publish_task(task) if task else None}


def handle_publish_task_result(task_id: str, payload: PublishTaskResultRequest, session: Session) -> dict:
    task = session.get(PublishTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="发帖任务不存在")
    result, created = save_task_result(
        session,
        task_type="publish",
        task_id=task_id,
        result_id=payload.result_id,
        device_id=payload.device_id,
        app_instance_id=payload.app_instance_id,
        status=payload.status,
        duration_seconds=payload.duration_seconds,
        error_message=payload.error_message,
        payload=payload.model_dump(mode="json"),
    )
    if created:
        task.claimed_by_device_id = ""
        task.claim_expires_at = None
        task.published_post_id = payload.post_id
        task.published_post_url = payload.post_url
        task.last_error = payload.error_message
        primary = require_account(session, task.account_id, "primary")
        if payload.status == "published":
            task.task_status = "success"
            mark_account_success(primary)
        else:
            task.task_status = "failed"
            task.retry_count += 1
            mark_account_failure(primary, payload.error_message)
        write_audit_log(
            session,
            log_type="app_result",
            operator_type="app",
            operator_id=payload.device_id,
            target_type="publish_task",
            target_id=task.id,
            message="回传发帖结果",
            payload={"status": payload.status},
        )
        session.commit()
        session.refresh(task)
    return {"created": created, "result_id": result.result_id, "task": to_publish_task(task)}


@app.post("/api/app/publish-tasks/{task_id}/result")
def app_publish_task_result(task_id: str, payload: PublishTaskResultRequest, session: Session = Depends(get_db)) -> dict:
    return handle_publish_task_result(task_id, payload, session)


@app.post("/api/search-tasks")
def create_search_task(payload: SearchTaskCreate, session: Session = Depends(get_db)) -> dict:
    task = SearchTask(
        keyword=payload.keyword.strip(),
        group_name=payload.group_name.strip(),
        require_num=payload.require_num,
        sort_type=payload.sort_type.strip(),
        note_type=payload.note_type.strip(),
        time_range=payload.time_range.strip(),
        interval_minutes=payload.interval_minutes,
        enabled=payload.enabled,
        task_status="pending",
        max_retry=payload.max_retry,
    )
    session.add(task)
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="search_task",
        target_id=task.id,
        message="创建关键词采集任务",
        payload={"group_name": task.group_name},
    )
    session.commit()
    session.refresh(task)
    return {"task": to_search_task(task)}


@app.get("/api/search-tasks")
def list_search_tasks(session: Session = Depends(get_db)) -> dict:
    stmt = select(SearchTask).order_by(SearchTask.created_at.desc())
    return {"tasks": [to_search_task(item) for item in session.execute(stmt).scalars().all()]}


@app.patch("/api/search-tasks/{task_id}")
def update_search_task(task_id: str, payload: SearchTaskUpdate, session: Session = Depends(get_db)) -> dict:
    task = session.get(SearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="关键词任务不存在")
    if payload.enabled is not None:
        task.enabled = payload.enabled
    if payload.group_name is not None:
        task.group_name = payload.group_name.strip()
    if payload.require_num is not None:
        task.require_num = payload.require_num
    if payload.interval_minutes is not None:
        task.interval_minutes = payload.interval_minutes
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="search_task",
        target_id=task.id,
        message="更新关键词采集任务",
        payload={"enabled": task.enabled},
    )
    session.commit()
    session.refresh(task)
    return {"task": to_search_task(task)}


@app.post("/api/search-tasks/{task_id}/requeue")
def requeue_search_task(task_id: str, session: Session = Depends(get_db)) -> dict:
    task = session.get(SearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="关键词任务不存在")
    reset_task_to_pending(task, reset_retry=True)
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="search_task",
        target_id=task.id,
        message="重新入队关键词采集任务",
        payload={},
    )
    session.commit()
    session.refresh(task)
    return {"task": to_search_task(task)}


@app.get("/api/app/search-tasks/next")
def app_next_search_task(
    request: Request,
    device_id: str,
    app_instance_id: str = Query(default=""),
    app_version: str = Query(default=""),
    device_name: str = Query(default=""),
    session: Session = Depends(get_db),
) -> dict:
    device = touch_device_from_query(
        session,
        request,
        device_id=device_id,
        app_instance_id=app_instance_id,
        app_version=app_version,
        device_name=device_name,
    )
    if device and device.status == "disabled":
        session.commit()
        raise HTTPException(status_code=403, detail="设备已禁用")
    claimed = claim_search_task(session, device_id)
    session.commit()
    if not claimed:
        return {"task": None}
    task, worker = claimed
    body = to_search_task(task)
    body["worker_cookie_id"] = worker.id
    return {"task": body}


def handle_search_task_result(task_id: str, payload: SearchTaskResultRequest, session: Session) -> dict:
    task = session.get(SearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="关键词任务不存在")
    result_status = "partial_success" if payload.partial_success else ("failed" if payload.error_message and not payload.items else "success")
    result, created = save_task_result(
        session,
        task_type="search",
        task_id=task_id,
        result_id=payload.result_id,
        device_id=payload.device_id,
        app_instance_id=payload.app_instance_id,
        status=result_status,
        duration_seconds=payload.duration_seconds,
        error_message=payload.error_message,
        payload=payload.model_dump(mode="json"),
    )
    saved_count = 0
    if created:
        worker = require_account(session, payload.worker_cookie_id, "worker")
        task.claimed_by_device_id = ""
        task.claim_expires_at = None
        task.task_status = "pending"
        task.last_run_at = utc_now()
        task.last_error = payload.error_message
        if payload.error_message and not payload.items:
            task.retry_count += 1
            mark_account_failure(worker, payload.error_message)
        else:
            task.last_success_at = utc_now()
            task.retry_count = 0
            mark_account_success(worker)
        seen_post_ids: set[str] = set()
        for item in payload.items:
            if item.post_id in seen_post_ids:
                continue
            seen_post_ids.add(item.post_id)
            exists_stmt = select(SearchResult).where(SearchResult.search_task_id == task.id, SearchResult.post_id == item.post_id)
            exists = session.execute(exists_stmt).scalar_one_or_none()
            if exists:
                continue
            session.add(
                SearchResult(
                    search_task_id=task.id,
                    result_id=payload.result_id,
                    worker_account_id=worker.id,
                    post_id=item.post_id,
                    post_url=item.post_url,
                    title=item.title,
                    content_preview=item.content_preview,
                    author_id=item.user_id,
                    author_name=item.username,
                    like_count=item.like_count,
                    comment_count=item.comment_count,
                    collect_count=item.collect_count,
                    publish_time=item.publish_time,
                    raw_payload=item.model_dump(mode="json"),
                )
            )
            saved_count += 1
        write_audit_log(
            session,
            log_type="app_result",
            operator_type="app",
            operator_id=payload.device_id,
            target_type="search_task",
            target_id=task.id,
            message="回传关键词采集结果",
            payload={"saved_count": saved_count, "partial_success": payload.partial_success},
        )
        session.commit()
    return {"created": created, "result_id": result.result_id, "saved_count": saved_count}


@app.post("/api/app/search-tasks/{task_id}/result")
def app_search_task_result(task_id: str, payload: SearchTaskResultRequest, session: Session = Depends(get_db)) -> dict:
    return handle_search_task_result(task_id, payload, session)


@app.get("/api/search-results")
def list_search_results(task_id: str | None = Query(default=None), session: Session = Depends(get_db)) -> dict:
    stmt = select(SearchResult).order_by(SearchResult.created_at.desc())
    if task_id:
        stmt = stmt.where(SearchResult.search_task_id == task_id)
    return {"results": [to_search_result_public(item) for item in session.execute(stmt).scalars().all()]}


@app.patch("/api/search-results/{result_id}")
def update_search_result(result_id: str, payload: SearchResultUpdate, session: Session = Depends(get_db)) -> dict:
    item = session.get(SearchResult, result_id)
    if not item:
        raise HTTPException(status_code=404, detail="采集结果不存在")
    if payload.review_status is not None:
        item.review_status = payload.review_status
    if payload.review_note is not None:
        item.review_note = payload.review_note.strip()
    if payload.hidden is not None:
        item.hidden = payload.hidden
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="search_result",
        target_id=item.id,
        message="更新采集结果",
        payload={"review_status": item.review_status, "hidden": item.hidden},
    )
    session.commit()
    session.refresh(item)
    return {"result": to_search_result_public(item)}


@app.post("/api/analytics-tasks")
def create_analytics_task(payload: AnalyticsTaskCreate, session: Session = Depends(get_db)) -> dict:
    require_account(session, payload.account_id, "primary")
    task = AnalyticsTask(
        account_id=payload.account_id,
        interval_minutes=payload.interval_minutes,
        enabled=payload.enabled,
        group_name=payload.group_name.strip(),
        task_status="pending",
        max_retry=payload.max_retry,
    )
    session.add(task)
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="analytics_task",
        target_id=task.id,
        message="创建账号监控任务",
        payload={"group_name": task.group_name},
    )
    session.commit()
    session.refresh(task)
    return {"task": to_analytics_task(task)}


@app.get("/api/analytics-tasks")
def list_analytics_tasks(session: Session = Depends(get_db)) -> dict:
    stmt = select(AnalyticsTask).order_by(AnalyticsTask.created_at.desc())
    return {"tasks": [to_analytics_task(item) for item in session.execute(stmt).scalars().all()]}


@app.patch("/api/analytics-tasks/{task_id}")
def update_analytics_task(task_id: str, payload: AnalyticsTaskUpdate, session: Session = Depends(get_db)) -> dict:
    task = session.get(AnalyticsTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="账号监控任务不存在")
    if payload.enabled is not None:
        task.enabled = payload.enabled
    if payload.group_name is not None:
        task.group_name = payload.group_name.strip()
    if payload.interval_minutes is not None:
        task.interval_minutes = payload.interval_minutes
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="analytics_task",
        target_id=task.id,
        message="更新账号监控任务",
        payload={"enabled": task.enabled},
    )
    session.commit()
    session.refresh(task)
    return {"task": to_analytics_task(task)}


@app.post("/api/analytics-tasks/{task_id}/requeue")
def requeue_analytics_task(task_id: str, session: Session = Depends(get_db)) -> dict:
    task = session.get(AnalyticsTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="账号监控任务不存在")
    reset_task_to_pending(task, reset_retry=True)
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id="web",
        target_type="analytics_task",
        target_id=task.id,
        message="重新入队账号监控任务",
        payload={},
    )
    session.commit()
    session.refresh(task)
    return {"task": to_analytics_task(task)}


@app.get("/api/app/analytics-tasks/next")
def app_next_analytics_task(
    request: Request,
    device_id: str,
    app_instance_id: str = Query(default=""),
    app_version: str = Query(default=""),
    device_name: str = Query(default=""),
    session: Session = Depends(get_db),
) -> dict:
    device = touch_device_from_query(
        session,
        request,
        device_id=device_id,
        app_instance_id=app_instance_id,
        app_version=app_version,
        device_name=device_name,
    )
    if device and device.status == "disabled":
        session.commit()
        raise HTTPException(status_code=403, detail="设备已禁用")
    claimed = claim_analytics_task(session, device_id)
    session.commit()
    if not claimed:
        return {"task": None}
    task, worker = claimed
    body = to_analytics_task(task)
    body["worker_cookie_id"] = worker.id
    return {"task": body}


def handle_analytics_task_result(task_id: str, payload: AnalyticsTaskResultRequest, session: Session) -> dict:
    task = session.get(AnalyticsTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="账号监控任务不存在")
    result_status = "failed" if payload.error_message and not payload.snapshot.posts else "success"
    result, created = save_task_result(
        session,
        task_type="analytics",
        task_id=task_id,
        result_id=payload.result_id,
        device_id=payload.device_id,
        app_instance_id=payload.app_instance_id,
        status=result_status,
        duration_seconds=payload.duration_seconds,
        error_message=payload.error_message,
        payload=payload.model_dump(mode="json"),
    )
    snapshot_id = ""
    if created:
        worker = require_account(session, payload.worker_cookie_id, "worker")
        task.claimed_by_device_id = ""
        task.claim_expires_at = None
        task.task_status = "pending"
        task.last_run_at = utc_now()
        task.last_error = payload.error_message
        if payload.error_message and not payload.snapshot.posts:
            task.retry_count += 1
            mark_account_failure(worker, payload.error_message)
        else:
            task.last_success_at = utc_now()
            task.retry_count = 0
            mark_account_success(worker)

        snapshot = AnalyticsSnapshot(
            analytics_task_id=task.id,
            result_id=payload.result_id,
            account_id=payload.snapshot.account_id,
            worker_account_id=worker.id,
            nickname=payload.snapshot.nickname,
            follower_count=payload.snapshot.follower_count,
            liked_total=payload.snapshot.liked_count,
            post_total=payload.snapshot.post_count,
            collected_total=payload.snapshot.collected_total,
            raw_payload=payload.snapshot.model_dump(mode="json"),
        )
        session.add(snapshot)
        session.flush()
        snapshot_id = snapshot.id
        for post in payload.snapshot.posts:
            session.add(
                AnalyticsSnapshotPost(
                    snapshot_id=snapshot.id,
                    post_id=post.post_id,
                    title=post.title,
                    post_url=post.post_url,
                    like_count=post.like_count,
                    comment_count=post.comment_count,
                    collect_count=post.collect_count,
                    publish_time=post.publish_time,
                    raw_payload=post.model_dump(mode="json"),
                )
            )
        write_audit_log(
            session,
            log_type="app_result",
            operator_type="app",
            operator_id=payload.device_id,
            target_type="analytics_task",
            target_id=task.id,
            message="回传账号监控结果",
            payload={"snapshot_id": snapshot_id},
        )
        session.commit()
    return {"created": created, "result_id": result.result_id, "snapshot_id": snapshot_id}


@app.post("/api/app/analytics-tasks/{task_id}/result")
def app_analytics_task_result(task_id: str, payload: AnalyticsTaskResultRequest, session: Session = Depends(get_db)) -> dict:
    return handle_analytics_task_result(task_id, payload, session)


@app.get("/api/app/tasks/next")
def app_next_task(
    request: Request,
    device_id: str,
    app_instance_id: str,
    app_version: str = Query(default=""),
    device_name: str = Query(default=""),
    session: Session = Depends(get_db),
) -> dict:
    device = ensure_device(
        session,
        AppHeartbeatRequest(
            device_id=device_id,
            app_instance_id=app_instance_id,
            app_version=app_version,
            device_name=device_name,
        ),
        request,
    )
    if device.status == "disabled":
        session.commit()
        raise HTTPException(status_code=403, detail="设备已禁用")

    task = claim_publish_task(session, device_id)
    if task:
        session.commit()
        return {"task_type": "publish", "task": to_publish_task(task)}

    claimed_search = claim_search_task(session, device_id)
    if claimed_search:
        task, worker = claimed_search
        body = to_search_task(task)
        body["worker_cookie_id"] = worker.id
        session.commit()
        return {"task_type": "search", "task": body}

    claimed_analytics = claim_analytics_task(session, device_id)
    if claimed_analytics:
        task, worker = claimed_analytics
        body = to_analytics_task(task)
        body["worker_cookie_id"] = worker.id
        session.commit()
        return {"task_type": "analytics", "task": body}

    session.commit()
    return {"task_type": None, "task": None}


@app.post("/api/app/tasks/{task_type}/{task_id}/result")
def app_task_result(task_type: str, task_id: str, payload: dict, session: Session = Depends(get_db)) -> dict:
    try:
        if task_type == "publish":
            return handle_publish_task_result(task_id, PublishTaskResultRequest.model_validate(payload), session)
        if task_type == "search":
            return handle_search_task_result(task_id, SearchTaskResultRequest.model_validate(payload), session)
        if task_type == "analytics":
            return handle_analytics_task_result(task_id, AnalyticsTaskResultRequest.model_validate(payload), session)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    raise HTTPException(status_code=404, detail="任务类型不存在")


@app.get("/api/analytics-snapshots")
def list_analytics_snapshots(account_id: str | None = Query(default=None), session: Session = Depends(get_db)) -> dict:
    stmt = select(AnalyticsSnapshot).options(selectinload(AnalyticsSnapshot.posts)).order_by(AnalyticsSnapshot.created_at.desc())
    if account_id:
        stmt = stmt.where(AnalyticsSnapshot.account_id == account_id)
    return {"snapshots": [to_snapshot_public(item) for item in session.execute(stmt).scalars().all()]}


@app.get("/api/logs")
def list_logs(session: Session = Depends(get_db)) -> dict:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)
    items = session.execute(stmt).scalars().all()
    return {
        "logs": [
            {
                "id": item.id,
                "log_type": item.log_type,
                "operator_type": item.operator_type,
                "operator_id": item.operator_id,
                "target_type": item.target_type,
                "target_id": item.target_id,
                "message": item.message,
                "payload": item.payload,
                "created_at": item.created_at,
            }
            for item in items
        ]
    }


@app.get("/api/ops/summary")
def ops_summary(session: Session = Depends(get_db)) -> dict:
    logs_stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(20)
    latest_logs = session.execute(logs_stmt).scalars().all()
    summary = {
        "primary_account_total": session.execute(select(func.count()).select_from(Account).where(Account.account_type == "primary")).scalar_one(),
        "worker_cookie_total": session.execute(select(func.count()).select_from(Account).where(Account.account_type == "worker")).scalar_one(),
        "worker_cookie_active": session.execute(select(func.count()).select_from(Account).where(Account.account_type == "worker", Account.status == "active")).scalar_one(),
        "publish_pending": session.execute(select(func.count()).select_from(PublishTask).where(PublishTask.task_status == "pending")).scalar_one(),
        "publish_success": session.execute(select(func.count()).select_from(PublishTask).where(PublishTask.task_status == "success")).scalar_one(),
        "search_task_total": session.execute(select(func.count()).select_from(SearchTask)).scalar_one(),
        "search_result_total": session.execute(select(func.count()).select_from(SearchResult)).scalar_one(),
        "analytics_task_total": session.execute(select(func.count()).select_from(AnalyticsTask)).scalar_one(),
        "analytics_snapshot_total": session.execute(select(func.count()).select_from(AnalyticsSnapshot)).scalar_one(),
        "online_device_total": session.execute(select(func.count()).select_from(Device).where(Device.status == "online")).scalar_one(),
        "latest_logs": [
            {
                "id": item.id,
                "log_type": item.log_type,
                "message": item.message,
                "created_at": item.created_at,
            }
            for item in latest_logs
        ],
    }
    return {"summary": summary}


if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/")
    def serve_frontend_index():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    def serve_frontend_app(full_path: str):
        requested_path = FRONTEND_DIST / full_path
        if requested_path.is_file():
            return FileResponse(requested_path)
        return FileResponse(FRONTEND_DIST / "index.html")
