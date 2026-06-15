import stat
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path):
    db_path = tmp_path / "app.sqlite"
    app = create_app(
        db_path=db_path,
        admin_username="admin",
        admin_password="secret-pass",
        secret_key="test-secret-key",
    )
    return TestClient(app)


def test_templates_are_readable_by_service_user():
    template_dir = Path(__file__).resolve().parents[1] / "templates"
    unreadable = []
    for template in template_dir.glob("*.html"):
        mode = template.stat().st_mode
        if not mode & stat.S_IROTH:
            unreadable.append(template.name)
    assert unreadable == []


def test_project_signature_asset_is_readable_and_documented():
    root = Path(__file__).resolve().parents[1]
    signature = root / "static" / "signature.svg"
    icon = root / "static" / "project-icon.svg"
    readme = root / "README.md"

    assert signature.exists()
    assert signature.stat().st_mode & stat.S_IROTH
    assert "Project signature" in signature.read_text(encoding="utf-8")
    assert icon.exists()
    assert icon.stat().st_mode & stat.S_IROTH
    assert "Project icon" in icon.read_text(encoding="utf-8")
    assert "![Project signature](static/signature.svg)" in readme.read_text(encoding="utf-8")


def test_login_and_all_app_pages_use_shared_project_icon_and_stable_nav(tmp_path):
    client = make_client(tmp_path)

    login = client.get("/login")
    assert login.status_code == 200
    assert 'src="/static/project-icon.svg"' in login.text
    assert 'alt="Project icon"' in login.text
    assert 'src="/static/signature.svg"' not in login.text

    client.post("/login", data={"username": "admin", "password": "secret-pass"})
    pages = ["/", "/weekly-plan", "/calendar", "/notifications", "/history", "/settings"]
    expected_nav = ["Matrix", "Weekly Plan", "Calendar", "Notifications", "History", "Settings", "Đăng xuất admin"]
    for path in pages:
        response = client.get(path)
        assert response.status_code == 200
        assert 'src="/static/project-icon.svg"' in response.text
        assert 'alt="Project icon"' in response.text
        assert 'class="top-actions fixed-actions"' in response.text
        nav_start = response.text.index('<div class="top-actions fixed-actions">')
        nav_end = response.text.index("</div>", nav_start)
        nav = response.text[nav_start:nav_end]
        positions = [nav.index(label) for label in expected_nav]
        assert positions == sorted(positions), path


