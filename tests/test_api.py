from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from server import main
from server.db import configure_database, get_session_factory, init_db, utc_now
from server.models import PublishTask, SearchTask, TaskResult


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "test.db"
    configure_database(f"sqlite:///{db_path}")
    init_db(drop_existing=True)
    return TestClient(main.app)


def create_primary_account(client: TestClient, name: str = "brand", bound_device_id: str = "") -> str:
    response = client.post(
        "/api/accounts/primary",
        json={
            "name": name,
            "cookies": "a" * 32,
            "nickname": name,
            "bound_device_id": bound_device_id,
            "remark": "",
        },
    )
    assert response.status_code == 200
    return response.json()["account"]["id"]


def create_worker_cookie(client: TestClient, name: str, tags: list[str], group_name: str = "brand_a") -> str:
    response = client.post(
        "/api/cookie-workers",
        json={
            "name": name,
            "cookies": "b" * 32,
            "remark": "",
            "usage_tags": tags,
            "group_name": group_name,
        },
    )
    assert response.status_code == 200
    return response.json()["worker_cookie"]["id"]


def test_health(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_primary_and_worker_accounts_are_listed(client: TestClient):
    primary_id = create_primary_account(client)
    worker_id = create_worker_cookie(client, "worker-1", ["worker_search"])

    response = client.get("/api/accounts")
    body = response.json()
    assert body["primary_accounts"][0]["id"] == primary_id
    assert body["worker_cookies"][0]["id"] == worker_id
    assert "cookies" not in body["primary_accounts"][0]
    assert "..." in body["primary_accounts"][0]["cookie_preview"]


def test_cookie_check_updates_status(client: TestClient):
    account_id = create_primary_account(client)
    response = client.post(f"/api/accounts/primary/{account_id}/check")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["account"]["status"] == "active"


def test_worker_is_allocated_by_group_and_tag(client: TestClient):
    create_worker_cookie(client, "worker-search", ["worker_search"], "brand_a")
    create_worker_cookie(client, "worker-analytics", ["worker_analytics"], "brand_a")
    response = client.post(
        "/api/search-tasks",
        json={
            "keyword": "新加坡 qt",
            "group_name": "brand_a",
            "require_num": 20,
            "interval_minutes": 120,
        },
    )
    assert response.status_code == 200

    response = client.get("/api/app/search-tasks/next", params={"device_id": "android-001"})
    assert response.status_code == 200
    task = response.json()["task"]
    assert task["worker_cookie_id"]


def test_publish_task_requires_approval_before_claim(client: TestClient):
    account_id = create_primary_account(client, bound_device_id="android-001")
    response = client.post(
        "/api/publish-tasks",
        json={
            "account_id": account_id,
            "title": "Title",
            "desc": "Body",
            "topics": ["tag"],
            "location": "",
            "media_type": "image",
            "media_urls": ["https://example.com/a.jpg"],
            "review_status": "pending",
        },
    )
    assert response.status_code == 200
    task_id = response.json()["task"]["id"]

    response = client.get("/api/app/publish-tasks/next", params={"device_id": "android-001"})
    assert response.status_code == 200
    assert response.json()["task"] is None

    response = client.patch(f"/api/publish-tasks/{task_id}", json={"review_status": "approved"})
    assert response.status_code == 200

    response = client.get("/api/app/publish-tasks/next", params={"device_id": "android-001"})
    assert response.status_code == 200
    assert response.json()["task"]["id"] == task_id


def test_same_device_cannot_claim_multiple_tasks(client: TestClient):
    create_worker_cookie(client, "worker-search", ["worker_search"])
    client.post("/api/search-tasks", json={"keyword": "A", "group_name": "brand_a"})
    client.post("/api/search-tasks", json={"keyword": "B", "group_name": "brand_a"})

    response = client.get("/api/app/search-tasks/next", params={"device_id": "android-001"})
    assert response.status_code == 200
    assert response.json()["task"] is not None

    response = client.get("/api/app/search-tasks/next", params={"device_id": "android-001"})
    assert response.status_code == 409


def test_publish_result_is_idempotent(client: TestClient):
    account_id = create_primary_account(client, bound_device_id="android-001")
    response = client.post(
        "/api/publish-tasks",
        json={
            "account_id": account_id,
            "title": "Title",
            "desc": "Body",
            "media_type": "image",
            "media_urls": ["https://example.com/a.jpg"],
            "review_status": "approved",
        },
    )
    task_id = response.json()["task"]["id"]
    claim = client.get("/api/app/publish-tasks/next", params={"device_id": "android-001"})
    assert claim.status_code == 200

    payload = {
        "device_id": "android-001",
        "app_instance_id": "app-1",
        "result_id": "result-1",
        "status": "published",
        "post_id": "post-1",
        "post_url": "https://www.xiaohongshu.com/explore/post-1",
        "error_message": "",
        "duration_seconds": 12,
    }
    first = client.post(f"/api/app/publish-tasks/{task_id}/result", json=payload)
    second = client.post(f"/api/app/publish-tasks/{task_id}/result", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["created"] is True
    assert second.json()["created"] is False

    with get_session_factory()() as session:
        count = session.execute(select(TaskResult).where(TaskResult.task_id == task_id)).scalars().all()
        assert len(count) == 1


def test_unified_app_task_claim_and_result(client: TestClient):
    account_id = create_primary_account(client, bound_device_id="android-001")
    response = client.post(
        "/api/publish-tasks",
        json={
            "account_id": account_id,
            "title": "Unified",
            "desc": "Body",
            "media_type": "image",
            "media_urls": ["https://example.com/a.jpg"],
            "review_status": "approved",
        },
    )
    task_id = response.json()["task"]["id"]

    claim = client.get(
        "/api/app/tasks/next",
        params={
            "device_id": "android-001",
            "app_instance_id": "app-1",
            "app_version": "1.0.0",
            "device_name": "Pixel",
        },
    )
    assert claim.status_code == 200
    assert claim.json()["task_type"] == "publish"
    assert claim.json()["task"]["id"] == task_id

    result = client.post(
        f"/api/app/tasks/publish/{task_id}/result",
        json={
            "device_id": "android-001",
            "app_instance_id": "app-1",
            "result_id": "unified-result-1",
            "status": "published",
            "post_id": "post-1",
            "post_url": "https://www.xiaohongshu.com/explore/post-1",
            "error_message": "",
            "duration_seconds": 10,
        },
    )
    assert result.status_code == 200
    assert result.json()["created"] is True
    assert result.json()["task"]["task_status"] == "success"


def test_requeue_publish_task(client: TestClient):
    account_id = create_primary_account(client)
    response = client.post(
        "/api/publish-tasks",
        json={
            "account_id": account_id,
            "title": "Requeue",
            "desc": "Body",
            "media_type": "image",
            "media_urls": ["https://example.com/a.jpg"],
            "review_status": "approved",
        },
    )
    task_id = response.json()["task"]["id"]
    client.patch(f"/api/publish-tasks/{task_id}", json={"task_status": "cancelled"})

    response = client.post(f"/api/publish-tasks/{task_id}/requeue")
    assert response.status_code == 200
    body = response.json()["task"]
    assert body["task_status"] == "pending"
    assert body["claim_expires_at"] is None


def test_claim_timeout_is_reclaimed(client: TestClient):
    create_worker_cookie(client, "worker-search", ["worker_search"])
    response = client.post("/api/search-tasks", json={"keyword": "A", "group_name": "brand_a"})
    task_id = response.json()["task"]["id"]
    response = client.get("/api/app/search-tasks/next", params={"device_id": "android-001"})
    assert response.status_code == 200
    assert response.json()["task"]["id"] == task_id

    with get_session_factory()() as session:
        task = session.get(SearchTask, task_id)
        assert task is not None
        task.claim_expires_at = utc_now() - timedelta(minutes=1)
        session.commit()

    response = client.get("/api/app/search-tasks/next", params={"device_id": "android-002"})
    assert response.status_code == 200
    assert response.json()["task"]["id"] == task_id


def test_search_result_is_saved_and_deduped(client: TestClient):
    worker_id = create_worker_cookie(client, "worker-search", ["worker_search"])
    response = client.post("/api/search-tasks", json={"keyword": "A", "group_name": "brand_a"})
    task_id = response.json()["task"]["id"]
    claim = client.get("/api/app/search-tasks/next", params={"device_id": "android-001"})
    assert claim.status_code == 200

    payload = {
        "device_id": "android-001",
        "app_instance_id": "app-1",
        "result_id": "search-result-1",
        "worker_cookie_id": worker_id,
        "partial_success": False,
        "items": [
            {
                "post_id": "note-1",
                "post_url": "https://www.xiaohongshu.com/explore/note-1",
                "title": "Title",
                "username": "作者",
                "user_id": "user-1",
                "content_preview": "正文摘要",
                "like_count": 1,
                "comment_count": 2,
                "collect_count": 3,
            },
            {
                "post_id": "note-1",
                "post_url": "https://www.xiaohongshu.com/explore/note-1",
                "title": "Title",
                "username": "作者",
                "user_id": "user-1",
                "content_preview": "正文摘要",
                "like_count": 1,
                "comment_count": 2,
                "collect_count": 3,
            },
        ],
        "error_message": "",
        "duration_seconds": 5,
    }
    response = client.post(f"/api/app/search-tasks/{task_id}/result", json=payload)
    assert response.status_code == 200
    assert response.json()["saved_count"] == 1

    response = client.get("/api/search-results", params={"task_id": task_id})
    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    result_id = response.json()["results"][0]["id"]

    response = client.patch(f"/api/search-results/{result_id}", json={"review_status": "valid", "hidden": True})
    assert response.status_code == 200
    assert response.json()["result"]["review_status"] == "valid"
    assert response.json()["result"]["hidden"] is True


def test_device_can_be_disabled(client: TestClient):
    response = client.post(
        "/api/app/heartbeat",
        json={
            "device_id": "android-001",
            "app_instance_id": "app-1",
            "app_version": "1.0.0",
            "device_name": "Pixel",
        },
    )
    assert response.status_code == 200
    device_id = response.json()["device"]["id"]

    response = client.patch(f"/api/devices/{device_id}", json={"status": "disabled"})
    assert response.status_code == 200
    assert response.json()["device"]["status"] == "disabled"

    response = client.get("/api/app/tasks/next", params={"device_id": "android-001", "app_instance_id": "app-1"})
    assert response.status_code == 403


def test_analytics_snapshot_is_saved(client: TestClient):
    account_id = create_primary_account(client)
    worker_id = create_worker_cookie(client, "worker-analytics", ["worker_analytics"])
    response = client.post("/api/analytics-tasks", json={"account_id": account_id, "group_name": "brand_a"})
    task_id = response.json()["task"]["id"]
    claim = client.get("/api/app/analytics-tasks/next", params={"device_id": "android-001"})
    assert claim.status_code == 200
    assert claim.json()["task"]["id"] == task_id

    payload = {
        "device_id": "android-001",
        "app_instance_id": "app-1",
        "result_id": "analytics-result-1",
        "worker_cookie_id": worker_id,
        "snapshot": {
            "account_id": account_id,
            "nickname": "品牌号",
            "follower_count": 120,
            "liked_count": 888,
            "post_count": 3,
            "collected_total": 12,
            "posts": [
                {
                    "post_id": "p-1",
                    "title": "帖子一",
                    "post_url": "https://www.xiaohongshu.com/explore/p-1",
                    "like_count": 1,
                    "comment_count": 2,
                    "collect_count": 3,
                }
            ],
        },
        "error_message": "",
        "duration_seconds": 8,
    }
    response = client.post(f"/api/app/analytics-tasks/{task_id}/result", json=payload)
    assert response.status_code == 200
    assert response.json()["created"] is True

    response = client.get("/api/analytics-snapshots", params={"account_id": account_id})
    assert response.status_code == 200
    snapshots = response.json()["snapshots"]
    assert len(snapshots) == 1
    assert snapshots[0]["nickname"] == "品牌号"
    assert snapshots[0]["posts"][0]["post_id"] == "p-1"


def test_summary_uses_database_aggregates(client: TestClient):
    create_primary_account(client)
    create_worker_cookie(client, "worker-search", ["worker_search"])
    response = client.get("/api/ops/summary")
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["primary_account_total"] == 1
    assert summary["worker_cookie_total"] == 1
    assert "latest_logs" in summary
