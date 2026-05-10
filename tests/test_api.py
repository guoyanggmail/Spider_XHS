from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from server import main
from server.db import configure_database, get_session_factory, init_db, utc_now
from server.models import Account, PublishTask, SearchTask, TaskResult


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "test.db"
    configure_database(f"sqlite:///{db_path}")
    init_db(drop_existing=True)
    main.LOGIN_SESSION_STORE.clear()
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


def test_worker_status_update_keeps_existing_usage_tags(client: TestClient):
    worker_id = create_worker_cookie(client, "worker-1", ["worker_search"])
    response = client.patch(
        f"/api/cookie-workers/{worker_id}",
        json={
            "status": "disabled",
            "remark": "",
            "group_name": "brand_a",
            "usage_tags": ["worker_search"],
        },
    )
    assert response.status_code == 200
    body = response.json()["worker_cookie"]
    assert body["status"] == "disabled"
    assert body["usage_tags"] == ["worker_search"]


def test_app_can_fetch_account_summary(client: TestClient):
    account_id = create_primary_account(client, name="brand-main")
    response = client.get(f"/api/app/accounts/{account_id}/summary")
    assert response.status_code == 200
    account = response.json()["account"]
    assert account["id"] == account_id
    assert account["name"] == "brand-main"
    assert account["status"] == "active"