def test_dashboard_requires_login(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_logout_flow(tmp_path):
    client = make_client(tmp_path)

    bad = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401

    good = client.post("/login", data={"username": "admin", "password": "secret-pass"}, follow_redirects=False)
    assert good.status_code == 303
    assert good.headers["location"] == "/"

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Eisenhower Matrix" in dashboard.text

    logout = client.post("/logout", follow_redirects=False)
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"


def test_create_move_toggle_delete_task_over_http(tmp_path):
    client = make_client(tmp_path)
    client.post("/login", data={"username": "admin", "password": "secret-pass"})

    created = client.post(
        "/tasks",
        data={
            "title": "Gọi khách hàng A",
            "description": "Chốt lịch demo",
            "important": "on",
            "urgent": "on",
            "due_date": "2026-06-03",
            "duration_minutes": "45",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303

    dashboard = client.get("/")
    assert "Gọi khách hàng A" in dashboard.text
    assert "45 phút" in dashboard.text
    assert "Q1 — Làm ngay" in dashboard.text

    moved = client.post("/tasks/1/move", data={"quadrant": "q2"}, follow_redirects=False)
    assert moved.status_code == 303
    dashboard = client.get("/")
    assert "Q2 — Lên lịch" in dashboard.text

    toggled = client.post("/tasks/1/toggle", data={"done": "true"}, follow_redirects=False)
    assert toggled.status_code == 303
    dashboard = client.get("/")
    assert "task done" in dashboard.text

    deleted = client.post("/tasks/1/delete", follow_redirects=False)
    assert deleted.status_code == 303
    dashboard = client.get("/")
    assert "Gọi khách hàng A" not in dashboard.text


def test_dashboard_renders_inline_task_editor_and_updates_task_over_http(tmp_path):
    client = make_client(tmp_path)
    client.post("/login", data={"username": "admin", "password": "secret-pass"})
    client.post(
        "/tasks",
        data={
            "title": "Chuẩn bị brief",
            "description": "Bản đầu",
            "quadrant": "q2",
            "due_date": "2026-06-10",
            "duration_minutes": "60",
            "energy_level": "high",
        },
    )

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Sửa" in dashboard.text
    assert 'action="/tasks/1/edit"' in dashboard.text
    assert 'value="Chuẩn bị brief"' in dashboard.text
    assert "Bản đầu" in dashboard.text

    updated = client.post(
        "/tasks/1/edit",
        data={
            "title": "Chốt brief cuối",
            "description": "Đã thêm scope và deadline",
            "quadrant": "q1",
            "due_date": "2026-06-08",
            "duration_minutes": "30",
            "energy_level": "medium",
        },
        follow_redirects=False,
    )
    assert updated.status_code == 303
    assert updated.headers["location"] == "/"

    dashboard = client.get("/")
    assert "Chốt brief cuối" in dashboard.text
    assert "Đã thêm scope và deadline" in dashboard.text
    assert "2026-06-08" in dashboard.text
    assert "30 phút" in dashboard.text
    assert "Chuẩn bị brief" not in dashboard.text


def test_quadrant_plus_forms_create_task_directly_in_selected_quadrant(tmp_path):
    client = make_client(tmp_path)
    client.post("/login", data={"username": "admin", "password": "secret-pass"})

    dashboard = client.get("/")
    assert "Thêm nhanh Q1" in dashboard.text
    assert "Thêm nhanh Q2" in dashboard.text
    assert "Thêm nhanh Q3" in dashboard.text
    assert "Thêm nhanh Q4" in dashboard.text

    created = client.post(
        "/tasks",
        data={
            "title": "Trả lời tin nhắn gấp",
            "quadrant": "q3",
            "duration_minutes": "15",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303

    dashboard = client.get("/")
    assert "Trả lời tin nhắn gấp" in dashboard.text
    assert "15 phút" in dashboard.text
    assert "Q3 — Ủy quyền / xử lý nhanh" in dashboard.text


def test_calendar_page_supports_day_week_month_and_year_views(tmp_path):
    client = make_client(tmp_path)
    client.post("/login", data={"username": "admin", "password": "secret-pass"})
    client.post(
        "/tasks",
        data={"title": "Nộp báo cáo tháng", "quadrant": "q2", "due_date": "2026-06-15", "duration_minutes": "60"},
    )
    client.post(
        "/tasks",
        data={"title": "Họp tuần", "quadrant": "q1", "due_date": "2026-06-03", "duration_minutes": "30"},
    )

    day = client.get("/calendar?view=day&date=2026-06-15")
    assert day.status_code == 200
    assert "Calendar" in day.text
    assert "Ngày" in day.text
    assert "Nộp báo cáo tháng" in day.text
    assert "Họp tuần" not in day.text

    week = client.get("/calendar?view=week&date=2026-06-03")
    assert week.status_code == 200
    assert "Tuần" in week.text
    assert "Họp tuần" in week.text

    month = client.get("/calendar?view=month&date=2026-06-01")
    assert month.status_code == 200
    assert "Tháng" in month.text
    assert "Nộp báo cáo tháng" in month.text
    assert "Họp tuần" in month.text

    year = client.get("/calendar?view=year&date=2026-01-01")
    assert year.status_code == 200
    assert "Năm" in year.text
    assert "Nộp báo cáo tháng" in year.text
    assert "Họp tuần" in year.text


def test_history_page_lists_all_task_statuses(tmp_path):
    client = make_client(tmp_path)
    client.post("/login", data={"username": "admin", "password": "secret-pass"})
    client.post("/tasks", data={"title": "Task đang xử lý", "quadrant": "q1"})
    client.post("/tasks", data={"title": "Task backlog", "quadrant": "q4"})
    client.post("/tasks", data={"title": "Task xong", "quadrant": "q2"})
    client.post("/tasks/3/toggle", data={"done": "true"})
    client.post("/tasks", data={"title": "Task đã xoá khỏi dashboard", "quadrant": "q3"})
    client.post("/tasks/4/delete")

    dashboard = client.get("/")
    assert "Task đã xoá khỏi dashboard" not in dashboard.text

    history = client.get("/history")
    assert history.status_code == 200
    assert "History" in history.text
    assert "Task đang xử lý" in history.text
    assert "Đang làm" in history.text
    assert "Task backlog" in history.text
    assert "Backlog" in history.text
    assert "Task xong" in history.text
    assert "Đã hoàn thành" in history.text
    assert "Task đã xoá khỏi dashboard" in history.text
    assert "Đã xoá" in history.text


def test_settings_page_updates_username_and_password_in_app(tmp_path):
    client = make_client(tmp_path)
    client.post("/login", data={"username": "admin", "password": "secret-pass"})

    settings = client.get("/settings")
    assert settings.status_code == 200
    assert "Đổi username/password" in settings.text

    changed = client.post(
        "/settings/credentials",
        data={
            "current_password": "secret-pass",
            "new_username": "thai",
            "new_password": "new-secret-pass",
            "confirm_password": "new-secret-pass",
        },
        follow_redirects=False,
    )
    assert changed.status_code == 303
    assert changed.headers["location"] == "/settings?updated=1"

    client.post("/logout")
    assert client.post("/login", data={"username": "admin", "password": "secret-pass"}).status_code == 401
    good = client.post("/login", data={"username": "thai", "password": "new-secret-pass"}, follow_redirects=False)
    assert good.status_code == 303
    assert client.get("/").status_code == 200


def test_notifications_move_from_matrix_to_bell_page(tmp_path):
    client = make_client(tmp_path)
    client.post("/login", data={"username": "admin", "password": "secret-pass"})
    client.post("/tasks", data={"title": "Hết hạn hôm qua", "quadrant": "q1", "due_date": "2026-06-02"})
    client.post("/tasks", data={"title": "Đến hạn hôm nay", "quadrant": "q2", "due_date": "2026-06-03"})
    client.post("/tasks", data={"title": "Sắp hết hạn mai", "quadrant": "q3", "due_date": "2026-06-04"})

    dashboard = client.get("/?today=2026-06-03")

    assert dashboard.status_code == 200
    assert "🔔" in dashboard.text
    assert "href=\"/notifications" in dashboard.text
    assert "Thông báo deadline" not in dashboard.text
    assert "notification-panel" not in dashboard.text

    notifications = client.get("/notifications?today=2026-06-03")

    assert notifications.status_code == 200
    assert "Thông báo deadline" in notifications.text
    assert "Hết hạn" in notifications.text
    assert "Hôm nay đến hạn" in notifications.text
    assert "Sắp hết hạn trong 1 ngày" in notifications.text
    assert "Hết hạn hôm qua" in notifications.text
    assert "Đến hạn hôm nay" in notifications.text
    assert "Sắp hết hạn mai" in notifications.text


def test_weekly_plan_page_updates_capacity_and_shows_buffer(tmp_path):
    client = make_client(tmp_path)
    client.post("/login", data={"username": "admin", "password": "secret-pass"})
    client.post("/tasks", data={"title": "Deep Q2", "quadrant": "q2", "due_date": "2026-06-03", "duration_minutes": "120"})
    client.post("/tasks", data={"title": "Fire Q1", "quadrant": "q1", "due_date": "2026-06-04", "duration_minutes": "45"})

    initial = client.get("/weekly-plan?week_start=2026-06-01")
    assert initial.status_code == 200
    assert "Weekly Planning" in initial.text
    assert "Deep Q2" in initial.text
    assert "2h 45m" in initial.text

    updated = client.post(
        "/weekly-plan/capacity",
        data={
            "week_start": "2026-06-01",
            "2026-06-01": "60",
            "2026-06-02": "120",
            "2026-06-03": "180",
        },
        follow_redirects=False,
    )
    assert updated.status_code == 303
    assert updated.headers["location"] == "/weekly-plan?week_start=2026-06-01"

    weekly = client.get("/weekly-plan?week_start=2026-06-01")
    assert "6h" in weekly.text
    assert "Buffer" in weekly.text
    assert "3h 15m" in weekly.text


def test_weekly_plan_shows_q2_focus_protection(tmp_path):
    client = make_client(tmp_path)
    client.post("/login", data={"username": "admin", "password": "secret-pass"})
    client.post("/tasks", data={"title": "Q2 học chứng chỉ", "quadrant": "q2", "due_date": "2026-06-02", "duration_minutes": "90"})

    weekly = client.get("/weekly-plan?week_start=2026-06-01")

    assert weekly.status_code == 200
    assert "Q2 Focus" in weekly.text
    assert "Q2 học chứng chỉ" in weekly.text
    assert "sắp thành Q1" in weekly.text


def test_dashboard_can_suggest_tasks_by_energy_level(tmp_path):
    client = make_client(tmp_path)
    client.post("/login", data={"username": "admin", "password": "secret-pass"})
    client.post("/tasks", data={"title": "Quick admin", "quadrant": "q3", "duration_minutes": "15", "energy_level": "low"})
    client.post("/tasks", data={"title": "Deep strategy", "quadrant": "q2", "duration_minutes": "120", "energy_level": "high"})

    dashboard = client.get("/?energy=high")

    assert dashboard.status_code == 200
    assert "Gợi ý theo năng lượng" in dashboard.text
    assert "Deep strategy" in dashboard.text
