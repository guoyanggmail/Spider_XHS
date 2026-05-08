from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from server.db import init_db, get_session_factory
from server.models import Account, PublishTask, SearchTask, SearchResult, AnalyticsSnapshot


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "datas"


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def import_accounts(session: Session, accounts_path: Path) -> None:
    accounts = load_json(accounts_path, [])
    for item in accounts:
        if session.get(Account, item.get("id", "")):
            continue
        session.add(
            Account(
                id=item.get("id"),
                account_type="primary",
                name=item.get("name") or "导入账号",
                nickname="",
                cookies=item.get("cookies") or "",
                cookie_preview=item.get("cookie_preview") or "",
                status=item.get("last_check_status") or "active",
                remark="imported from json",
            )
        )


def import_operations(session: Session, operations_path: Path) -> None:
    data = load_json(operations_path, {})
    for item in data.get("publish_tasks", []):
        if session.get(PublishTask, item.get("id", "")):
            continue
        session.add(
            PublishTask(
                id=item.get("id"),
                account_id=item.get("account_id"),
                title=item.get("title") or "",
                content=item.get("desc") or "",
                topics_json=item.get("topics") or [],
                location=item.get("location") or "",
                media_type=item.get("media_type") or "image",
                media_urls_json=item.get("media_names") or [],
                review_status="approved" if item.get("status") == "published" else "pending",
                task_status="success" if item.get("status") == "published" else "pending",
                last_error=item.get("last_error") or "",
            )
        )
    for item in data.get("search_monitors", []):
        if session.get(SearchTask, item.get("id", "")):
            continue
        session.add(
            SearchTask(
                id=item.get("id"),
                keyword=item.get("keyword") or "",
                group_name="",
                require_num=item.get("require_num") or 10,
                sort_type=str(item.get("sort_type_choice", "general")),
                note_type=str(item.get("note_type", "all")),
                time_range=str(item.get("note_time", "all")),
                interval_minutes=item.get("interval_minutes") or 120,
                enabled=item.get("enabled", True),
            )
        )
    for item in data.get("search_results", []):
        note = item.get("note") or {}
        if not note.get("note_id"):
            continue
        exists = session.query(SearchResult).filter_by(search_task_id=item.get("monitor_id"), post_id=note.get("note_id")).first()
        if exists:
            continue
        session.add(
            SearchResult(
                search_task_id=item.get("monitor_id"),
                result_id=item.get("id") or note.get("note_id"),
                worker_account_id=None,
                post_id=note.get("note_id"),
                post_url=note.get("note_url") or "",
                title=note.get("title") or "",
                content_preview=note.get("desc") or "",
                author_id=note.get("user_id") or "",
                author_name=note.get("nickname") or "",
                like_count=int(note.get("liked_count") or 0),
                comment_count=int(note.get("comment_count") or 0),
                collect_count=int(note.get("collected_count") or 0),
                raw_payload=note,
            )
        )
    for item in data.get("analytics_snapshots", []):
        if session.get(AnalyticsSnapshot, item.get("id", "")):
            continue
        profile = item.get("profile") or {}
        session.add(
            AnalyticsSnapshot(
                id=item.get("id"),
                analytics_task_id=None,
                result_id=item.get("id"),
                account_id=item.get("account_id"),
                worker_account_id=None,
                nickname=profile.get("nickname") or "",
                follower_count=int(profile.get("fans") or 0),
                liked_total=int(profile.get("interaction") or 0),
                post_total=len(item.get("recent_notes") or []),
                raw_payload=item,
            )
        )


def main() -> None:
    init_db()
    session_factory = get_session_factory()
    with session_factory() as session:
        import_accounts(session, DATA_DIR / "accounts.json")
        import_operations(session, DATA_DIR / "operations.json")
        session.commit()
    print("Import finished.")


if __name__ == "__main__":
    main()