def test_app_account_summary_prefers_worker_profile_and_published_notes(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    account_id = create_primary_account(client, name="brand-main")
    create_worker_cookie(client, "worker-search", ["worker_search"])

    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        assert account is not None
        account.user_uid = "uid-1"
        account.nickname = "主账号"
        session.commit()

    class FakeContentApi:
        def get_user_info(self, user_id: str, cookies_str: str, proxies=None):
            assert user_id == "uid-1"
            return True, "成功", {
                "success": True,
                "data": {
                    "nickname": "主账号昵称",
                    "avatar": "https://img.example.com/avatar.jpg",
                    "follow_count": 15,
                    "fans_count": 230,
                    "interaction": 980,
                },
            }

        def get_user_note_info(self, user_id: str, cursor: str, cookies_str: str, xsec_token="", xsec_source="", proxies=None):
            assert user_id == "uid-1"
            assert cursor == ""
            return True, "成功", {
                "success": True,
                "data": {
                    "notes": [
                        {
                            "id": "note-1",
                            "xsec_token": "token-1",
                            "note_card": {
                                "type": "normal",
                                "display_title": "发布笔记A",
                                "desc": "正文A",
                                "user": {
                                    "user_id": "uid-1",
                                    "nickname": "主账号昵称",
                                    "avatar": "https://img.example.com/avatar.jpg",
                                },
                                "interact_info": {
                                    "liked_count": 11,
                                    "comment_count": 2,
                                    "collected_count": 3,
                                },
                                "image_list": [
                                    {"info_list": [{"url": "https://img.example.com/cover-a.jpg"}]}
                                ],
                            },
                        }
                    ]
                },
            }

        def get_user_self_info2(self, cookies_str: str, proxies=None):
            raise AssertionError("worker profile available, should not fallback to self profile")

    monkeypatch.setattr(main, "get_pc_content_api", lambda: FakeContentApi())

    response = client.get(f"/api/app/accounts/{account_id}/summary")
    assert response.status_code == 200
    account = response.json()["account"]
    assert account["nickname"] == "主账号昵称"
    assert account["avatar"] == "https://img.example.com/avatar.jpg"
    assert account["following_count"] == 15
    assert account["follower_count"] == 230
    assert account["liked_count"] == 980
    assert account["profile_source"] == "worker_public"
    assert len(account["published_notes"]) == 1
    assert account["published_notes"][0]["title"] == "发布笔记A"
    assert account["published_notes"][0]["worker_cookie_id"] != ""


def test_app_account_summary_prefers_creator_notes_for_recent_published_posts(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    account_id = create_primary_account(client, name="brand-main")
    create_worker_cookie(client, "worker-search", ["worker_search"])

    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        assert account is not None
        account.user_uid = "uid-1"
        session.commit()

    class FakeContentApi:
        def get_user_info(self, user_id: str, cookies_str: str, proxies=None):
            return True, "成功", {"success": True, "data": {"nickname": "主账号昵称", "fans_count": 230}}

        def get_user_note_info(self, user_id: str, cursor: str, cookies_str: str, xsec_token="", xsec_source="", proxies=None):
            return True, "成功", {"success": True, "data": {"notes": []}}

        def get_user_self_info2(self, cookies_str: str, proxies=None):
            return True, "成功", {"success": True, "data": {"avatar": "https://img.example.com/avatar.jpg"}}

    class FakeCreatorApi:
        def get_all_publish_note_info(self, cookies_str: str):
            return True, "成功", [
                {
                    "note_id": "creator-note-1",
                    "title": "刚发布的笔记",
                    "desc": "正文内容",
                    "cover_url": "https://img.example.com/cover.jpg",
                    "image_urls": ["https://img.example.com/cover.jpg"],
                }
            ]

    monkeypatch.setattr(main, "get_pc_content_api", lambda: FakeContentApi())
    monkeypatch.setattr(main, "get_creator_api", lambda: FakeCreatorApi())

    response = client.get(f"/api/app/accounts/{account_id}/summary")
    assert response.status_code == 200
    account = response.json()["account"]
    assert account["profile_source"] == "creator_notes"
    assert account["published_notes"][0]["post_id"] == "creator-note-1"
    assert account["published_notes"][0]["title"] == "刚发布的笔记"


def test_app_account_summary_falls_back_to_primary_public_profile_and_notes(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    account_id = create_primary_account(client, name="brand-main")

    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        assert account is not None
        account.user_uid = "uid-1"
        session.commit()

    class FakeContentApi:
        def get_user_self_info2(self, cookies_str: str, proxies=None):
            return True, "成功", {"success": True, "data": {"nickname": "叨叨", "imageb": "https://img.example.com/a.jpg"}}

        def get_user_info(self, user_id: str, cookies_str: str, proxies=None):
            return True, "成功", {
                "success": True,
                "data": {
                    "basic_info": {"nickname": "叨叨", "imageb": "https://img.example.com/a.jpg"},
                    "interactions": [
                        {"type": "follows", "count": "22"},
                        {"type": "fans", "count": "5"},
                        {"type": "interaction", "count": "1"},
                    ],
                },
                "interactions": [
                    {"type": "follows", "count": "22"},
                    {"type": "fans", "count": "5"},
                    {"type": "interaction", "count": "1"},
                ],
            }

        def get_user_note_info(self, user_id: str, cursor: str, cookies_str: str, xsec_token="", xsec_source="", proxies=None):
            return True, "成功", {
                "success": True,
                "data": {
                    "notes": [
                        {
                            "id": "note-1",
                            "xsec_token": "token-1",
                            "note_card": {
                                "display_title": "公开笔记A",
                                "desc": "正文A",
                                "user": {"user_id": "uid-1", "nickname": "叨叨", "avatar": "https://img.example.com/a.jpg"},
                                "interact_info": {"liked_count": 2, "comment_count": 3, "collected_count": 4},
                                "image_list": [{"info_list": [{"url": "https://img.example.com/cover.jpg"}]}],
                            },
                        }
                    ]
                },
            }

    class FakeCreatorApi:
        def get_all_publish_note_info(self, cookies_str: str):
            return False, "登录已过期", []

    monkeypatch.setattr(main, "get_pc_content_api", lambda: FakeContentApi())
    monkeypatch.setattr(main, "get_creator_api", lambda: FakeCreatorApi())

    response = client.get(f"/api/app/accounts/{account_id}/summary")
    assert response.status_code == 200
    account = response.json()["account"]
    assert account["following_count"] == 22
    assert account["follower_count"] == 5
    assert account["liked_count"] == 1
    assert account["published_notes"][0]["title"] == "公开笔记A"
    assert account["profile_source"] == "primary_public_notes"


def test_app_can_check_account_status(client: TestClient):
    account_id = create_primary_account(client, name="brand-main")
    response = client.post(f"/api/app/accounts/{account_id}/check")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["account"]["status"] == "active"


def test_profile_note_summary_supports_public_user_note_shape():
    item = main.to_profile_note_summary(
        {
            "note_id": "note-1",
            "xsec_token": "token-1",
            "display_title": "公开笔记",
            "type": "normal",
            "user": {
                "nickname": "叨叨",
                "avatar": "https://img.example.com/avatar.jpg",
            },
            "interact_info": {
                "liked_count": "8",
                "comment_count": "3",
                "collected_count": "2",
            },
            "cover": {
                "url_default": "https://img.example.com/cover.jpg",
            },
        }
    )
    assert item["post_id"] == "note-1"
    assert "xsec_token=token-1" in item["post_url"]
    assert item["cover_url"] == "https://img.example.com/cover.jpg"
    assert item["author_name"] == "叨叨"
    assert item["author_avatar"] == "https://img.example.com/avatar.jpg"
    assert item["like_count"] == 8
    assert item["comment_count"] == 3


def test_app_can_search_preview(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    account_id = create_primary_account(client, name="brand-main")
    create_worker_cookie(client, "worker-search", ["worker_search"])

    class FakeContentApi:
        def search_some_note(self, query, require_num, cookies_str, sort_type_choice=0, note_type=0, note_time=0, **kwargs):
            assert query == "新加坡酒店"
            assert require_num == 2
            return True, "成功", [
                {
                    "id": "note-1",
                    "url": "https://www.xiaohongshu.com/explore/note-1",
                    "note_card": {
                        "type": "normal",
                        "user": {"user_id": "user-1", "nickname": "作者A", "avatar": ""},
                        "title": "帖子A",
                        "desc": "内容A",
                        "interact_info": {
                            "liked_count": 12,
                            "collected_count": 3,
                            "comment_count": 2,
                            "share_count": 1,
                        },
                        "image_list": [],
                        "tag_list": [],
                        "time": 1710000000000,
                        "ip_location": "新加坡",
                    },
                },
                {
                    "id": "note-2",
                    "url": "https://www.xiaohongshu.com/explore/note-2",
                    "note_card": {
                        "type": "video",
                        "user": {"user_id": "user-2", "nickname": "作者B", "avatar": ""},
                        "title": "帖子B",
                        "desc": "内容B",
                        "interact_info": {
                            "liked_count": 20,
                            "collected_count": 5,
                            "comment_count": 4,
                            "share_count": 2,
                        },
                        "image_list": [],
                        "tag_list": [],
                        "video": {"media": {"stream": {"h264": []}}},
                        "time": 1710000001000,
                        "ip_location": "新加坡",
                    },
                },
            ]

    monkeypatch.setattr(main, "get_pc_content_api", lambda: FakeContentApi())

    response = client.post(
        "/api/app/search-preview",
        json={
            "account_id": account_id,
            "keyword": "新加坡酒店",
            "require_num": 2,
            "sort_type": "general",
            "note_type": "all",
            "time_range": "all",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["keyword"] == "新加坡酒店"
    assert body["post_count"] == 2
    assert body["results"][0]["post_id"] == "note-1"
    assert body["results"][0]["title"] == "帖子A"
    assert body["results"][0]["author_name"] == "作者A"
    assert body["results"][0]["author_avatar"] == ""
    assert body["results"][0]["content"] == "内容A"
    assert body["results"][0]["note_type"] == "normal"
    assert body["results"][0]["location"] == "新加坡"
    assert body["results"][0]["worker_cookie_id"]


def test_app_search_preview_returns_401_when_account_already_invalid(client: TestClient):
    account_id = create_primary_account(client, name="brand-main")
    create_worker_cookie(client, "worker-search", ["worker_search"])
    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        assert account is not None
        account.status = "invalid"
        session.commit()

    response = client.post(
        "/api/app/search-preview",
        json={
            "account_id": account_id,
            "keyword": "新加坡酒店",
            "require_num": 1,
            "sort_type": "general",
            "note_type": "all",
            "time_range": "all",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "登录已失效，请重新登录"


def test_app_search_preview_marks_worker_invalid_and_returns_409_on_upstream_login_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    account_id = create_primary_account(client, name="brand-main")
    worker_id = create_worker_cookie(client, "worker-search", ["worker_search"])

    class FakeContentApi:
        def search_some_note(self, query, require_num, cookies_str, sort_type_choice=0, note_type=0, note_time=0, **kwargs):
            return False, "Cookie 已失效，请重新登录", []

    monkeypatch.setattr(main, "get_pc_content_api", lambda: FakeContentApi())

    response = client.post(
        "/api/app/search-preview",
        json={
            "account_id": account_id,
            "keyword": "新加坡酒店",
            "require_num": 1,
            "sort_type": "general",
            "note_type": "all",
            "time_range": "all",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Cookie 已失效，请重新登录"

    session_factory = get_session_factory()
    with session_factory() as session:
        worker = session.get(Account, worker_id)
        account = session.get(Account, account_id)
        assert worker is not None
        assert account is not None
        assert worker.status == "invalid"
        assert account.status == "active"


def test_app_search_preview_builds_post_url_from_id_and_xsec_token(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    account_id = create_primary_account(client, name="brand-main")
    create_worker_cookie(client, "worker-search", ["worker_search"])

    class FakeContentApi:
        def search_some_note(self, query, require_num, cookies_str, sort_type_choice=0, note_type=0, note_time=0, **kwargs):
            return True, "成功", [
                {
                    "id": "note-1",
                    "xsec_token": "token-1",
                    "note_card": {
                        "display_title": "帖子A",
                        "user": {"user_id": "user-1", "nickname": "作者A"},
                        "interact_info": {},
                        "image_list": [],
                    },
                }
            ]

    monkeypatch.setattr(main, "get_pc_content_api", lambda: FakeContentApi())

    response = client.post(
        "/api/app/search-preview",
        json={
            "account_id": account_id,
            "keyword": "新加坡酒店",
            "require_num": 1,
            "sort_type": "general",
            "note_type": "all",
            "time_range": "all",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["post_url"] == "https://www.xiaohongshu.com/explore/note-1?xsec_token=token-1&xsec_source=pc_search"


def test_app_search_preview_tolerates_sparse_note_fields(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    account_id = create_primary_account(client, name="brand-main")
    create_worker_cookie(client, "worker-search", ["worker_search"])

    class FakeContentApi:
        def search_some_note(self, query, require_num, cookies_str, sort_type_choice=0, note_type=0, note_time=0, **kwargs):
            return True, "成功", [
                {
                    "id": "note-1",
                    "url": "https://www.xiaohongshu.com/explore/note-1",
                    "note_card": {
                        "user": {"user_id": "user-1"},
                        "interact_info": {},
                    },
                }
            ]

    monkeypatch.setattr(main, "get_pc_content_api", lambda: FakeContentApi())

    response = client.post(
        "/api/app/search-preview",
        json={
            "account_id": account_id,
            "keyword": "新加坡酒店",
            "require_num": 1,
            "sort_type": "general",
            "note_type": "all",
            "time_range": "all",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["post_count"] == 1
    assert body["results"][0]["title"] == "无标题"
    assert body["results"][0]["author_name"] == ""


def test_app_search_preview_supports_alternate_title_and_content_fields(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    account_id = create_primary_account(client, name="brand-main")
    create_worker_cookie(client, "worker-search", ["worker_search"])

    class FakeContentApi:
        def search_some_note(self, query, require_num, cookies_str, sort_type_choice=0, note_type=0, note_time=0, **kwargs):
            return True, "成功", [
                {
                    "id": "note-1",
                    "url": "https://www.xiaohongshu.com/explore/note-1",
                    "display_title": "展示标题A",
                    "author_name": "作者A",
                    "note_card": {
                        "user": {"userid": "user-1"},
                        "display_desc": [{"text": "第一段"}, {"content": "第二段"}],
                        "interact_info": {
                            "liked_count": "12",
                            "collected_count": None,
                            "comment_count": "3",
                        },
                    },
                }
            ]

    monkeypatch.setattr(main, "get_pc_content_api", lambda: FakeContentApi())

    response = client.post(
        "/api/app/search-preview",
        json={
            "account_id": account_id,
            "keyword": "新加坡酒店",
            "require_num": 1,
            "sort_type": "general",
            "note_type": "all",
            "time_range": "all",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["post_count"] == 1
    assert body["results"][0]["title"] == "展示标题A"
    assert body["results"][0]["author_name"] == "作者A"
    assert body["results"][0]["author_id"] == "user-1"
    assert body["results"][0]["content_preview"] == "第一段 第二段"
    assert body["results"][0]["like_count"] == 12
    assert body["results"][0]["comment_count"] == 3
    assert body["results"][0]["collect_count"] == 0


def test_app_search_preview_uses_content_as_title_fallback(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    account_id = create_primary_account(client, name="brand-main")
    create_worker_cookie(client, "worker-search", ["worker_search"])

    class FakeContentApi:
        def search_some_note(self, query, require_num, cookies_str, sort_type_choice=0, note_type=0, note_time=0, **kwargs):
            return True, "成功", [
                {
                    "id": "note-1",
                    "url": "https://www.xiaohongshu.com/explore/note-1",
                    "note_card": {
                        "desc": "这是正文第一句，这是正文第二句，用来补标题",
                        "interact_info": {},
                    },
                }
            ]

    monkeypatch.setattr(main, "get_pc_content_api", lambda: FakeContentApi())

    response = client.post(
        "/api/app/search-preview",
        json={
            "account_id": account_id,
            "keyword": "新加坡酒店",
            "require_num": 1,
            "sort_type": "general",
            "note_type": "all",
            "time_range": "all",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["title"] == "这是正文第一句，这是正文第二句，用来补标题"
    assert body["results"][0]["content"] == "这是正文第一句，这是正文第二句，用来补标题"


def test_app_can_fetch_search_post_detail(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    account_id = create_primary_account(client, name="brand-main")
    create_worker_cookie(client, "worker-search", ["worker_search"])

    class FakeContentApi:
        def get_note_info(self, url, cookies_str, proxies=None):
            assert url == "https://www.xiaohongshu.com/explore/note-1"
            return True, "成功", {
                "data": {
                    "items": [
                        {
                            "id": "note-1",
                            "url": "https://www.xiaohongshu.com/explore/note-1",
                            "note_card": {
                                "type": "video",
                                "user": {"user_id": "user-1", "nickname": "作者A", "avatar": ""},
                                "title": "",
                                "desc": "完整正文",
                                "interact_info": {
                                    "liked_count": 12,
                                    "collected_count": 3,
                                    "comment_count": 2,
                                    "share_count": 1,
                                },
                                "image_list": [
                                    {"info_list": [{"url": "https://cdn.example.com/s.jpg"}, {"url": "https://cdn.example.com/1.jpg"}]}
                                ],
                                "tag_list": [{"name": "新加坡"}, {"name": "酒店"}],
                                "video": {
                                    "media": {"stream": {"h264": [{"master_url": "https://cdn.example.com/1.mp4"}]}}
                                },
                                "time": 1710000000000,
                            },
                        }
                    ]
                }
            }

    monkeypatch.setattr(main, "get_pc_content_api", lambda: FakeContentApi())

    response = client.post(
        "/api/app/search-post-detail",
        json={
            "account_id": account_id,
            "post_url": "https://www.xiaohongshu.com/explore/note-1",
        },
    )
    assert response.status_code == 200
    detail = response.json()["detail"]
    assert detail["post_id"] == "note-1"
    assert detail["title"] == "完整正文"
    assert detail["content"] == "完整正文"
    assert detail["topics"] == ["新加坡", "酒店"]
    assert detail["image_urls"] == ["https://cdn.example.com/1.jpg"]
    assert detail["video_url"] == "https://cdn.example.com/1.mp4"
    assert detail["worker_cookie_id"]


def test_app_search_post_detail_retries_multiple_xsec_sources(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    account_id = create_primary_account(client, name="brand-main")
    create_worker_cookie(client, "worker-search", ["worker_search"])
    called_urls: list[str] = []

    class FakeContentApi:
        def get_note_info(self, url, cookies_str, proxies=None):
            called_urls.append(url)
            if "xsec_source=pc_feed" not in url:
                return False, "失败", None
            return True, "成功", {
                "data": {
                    "items": [
                        {
                            "id": "note-1",
                            "url": "https://www.xiaohongshu.com/explore/note-1",
                            "note_card": {
                                "type": "normal",
                                "user": {"user_id": "user-1", "nickname": "作者A"},
                                "title": "帖子A",
                                "desc": "正文A",
                                "interact_info": {},
                                "image_list": [],
                            },
                        }
                    ]
                }
            }

    monkeypatch.setattr(main, "get_pc_content_api", lambda: FakeContentApi())

    response = client.post(
        "/api/app/search-post-detail",
        json={
            "account_id": account_id,
            "post_url": "https://www.xiaohongshu.com/explore/note-1?xsec_token=token-1&xsec_source=pc_search",
        },
    )
    assert response.status_code == 200
    assert len(called_urls) == 3
    assert called_urls[0].endswith("xsec_source=pc_search")
    assert called_urls[1].endswith("xsec_source=pc_user")
    assert called_urls[2].endswith("xsec_source=pc_feed")


def test_app_search_post_detail_supports_basic_info_and_desc_extra(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    account_id = create_primary_account(client, name="brand-main")
    create_worker_cookie(client, "worker-search", ["worker_search"])

    class FakeContentApi:
        def get_note_info(self, url, cookies_str, proxies=None):
            return True, "成功", {
                "data": {
                    "items": [
                        {
                            "id": "note-2",
                            "url": "https://www.xiaohongshu.com/explore/note-2",
                            "basic_info": {"desc": "basic_info 正文"},
                            "body_topic_list": [{"name": "城市漫步"}],
                            "note_card": {
                                "type": "normal",
                                "user": {"user_id": "user-2", "nickname": "作者B"},
                                "title": "",
                                "desc": "",
                                "desc_extra": [{"topic_name": "酒店推荐"}],
                                "interact_info": {},
                                "image_list": [],
                                "time": 1710000000000,
                            },
                        }
                    ]
                }
            }

    monkeypatch.setattr(main, "get_pc_content_api", lambda: FakeContentApi())

    response = client.post(
        "/api/app/search-post-detail",
        json={
            "account_id": account_id,
            "post_url": "https://www.xiaohongshu.com/explore/note-2",
        },
    )
    assert response.status_code == 200
    detail = response.json()["detail"]
    assert detail["content"] == "basic_info 正文"
    assert detail["title"] == "basic_info 正文"
    assert detail["topics"] == ["酒店推荐", "城市漫步"]


def test_app_search_post_detail_falls_back_to_primary_cookie_when_worker_returns_empty_items(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    account_id = create_primary_account(client, name="brand-main")
    worker_id = create_worker_cookie(client, "worker-search", ["worker_search"])

    with get_session_factory()() as session:
        worker = session.get(Account, worker_id)
        assert worker is not None
        worker.cookies = "worker-cookie"
        account = session.get(Account, account_id)
        assert account is not None
        account.cookies = "primary-cookie"
        session.commit()

    class FakeContentApi:
        def get_note_info(self, url, cookies_str, proxies=None):
            if cookies_str == "worker-cookie":
                return True, "成功", {"success": True, "data": {"items": []}}
            return True, "成功", {
                "success": True,
                "data": {
                    "items": [
                        {
                            "id": "note-1",
                            "note_card": {
                                "title": "主号详情",
                                "desc": "正文",
                                "user": {"nickname": "作者A"},
                                "interact_info": {"liked_count": 1, "comment_count": 2, "collected_count": 3},
                                "image_list": [],
                            },
                        }
                    ]
                },
            }

    monkeypatch.setattr(main, "get_pc_content_api", lambda: FakeContentApi())
    monkeypatch.setattr(main, "validate_cookie", lambda account: (True, "成功"))

    response = client.post(
        "/api/app/search-post-detail",
        json={
            "account_id": account_id,
            "post_url": "https://www.xiaohongshu.com/explore/note-1?xsec_token=token-1&xsec_source=pc_user",
        },
    )
    assert response.status_code == 200
    assert response.json()["detail"]["title"] == "主号详情"


def test_app_sms_login_flow_creates_primary_account(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    class FakeLoginApi:
        def generate_init_cookies(self):
            return {"a1": "a1-token", "web_session": "session-before"}

        def send_phone_code(self, phone, cookies, zone="86"):
            assert phone == "13800138000"
            assert zone == "86"
            return True, "验证码已发送", {"ok": True}

        def login_by_phone(self, phone, code, cookies, zone="86"):
            assert code == "123456"
            cookies["web_session"] = "session-after"
            cookies["gid"] = "gid-1"
            return True, "登录成功", {"cookies": cookies}

        def get_user_info(self, cookies):
            return True, {"nickname": "测试账号", "red_id": "red-1", "user_id": "uid-1"}, cookies

        def cookies_to_str(self, cookies):
            return "; ".join(f"{k}={v}" for k, v in cookies.items())

    monkeypatch.setattr(main, "get_pc_login_api", lambda: FakeLoginApi())

    request_response = client.post(
        "/api/app/auth/request-sms-code",
        json={"phone": "13800138000", "zone": "86"},
    )
    assert request_response.status_code == 200
    login_session_id = request_response.json()["login_session_id"]

    login_response = client.post(
        "/api/app/auth/login-with-sms",
        json={
            "login_session_id": login_session_id,
            "phone": "13800138000",
            "code": "123456",
            "zone": "86",
            "device_id": "android-001",
        },
    )
    assert login_response.status_code == 200
    body = login_response.json()
    assert body["success"] is True
    assert body["account"]["nickname"] == "测试账号"
    assert body["account"]["user_uid"] == "uid-1"
    assert "web_session=session-after" in body["cookies"]
    assert login_session_id not in main.LOGIN_SESSION_STORE


def test_app_sms_login_flow_reuses_primary_account_by_user_uid(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    account_id = create_primary_account(client, name="测试账号")

    class FakeLoginApi:
        def generate_init_cookies(self):
            return {"a1": "a1-token", "web_session": "session-before"}

        def send_phone_code(self, phone, cookies, zone="86"):
            return True, "验证码已发送", {"ok": True}

        def login_by_phone(self, phone, code, cookies, zone="86"):
            cookies["web_session"] = "session-after"
            return True, "登录成功", {"cookies": cookies}

        def get_user_info(self, cookies):
            return True, {"nickname": "测试账号", "red_id": "red-1", "user_id": "uid-1"}, cookies

        def cookies_to_str(self, cookies):
            return "; ".join(f"{k}={v}" for k, v in cookies.items())

    monkeypatch.setattr(main, "get_pc_login_api", lambda: FakeLoginApi())

    request_response = client.post(
        "/api/app/auth/request-sms-code",
        json={"phone": "13800138000", "zone": "86"},
    )
    login_session_id = request_response.json()["login_session_id"]

    login_response = client.post(
        "/api/app/auth/login-with-sms",
        json={
            "login_session_id": login_session_id,
            "phone": "13800138000",
            "code": "123456",
            "zone": "86",
            "device_id": "android-001",
        },
    )
    assert login_response.status_code == 200
    body = login_response.json()
    assert body["account"]["id"] == account_id
    assert body["account"]["user_uid"] == "uid-1"
    assert body["account"]["bound_device_id"] == "android-001"

    with get_session_factory()() as session:
        accounts = session.execute(select(Account).where(Account.account_type == "primary")).scalars().all()
        assert len(accounts) == 1


def test_app_sms_login_reuses_legacy_primary_account_and_publish_task_remains_claimable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    account_id = create_primary_account(client, name="测试账号", bound_device_id="android-001")
    client.post(
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
    with get_session_factory()() as session:
        account = session.get(Account, account_id)
        assert account is not None
        account.status = "invalid"
        session.commit()

    class FakeLoginApi:
        def generate_init_cookies(self):
            return {"a1": "a1-token", "web_session": "session-before"}

        def send_phone_code(self, phone, cookies, zone="86"):
            return True, "验证码已发送", {"ok": True}

        def login_by_phone(self, phone, code, cookies, zone="86"):
            cookies["web_session"] = "session-after"
            return True, "登录成功", {"cookies": cookies}

        def get_user_info(self, cookies):
            return True, {"nickname": "测试账号", "red_id": "red-1", "user_id": "uid-1"}, cookies

        def cookies_to_str(self, cookies):
            return "; ".join(f"{k}={v}" for k, v in cookies.items())

    monkeypatch.setattr(main, "get_pc_login_api", lambda: FakeLoginApi())

    request_response = client.post(
        "/api/app/auth/request-sms-code",
        json={"phone": "13800138000", "zone": "86"},
    )
    login_session_id = request_response.json()["login_session_id"]
    login_response = client.post(
        "/api/app/auth/login-with-sms",
        json={
            "login_session_id": login_session_id,
            "phone": "13800138000",
            "code": "123456",
            "zone": "86",
            "device_id": "android-001",
        },
    )
    assert login_response.status_code == 200
    assert login_response.json()["account"]["id"] == account_id

    claim_response = client.get("/api/app/publish-tasks/next", params={"device_id": "android-001", "app_instance_id": "app-1"})
    assert claim_response.status_code == 200
    assert claim_response.json()["task"] is not None


def test_worker_sms_login_flow_creates_worker_cookie(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    class FakeLoginApi:
        def generate_init_cookies(self):
            return {"a1": "a1-token", "web_session": "session-before"}

        def send_phone_code(self, phone, cookies, zone="86"):
            assert phone == "13800138001"
            return True, "验证码已发送", {"ok": True}

        def login_by_phone(self, phone, code, cookies, zone="86"):
            assert code == "654321"
            cookies["web_session"] = "session-after"
            return True, "登录成功", {"cookies": cookies}

        def get_user_info(self, cookies):
            return True, {"nickname": "小号测试"}, cookies

        def cookies_to_str(self, cookies):
            return "; ".join(f"{k}={v}" for k, v in cookies.items())

    monkeypatch.setattr(main, "get_pc_login_api", lambda: FakeLoginApi())

    request_response = client.post(
        "/api/cookie-workers/auth/request-sms-code",
        json={
            "phone": "13800138001",
            "zone": "86",
            "name": "",
            "group_name": "brand_a",
            "usage_tags": ["worker_search"],
            "remark": "sms",
        },
    )
    assert request_response.status_code == 200
    login_session_id = request_response.json()["login_session_id"]

    login_response = client.post(
        "/api/cookie-workers/auth/login-with-sms",
        json={
            "login_session_id": login_session_id,
            "phone": "13800138001",
            "code": "654321",
            "zone": "86",
            "name": "",
            "group_name": "brand_a",
            "usage_tags": ["worker_search"],
            "remark": "sms",
        },
    )
    assert login_response.status_code == 200
    body = login_response.json()
    assert body["success"] is True
    assert body["worker_cookie"]["account_type"] == "worker"
    assert body["worker_cookie"]["nickname"] == "小号测试"
    assert login_session_id not in main.LOGIN_SESSION_STORE


def test_worker_qrcode_login_flow_creates_worker_cookie(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    class FakeLoginApi:
        def generate_init_cookies(self):
            return {"a1": "a1-token", "web_session": "session-before"}

        def generate_qrcode(self, cookies):
            return True, "成功", {
                "cookies": cookies,
                "qr_id": "qr-1",
                "code": "code-1",
                "qr_url": "https://example.com/qr-1",
            }

        def check_qrcode_status(self, qr_id, code, cookies):
            cookies["web_session"] = "session-after"
            return True, "验证成功", cookies

        def get_user_info(self, cookies):
            return True, {"nickname": "扫码小号"}, cookies

        def cookies_to_str(self, cookies):
            return "; ".join(f"{k}={v}" for k, v in cookies.items())

    monkeypatch.setattr(main, "get_pc_login_api", lambda: FakeLoginApi())

    request_response = client.post(
        "/api/cookie-workers/auth/request-qrcode",
        json={
            "name": "扫码小号",
            "group_name": "brand_b",
            "usage_tags": ["worker_analytics"],
            "remark": "qr",
        },
    )
    assert request_response.status_code == 200
    body = request_response.json()
    assert body["qr_url"] == "https://example.com/qr-1"
    assert body["qr_data_url"].startswith("data:image/svg+xml;base64,")
    login_session_id = body["login_session_id"]

    check_response = client.post(
        "/api/cookie-workers/auth/check-qrcode",
        json={
            "login_session_id": login_session_id,
            "name": "扫码小号",
            "group_name": "brand_b",
            "usage_tags": ["worker_analytics"],
            "remark": "qr",
        },
    )
    assert check_response.status_code == 200
    check_body = check_response.json()
    assert check_body["success"] is True
    assert check_body["worker_cookie"]["account_type"] == "worker"
    assert check_body["worker_cookie"]["name"] == "扫码小号"
    assert login_session_id not in main.LOGIN_SESSION_STORE


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


def test_app_can_execute_publish_task_via_backend_publish_api(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    account_id = create_primary_account(client, bound_device_id="android-001")
    response = client.post(
        "/api/publish-tasks",
        json={
            "account_id": account_id,
            "title": "Title",
            "desc": "Body",
            "topics": ["tag1", "tag2"],
            "media_type": "image",
            "media_urls": ["https://example.com/a.jpg", "https://example.com/b.jpg"],
            "review_status": "approved",
        },
    )
    task_id = response.json()["task"]["id"]
    claim = client.get("/api/app/publish-tasks/next", params={"device_id": "android-001", "app_instance_id": "app-1"})
    assert claim.status_code == 200

    downloaded: list[str] = []

    class FakeCreatorApi:
        def post_note(self, note_info, cookies_str):
            assert cookies_str == "a" * 32
            assert note_info["title"] == "Title"
            assert note_info["desc"] == "Body"
            assert note_info["topics"] == ["tag1", "tag2"]
            assert note_info["media_type"] == "image"
            assert note_info["images"] == [b"image-a", b"image-b"]
            return True, "成功", {"data": {"note_id": "post-1", "note_url": "https://www.xiaohongshu.com/explore/post-1"}}

    monkeypatch.setattr(main, "download_media_bytes", lambda url: downloaded.append(url) or (b"image-a" if url.endswith("a.jpg") else b"image-b"))
    monkeypatch.setattr(main, "get_creator_api", lambda: FakeCreatorApi())

    result = client.post(
        f"/api/app/publish-tasks/{task_id}/execute",
        json={"device_id": "android-001", "app_instance_id": "app-1"},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["task"]["task_status"] == "success"
    assert body["task"]["published_post_id"] == "post-1"
    assert body["task"]["published_post_url"] == "https://www.xiaohongshu.com/explore/post-1"
    assert downloaded == ["https://example.com/a.jpg", "https://example.com/b.jpg"]


def test_app_execute_publish_task_marks_failure_when_publish_api_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch):
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
    claim = client.get("/api/app/publish-tasks/next", params={"device_id": "android-001", "app_instance_id": "app-1"})
    assert claim.status_code == 200

    class FakeCreatorApi:
        def post_note(self, note_info, cookies_str):
            return False, "发布失败", {}

    monkeypatch.setattr(main, "download_media_bytes", lambda url: b"image-a")
    monkeypatch.setattr(main, "get_creator_api", lambda: FakeCreatorApi())

    result = client.post(
        f"/api/app/publish-tasks/{task_id}/execute",
        json={"device_id": "android-001", "app_instance_id": "app-1"},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["task"]["task_status"] == "failed"
    assert body["task"]["last_error"] == "发布失败"


def test_app_execute_publish_task_allows_repeat_fetch_after_success(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    account_id = create_primary_account(client, bound_device_id="android-001")
    response = client.post(
        "/api/publish-tasks",
        json={
            "account_id": account_id,
            "title": "Repeat",
            "desc": "Body",
            "media_type": "image",
            "media_urls": ["https://example.com/a.jpg"],
            "review_status": "approved",
        },
    )
    task_id = response.json()["task"]["id"]
    claim = client.get("/api/app/publish-tasks/next", params={"device_id": "android-001", "app_instance_id": "app-1"})
    assert claim.status_code == 200

    class FakeCreatorApi:
        def post_note(self, note_info, cookies_str):
            return True, "成功", {"data": {"note_id": "post-repeat", "note_url": "https://www.xiaohongshu.com/explore/post-repeat"}}

    monkeypatch.setattr(main, "download_media_bytes", lambda url: b"image-a")
    monkeypatch.setattr(main, "get_creator_api", lambda: FakeCreatorApi())

    first = client.post(
        f"/api/app/publish-tasks/{task_id}/execute",
        json={"device_id": "android-001", "app_instance_id": "app-1"},
    )
    assert first.status_code == 200
    assert first.json()["task"]["task_status"] == "success"

    second = client.post(
        f"/api/app/publish-tasks/{task_id}/execute",
        json={"device_id": "android-001", "app_instance_id": "app-1"},
    )
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["task"]["task_status"] == "success"
    assert second.json()["task"]["published_post_id"] == "post-repeat"


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


def test_publish_claim_returns_existing_claim_for_same_device(client: TestClient):
    account_id = create_primary_account(client, bound_device_id="android-001")
    response = client.post(
        "/api/publish-tasks",
        json={
            "account_id": account_id,
            "title": "Existing Claim",
            "desc": "Body",
            "media_type": "image",
            "media_urls": ["https://example.com/a.jpg"],
            "review_status": "approved",
        },
    )
    task_id = response.json()["task"]["id"]

    first_claim = client.get(
        "/api/app/publish-tasks/next",
        params={"device_id": "android-001", "app_instance_id": "app-1"},
    )
    assert first_claim.status_code == 200
    assert first_claim.json()["task"]["id"] == task_id

    second_claim = client.get(
        "/api/app/publish-tasks/next",
        params={"device_id": "android-001", "app_instance_id": "app-1"},
    )
    assert second_claim.status_code == 200
    assert second_claim.json()["task"]["id"] == task_id


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


def test_search_claim_does_not_block_publish_claim_for_same_device(client: TestClient):
    account_id = create_primary_account(client, bound_device_id="android-001")
    create_worker_cookie(client, "worker-search", ["worker_search"])

    publish_response = client.post(
        "/api/publish-tasks",
        json={
            "account_id": account_id,
            "title": "Publish A",
            "desc": "Body",
            "media_type": "image",
            "media_urls": ["https://example.com/a.jpg"],
            "review_status": "approved",
        },
    )
    publish_task_id = publish_response.json()["task"]["id"]

    client.post("/api/search-tasks", json={"keyword": "A", "group_name": "brand_a"})
    search_claim = client.get("/api/app/search-tasks/next", params={"device_id": "android-001"})
    assert search_claim.status_code == 200
    assert search_claim.json()["task"] is not None

    publish_claim = client.get(
        "/api/app/publish-tasks/next",
        params={"device_id": "android-001", "app_instance_id": "app-1"},
    )
    assert publish_claim.status_code == 200
    assert publish_claim.json()["task"]["id"] == publish_task_id


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


def test_app_can_create_and_view_search_task_detail(client: TestClient):
    worker_id = create_worker_cookie(client, "worker-search", ["worker_search"])
    response = client.post(
        "/api/app/search-tasks",
        json={
            "keyword": "新加坡酒店",
            "require_num": 10,
            "device_id": "android-001",
            "app_instance_id": "app-1",
        },
    )
    assert response.status_code == 200
    task_id = response.json()["task"]["id"]

    claim = client.get("/api/app/search-tasks/next", params={"device_id": "android-001"})
    assert claim.status_code == 200
    assert claim.json()["task"]["id"] == task_id

    payload = {
        "device_id": "android-001",
        "app_instance_id": "app-1",
        "result_id": "app-search-result-1",
        "worker_cookie_id": worker_id,
        "partial_success": False,
        "items": [
            {
                "post_id": "note-app-1",
                "post_url": "https://www.xiaohongshu.com/explore/note-app-1",
                "title": "App 创建任务结果",
                "username": "作者",
                "user_id": "user-app-1",
                "content_preview": "正文摘要",
                "content": "完整正文",
                "note_type": "video",
                "topics": ["新加坡", "酒店"],
                "image_urls": ["https://cdn.example.com/1.jpg"],
                "video_url": "https://cdn.example.com/1.mp4",
                "video_cover_url": "https://cdn.example.com/cover.jpg",
            }
        ],
        "error_message": "",
    }
    result = client.post(f"/api/app/search-tasks/{task_id}/result", json=payload)
    assert result.status_code == 200

    list_response = client.get("/api/app/search-tasks")
    assert list_response.status_code == 200
    assert list_response.json()["tasks"][0]["post_count"] == 1

    detail_response = client.get(f"/api/app/search-tasks/{task_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["post_count"] == 1
    assert detail["results"][0]["post_id"] == "note-app-1"
    assert detail["results"][0]["content"] == "完整正文"
    assert detail["results"][0]["topics"] == ["新加坡", "酒店"]
    assert detail["results"][0]["image_urls"] == ["https://cdn.example.com/1.jpg"]
    assert detail["results"][0]["video_url"] == "https://cdn.example.com/1.mp4"


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
