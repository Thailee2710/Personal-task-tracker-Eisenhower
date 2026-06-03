import pytest

from app.core import (
    QUADRANTS,
    authenticate,
    classify_quadrant,
    create_task,
    delete_task,
    ensure_admin_user,
    get_task,
    init_db,
    list_calendar_tasks,
    list_due_notifications,
    list_task_history,
    list_tasks_by_quadrant,
    move_task,
    toggle_task,
    update_user_credentials,
)


def test_quadrants_have_eisenhower_labels():
    assert QUADRANTS["q1"].title == "Q1 — Làm ngay"
    assert QUADRANTS["q2"].title == "Q2 — Lên lịch"
    assert QUADRANTS["q3"].title == "Q3 — Ủy quyền / xử lý nhanh"
    assert QUADRANTS["q4"].title == "Q4 — Loại bỏ / Backlog thấp"


@pytest.mark.parametrize(
    ("important", "urgent", "expected"),
    [
        (True, True, "q1"),
        (True, False, "q2"),
        (False, True, "q3"),
        (False, False, "q4"),
    ],
)
def test_classify_quadrant_from_important_urgent_flags(important, urgent, expected):
    assert classify_quadrant(important=important, urgent=urgent) == expected


def test_create_list_move_toggle_delete_task(tmp_path):
    db_path = tmp_path / "tasks.sqlite"
    init_db(db_path)

    task_id = create_task(
        db_path,
        title="Viết proposal khách hàng",
        quadrant="q2",
        description="Chuẩn bị bản nháp đầu tiên",
        due_date="2026-06-05",
        duration_minutes=90,
    )

    task = get_task(db_path, task_id)
    assert task["title"] == "Viết proposal khách hàng"
    assert task["quadrant"] == "q2"
    assert task["duration_minutes"] == 90
    assert task["done"] is False

    grouped = list_tasks_by_quadrant(db_path)
    assert grouped["q2"][0]["id"] == task_id
    assert grouped["q1"] == []

    move_task(db_path, task_id, "q1")
    assert get_task(db_path, task_id)["quadrant"] == "q1"

    toggle_task(db_path, task_id, done=True)
    assert get_task(db_path, task_id)["done"] is True

    delete_task(db_path, task_id)
    assert get_task(db_path, task_id) is None


def test_invalid_quadrant_is_rejected(tmp_path):
    db_path = tmp_path / "tasks.sqlite"
    init_db(db_path)

    with pytest.raises(ValueError, match="Invalid quadrant"):
        create_task(db_path, title="bad", quadrant="q9")


def test_calendar_tasks_filter_by_deadline_range(tmp_path):
    db_path = tmp_path / "tasks.sqlite"
    init_db(db_path)
    create_task(db_path, title="Task trong tuần", quadrant="q2", due_date="2026-06-03")
    create_task(db_path, title="Task ngoài tuần", quadrant="q2", due_date="2026-06-20")
    create_task(db_path, title="Task không deadline", quadrant="q4")

    tasks = list_calendar_tasks(db_path, start_date="2026-06-01", end_date="2026-06-07")

    assert [task["title"] for task in tasks] == ["Task trong tuần"]


def test_history_includes_active_done_backlog_and_deleted_tasks(tmp_path):
    db_path = tmp_path / "tasks.sqlite"
    init_db(db_path)
    active_id = create_task(db_path, title="Task đang làm", quadrant="q1")
    done_id = create_task(db_path, title="Task đã hoàn thành", quadrant="q2")
    backlog_id = create_task(db_path, title="Task backlog", quadrant="q4")
    deleted_id = create_task(db_path, title="Task đã xoá", quadrant="q3")
    toggle_task(db_path, done_id, done=True)
    delete_task(db_path, deleted_id)

    dashboard = list_tasks_by_quadrant(db_path)
    assert "Task đã xoá" not in [task["title"] for tasks in dashboard.values() for task in tasks]

    history = list_task_history(db_path)
    by_title = {task["title"]: task for task in history}
    assert by_title["Task đang làm"]["status_label"] == "Đang làm"
    assert by_title["Task đã hoàn thành"]["status_label"] == "Đã hoàn thành"
    assert by_title["Task backlog"]["quadrant"] == "q4"
    assert by_title["Task đã xoá"]["status_label"] == "Đã xoá"
    assert get_task(db_path, active_id) is not None
    assert get_task(db_path, backlog_id) is not None


def test_update_user_credentials_changes_login_and_preserves_single_admin(tmp_path):
    db_path = tmp_path / "tasks.sqlite"
    init_db(db_path)
    ensure_admin_user(db_path, "admin", "old-pass")

    update_user_credentials(db_path, current_username="admin", new_username="thai", new_password="new-pass")

    assert authenticate(db_path, "thai", "new-pass") is True
    assert authenticate(db_path, "admin", "old-pass") is False
    ensure_admin_user(db_path, "admin", "old-pass")
    assert authenticate(db_path, "admin", "old-pass") is False


def test_due_notifications_classify_tomorrow_today_and_overdue(tmp_path):
    db_path = tmp_path / "tasks.sqlite"
    init_db(db_path)
    create_task(db_path, title="Hết hạn hôm qua", quadrant="q1", due_date="2026-06-02")
    create_task(db_path, title="Đến hạn hôm nay", quadrant="q2", due_date="2026-06-03")
    create_task(db_path, title="Sắp hết hạn mai", quadrant="q3", due_date="2026-06-04")
    create_task(db_path, title="Tương lai xa", quadrant="q4", due_date="2026-06-06")
    done_id = create_task(db_path, title="Đã xong hôm nay", quadrant="q2", due_date="2026-06-03")
    deleted_id = create_task(db_path, title="Đã xoá hôm nay", quadrant="q2", due_date="2026-06-03")
    toggle_task(db_path, done_id, done=True)
    delete_task(db_path, deleted_id)

    notifications = list_due_notifications(db_path, today="2026-06-03")

    assert [task["title"] for task in notifications["overdue"]] == ["Hết hạn hôm qua"]
    assert [task["title"] for task in notifications["today"]] == ["Đến hạn hôm nay"]
    assert [task["title"] for task in notifications["tomorrow"]] == ["Sắp hết hạn mai"]
