from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Quadrant:
    key: str
    title: str
    subtitle: str
    important: bool
    urgent: bool


QUADRANTS: dict[str, Quadrant] = {
    "q1": Quadrant("q1", "Q1 — Làm ngay", "Quan trọng + khẩn cấp", True, True),
    "q2": Quadrant("q2", "Q2 — Lên lịch", "Quan trọng + không khẩn cấp", True, False),
    "q3": Quadrant("q3", "Q3 — Ủy quyền / xử lý nhanh", "Không quan trọng + khẩn cấp", False, True),
    "q4": Quadrant("q4", "Q4 — Loại bỏ / Backlog thấp", "Không quan trọng + không khẩn cấp", False, False),
}


def classify_quadrant(*, important: bool, urgent: bool) -> str:
    if important and urgent:
        return "q1"
    if important and not urgent:
        return "q2"
    if not important and urgent:
        return "q3"
    return "q4"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                quadrant TEXT NOT NULL,
                due_date TEXT NOT NULL DEFAULT '',
                duration_minutes INTEGER NOT NULL DEFAULT 0,
                done INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK (quadrant IN ('q1', 'q2', 'q3', 'q4'))
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_quadrant_done_updated
                ON tasks(quadrant, done, updated_at DESC);
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
        if "duration_minutes" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN duration_minutes INTEGER NOT NULL DEFAULT 0")
        if "deleted_at" not in columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN deleted_at TEXT NOT NULL DEFAULT ''")


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not password:
        raise ValueError("Password must not be empty")
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"pbkdf2_sha256$200000${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        ).hex()
        return hmac.compare_digest(expected, digest_hex)
    except Exception:
        return False


def ensure_admin_user(db_path: str | Path, username: str, password: str) -> None:
    if not username:
        raise ValueError("Admin username must not be empty")
    with connect(db_path) as conn:
        existing_count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        if existing_count == 0:
            conn.execute(
                "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, hash_password(password), now_iso()),
            )


def user_exists(db_path: str | Path, username: str) -> bool:
    with connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
    return row is not None


def update_user_credentials(
    db_path: str | Path,
    *,
    current_username: str,
    new_username: str,
    new_password: str,
) -> None:
    new_username = new_username.strip()
    if not new_username:
        raise ValueError("Username must not be empty")
    if not new_password:
        raise ValueError("Password must not be empty")
    with connect(db_path) as conn:
        user = conn.execute("SELECT id FROM users WHERE username = ?", (current_username,)).fetchone()
        if user is None:
            raise ValueError("Current user does not exist")
        duplicate = conn.execute(
            "SELECT id FROM users WHERE username = ? AND id != ?",
            (new_username, user["id"]),
        ).fetchone()
        if duplicate is not None:
            raise ValueError("Username already exists")
        conn.execute(
            "UPDATE users SET username = ?, password_hash = ? WHERE id = ?",
            (new_username, hash_password(new_password), user["id"]),
        )


def authenticate(db_path: str | Path, username: str, password: str) -> bool:
    with connect(db_path) as conn:
        user = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
    return bool(user and verify_password(password, user["password_hash"]))


def row_to_task(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data["done"] = bool(data["done"])
    if data.get("deleted_at"):
        data["status_label"] = "Đã xoá"
    elif data["done"]:
        data["status_label"] = "Đã hoàn thành"
    elif data.get("quadrant") == "q4":
        data["status_label"] = "Backlog"
    else:
        data["status_label"] = "Đang làm"
    return data


def validate_quadrant(quadrant: str) -> None:
    if quadrant not in QUADRANTS:
        raise ValueError(f"Invalid quadrant: {quadrant}")


def normalize_duration_minutes(value: int | str | None) -> int:
    if value in (None, ""):
        return 0
    try:
        minutes = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Duration must be a number of minutes") from exc
    if minutes < 0:
        raise ValueError("Duration must not be negative")
    return minutes


def create_task(
    db_path: str | Path,
    *,
    title: str,
    quadrant: str,
    description: str = "",
    due_date: str = "",
    duration_minutes: int | str | None = 0,
) -> int:
    validate_quadrant(quadrant)
    title = title.strip()
    if not title:
        raise ValueError("Title must not be empty")
    duration = normalize_duration_minutes(duration_minutes)
    timestamp = now_iso()
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks(title, description, quadrant, due_date, duration_minutes, done, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (title, description.strip(), quadrant, due_date.strip(), duration, timestamp, timestamp),
        )
        return int(cur.lastrowid)


def get_task(db_path: str | Path, task_id: int) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ? AND deleted_at = ''", (task_id,)).fetchone()
    return row_to_task(row)


def list_tasks_by_quadrant(db_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in QUADRANTS}
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks
            WHERE deleted_at = ''
            ORDER BY done ASC, due_date = '' ASC, due_date ASC, updated_at DESC, id DESC
            """
        ).fetchall()
    for row in rows:
        task = row_to_task(row)
        assert task is not None
        grouped[task["quadrant"]].append(task)
    return grouped


def list_calendar_tasks(db_path: str | Path, *, start_date: str, end_date: str) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks
            WHERE deleted_at = ''
              AND due_date != ''
              AND due_date >= ?
              AND due_date <= ?
            ORDER BY due_date ASC, done ASC, updated_at DESC, id DESC
            """,
            (start_date, end_date),
        ).fetchall()
    return [task for row in rows if (task := row_to_task(row)) is not None]


def list_task_history(db_path: str | Path) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
    return [task for row in rows if (task := row_to_task(row)) is not None]


def list_due_notifications(db_path: str | Path, *, today: str | date | None = None) -> dict[str, list[dict[str, Any]]]:
    if today is None:
        current = date.today()
    elif isinstance(today, date):
        current = today
    else:
        current = datetime.strptime(today, "%Y-%m-%d").date()
    tomorrow = current + timedelta(days=1)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks
            WHERE deleted_at = ''
              AND done = 0
              AND due_date != ''
              AND due_date <= ?
            ORDER BY due_date ASC, updated_at DESC, id DESC
            """,
            (tomorrow.isoformat(),),
        ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {"overdue": [], "today": [], "tomorrow": []}
    for row in rows:
        task = row_to_task(row)
        if task is None:
            continue
        if task["due_date"] < current.isoformat():
            grouped["overdue"].append(task)
        elif task["due_date"] == current.isoformat():
            grouped["today"].append(task)
        elif task["due_date"] == tomorrow.isoformat():
            grouped["tomorrow"].append(task)
    return grouped


def move_task(db_path: str | Path, task_id: int, quadrant: str) -> None:
    validate_quadrant(quadrant)
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE tasks SET quadrant = ?, updated_at = ? WHERE id = ? AND deleted_at = ''",
            (quadrant, now_iso(), task_id),
        )


def toggle_task(db_path: str | Path, task_id: int, *, done: bool) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE tasks SET done = ?, updated_at = ? WHERE id = ? AND deleted_at = ''",
            (1 if done else 0, now_iso(), task_id),
        )


def delete_task(db_path: str | Path, task_id: int) -> None:
    timestamp = now_iso()
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE tasks SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at = ''",
            (timestamp, timestamp, task_id),
        )
