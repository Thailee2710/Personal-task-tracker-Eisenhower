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
    get_weekly_plan,
    list_energy_suggestions,
    move_task,
    set_weekly_capacity,
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
        energy_level="high",
    )

    task = get_task(db_path, task_id)
    assert task["title"] == "Viết proposal khách hàng"
    assert task["quadrant"] == "q2"
    assert task["duration_minutes"] == 90
    assert task["energy_level"] == "high"
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


def test_weekly_plan_sums_capacity_task_time_and_quadrants(tmp_path):
    db_path = tmp_path / "tasks.sqlite"
    init_db(db_path)
    create_task(db_path, title="Deep Q2", quadrant="q2", due_date="2026-06-03", duration_minutes=120)
    create_task(db_path, title="Fire Q1", quadrant="q1", due_date="2026-06-04", duration_minutes=45)
    create_task(db_path, title="Outside week", quadrant="q4", due_date="2026-06-12", duration_minutes=999)
    done_id = create_task(db_path, title="Done in week", quadrant="q3", due_date="2026-06-05", duration_minutes=30)
    delete_id = create_task(db_path, title="Deleted in week", quadrant="q2", due_date="2026-06-06", duration_minutes=30)
    toggle_task(db_path, done_id, done=True)
    delete_task(db_path, delete_id)
    set_weekly_capacity(
        db_path,
        week_start="2026-06-01",
        daily_minutes={"2026-06-01": 60, "2026-06-02": 120, "2026-06-03": 180},
    )

    plan = get_weekly_plan(db_path, week_start="2026-06-01")

    assert plan["week_start"] == "2026-06-01"
    assert plan["week_end"] == "2026-06-07"
    assert plan["required_minutes"] == 165
    assert plan["available_minutes"] == 360
    assert plan["buffer_minutes"] == 195
    assert plan["quadrant_minutes"] == {"q1": 45, "q2": 120, "q3": 0, "q4": 0}
    assert [task["title"] for task in plan["tasks_by_day"]["2026-06-03"]] == ["Deep Q2"]


def test_weekly_plan_surfaces_q2_focus_and_urgent_risk(tmp_path):
    db_path = tmp_path / "tasks.sqlite"
    init_db(db_path)
    create_task(db_path, title="Q2 gần hạn", quadrant="q2", due_date="2026-06-02", duration_minutes=60)
    create_task(db_path, title="Q2 cuối tuần", quadrant="q2", due_date="2026-06-07", duration_minutes=90)
    create_task(db_path, title="Q1 không phải focus", quadrant="q1", due_date="2026-06-02", duration_minutes=30)

    plan = get_weekly_plan(db_path, week_start="2026-06-01")

    assert [task["title"] for task in plan["q2_focus_tasks"]] == ["Q2 gần hạn", "Q2 cuối tuần"]
    assert plan["q2_minutes"] == 150
    assert plan["q2_risk_count"] == 1
    assert plan["q2_focus_tasks"][0]["q2_risk"] is True


def test_energy_suggestions_prioritize_matching_unfinished_tasks(tmp_path):
    db_path = tmp_path / "tasks.sqlite"
    init_db(db_path)
    create_task(db_path, title="Low admin", quadrant="q3", duration_minutes=15, energy_level="low")
    create_task(db_path, title="Deep work", quadrant="q2", duration_minutes=120, energy_level="high")
    create_task(db_path, title="Medium task", quadrant="q1", duration_minutes=60, energy_level="medium")
    done_id = create_task(db_path, title="Done low", quadrant="q3", duration_minutes=10, energy_level="low")
    toggle_task(db_path, done_id, done=True)

    low = list_energy_suggestions(db_path, energy_level="low")
    high = list_energy_suggestions(db_path, energy_level="high")

    assert [task["title"] for task in low] == ["Low admin"]
    assert [task["title"] for task in high] == ["Deep work"]
