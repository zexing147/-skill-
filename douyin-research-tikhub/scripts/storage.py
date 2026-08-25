from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def unix_to_iso(value: int | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


class Storage:
    def __init__(self, output_dir: Path, provider: str = "tikhub") -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = output_dir
        self.provider = provider
        self.db_path = output_dir / "douyin-research.sqlite"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
          id INTEGER PRIMARY KEY, provider TEXT NOT NULL, sec_user_id TEXT NOT NULL,
          input_ref TEXT, profile_url TEXT, nickname TEXT, signature TEXT,
          follower_count INTEGER, following_count INTEGER, total_favorited INTEGER,
          aweme_count INTEGER, raw_json TEXT NOT NULL, fetched_at TEXT NOT NULL,
          UNIQUE(provider, sec_user_id)
        );
        CREATE TABLE IF NOT EXISTS videos (
          id INTEGER PRIMARY KEY, provider TEXT NOT NULL, platform_video_id TEXT NOT NULL,
          account_id INTEGER NOT NULL, description TEXT, published_at TEXT, video_url TEXT,
          duration_ms INTEGER, raw_json TEXT NOT NULL, first_seen_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL, UNIQUE(provider, platform_video_id),
          FOREIGN KEY(account_id) REFERENCES accounts(id)
        );
        CREATE TABLE IF NOT EXISTS video_metrics (
          id INTEGER PRIMARY KEY, video_id INTEGER NOT NULL, play_count INTEGER,
          like_count INTEGER, comment_count INTEGER, collect_count INTEGER,
          share_count INTEGER, captured_at TEXT NOT NULL,
          FOREIGN KEY(video_id) REFERENCES videos(id)
        );
        CREATE TABLE IF NOT EXISTS comments (
          id INTEGER PRIMARY KEY, provider TEXT NOT NULL, platform_comment_id TEXT NOT NULL,
          video_id INTEGER NOT NULL, parent_comment_id TEXT, author_platform_id TEXT,
          author_name TEXT, content TEXT, like_count INTEGER, reply_count INTEGER,
          published_at TEXT, raw_json TEXT NOT NULL, fetched_at TEXT NOT NULL,
          UNIQUE(provider, platform_comment_id), FOREIGN KEY(video_id) REFERENCES videos(id)
        );
        CREATE TABLE IF NOT EXISTS crawl_jobs (
          id TEXT PRIMARY KEY, provider TEXT NOT NULL, status TEXT NOT NULL,
          parameters_json TEXT NOT NULL, max_requests INTEGER NOT NULL,
          estimated_requests INTEGER NOT NULL, estimated_cost_usd REAL,
          actual_requests INTEGER NOT NULL DEFAULT 0, started_at TEXT NOT NULL,
          finished_at TEXT, stopped_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS api_usage (
          id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, operation TEXT NOT NULL,
          request_status TEXT NOT NULL, http_status INTEGER, error TEXT,
          occurred_at TEXT NOT NULL, FOREIGN KEY(job_id) REFERENCES crawl_jobs(id)
        );
        CREATE TABLE IF NOT EXISTS crawl_checkpoints (
          resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, target_limit INTEGER NOT NULL,
          cursor TEXT NOT NULL, saved_count INTEGER NOT NULL DEFAULT 0,
          completed INTEGER NOT NULL DEFAULT 0, source_exhausted INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(resource_type, resource_id)
        );
        """)
        self.conn.commit()

    def start_job(self, job_id: str, parameters: dict[str, Any], max_requests: int,
                  estimated_requests: int, estimated_cost: float) -> None:
        self.conn.execute(
            "INSERT INTO crawl_jobs VALUES (?, ?, 'running', ?, ?, ?, ?, 0, ?, NULL, NULL)",
            (job_id, self.provider, json.dumps(parameters, ensure_ascii=False), max_requests,
             estimated_requests, estimated_cost, utc_now()),
        )
        self.conn.commit()

    def finish_job(self, job_id: str, status: str, actual_requests: int,
                   stopped_reason: str | None) -> None:
        self.conn.execute(
            "UPDATE crawl_jobs SET status=?, actual_requests=?, finished_at=?, stopped_reason=? WHERE id=?",
            (status, actual_requests, utc_now(), stopped_reason, job_id),
        )
        self.conn.commit()

    def log_usage(self, job_id: str, event: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO api_usage(job_id, operation, request_status, http_status, error, occurred_at) VALUES(?,?,?,?,?,?)",
            (job_id, event["operation"], event["status"], event.get("http_status"),
             event.get("error"), utc_now()),
        )
        self.conn.commit()

    def upsert_account(self, row: dict[str, Any]) -> int:
        now = utc_now()
        self.conn.execute("""
        INSERT INTO accounts(provider, sec_user_id, input_ref, profile_url, nickname, signature,
          follower_count, following_count, total_favorited, aweme_count, raw_json, fetched_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(provider, sec_user_id) DO UPDATE SET input_ref=excluded.input_ref,
          profile_url=excluded.profile_url, nickname=excluded.nickname, signature=excluded.signature,
          follower_count=excluded.follower_count, following_count=excluded.following_count,
          total_favorited=excluded.total_favorited, aweme_count=excluded.aweme_count,
          raw_json=excluded.raw_json, fetched_at=excluded.fetched_at
        """, (self.provider, row["sec_user_id"], row["input_ref"], row["profile_url"], row["nickname"],
                row["signature"], row["follower_count"], row["following_count"],
                row["total_favorited"], row["aweme_count"],
                json.dumps(row["raw_json"], ensure_ascii=False), now))
        self.conn.commit()
        return int(self.conn.execute(
            "SELECT id FROM accounts WHERE provider=? AND sec_user_id=?",
            (self.provider, row["sec_user_id"])).fetchone()[0])

    def upsert_video(self, account_id: int, row: dict[str, Any]) -> int:
        now = utc_now()
        self.conn.execute("""
        INSERT INTO videos(provider, platform_video_id, account_id, description, published_at,
          video_url, duration_ms, raw_json, first_seen_at, last_seen_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(provider, platform_video_id) DO UPDATE SET account_id=excluded.account_id,
          description=excluded.description, published_at=excluded.published_at,
          video_url=excluded.video_url, duration_ms=excluded.duration_ms,
          raw_json=excluded.raw_json, last_seen_at=excluded.last_seen_at
        """, (self.provider, row["aweme_id"], account_id, row["description"], unix_to_iso(row["create_time"]),
                row["video_url"], row["duration_ms"],
                json.dumps(row["raw_json"], ensure_ascii=False), now, now))
        video_id = int(self.conn.execute(
            "SELECT id FROM videos WHERE provider=? AND platform_video_id=?",
            (self.provider, row["aweme_id"])).fetchone()[0])
        self.conn.execute("""
        INSERT INTO video_metrics(video_id, play_count, like_count, comment_count,
          collect_count, share_count, captured_at) VALUES(?,?,?,?,?,?,?)
        """, (video_id, row["play_count"], row["like_count"], row["comment_count"],
                row["collect_count"], row["share_count"], now))
        self.conn.commit()
        return video_id

    def upsert_comment(self, video_id: int, row: dict[str, Any]) -> None:
        now = utc_now()
        self.conn.execute("""
        INSERT INTO comments(provider, platform_comment_id, video_id, parent_comment_id,
          author_platform_id, author_name, content, like_count, reply_count, published_at,
          raw_json, fetched_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(provider, platform_comment_id) DO UPDATE SET
          parent_comment_id=excluded.parent_comment_id, author_platform_id=excluded.author_platform_id,
          author_name=excluded.author_name, content=excluded.content, like_count=excluded.like_count,
          reply_count=excluded.reply_count, raw_json=excluded.raw_json, fetched_at=excluded.fetched_at
        """, (self.provider, row["comment_id"], video_id, row["parent_comment_id"], row["author_id"],
                row["author_name"], row["content"], row["like_count"], row["reply_count"],
                unix_to_iso(row["create_time"]), json.dumps(row["raw_json"], ensure_ascii=False), now))
        self.conn.commit()

    def videos(self) -> list[tuple[int, str]]:
        return [(int(row[0]), str(row[1])) for row in self.conn.execute(
            "SELECT id, platform_video_id FROM videos WHERE provider=? ORDER BY id",
            (self.provider,))]

    def top_level_comments(self, video_id: int, limit: int) -> list[str]:
        return [str(row[0]) for row in self.conn.execute(
            "SELECT platform_comment_id FROM comments WHERE provider=? AND video_id=? "
            "AND parent_comment_id IS NULL ORDER BY id LIMIT ?",
            (self.provider, video_id, limit))]

    def checkpoint(self, resource_type: str, resource_id: str,
                   target_limit: int) -> tuple[str, int, bool, bool] | None:
        row = self.conn.execute(
            "SELECT cursor, saved_count, completed, source_exhausted FROM crawl_checkpoints "
            "WHERE resource_type=? AND resource_id=?",
            (resource_type, resource_id),
        ).fetchone()
        return (str(row[0]), int(row[1]), bool(row[2]), bool(row[3])) if row else None

    def save_checkpoint(self, resource_type: str, resource_id: str, target_limit: int,
                        cursor: str, saved_count: int, completed: bool,
                        source_exhausted: bool) -> None:
        self.conn.execute("""
        INSERT INTO crawl_checkpoints(resource_type, resource_id, target_limit, cursor,
          saved_count, completed, source_exhausted, updated_at) VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(resource_type, resource_id) DO UPDATE SET
          target_limit=excluded.target_limit, cursor=excluded.cursor, saved_count=excluded.saved_count,
          completed=excluded.completed, source_exhausted=excluded.source_exhausted,
          updated_at=excluded.updated_at
        """, (resource_type, resource_id, target_limit, cursor, saved_count,
                int(completed), int(source_exhausted), utc_now()))
        self.conn.commit()

    def clear_checkpoint(self, resource_type: str, resource_id: str,
                         target_limit: int) -> None:
        self.conn.execute(
            "DELETE FROM crawl_checkpoints WHERE resource_type=? AND resource_id=?",
            (resource_type, resource_id),
        )
        self.conn.commit()

    def export_csv(self) -> dict[str, int]:
        exports = {
            "accounts.csv": "SELECT * FROM accounts",
            "videos.csv": "SELECT * FROM videos",
            "video-metrics.csv": "SELECT * FROM video_metrics",
            "comments.csv": "SELECT * FROM comments",
            "api-usage.csv": "SELECT * FROM api_usage",
        }
        counts: dict[str, int] = {}
        for filename, query in exports.items():
            cursor = self.conn.execute(query)
            headers = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            with (self.output_dir / filename).open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                writer.writerows(rows)
            counts[filename] = len(rows)
        return counts

    def close(self) -> None:
        self.conn.close()
