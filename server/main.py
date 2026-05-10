from __future__ import annotations

import os
import base64
import requests
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, Field, ValidationError
import qrcode
import qrcode.image.svg
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
from apis.xhs_pc_apis import XHS_Apis
from apis.xhs_pc_login_apis import XHSLoginApi
from apis.xhs_creator_apis import XHS_Creator_Apis


COOKIE_CHECK_TTL_SECONDS = 600
FAILURE_COOLDOWN_THRESHOLD = 3
FAILURE_COOLDOWN_SECONDS = 300
CLAIM_TIMEOUT_MINUTES = 15
LOGIN_SESSION_TTL_SECONDS = 600

ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
LOG_DIR = ROOT_DIR / "logs"
LOGIN_SESSION_STORE: dict[str, dict] = {}
LOGGER_CONFIGURED = False


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


def configure_app_logger() -> None:
    global LOGGER_CONFIGURED
    if LOGGER_CONFIGURED:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.add(
        LOG_DIR / "backend.log",
        level="INFO",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        enqueue=False,
    )
    LOGGER_CONFIGURED = True


configure_app_logger()


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


class AppSmsCodeRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=32)
    zone: str = Field(default="86", max_length=8)


class AppSmsLoginRequest(BaseModel):
    login_session_id: str = Field(min_length=1, max_length=64)
    phone: str = Field(min_length=1, max_length=32)
    code: str = Field(min_length=1, max_length=16)
    zone: str = Field(default="86", max_length=8)
    account_id: str = Field(default="")
    device_id: str = Field(default="", max_length=100)


class WorkerCookieCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    cookies: str = Field(min_length=20)
    remark: str = Field(default="", max_length=500)
    usage_tags: list[str] = Field(default_factory=list)
    group_name: str = Field(default="", max_length=100)


class WorkerLoginDraft(BaseModel):
    name: str = Field(default="", max_length=100)
    remark: str = Field(default="", max_length=500)
    usage_tags: list[str] = Field(default_factory=list)
    group_name: str = Field(default="", max_length=100)


class WorkerCookieUpdate(BaseModel):
    status: str | None = Field(default=None, max_length=20)
    remark: str | None = Field(default=None, max_length=500)
    usage_tags: list[str] | None = None
    group_name: str | None = Field(default=None, max_length=100)


class WorkerSmsCodeRequest(WorkerLoginDraft):
    phone: str = Field(min_length=1, max_length=32)
    zone: str = Field(default="86", max_length=8)


class WorkerSmsLoginRequest(WorkerLoginDraft):
    login_session_id: str = Field(min_length=1, max_length=64)
    phone: str = Field(min_length=1, max_length=32)
    code: str = Field(min_length=1, max_length=16)
    zone: str = Field(default="86", max_length=8)


class WorkerQrCodeRequest(WorkerLoginDraft):
    pass


class WorkerQrCodeCheckRequest(WorkerLoginDraft):
    login_session_id: str = Field(min_length=1, max_length=64)


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


class AppSearchTaskCreate(SearchTaskCreate):
    device_id: str = Field(default="", max_length=100)
    app_instance_id: str = Field(default="", max_length=100)


class AppDirectSearchRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=36)
    keyword: str = Field(min_length=1, max_length=200)
    require_num: int = Field(default=10, ge=1, le=20)
    sort_type: str = Field(default="general", max_length=30)
    note_type: str = Field(default="all", max_length=30)
    time_range: str = Field(default="all", max_length=30)


class AppSearchPostDetailRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=36)
    post_url: str = Field(min_length=1, max_length=1000)
    worker_cookie_id: str = Field(default="", max_length=36)


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


class AppPublishExecuteRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    app_instance_id: str = Field(min_length=1, max_length=100)


class SearchItemPayload(BaseModel):
    post_id: str = Field(min_length=1, max_length=100)
    post_url: str = Field(default="", max_length=1000)
    title: str = Field(default="", max_length=300)
    username: str = Field(default="", max_length=100)
    user_id: str = Field(default="", max_length=100)
    author_avatar: str = Field(default="", max_length=2000)
    content_preview: str = Field(default="", max_length=5000)
    content: str = Field(default="", max_length=20000)
    note_type: str = Field(default="", max_length=30)
    topics: list[str] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    video_url: str = Field(default="", max_length=2000)
    video_cover_url: str = Field(default="", max_length=2000)
    like_count: int = Field(default=0, ge=0)
    comment_count: int = Field(default=0, ge=0)
    collect_count: int = Field(default=0, ge=0)
    location: str = Field(default="", max_length=200)
    publish_time: datetime | None = None


class SearchTaskResultRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    app_instance_id: str = Field(min_length=1, max_length=100)
    result_id: str = Field(min_length=1, max_length=100)
    worker_cookie_id: str = Field(default="", max_length=36)
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
        "user_uid": account.user_uid,
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
    raw_payload = item.raw_payload or {}
    content = first_non_blank_text(raw_payload.get("content"), raw_payload.get("content_preview"), item.content_preview)
    title = first_non_blank_text(item.title, raw_payload.get("title")) or build_title_fallback(content)
    topics = raw_payload.get("topics")
    if not isinstance(topics, list):
        topics = []
    image_urls = raw_payload.get("image_urls")
    if not isinstance(image_urls, list):
        image_urls = []
    return {
        "id": item.id,
        "search_task_id": item.search_task_id,
        "result_id": item.result_id,
        "worker_account_id": item.worker_account_id,
        "post_id": item.post_id,
        "post_url": item.post_url,
        "title": title,
        "content_preview": item.content_preview,
        "content": content,
        "note_type": first_non_blank_text(raw_payload.get("note_type")),
        "topics": topics,
        "image_urls": image_urls,
        "video_url": first_non_blank_text(raw_payload.get("video_url")),
        "video_cover_url": first_non_blank_text(raw_payload.get("video_cover_url")),
        "author_id": item.author_id,
        "author_name": item.author_name,
        "author_avatar": first_non_blank_text(raw_payload.get("author_avatar")),
        "cover_url": first_non_blank_text(raw_payload.get("cover_url"), image_urls[0] if image_urls else ""),
        "location": first_non_blank_text(raw_payload.get("location")),
        "like_count": item.like_count,
        "comment_count": item.comment_count,
        "collect_count": item.collect_count,
        "publish_time": item.publish_time,
        "review_status": item.review_status,
        "review_note": item.review_note,
        "hidden": item.hidden,
        "created_at": item.created_at,
    }


def to_account_summary(account: Account) -> dict:
    return {
        "id": account.id,
        "name": account.name,
        "nickname": account.nickname,
        "user_uid": account.user_uid,
        "status": account.status,
        "cookie_preview": account.cookie_preview,
        "remark": account.remark,
        "last_check_at": account.last_check_at,
        "last_failure_at": account.last_failure_at,
        "failure_count": account.failure_count,
        "cooldown_until": account.cooldown_until,
        "bound_device_id": account.bound_device_id,
        "avatar": "",
        "following_count": 0,
        "follower_count": 0,
        "liked_count": 0,
        "published_notes": [],
        "profile_source": "base",
    }


