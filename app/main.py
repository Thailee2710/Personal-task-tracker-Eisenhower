from __future__ import annotations

import base64
import calendar as pycalendar
import hmac
import os
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .core import (
    QUADRANTS,
    authenticate,
    classify_quadrant,
    create_task,
    delete_task,
    ensure_admin_user,
    format_minutes,
    get_weekly_plan,
    init_db,
    list_calendar_tasks,
    list_due_notifications,
    list_energy_suggestions,
    list_task_history,
    list_tasks_by_quadrant,
    move_task,
    set_weekly_capacity,
    toggle_task,
    update_user_credentials,
    user_exists,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = Path(os.environ.get("EISENHOWER_DB_PATH", BASE_DIR / "data" / "tasks.sqlite"))
DEFAULT_ADMIN_USER = os.environ.get("EISENHOWER_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("EISENHOWER_ADMIN_PASSWORD", "change-me-now")
DEFAULT_SECRET_KEY = os.environ.get("EISENHOWER_SECRET_KEY", "dev-only-secret-change-me")
VALID_CALENDAR_VIEWS = {"day", "week", "month", "year"}


def _parse_focus_date(raw: str | None) -> date:
    if not raw:
        return date.today()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def _calendar_period(view: str, focus: date) -> tuple[date, date, str]:
    view = view if view in VALID_CALENDAR_VIEWS else "month"
    if view == "day":
        return focus, focus, "Ngày"
    if view == "week":
        start = focus - timedelta(days=focus.weekday())
        return start, start + timedelta(days=6), "Tuần"
    if view == "year":
        return date(focus.year, 1, 1), date(focus.year, 12, 31), "Năm"
    start = date(focus.year, focus.month, 1)
    _, last_day = pycalendar.monthrange(focus.year, focus.month)
    return start, date(focus.year, focus.month, last_day), "Tháng"


def _group_tasks_by_due_date(tasks: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for task in tasks:
        grouped.setdefault(task["due_date"], []).append(task)
    return grouped


def _month_days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _year_months(focus: date) -> list[dict[str, str]]:
    return [
        {"label": f"Tháng {month}", "date": date(focus.year, month, 1).isoformat()}
        for month in range(1, 13)
    ]


def _week_start(focus: date | None = None) -> date:
    focus = focus or date.today()
    return focus - timedelta(days=focus.weekday())


def _minute_label_filter(minutes: int) -> str:
    return format_minutes(int(minutes or 0))


def _sign(value: str, secret_key: str) -> str:
    signature = hmac.new(secret_key.encode("utf-8"), value.encode("utf-8"), sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
    return f"{encoded}.{signature}"


def _unsign(token: str, secret_key: str) -> str | None:
    try:
        encoded, signature = token.split(".", 1)
        value = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
        expected = hmac.new(secret_key.encode("utf-8"), value.encode("utf-8"), sha256).hexdigest()
        if hmac.compare_digest(expected, signature):
            return value
    except Exception:
        return None
    return None


def create_app(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    admin_username: str = DEFAULT_ADMIN_USER,
    admin_password: str = DEFAULT_ADMIN_PASSWORD,
    secret_key: str = DEFAULT_SECRET_KEY,
) -> FastAPI:
    db_path = Path(db_path)
    init_db(db_path)
    ensure_admin_user(db_path, admin_username, admin_password)

    app = FastAPI(title="Eisenhower Task Logger")
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    templates.env.filters["minutes"] = _minute_label_filter
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    def current_user(request: Request) -> str | None:
        token = request.cookies.get("em_session", "")
        username = _unsign(token, secret_key) if token else None
        return username if username and user_exists(db_path, username) else None

    def require_user(request: Request) -> str:
        username = current_user(request)
        if not username:
            raise LoginRequired()
        return username

    @app.exception_handler(LoginRequired)
    async def login_required_handler(request: Request, exc: LoginRequired):
        return RedirectResponse("/login", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    async def login_form(request: Request):
        if current_user(request):
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse(request, "login.html", {"error": None})

    @app.post("/login")
    async def login(request: Request, username: str = Form(""), password: str = Form("")):
        if not authenticate(db_path, username, password):
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "Sai username hoặc mật khẩu."},
                status_code=401,
            )
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            "em_session",
            _sign(username, secret_key),
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
        )
        return response

    @app.post("/logout")
    async def logout():
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("em_session")
        return response

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request, username: str = Depends(require_user), today: str | None = None, energy: str = "medium"):
        grouped = list_tasks_by_quadrant(db_path)
        counts = {key: len([task for task in tasks if not task["done"]]) for key, tasks in grouped.items()}
        notifications = list_due_notifications(db_path, today=_parse_focus_date(today) if today else None)
        notification_count = sum(len(tasks) for tasks in notifications.values())
        energy = energy if energy in {"low", "medium", "high"} else "medium"
        energy_suggestions = list_energy_suggestions(db_path, energy_level=energy)
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "username": username,
                "quadrants": QUADRANTS,
                "tasks_by_quadrant": grouped,
                "counts": counts,
                "notifications": notifications,
                "notification_count": notification_count,
                "today": today,
                "selected_energy": energy,
                "energy_suggestions": energy_suggestions,
            },
        )

    @app.get("/weekly-plan", response_class=HTMLResponse)
    async def weekly_plan_page(
        request: Request,
        username: str = Depends(require_user),
        week_start: str | None = None,
    ):
        start = _parse_focus_date(week_start) if week_start else _week_start()
        plan = get_weekly_plan(db_path, week_start=start.isoformat())
        return templates.TemplateResponse(
            request,
            "weekly_plan.html",
            {"username": username, "plan": plan, "quadrants": QUADRANTS},
        )

    @app.post("/weekly-plan/capacity")
    async def update_weekly_capacity(request: Request, username: str = Depends(require_user)):
        form = await request.form()
        raw_week_start = str(form.get("week_start") or _week_start().isoformat())
        start = _parse_focus_date(raw_week_start)
        days = [(start + timedelta(days=offset)).isoformat() for offset in range(7)]
        daily_minutes = {day: str(form.get(day) or 0) for day in days}
        set_weekly_capacity(db_path, week_start=start.isoformat(), daily_minutes=daily_minutes)
        return RedirectResponse(f"/weekly-plan?week_start={start.isoformat()}", status_code=303)

    @app.get("/notifications", response_class=HTMLResponse)
    async def notifications_page(request: Request, username: str = Depends(require_user), today: str | None = None):
        notifications = list_due_notifications(db_path, today=_parse_focus_date(today) if today else None)
        notification_count = sum(len(tasks) for tasks in notifications.values())
        return templates.TemplateResponse(
            request,
            "notifications.html",
            {
                "username": username,
                "quadrants": QUADRANTS,
                "notifications": notifications,
                "notification_count": notification_count,
                "today": today,
            },
        )

    @app.get("/calendar", response_class=HTMLResponse)
    async def calendar_page(
        request: Request,
        username: str = Depends(require_user),
        view: str = "month",
        date: str | None = None,
    ):
        selected_view = view if view in VALID_CALENDAR_VIEWS else "month"
        focus = _parse_focus_date(date)
        start, end, view_label = _calendar_period(selected_view, focus)
        tasks = list_calendar_tasks(db_path, start_date=start.isoformat(), end_date=end.isoformat())
        tasks_by_date = _group_tasks_by_due_date(tasks)
        return templates.TemplateResponse(
            request,
            "calendar.html",
            {
                "username": username,
                "view": selected_view,
                "view_label": view_label,
                "focus_date": focus.isoformat(),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "tasks": tasks,
                "tasks_by_date": tasks_by_date,
                "month_days": _month_days(start, end) if selected_view in {"day", "week", "month"} else [],
                "year_months": _year_months(focus) if selected_view == "year" else [],
                "quadrants": QUADRANTS,
            },
        )

    @app.get("/history", response_class=HTMLResponse)
    async def history_page(request: Request, username: str = Depends(require_user)):
        tasks = list_task_history(db_path)
        return templates.TemplateResponse(
            request,
            "history.html",
            {"username": username, "tasks": tasks, "quadrants": QUADRANTS},
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(
        request: Request,
        username: str = Depends(require_user),
        updated: str | None = None,
    ):
        return templates.TemplateResponse(
            request,
            "settings.html",
            {"username": username, "error": None, "updated": updated == "1"},
        )

    @app.post("/settings/credentials")
    async def change_credentials(
        request: Request,
        username: str = Depends(require_user),
        current_password: str = Form(""),
        new_username: str = Form(""),
        new_password: str = Form(""),
        confirm_password: str = Form(""),
    ):
        error = None
        if not authenticate(db_path, username, current_password):
            error = "Mật khẩu hiện tại không đúng."
        elif new_password != confirm_password:
            error = "Mật khẩu mới và xác nhận mật khẩu không khớp."
        elif len(new_password) < 8:
            error = "Mật khẩu mới cần tối thiểu 8 ký tự."
        if error:
            return templates.TemplateResponse(
                request,
                "settings.html",
                {"username": username, "error": error, "updated": False},
                status_code=400,
            )
        try:
            update_user_credentials(
                db_path,
                current_username=username,
                new_username=new_username,
                new_password=new_password,
            )
        except ValueError as exc:
            return templates.TemplateResponse(
                request,
                "settings.html",
                {"username": username, "error": str(exc), "updated": False},
                status_code=400,
            )
        response = RedirectResponse("/settings?updated=1", status_code=303)
        response.set_cookie(
            "em_session",
            _sign(new_username.strip(), secret_key),
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
        )
        return response

    @app.post("/tasks")
    async def add_task(
        username: str = Depends(require_user),
        title: str = Form(""),
        description: str = Form(""),
        due_date: str = Form(""),
        duration_minutes: str = Form(""),
        energy_level: str = Form("medium"),
        important: str | None = Form(None),
        urgent: str | None = Form(None),
        quadrant: str | None = Form(None),
    ):
        selected_quadrant = quadrant or classify_quadrant(important=bool(important), urgent=bool(urgent))
        create_task(
            db_path,
            title=title,
            description=description,
            due_date=due_date,
            duration_minutes=duration_minutes,
            energy_level=energy_level,
            quadrant=selected_quadrant,
        )
        return RedirectResponse("/", status_code=303)

    @app.post("/tasks/{task_id}/move")
    async def move(task_id: int, username: str = Depends(require_user), quadrant: str = Form(...)):
        move_task(db_path, task_id, quadrant)
        return RedirectResponse("/", status_code=303)

    @app.post("/tasks/{task_id}/toggle")
    async def toggle(task_id: int, username: str = Depends(require_user), done: str = Form("false")):
        toggle_task(db_path, task_id, done=done.lower() == "true")
        return RedirectResponse("/", status_code=303)

    @app.post("/tasks/{task_id}/delete")
    async def delete(task_id: int, username: str = Depends(require_user)):
        delete_task(db_path, task_id)
        return RedirectResponse("/", status_code=303)

    return app


class LoginRequired(Exception):
    pass


app = create_app()