def to_search_task_detail(task: SearchTask, results: list[SearchResult]) -> dict:
    return {
        "task": to_search_task(task),
        "post_count": len(results),
        "results": [to_search_result_public(item) for item in results],
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


def extract_profile_data(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    for key in ("data", "user", "basic_info"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def extract_profile_avatar(payload: dict) -> str:
    data = extract_profile_data(payload)
    avatar = (
        data.get("avatar")
        or data.get("image")
        or data.get("images")
        or data.get("avatar_url")
        or data.get("imageb")
        or data.get("image_s")
        or {}
    )
    if isinstance(avatar, str):
        return avatar.strip()
    if isinstance(avatar, dict):
        return first_non_blank_text(
            avatar.get("url"),
            avatar.get("default"),
            avatar.get("large"),
            avatar.get("medium"),
            avatar.get("small"),
        )
    if isinstance(avatar, list):
        for item in avatar:
            url = first_non_blank_text(item)
            if url:
                return url
    return ""


def extract_profile_text(payload: dict, *keys: str) -> str:
    data = extract_profile_data(payload)
    for key in keys:
        text = first_non_blank_text(data.get(key), payload.get(key))
        if text:
            return text
    return ""


def extract_profile_count(payload: dict, *keys: str) -> int:
    data = extract_profile_data(payload)
    for key in keys:
        if key in data:
            value = safe_int(data.get(key))
            if value:
                return value
        if key in payload:
            value = safe_int(payload.get(key))
            if value:
                return value
    return 0


def extract_profile_interaction_count(payload: dict, interaction_type: str) -> int:
    data = extract_profile_data(payload)
    for source in (payload.get("interactions"), data.get("interactions")):
        if not isinstance(source, list):
            continue
        for item in source:
            if not isinstance(item, dict):
                continue
            if first_non_blank_text(item.get("type")) != interaction_type:
                continue
            return safe_int(item.get("count") or item.get("i18n_count"))
    return 0


def build_profile_user_url(user_uid: str) -> str:
    return f"https://www.xiaohongshu.com/user/profile/{user_uid.strip()}"


def to_profile_note_summary(raw_item: dict) -> dict:
    if not raw_item.get("note_card") and raw_item.get("note_id"):
        return to_public_user_note_summary(raw_item)
    parsed = to_search_preview_item(raw_item)
    return {
        "post_id": parsed.get("post_id", ""),
        "post_url": parsed.get("post_url", ""),
        "title": parsed.get("title", ""),
        "author_name": parsed.get("author_name", ""),
        "author_avatar": parsed.get("author_avatar", ""),
        "content_preview": parsed.get("content_preview", ""),
        "content": parsed.get("content", ""),
        "note_type": parsed.get("note_type", ""),
        "topics": parsed.get("topics", []),
        "cover_url": parsed.get("cover_url", ""),
        "image_urls": parsed.get("image_urls", []),
        "video_url": parsed.get("video_url", ""),
        "video_cover_url": parsed.get("video_cover_url", ""),
        "location": parsed.get("location", ""),
        "like_count": parsed.get("like_count", 0),
        "comment_count": parsed.get("comment_count", 0),
        "collect_count": parsed.get("collect_count", 0),
        "publish_time": parsed.get("publish_time"),
    }


def build_publish_post_url(note_id: str) -> str:
    note_id = first_non_blank_text(note_id)
    return f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""


def to_creator_note_summary(raw_item: dict) -> dict:
    note_id = first_non_blank_text(
        raw_item.get("note_id"),
        raw_item.get("id"),
        raw_item.get("noteId"),
    )
    title = first_non_blank_text(
        raw_item.get("title"),
        raw_item.get("display_title"),
        raw_item.get("name"),
    )
    content = first_non_blank_text(
        raw_item.get("desc"),
        raw_item.get("content"),
        raw_item.get("description"),
    )
    cover = first_non_blank_text(
        raw_item.get("cover_url"),
        raw_item.get("image_url"),
        raw_item.get("cover"),
    )
    image_urls: list[str] = []
    for source in (raw_item.get("image_urls"), raw_item.get("images"), raw_item.get("image_list")):
        if isinstance(source, list):
            for item in source:
                if isinstance(item, dict):
                    url = first_non_blank_text(item.get("url"), item.get("default"))
                else:
                    url = first_non_blank_text(item)
                if url:
                    image_urls.append(url)
    if not cover and image_urls:
        cover = image_urls[0]
    video_url = first_non_blank_text(
        raw_item.get("video_url"),
        raw_item.get("videoAddr"),
        raw_item.get("video_addr"),
    )
    author_name = first_non_blank_text(
        raw_item.get("nickname"),
        raw_item.get("author_name"),
        raw_item.get("user_name"),
    )
    author_avatar = first_non_blank_text(
        raw_item.get("author_avatar"),
        raw_item.get("avatar"),
        raw_item.get("images"),
        raw_item.get("imageb"),
    )
    topics = []
    for source in (raw_item.get("topics"), raw_item.get("tag_list"), raw_item.get("tags")):
        if isinstance(source, list):
            for item in source:
                name = first_non_blank_text(item.get("name") if isinstance(item, dict) else item)
                if name and name not in topics:
                    topics.append(name)
    return {
        "post_id": note_id,
        "post_url": first_non_blank_text(raw_item.get("post_url"), raw_item.get("url"), build_publish_post_url(note_id)),
        "title": title or build_title_fallback(content),
        "author_name": author_name,
        "author_avatar": author_avatar,
        "content_preview": content[:120],
        "content": content,
        "note_type": first_non_blank_text(raw_item.get("note_type"), raw_item.get("type")),
        "topics": topics,
        "cover_url": cover,
        "image_urls": image_urls,
        "video_url": video_url,
        "video_cover_url": cover,
        "location": first_non_blank_text(raw_item.get("location")),
        "like_count": safe_int(raw_item.get("liked_count") or raw_item.get("like_count")),
        "comment_count": safe_int(raw_item.get("comment_count")),
        "collect_count": safe_int(raw_item.get("collected_count") or raw_item.get("collect_count")),
        "publish_time": first_non_blank_text(raw_item.get("publish_time"), raw_item.get("time")),
    }


def hydrate_profile_note_defaults(notes: list[dict], *, author_name: str, author_avatar: str) -> list[dict]:
    hydrated: list[dict] = []
    for item in notes:
        cloned = dict(item)
        cloned["author_name"] = first_non_blank_text(cloned.get("author_name"), author_name)
        cloned["author_avatar"] = first_non_blank_text(cloned.get("author_avatar"), author_avatar)
        if not first_non_blank_text(cloned.get("post_url")):
            cloned["post_url"] = build_publish_post_url(first_non_blank_text(cloned.get("post_id")))
        if not first_non_blank_text(cloned.get("cover_url")):
            image_urls = cloned.get("image_urls") or []
            if isinstance(image_urls, list) and image_urls:
                cloned["cover_url"] = first_non_blank_text(image_urls[0])
        hydrated.append(cloned)
    return hydrated


def to_snapshot_post_summary(item: AnalyticsSnapshotPost, *, author_name: str = "", author_avatar: str = "") -> dict:
    return {
        "post_id": item.post_id,
        "post_url": item.post_url,
        "title": item.title,
        "author_name": author_name,
        "author_avatar": author_avatar,
        "content_preview": "",
        "content": "",
        "note_type": "",
        "topics": [],
        "cover_url": "",
        "image_urls": [],
        "video_url": "",
        "video_cover_url": "",
        "location": "",
        "like_count": item.like_count,
        "comment_count": item.comment_count,
        "collect_count": item.collect_count,
        "publish_time": item.publish_time,
    }


def get_latest_analytics_snapshot(session: Session, account_id: str) -> AnalyticsSnapshot | None:
    stmt = (
        select(AnalyticsSnapshot)
        .options(selectinload(AnalyticsSnapshot.posts))
        .where(AnalyticsSnapshot.account_id == account_id)
        .order_by(AnalyticsSnapshot.created_at.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def build_account_profile_summary(session: Session, account: Account) -> dict:
    summary = to_account_summary(account)
    latest_snapshot = get_latest_analytics_snapshot(session, account.id)
    if latest_snapshot:
        summary["nickname"] = summary["nickname"] or latest_snapshot.nickname
        summary["follower_count"] = latest_snapshot.follower_count
        summary["liked_count"] = latest_snapshot.liked_total
        summary["published_notes"] = [
            to_snapshot_post_summary(
                post,
                author_name=summary["nickname"],
                author_avatar=summary["avatar"],
            )
            for post in latest_snapshot.posts
        ]
        summary["profile_source"] = "snapshot"

    if account.cookies:
        try:
            creator_api = get_creator_api()
            success, creator_msg, creator_notes = creator_api.get_all_publish_note_info(account.cookies)
            if success and creator_notes:
                summary["published_notes"] = [to_creator_note_summary(item) for item in creator_notes]
                summary["profile_source"] = "creator_notes"
            elif not success:
                logger.warning("account-summary creator notes failed account_id={} message={}", account.id, creator_msg)
        except Exception as exc:
            logger.exception("account-summary creator fetch failed account_id={} error={}", account.id, exc)

    worker = choose_worker(session, usage_tag="worker_search")
    worker_cookie_id = worker.id if worker else ""
    content_api = get_pc_content_api()

    if worker and account.user_uid:
        ok, message = validate_cookie(worker)
        if ok:
            try:
                success, profile_msg, profile_res = content_api.get_user_info(account.user_uid, worker.cookies)
                if success:
                    profile_data = extract_profile_data(profile_res)
                    summary["avatar"] = extract_profile_avatar(profile_res)
                    summary["nickname"] = (
                        extract_profile_text(profile_res, "nickname", "nick_name", "name")
                        or summary["nickname"]
                    )
                    summary["following_count"] = extract_profile_count(
                        profile_data,
                        "follows",
                        "follow_count",
                        "following_count",
                    ) or extract_profile_interaction_count(profile_res, "follows")
                    summary["follower_count"] = extract_profile_count(
                        profile_data,
                        "fans",
                        "fans_count",
                        "follower_count",
                    ) or extract_profile_interaction_count(profile_res, "fans") or summary["follower_count"]
                    summary["liked_count"] = extract_profile_count(
                        profile_data,
                        "interaction",
                        "liked_count",
                        "liked_total",
                        "likes",
                    ) or extract_profile_interaction_count(profile_res, "interaction") or summary["liked_count"]
                    if summary["profile_source"] in {"base", "snapshot", "self_profile", "worker_notes"}:
                        summary["profile_source"] = "worker_public"
                else:
                    logger.warning("account-summary public profile failed account_id={} worker_id={} message={}", account.id, worker.id, profile_msg)

                success, notes_msg, notes_res = content_api.get_user_note_info(account.user_uid, "", worker.cookies)
                notes_payload = (((notes_res or {}).get("data") or {}).get("notes") or []) if success else []
                if notes_payload and not summary["published_notes"]:
                    parsed_notes = attach_worker_cookie_id([to_profile_note_summary(item) for item in notes_payload], worker)
                    summary["published_notes"] = parsed_notes
                    if summary["profile_source"] == "base":
                        summary["profile_source"] = "worker_notes"
                elif not success:
                    logger.warning("account-summary public notes failed account_id={} worker_id={} message={}", account.id, worker.id, notes_msg)
            except Exception as exc:
                logger.exception("account-summary worker fetch failed account_id={} worker_id={} error={}", account.id, worker.id, exc)
        else:
            mark_account_failure(worker, message)
            session.flush()

    if not summary["avatar"] and account.cookies:
        try:
            success, _, self_res = content_api.get_user_self_info2(account.cookies)
            if success:
                summary["avatar"] = extract_profile_avatar(self_res)
                summary["nickname"] = (
                    extract_profile_text(self_res, "nickname", "nick_name", "name", "red_id")
                    or summary["nickname"]
                )
                summary["following_count"] = extract_profile_count(
                    self_res,
                    "follow_count",
                    "following_count",
                    "follows",
                ) or summary["following_count"]
                summary["follower_count"] = extract_profile_count(
                    self_res,
                    "fans_count",
                    "follower_count",
                    "fans",
                ) or summary["follower_count"]
                summary["liked_count"] = extract_profile_count(
                    self_res,
                    "liked_count",
                    "liked_total",
                    "interaction",
                ) or summary["liked_count"]
                if summary["profile_source"] == "base":
                    summary["profile_source"] = "self_profile"
        except Exception as exc:
            logger.exception("account-summary self profile fallback failed account_id={} error={}", account.id, exc)

    if account.user_uid and account.cookies:
        try:
            success, msg, profile_res = content_api.get_user_info(account.user_uid, account.cookies)
            if success:
                summary["avatar"] = extract_profile_avatar(profile_res) or summary["avatar"]
                summary["nickname"] = extract_profile_text(profile_res, "nickname", "nick_name", "name") or summary["nickname"]
                summary["following_count"] = (
                    extract_profile_count(profile_res, "follows", "follow_count", "following_count")
                    or extract_profile_interaction_count(profile_res, "follows")
                    or summary["following_count"]
                )
                summary["follower_count"] = (
                    extract_profile_count(profile_res, "fans", "fans_count", "follower_count")
                    or extract_profile_interaction_count(profile_res, "fans")
                    or summary["follower_count"]
                )
                summary["liked_count"] = (
                    extract_profile_count(profile_res, "interaction", "liked_count", "liked_total", "likes")
                    or extract_profile_interaction_count(profile_res, "interaction")
                    or summary["liked_count"]
                )
                if summary["profile_source"] in {"base", "self_profile", "snapshot"}:
                    summary["profile_source"] = "primary_public"
            else:
                logger.warning("account-summary primary public profile failed account_id={} message={}", account.id, msg)
        except Exception as exc:
            logger.exception("account-summary primary public profile fetch failed account_id={} error={}", account.id, exc)

        if not summary["published_notes"]:
            try:
                success, msg, notes_res = content_api.get_user_note_info(account.user_uid, "", account.cookies)
                notes_payload = (((notes_res or {}).get("data") or {}).get("notes") or []) if success else []
                if notes_payload:
                    summary["published_notes"] = [to_profile_note_summary(item) for item in notes_payload]
                    if summary["profile_source"] in {"base", "self_profile", "snapshot", "primary_public"}:
                        summary["profile_source"] = "primary_public_notes"
                elif not success:
                    logger.warning("account-summary primary public notes failed account_id={} message={}", account.id, msg)
            except Exception as exc:
                logger.exception("account-summary primary public notes fetch failed account_id={} error={}", account.id, exc)

    summary["worker_cookie_id"] = worker_cookie_id
    if summary["published_notes"] and worker_cookie_id:
        summary["published_notes"] = attach_worker_cookie_id(summary["published_notes"], worker)
    summary["published_notes"] = hydrate_profile_note_defaults(
        summary["published_notes"],
        author_name=summary["nickname"],
        author_avatar=summary["avatar"],
    )
    logger.info(
        "account-summary account_id={} source={} worker_cookie_id={} notes={}",
        account.id,
        summary["profile_source"],
        worker_cookie_id,
        len(summary["published_notes"]),
    )
    return summary


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
    existing_tags = {item.usage_tag: item for item in list(account.usage_tags)}
    for usage_tag, item in existing_tags.items():
        if usage_tag not in normalized:
            account.usage_tags.remove(item)
    current = {item.usage_tag for item in account.usage_tags}
    for tag in normalized:
        if tag not in current:
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


def ensure_account_session_available(account: Account) -> None:
    refresh_account_status(account)
    if account.status == "invalid":
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    if account.status == "disabled":
        raise HTTPException(status_code=403, detail="账号已停用")


def get_pc_login_api() -> XHSLoginApi:
    return XHSLoginApi()


def get_pc_content_api() -> XHS_Apis:
    return XHS_Apis()


def get_creator_api() -> XHS_Creator_Apis:
    return XHS_Creator_Apis()


def download_media_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def extract_publish_result_fields(res_json: dict | None) -> tuple[str, str]:
    data = (res_json or {}).get("data") or {}
    post_id = (
        data.get("note_id")
        or data.get("noteId")
        or data.get("id")
        or (res_json or {}).get("note_id")
        or (res_json or {}).get("id")
        or ""
    )
    post_url = (
        data.get("note_url")
        or data.get("noteUrl")
        or data.get("url")
        or data.get("share_link")
        or (res_json or {}).get("url")
        or ""
    )
    if post_id and not post_url:
        post_url = f"https://www.xiaohongshu.com/explore/{post_id}"
    return str(post_id), str(post_url)


def build_publish_note_payload(task: PublishTask) -> dict:
    payload = {
        "title": task.title,
        "desc": task.content,
        "topics": task.topics_json or [],
        "location": task.location or None,
        "type": 0,
        "media_type": task.media_type,
    }
    media_urls = [item for item in task.media_urls_json if item]
    if task.media_type == "video":
        if not media_urls:
            raise ValueError("视频任务缺少媒体 URL")
        payload["video"] = download_media_bytes(media_urls[0])
    else:
        if not media_urls:
            raise ValueError("图片任务缺少媒体 URL")
        payload["images"] = [download_media_bytes(item) for item in media_urls]
    return payload


def map_sort_type(value: str) -> int:
    return {
        "general": 0,
        "time_descending": 1,
        "popularity_descending": 2,
        "comment_descending": 3,
        "collect_descending": 4,
    }.get((value or "").strip(), 0)


def map_note_type(value: str) -> int:
    return {
        "all": 0,
        "video": 1,
        "normal": 2,
    }.get((value or "").strip(), 0)


def map_time_range(value: str) -> int:
    return {
        "all": 0,
        "day": 1,
        "week": 2,
        "half_year": 3,
    }.get((value or "").strip(), 0)


def to_search_item_payload(item: dict) -> dict:
    raw_payload = item.raw_payload or {}
    return {
        "post_id": item.get("note_id", ""),
        "post_url": item.get("note_url", ""),
        "title": item.get("title", ""),
        "author_name": item.get("nickname", ""),
        "author_id": item.get("user_id", ""),
        "author_avatar": item.get("author_avatar", ""),
        "content_preview": item.get("desc", ""),
        "content": item.get("desc", ""),
        "note_type": item.get("note_type", ""),
        "topics": item.get("tags", []),
        "image_urls": item.get("image_list", []),
        "video_url": item.get("video_addr", ""),
        "video_cover_url": item.get("video_cover", ""),
        "location": item.get("location", ""),
        "like_count": item.get("liked_count", 0),
        "comment_count": item.get("comment_count", 0),
        "collect_count": item.get("collected_count", 0),
        "publish_time": item.get("upload_time", ""),
    }


def normalize_preview_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value).strip()
    if isinstance(value, list):
        parts = [normalize_preview_text(item) for item in value]
        return " ".join(item for item in parts if item).strip()
    if isinstance(value, dict):
        for key in ("text", "content", "title", "desc", "name", "value"):
            text = normalize_preview_text(value.get(key))
            if text:
                return text
        parts = [normalize_preview_text(item) for item in value.values()]
        return " ".join(item for item in parts if item).strip()
    return str(value).strip()


def first_non_blank_text(*values) -> str:
    for value in values:
        text = normalize_preview_text(value)
        if text:
            return text
    return ""


def safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def build_title_fallback(content: str) -> str:
    text = normalize_preview_text(content).replace("\n", " ").strip()
    if not text:
        return "无标题"
    return text[:30]


def extract_image_urls(note_card: dict) -> list[str]:
    image_list = []
    for image in note_card.get("image_list") or []:
        if not isinstance(image, dict):
            continue
        info_list = image.get("info_list") or []
        for info in reversed(info_list):
            url = first_non_blank_text(info.get("url") if isinstance(info, dict) else "")
            if url:
                image_list.append(url)
                break
    return image_list


def extract_cover_url(note_card: dict, image_urls: list[str]) -> str:
    cover = note_card.get("cover") or {}
    return first_non_blank_text(
        cover.get("url") if isinstance(cover, dict) else "",
        cover.get("url_pre") if isinstance(cover, dict) else "",
        cover.get("url_default") if isinstance(cover, dict) else "",
        cover.get("default") if isinstance(cover, dict) else "",
        (
            first_non_blank_text(*[
                item.get("url")
                for item in (cover.get("info_list") or [])
                if isinstance(item, dict)
            ])
            if isinstance(cover, dict)
            else ""
        ),
        image_urls[0] if image_urls else "",
    )


def extract_author_avatar(user: dict, raw_item: dict) -> str:
    avatar = user.get("avatar") or raw_item.get("avatar") or raw_item.get("author_avatar") or {}
    if isinstance(avatar, str):
        return avatar.strip()
    if isinstance(avatar, dict):
        return first_non_blank_text(
            avatar.get("url"),
            avatar.get("default"),
            avatar.get("large"),
            avatar.get("medium"),
            avatar.get("small"),
        )
    return ""


def extract_location(note_card: dict, raw_item: dict) -> str:
    return first_non_blank_text(
        note_card.get("ip_location"),
        raw_item.get("ip_location"),
        raw_item.get("location"),
    )


def extract_topics(note_card: dict, raw_item: dict) -> list[str]:
    topics: list[str] = []
    for source in (
        note_card.get("tag_list"),
        note_card.get("topic_list"),
        note_card.get("desc_extra"),
        note_card.get("at_desc"),
        raw_item.get("tag_list"),
        raw_item.get("topic_list"),
        raw_item.get("topics"),
        raw_item.get("body_topic_list"),
    ):
        if not source:
            continue
        if isinstance(source, list):
            for item in source:
                if isinstance(item, dict):
                    name = first_non_blank_text(
                        item.get("name"),
                        item.get("text"),
                        item.get("title"),
                        item.get("topic_name"),
                        item.get("tag_name"),
                        item.get("hashtag_name"),
                    )
                else:
                    name = first_non_blank_text(item)
                if name and name not in topics:
                    topics.append(name)
    return topics


def extract_video_urls(note_card: dict, image_urls: list[str]) -> tuple[str, str]:
    video_info = note_card.get("video") or {}
    streams = (((video_info.get("media") or {}).get("stream") or {}).get("h264") or [])
    video_url = ""
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        video_url = first_non_blank_text(stream.get("master_url"), stream.get("url"))
        if video_url:
            break
    if not video_url and "consumer" in video_info:
        origin_key = ((video_info.get("consumer") or {}).get("origin_video_key")) or ""
        if origin_key:
            video_url = f"https://sns-video-bd.xhscdn.com/{origin_key}"
    video_cover_url = image_urls[0] if image_urls else ""
    return video_url, video_cover_url


def extract_content(raw_item: dict, note_card: dict) -> str:
    basic_info = raw_item.get("basic_info") or {}
    return first_non_blank_text(
        note_card.get("desc"),
        note_card.get("display_desc"),
        note_card.get("content"),
        note_card.get("note_abstract"),
        basic_info.get("desc"),
        raw_item.get("desc"),
        raw_item.get("display_desc"),
        raw_item.get("content"),
        raw_item.get("note_abstract"),
    )


def build_search_post_url(raw_item: dict) -> str:
    note_id = first_non_blank_text(raw_item.get("id"), raw_item.get("note_id"))
    direct_url = first_non_blank_text(raw_item.get("url"))
    if direct_url:
        return direct_url
    if not note_id:
        return ""
    xsec_token = first_non_blank_text(raw_item.get("xsec_token"))
    xsec_source = first_non_blank_text(raw_item.get("xsec_source")) or "pc_search"
    if xsec_token:
        return f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source={xsec_source}"
    return f"https://www.xiaohongshu.com/explore/{note_id}"


def to_public_user_note_summary(raw_item: dict) -> dict:
    user = raw_item.get("user") or {}
    interact_info = raw_item.get("interact_info") or {}
    cover = raw_item.get("cover") or {}
    cover_url = first_non_blank_text(
        cover.get("url") if isinstance(cover, dict) else "",
        cover.get("url_pre") if isinstance(cover, dict) else "",
        cover.get("url_default") if isinstance(cover, dict) else "",
        first_non_blank_text(*[
            item.get("url")
            for item in (cover.get("info_list") or [])
            if isinstance(item, dict)
        ]) if isinstance(cover, dict) else "",
    )
    return {
        "post_id": first_non_blank_text(raw_item.get("note_id"), raw_item.get("id")),
        "post_url": build_search_post_url(raw_item),
        "title": first_non_blank_text(raw_item.get("display_title"), raw_item.get("title")),
        "author_name": first_non_blank_text(user.get("nickname"), user.get("nick_name"), raw_item.get("nickname")),
        "author_avatar": extract_author_avatar(user, raw_item),
        "content_preview": "",
        "content": "",
        "note_type": first_non_blank_text(raw_item.get("type")),
        "topics": [],
        "cover_url": cover_url,
        "image_urls": [cover_url] if cover_url else [],
        "video_url": "",
        "video_cover_url": cover_url,
        "location": "",
        "like_count": safe_int(interact_info.get("liked_count")),
        "comment_count": safe_int(interact_info.get("comment_count")),
        "collect_count": safe_int(interact_info.get("collected_count")),
        "publish_time": "",
    }


def summarize_raw_note_fields(raw_item: dict) -> dict:
    note_card = raw_item.get("note_card") or {}
    basic_info = raw_item.get("basic_info") or {}
    return {
        "post_id": first_non_blank_text(raw_item.get("id")),
        "raw_keys": sorted(raw_item.keys()),
        "note_card_keys": sorted(note_card.keys()) if isinstance(note_card, dict) else [],
        "basic_info_keys": sorted(basic_info.keys()) if isinstance(basic_info, dict) else [],
        "title_fields": {
            "note_card.title": first_non_blank_text(note_card.get("title")),
            "note_card.display_title": first_non_blank_text(note_card.get("display_title")),
            "raw.title": first_non_blank_text(raw_item.get("title")),
        },
        "content_fields": {
            "note_card.desc": first_non_blank_text(note_card.get("desc")),
            "note_card.display_desc": first_non_blank_text(note_card.get("display_desc")),
            "note_card.content": first_non_blank_text(note_card.get("content")),
            "basic_info.desc": first_non_blank_text(basic_info.get("desc")),
            "raw.desc": first_non_blank_text(raw_item.get("desc")),
        },
        "topic_sources": {
            "note_card.tag_list_count": len(note_card.get("tag_list") or []),
            "note_card.topic_list_count": len(note_card.get("topic_list") or []),
            "note_card.desc_extra_count": len(note_card.get("desc_extra") or []),
            "raw.body_topic_list_count": len(raw_item.get("body_topic_list") or []),
        },
    }


def build_detail_url_candidates(post_url: str) -> list[str]:
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(post_url.strip())
    note_id = parsed.path.split("/")[-1] if parsed.path else ""
    xsec_token = parse_qs(parsed.query).get("xsec_token", [""])[-1]
    if not note_id:
        return [post_url.strip()] if post_url.strip() else []

    candidates: list[str] = []
    if xsec_token:
        for xsec_source in ("pc_search", "pc_user", "pc_feed"):
            candidates.append(f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source={xsec_source}")
    candidates.append(f"https://www.xiaohongshu.com/explore/{note_id}")

    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def to_search_preview_item(raw_item: dict) -> dict:
    note_card = raw_item.get("note_card") or {}
    user = note_card.get("user") or {}
    interact_info = note_card.get("interact_info") or {}
    title = first_non_blank_text(
        note_card.get("title"),
        note_card.get("display_title"),
        note_card.get("note_title"),
        raw_item.get("title"),
        raw_item.get("display_title"),
        raw_item.get("note_title"),
    )
    content_preview = extract_content(raw_item, note_card)
    title = title or build_title_fallback(content_preview)
    author_name = first_non_blank_text(
        user.get("nickname"),
        user.get("nick_name"),
        raw_item.get("nickname"),
        raw_item.get("author_name"),
    )
    author_id = first_non_blank_text(
        user.get("user_id"),
        user.get("userid"),
        raw_item.get("user_id"),
        raw_item.get("author_id"),
    )
    image_urls = extract_image_urls(note_card)
    cover_url = extract_cover_url(note_card, image_urls)
    video_url, video_cover_url = extract_video_urls(note_card, image_urls)
    topics = extract_topics(note_card, raw_item)
    note_type = first_non_blank_text(note_card.get("type"), raw_item.get("type"))
    return {
        "post_id": raw_item.get("id", ""),
        "post_url": build_search_post_url(raw_item),
        "title": title,
        "author_name": author_name,
        "author_id": author_id,
        "author_avatar": extract_author_avatar(user, raw_item),
        "content_preview": content_preview,
        "content": content_preview,
        "note_type": note_type,
        "topics": topics,
        "cover_url": cover_url,
        "image_urls": image_urls,
        "video_url": video_url,
        "video_cover_url": video_cover_url,
        "location": extract_location(note_card, raw_item),
        "like_count": safe_int(interact_info.get("liked_count")),
        "comment_count": safe_int(interact_info.get("comment_count")),
        "collect_count": safe_int(interact_info.get("collected_count")),
        "publish_time": note_card.get("time", ""),
    }


def attach_worker_cookie_id(items: list[dict], worker: Account | None) -> list[dict]:
    if not worker:
        return items
    enriched: list[dict] = []
    for item in items:
        cloned = dict(item)
        cloned["worker_cookie_id"] = worker.id
        enriched.append(cloned)
    return enriched


def to_search_post_detail(raw_item: dict) -> dict:
    note_card = raw_item.get("note_card") or {}
    user = note_card.get("user") or {}
    interact_info = note_card.get("interact_info") or {}
    content = extract_content(raw_item, note_card)
    raw_title = first_non_blank_text(
        note_card.get("title"),
        note_card.get("display_title"),
        note_card.get("note_title"),
        raw_item.get("title"),
        raw_item.get("display_title"),
        raw_item.get("note_title"),
    )
    title = build_title_fallback(content) if raw_title == "无标题" else (raw_title or build_title_fallback(content))
    image_urls = extract_image_urls(note_card)
    cover_url = extract_cover_url(note_card, image_urls)
    video_url, video_cover_url = extract_video_urls(note_card, image_urls)
    topics = extract_topics(note_card, raw_item)
    return {
        "post_id": first_non_blank_text(raw_item.get("id")),
        "post_url": build_search_post_url(raw_item),
        "title": title,
        "author_name": first_non_blank_text(user.get("nickname"), user.get("nick_name"), raw_item.get("author_name")),
        "author_id": first_non_blank_text(user.get("user_id"), user.get("userid"), raw_item.get("author_id")),
        "author_avatar": extract_author_avatar(user, raw_item),
        "content_preview": content[:120],
        "content": content,
        "note_type": first_non_blank_text(note_card.get("type"), raw_item.get("type")),
        "topics": topics,
        "cover_url": cover_url,
        "image_urls": image_urls,
        "video_url": video_url,
        "video_cover_url": video_cover_url,
        "location": extract_location(note_card, raw_item),
        "like_count": safe_int(interact_info.get("liked_count")),
        "comment_count": safe_int(interact_info.get("comment_count")),
        "collect_count": safe_int(interact_info.get("collected_count")),
        "publish_time": first_non_blank_text(note_card.get("time"), raw_item.get("publish_time")),
    }


def cleanup_login_sessions() -> None:
    expire_before = utc_now() - timedelta(seconds=LOGIN_SESSION_TTL_SECONDS)
    expired_keys = [key for key, value in LOGIN_SESSION_STORE.items() if value["created_at"] <= expire_before]
    for key in expired_keys:
        LOGIN_SESSION_STORE.pop(key, None)


def get_login_session(login_session_id: str) -> dict:
    cleanup_login_sessions()
    item = LOGIN_SESSION_STORE.get(login_session_id)
    if not item:
        raise HTTPException(status_code=404, detail="登录会话不存在或已过期")
    return item


def qr_code_data_url(content: str) -> str:
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(content)
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def upsert_primary_account_from_login(
    session: Session,
    *,
    account_id: str,
    phone: str,
    cookies_str: str,
    nickname: str,
    user_uid: str,
    device_id: str,
) -> Account:
    if account_id:
        account = require_account(session, account_id, "primary")
        account.cookies = cookies_str
        account.cookie_preview = mask_cookie(cookies_str)
        account.nickname = nickname.strip()
        account.user_uid = user_uid.strip()
        account.status = "active"
        account.last_check_at = utc_now()
        if device_id.strip():
            account.bound_device_id = device_id.strip()
        if not account.name.strip():
            account.name = nickname.strip() or phone
        write_audit_log(
            session,
            log_type="manual_action",
            operator_type="app",
            operator_id="android_app",
            target_type="account",
            target_id=account.id,
            message="App 手机号验证码登录更新主账号",
            payload={"phone": phone},
        )
        return account

    normalized_nickname = nickname.strip()
    normalized_user_uid = user_uid.strip()
    existing_candidates: list[Account] = []
    if normalized_user_uid:
        stmt = (
            select(Account)
            .where(Account.account_type == "primary", Account.user_uid == normalized_user_uid)
            .order_by(Account.created_at.asc())
        )
        existing_candidates = session.execute(stmt).scalars().all()
    if not existing_candidates and normalized_nickname:
        stmt = (
            select(Account)
            .where(
                Account.account_type == "primary",
                Account.user_uid == "",
                or_(Account.nickname == normalized_nickname, Account.name == normalized_nickname),
            )
            .order_by(Account.created_at.asc())
        )
        existing_candidates = session.execute(stmt).scalars().all()
    if existing_candidates:
        task_account_ids = {
            account_id
            for account_id, in session.execute(
                select(PublishTask.account_id).distinct().where(PublishTask.account_id.in_([item.id for item in existing_candidates]))
            ).all()
        }
        account = next((item for item in existing_candidates if item.id in task_account_ids), existing_candidates[0])
        account.cookies = cookies_str
        account.cookie_preview = mask_cookie(cookies_str)
        account.nickname = normalized_nickname
        account.user_uid = normalized_user_uid
        account.status = "active"
        account.last_check_at = utc_now()
        if device_id.strip():
            account.bound_device_id = device_id.strip()
        if not account.name.strip():
            account.name = normalized_nickname or phone
        write_audit_log(
            session,
            log_type="manual_action",
            operator_type="app",
            operator_id="android_app",
            target_type="account",
            target_id=account.id,
            message="App 手机号验证码登录复用主账号",
            payload={"phone": phone},
        )
        return account

    account = Account(
        account_type="primary",
        name=nickname.strip() or phone,
        nickname=nickname.strip(),
        user_uid=user_uid.strip(),
        cookies=cookies_str,
        cookie_preview=mask_cookie(cookies_str),
        status="active",
        remark="App 手机号验证码登录创建",
        last_check_at=utc_now(),
        bound_device_id=device_id.strip(),
    )
    session.add(account)
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="app",
        operator_id="android_app",
        target_type="account",
        target_id=account.id,
        message="App 手机号验证码登录创建主账号",
        payload={"phone": phone},
    )
    return account


def create_worker_account_from_login(
    session: Session,
    *,
    cookies_str: str,
    nickname: str,
    name: str,
    group_name: str,
    remark: str,
    usage_tags: list[str],
    operator_id: str,
    source_message: str,
) -> Account:
    display_name = name.strip() or nickname.strip() or "小号账号"
    worker = Account(
        account_type="worker",
        name=display_name,
        nickname=nickname.strip(),
        cookies=cookies_str,
        cookie_preview=mask_cookie(cookies_str),
        status="active",
        group_name=group_name.strip(),
        remark=remark.strip(),
        last_check_at=utc_now(),
    )
    session.add(worker)
    session.flush()
    set_usage_tags(session, worker, usage_tags)
    write_audit_log(
        session,
        log_type="manual_action",
        operator_type="web",
        operator_id=operator_id,
        target_type="account",
        target_id=worker.id,
        message=source_message,
        payload={"group_name": worker.group_name, "usage_tags": usage_tags},
    )
    return worker


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


def device_has_active_task_for_model(session: Session, device_id: str, model) -> bool:
    active_statuses = ("claimed", "running")
    stmt = select(func.count()).select_from(model).where(
        model.claimed_by_device_id == device_id,
        model.task_status.in_(active_statuses),
    )
    return session.execute(stmt).scalar_one() > 0


def account_has_active_publish(session: Session, account_id: str) -> bool:
    stmt = select(func.count()).select_from(PublishTask).where(
        PublishTask.account_id == account_id,
        PublishTask.task_status.in_(("claimed", "running")),
    )
    return session.execute(stmt).scalar_one() > 0


def worker_is_busy(session: Session, worker_id: str) -> bool:
    now = utc_now()
    for model in (SearchTask, AnalyticsTask):
        stmt = select(func.count()).select_from(model).where(
            model.assigned_worker_account_id == worker_id,
            or_(
                model.task_status == "running",
                (
                    (model.task_status == "claimed")
                    & model.claim_expires_at.is_not(None)
                    & (model.claim_expires_at > now)
                ),
            ),
        )
        if session.execute(stmt).scalar_one() > 0:
            return True
    return False


def choose_worker(session: Session, *, usage_tag: str, group_name: str = "") -> Account | None:
    reclaim_expired_claims(session)
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
    now = utc_now()
    existing_stmt = (
        select(PublishTask)
        .where(
            PublishTask.claimed_by_device_id == device_id,
            PublishTask.task_status.in_(("claimed", "running")),
        )
        .order_by(PublishTask.updated_at.desc(), PublishTask.created_at.desc())
    )
    existing = session.execute(existing_stmt).scalars().first()
    if existing:
        return existing
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


def claim_search_task(session: Session, device_id: str) -> tuple[SearchTask, Account | None] | None:
    reclaim_expired_claims(session)
    if device_has_active_task_for_model(session, device_id, SearchTask):
        raise HTTPException(status_code=409, detail="当前设备已有运行中任务")
    stmt = select(SearchTask).order_by(SearchTask.last_run_at.asc().nullsfirst(), SearchTask.created_at.asc())
    for task in session.execute(stmt).scalars():
        if not search_task_due(task):
            continue
        worker = choose_worker(session, usage_tag="worker_search", group_name=task.group_name)
        task.task_status = "claimed"
        task.claimed_by_device_id = device_id
        task.assigned_worker_account_id = worker.id if worker else None
        task.claim_expires_at = utc_now() + timedelta(minutes=CLAIM_TIMEOUT_MINUTES)
        write_audit_log(
            session,
            log_type="cookie_assign" if worker else "task_claim",
            operator_type="system" if worker else "app",
            operator_id="system" if worker else device_id,
            target_type="search_task",
            target_id=task.id,
            message="搜索任务已分配小号" if worker else "搜索任务已领取",
            payload={"worker_account_id": worker.id if worker else ""},
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
    if device_has_active_task_for_model(session, device_id, AnalyticsTask):
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


@app.post("/api/app/auth/request-sms-code")
def app_request_sms_code(payload: AppSmsCodeRequest) -> dict:
    login_api = get_pc_login_api()
    cookies = login_api.generate_init_cookies()
    success, message, detail = login_api.send_phone_code(payload.phone.strip(), cookies, payload.zone.strip())
    if not success:
        raise HTTPException(status_code=502, detail=message or "发送验证码失败")
    login_session_id = uuid4().hex
    LOGIN_SESSION_STORE[login_session_id] = {
        "phone": payload.phone.strip(),
        "zone": payload.zone.strip(),
        "cookies": cookies,
        "created_at": utc_now(),
    }
    return {
        "success": True,
        "message": message or "验证码已发送",
        "login_session_id": login_session_id,
        "expires_in_seconds": LOGIN_SESSION_TTL_SECONDS,
        "detail": detail,
    }


@app.post("/api/app/auth/login-with-sms")
def app_login_with_sms(payload: AppSmsLoginRequest, session: Session = Depends(get_db)) -> dict:
    login_session = get_login_session(payload.login_session_id)
    phone = payload.phone.strip()
    zone = payload.zone.strip()
    if login_session["phone"] != phone or login_session["zone"] != zone:
        raise HTTPException(status_code=400, detail="登录手机号或区号与验证码会话不匹配")

    login_api = get_pc_login_api()
    success, message, result = login_api.login_by_phone(phone, payload.code.strip(), login_session["cookies"], zone)
    if not success:
        raise HTTPException(status_code=502, detail=message or "验证码登录失败")

    cookies = result["cookies"]
    user_ok, user_info, cookies = login_api.get_user_info(cookies)
    cookies_str = login_api.cookies_to_str(cookies)
    nickname = ""
    user_uid = ""
    if user_ok:
        nickname = (user_info or {}).get("nickname", "") or (user_info or {}).get("red_id", "")
        user_uid = (
            (user_info or {}).get("user_id", "")
            or (user_info or {}).get("userid", "")
            or (user_info or {}).get("uid", "")
            or (user_info or {}).get("red_id", "")
        )

    account = upsert_primary_account_from_login(
        session,
        account_id=payload.account_id.strip(),
        phone=phone,
        cookies_str=cookies_str,
        nickname=nickname,
        user_uid=user_uid,
        device_id=payload.device_id.strip(),
    )
    session.commit()
    session.refresh(account)
    LOGIN_SESSION_STORE.pop(payload.login_session_id, None)
    return {
        "success": True,
        "message": message or "登录成功",
        "cookies": cookies_str,
        "account": to_account_public(account),
        "account_summary": to_account_summary(account),
        "user_info": user_info if user_ok else {},
    }


@app.get("/api/app/accounts/{account_id}/summary")
def app_account_summary(account_id: str, session: Session = Depends(get_db)) -> dict:
    account = require_account(session, account_id, "primary")
    summary = build_account_profile_summary(session, account)
    session.commit()
    return {"account": summary}


@app.post("/api/app/accounts/{account_id}/check")
def app_check_account_summary(account_id: str, session: Session = Depends(get_db)) -> dict:
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
    return {
        "success": ok,
        "message": message,
        "account": to_account_summary(account),
    }


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
    worker = create_worker_account_from_login(
        session,
        cookies_str=payload.cookies.strip(),
        nickname="",
        name=payload.name,
        group_name=payload.group_name,
        remark=payload.remark,
        usage_tags=payload.usage_tags,
        operator_id="web",
        source_message="创建小号 Cookie",
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


@app.post("/api/cookie-workers/auth/request-sms-code")
def request_worker_sms_code(payload: WorkerSmsCodeRequest) -> dict:
    login_api = get_pc_login_api()
    cookies = login_api.generate_init_cookies()
    success, message, detail = login_api.send_phone_code(payload.phone.strip(), cookies, payload.zone.strip())
    if not success:
        raise HTTPException(status_code=502, detail=message or "发送验证码失败")
    login_session_id = uuid4().hex
    LOGIN_SESSION_STORE[login_session_id] = {
        "account_type": "worker",
        "method": "sms",
        "phone": payload.phone.strip(),
        "zone": payload.zone.strip(),
        "cookies": cookies,
        "draft": payload.model_dump(),
        "created_at": utc_now(),
    }
    return {
        "success": True,
        "message": message or "验证码已发送",
        "login_session_id": login_session_id,
        "expires_in_seconds": LOGIN_SESSION_TTL_SECONDS,
        "detail": detail,
    }


@app.post("/api/cookie-workers/auth/login-with-sms")
def login_worker_with_sms(payload: WorkerSmsLoginRequest, session: Session = Depends(get_db)) -> dict:
    login_session = get_login_session(payload.login_session_id)
    if login_session.get("account_type") != "worker" or login_session.get("method") != "sms":
        raise HTTPException(status_code=400, detail="登录会话类型不匹配")
    phone = payload.phone.strip()
    zone = payload.zone.strip()
    if login_session["phone"] != phone or login_session["zone"] != zone:
        raise HTTPException(status_code=400, detail="登录手机号或区号与验证码会话不匹配")

    login_api = get_pc_login_api()
    success, message, result = login_api.login_by_phone(phone, payload.code.strip(), login_session["cookies"], zone)
    if not success:
        raise HTTPException(status_code=502, detail=message or "验证码登录失败")

    cookies = result["cookies"]
    user_ok, user_info, cookies = login_api.get_user_info(cookies)
    cookies_str = login_api.cookies_to_str(cookies)
    nickname = ""
    if user_ok:
        nickname = (user_info or {}).get("nickname", "") or (user_info or {}).get("red_id", "")
    worker = create_worker_account_from_login(
        session,
        cookies_str=cookies_str,
        nickname=nickname,
        name=payload.name,
        group_name=payload.group_name,
        remark=payload.remark or "手机号验证码登录创建",
        usage_tags=payload.usage_tags,
        operator_id="web_sms",
        source_message="手机号验证码登录创建小号",
    )
    session.commit()
    session.refresh(worker)
    LOGIN_SESSION_STORE.pop(payload.login_session_id, None)
    return {
        "success": True,
        "message": message or "登录成功",
        "worker_cookie": to_account_public(worker),
        "user_info": user_info if user_ok else {},
    }


@app.post("/api/cookie-workers/auth/request-qrcode")
def request_worker_qrcode(payload: WorkerQrCodeRequest) -> dict:
    login_api = get_pc_login_api()
    cookies = login_api.generate_init_cookies()
    success, message, qr_data = login_api.generate_qrcode(cookies)
    if not success or not qr_data:
        raise HTTPException(status_code=502, detail=message or "生成二维码失败")
    login_session_id = uuid4().hex
    LOGIN_SESSION_STORE[login_session_id] = {
        "account_type": "worker",
        "method": "qrcode",
        "cookies": qr_data["cookies"],
        "qr_id": qr_data["qr_id"],
        "qr_code": qr_data["code"],
        "qr_url": qr_data["qr_url"],
        "draft": payload.model_dump(),
        "created_at": utc_now(),
    }
    return {
        "success": True,
        "message": "二维码已生成",
        "login_session_id": login_session_id,
        "expires_in_seconds": LOGIN_SESSION_TTL_SECONDS,
        "qr_url": qr_data["qr_url"],
        "qr_data_url": qr_code_data_url(qr_data["qr_url"]),
    }


@app.post("/api/cookie-workers/auth/check-qrcode")
def check_worker_qrcode(payload: WorkerQrCodeCheckRequest, session: Session = Depends(get_db)) -> dict:
    login_session = get_login_session(payload.login_session_id)
    if login_session.get("account_type") != "worker" or login_session.get("method") != "qrcode":
        raise HTTPException(status_code=400, detail="登录会话类型不匹配")

    login_api = get_pc_login_api()
    success, message, cookies = login_api.check_qrcode_status(
        login_session["qr_id"],
        login_session["qr_code"],
        login_session["cookies"],
    )
    login_session["cookies"] = cookies
    if not success:
        return {
            "success": False,
            "message": message,
            "login_session_id": payload.login_session_id,
        }

    user_ok, user_info, cookies = login_api.get_user_info(cookies)
    cookies_str = login_api.cookies_to_str(cookies)
    nickname = ""
    if user_ok:
        nickname = (user_info or {}).get("nickname", "") or (user_info or {}).get("red_id", "")
    worker = create_worker_account_from_login(
        session,
        cookies_str=cookies_str,
        nickname=nickname,
        name=payload.name,
        group_name=payload.group_name,
        remark=payload.remark or "扫码登录创建",
        usage_tags=payload.usage_tags,
        operator_id="web_qrcode",
        source_message="扫码登录创建小号",
    )
    session.commit()
    session.refresh(worker)
    LOGIN_SESSION_STORE.pop(payload.login_session_id, None)
    return {
        "success": True,
        "message": message or "扫码登录成功",
        "worker_cookie": to_account_public(worker),
        "user_info": user_info if user_ok else {},
    }


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


@app.post("/api/app/publish-tasks/{task_id}/execute")
def app_execute_publish_task(task_id: str, payload: AppPublishExecuteRequest, session: Session = Depends(get_db)) -> dict:
    task = session.get(PublishTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="发帖任务不存在")
    if task.task_status == "success":
        return {"created": False, "task": to_publish_task(task)}
    if task.task_status != "claimed":
        raise HTTPException(status_code=409, detail="发帖任务未处于已领取状态")
    if task.claimed_by_device_id != payload.device_id:
        raise HTTPException(status_code=409, detail="当前设备未领取该发帖任务")

    account = require_account(session, task.account_id, "primary")
    ensure_account_session_available(account)
    ok, message = validate_cookie(account)
    account.last_check_at = utc_now()
    if not ok:
        mark_account_failure(account, message)
        session.commit()
        raise HTTPException(status_code=401, detail=message)

    creator_api = get_creator_api()
    try:
        note_payload = build_publish_note_payload(task)
        success, publish_message, res_json = creator_api.post_note(note_payload, account.cookies)
        if success:
            mark_account_success(account)
            post_id, post_url = extract_publish_result_fields(res_json)
            result_payload = PublishTaskResultRequest(
                device_id=payload.device_id,
                app_instance_id=payload.app_instance_id,
                result_id=uuid4().hex,
                status="published",
                post_id=post_id,
                post_url=post_url,
                error_message="",
                duration_seconds=0,
            )
            return handle_publish_task_result(task_id, result_payload, session)

        mark_account_failure(account, publish_message)
        result_payload = PublishTaskResultRequest(
            device_id=payload.device_id,
            app_instance_id=payload.app_instance_id,
            result_id=uuid4().hex,
            status="failed",
            post_id="",
            post_url="",
            error_message=publish_message or "发布失败",
            duration_seconds=0,
        )
        return handle_publish_task_result(task_id, result_payload, session)
    except HTTPException:
        raise
    except Exception as exc:
        mark_account_failure(account, str(exc))
        result_payload = PublishTaskResultRequest(
            device_id=payload.device_id,
            app_instance_id=payload.app_instance_id,
            result_id=uuid4().hex,
            status="failed",
            post_id="",
            post_url="",
            error_message=str(exc),
            duration_seconds=0,
        )
        return handle_publish_task_result(task_id, result_payload, session)


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


@app.post("/api/app/search-tasks")
def app_create_search_task(payload: AppSearchTaskCreate, session: Session = Depends(get_db)) -> dict:
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
        operator_type="app",
        operator_id=payload.device_id or payload.app_instance_id or "app",
        target_type="search_task",
        target_id=task.id,
        message="App 创建关键词搜索任务",
        payload={"group_name": task.group_name},
    )
    session.commit()
    session.refresh(task)
    return {"task": to_search_task(task)}


@app.post("/api/app/search-preview")
def app_search_preview(payload: AppDirectSearchRequest, session: Session = Depends(get_db)) -> dict:
    account = require_account(session, payload.account_id, "primary")
    ensure_account_session_available(account)
    worker = choose_worker(session, usage_tag="worker_search")
    if not worker:
        session.commit()
        raise HTTPException(status_code=409, detail="当前没有可用的搜索小号")
    ok, message = validate_cookie(worker)
    worker.last_check_at = utc_now()
    if not ok:
        mark_account_failure(worker, message)
        session.commit()
        raise HTTPException(status_code=409, detail="搜索小号 Cookie 不可用，请先检查小号池")

    api = get_pc_content_api()
    success, search_message, notes = api.search_some_note(
        payload.keyword.strip(),
        payload.require_num,
        worker.cookies,
        sort_type_choice=map_sort_type(payload.sort_type),
        note_type=map_note_type(payload.note_type),
        note_time=map_time_range(payload.time_range),
    )
    if not success:
        mark_account_failure(worker, search_message)
        session.commit()
        if worker.status == "invalid":
            raise HTTPException(status_code=409, detail=search_message or "搜索小号已失效，请更换小号")
        raise HTTPException(status_code=502, detail=search_message or "搜索失败")

    mark_account_success(worker)
    results = attach_worker_cookie_id([to_search_preview_item(item) for item in notes if item.get("id")], worker)
    if notes:
        logger.info(
            "search-preview keyword={} worker={} count={} first_raw={}",
            payload.keyword.strip(),
            worker.id,
            len(results),
            summarize_raw_note_fields(notes[0]),
        )
        logger.info(
            "search-preview first_parsed={}",
            {
                "post_id": results[0].get("post_id", "") if results else "",
                "title": results[0].get("title", "") if results else "",
                "content_preview": results[0].get("content_preview", "") if results else "",
                "topics": results[0].get("topics", []) if results else [],
                "image_count": len(results[0].get("image_urls", [])) if results else 0,
                "has_video": bool(results[0].get("video_url")) if results else False,
            },
        )
    write_audit_log(
        session,
        log_type="app_result",
        operator_type="app",
        operator_id=payload.account_id,
        target_type="search_task",
        target_id="direct_search",
        message="App 即时搜索",
        payload={"keyword": payload.keyword.strip(), "count": len(results), "worker_cookie_id": worker.id},
    )
    session.commit()
    return {
        "keyword": payload.keyword.strip(),
        "post_count": len(results),
        "results": results,
    }


@app.post("/api/app/search-post-detail")
def app_search_post_detail(payload: AppSearchPostDetailRequest, session: Session = Depends(get_db)) -> dict:
    account = require_account(session, payload.account_id, "primary")
    ensure_account_session_available(account)
    worker: Account | None = None
    if payload.worker_cookie_id.strip():
        worker = require_account(session, payload.worker_cookie_id.strip(), "worker")
    else:
        worker = choose_worker(session, usage_tag="worker_search")
    if not worker:
        session.commit()
        raise HTTPException(status_code=409, detail="当前没有可用的搜索小号")
    ok, message = validate_cookie(worker)
    worker.last_check_at = utc_now()
    if not ok:
        mark_account_failure(worker, message)
        session.commit()
        raise HTTPException(status_code=409, detail="搜索小号 Cookie 不可用，请先检查小号池")

    api = get_pc_content_api()
    success = False
    detail_message = ""
    res_json = None
    attempts = []

    def try_fetch_detail(cookies_str: str, source: str) -> tuple[bool, str, dict | None]:
        local_success = False
        local_message = ""
        local_json = None
        for candidate_url in build_detail_url_candidates(payload.post_url.strip()):
            attempt_success, attempt_message, attempt_json = api.get_note_info(candidate_url, cookies_str)
            attempts.append({"source": source, "url": candidate_url, "success": attempt_success, "message": attempt_message})
            if attempt_success:
                local_success = True
                local_message = attempt_message
                local_json = attempt_json
                break
            local_message = attempt_message
        return local_success, local_message, local_json

    success, detail_message, res_json = try_fetch_detail(worker.cookies, "worker")
    if not success:
        fallback_success, fallback_message, fallback_json = try_fetch_detail(account.cookies, "primary")
        if fallback_success:
            success = True
            detail_message = fallback_message
            res_json = fallback_json
        else:
            logger.warning("search-post-detail attempts={}", attempts)
            mark_account_failure(worker, detail_message)
            session.commit()
            if worker.status == "invalid":
                raise HTTPException(status_code=409, detail=detail_message or "搜索小号已失效，请更换小号")
            raise HTTPException(status_code=502, detail=detail_message or "获取帖子详情失败")

    items = (((res_json or {}).get("data") or {}).get("items") or [])
    if not items:
        fallback_success, fallback_message, fallback_json = try_fetch_detail(account.cookies, "primary") if success else (False, "", None)
        fallback_items = (((fallback_json or {}).get("data") or {}).get("items") or []) if fallback_json else []
        if fallback_success and fallback_items:
            res_json = fallback_json
            items = fallback_items
            detail_message = fallback_message
        else:
            session.commit()
            raise HTTPException(status_code=404, detail="帖子详情不存在")

    mark_account_success(worker)
    detail = to_search_post_detail(items[0])
    detail["worker_cookie_id"] = worker.id
    logger.info("search-post-detail attempts={}", attempts)
    logger.info("search-post-detail raw={}", summarize_raw_note_fields(items[0]))
    logger.info(
        "search-post-detail parsed={}",
        {
            "post_id": detail.get("post_id", ""),
            "title": detail.get("title", ""),
            "content": detail.get("content", ""),
            "topics": detail.get("topics", []),
            "image_count": len(detail.get("image_urls", [])),
            "video_url": detail.get("video_url", ""),
        },
    )
    write_audit_log(
        session,
        log_type="app_result",
        operator_type="app",
        operator_id=payload.account_id,
        target_type="search_task",
        target_id="post_detail",
        message="App 查看帖子详情",
        payload={"post_id": detail.get("post_id"), "post_url": payload.post_url.strip()},
    )
    session.commit()
    return {"detail": detail}


@app.get("/api/search-tasks")
def list_search_tasks(session: Session = Depends(get_db)) -> dict:
    stmt = select(SearchTask).order_by(SearchTask.created_at.desc())
    return {"tasks": [to_search_task(item) for item in session.execute(stmt).scalars().all()]}


@app.get("/api/app/search-tasks")
def app_list_search_tasks(session: Session = Depends(get_db)) -> dict:
    stmt = select(SearchTask).order_by(SearchTask.created_at.desc())
    tasks = session.execute(stmt).scalars().all()
    result_counts = dict(
        session.execute(
            select(SearchResult.search_task_id, func.count(SearchResult.id))
            .group_by(SearchResult.search_task_id)
        ).all()
    )
    return {
        "tasks": [
            {
                **to_search_task(item),
                "post_count": result_counts.get(item.id, 0),
            }
            for item in tasks
        ]
    }


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
    if worker:
        body["worker_cookie_id"] = worker.id
    return {"task": body}


@app.get("/api/app/search-tasks/{task_id}")
def app_get_search_task_detail(task_id: str, session: Session = Depends(get_db)) -> dict:
    task = session.get(SearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="关键词任务不存在")
    stmt = select(SearchResult).where(SearchResult.search_task_id == task_id).order_by(SearchResult.created_at.desc())
    return to_search_task_detail(task, session.execute(stmt).scalars().all())


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
        worker = require_account(session, payload.worker_cookie_id, "worker") if payload.worker_cookie_id else None
        task.claimed_by_device_id = ""
        task.claim_expires_at = None
        task.task_status = "pending"
        task.last_run_at = utc_now()
        task.last_error = payload.error_message
        if payload.error_message and not payload.items:
            task.retry_count += 1
            if worker:
                mark_account_failure(worker, payload.error_message)
        else:
            task.last_success_at = utc_now()
            task.retry_count = 0
            if worker:
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
                    worker_account_id=worker.id if worker else None,
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
        if worker:
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
