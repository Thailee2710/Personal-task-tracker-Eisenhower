# Personal Task Tracker — Eisenhower Matrix

A lightweight self-hosted task tracker built with **FastAPI + SQLite**. It helps you capture tasks quickly, organize them with the Eisenhower Matrix, plan weekly capacity, and keep deadline alerts separate from the main Matrix dashboard.

The app is designed for small VPS deployments: minimal dependencies, no database server, no Docker requirement, and a simple server-rendered UI.

## Current status

- Repository: `https://github.com/Thailee2710/Personal-task-tracker-Eisenhower.git`
- Production-style app path used by the deployment guide: `/opt/eisenhower-task`
- Backend: FastAPI + Uvicorn
- Storage: SQLite
- UI: server-rendered Jinja templates + plain CSS
- Test suite: pytest
- Current expected test result: `26 passed`

## Eisenhower quadrants

- **Q1 — Do now**: Important + urgent
- **Q2 — Schedule**: Important + not urgent
- **Q3 — Delegate / quick handle**: Not important + urgent
- **Q4 — Eliminate / low backlog**: Not important + not urgent

## Features

### Authentication and security

- Login/logout with signed cookie sessions.
- In-app username/password change page.
- Initial admin credentials are created only when the user table is empty.
- After credentials are changed in-app, the SQLite database is the source of truth for login.
- Designed to run behind nginx, optionally with nginx Basic Auth as a second protection layer.

### Matrix task management

- Main Matrix dashboard at `/`.
- Quick task creation with important/urgent flags.
- Automatic quadrant classification from `important` / `urgent` flags.
- Direct quick-add form inside each quadrant.
- Task notes, due date, estimated duration, and energy level.
- Move tasks between quadrants.
- Mark tasks done / reopen.
- Soft delete: deleted tasks disappear from the dashboard but remain visible in History.

### Calendar and history

- Calendar page at `/calendar`.
- Deadline views by day, week, month, and year:
  - `/calendar?view=day&date=YYYY-MM-DD`
  - `/calendar?view=week&date=YYYY-MM-DD`
  - `/calendar?view=month&date=YYYY-MM-DD`
  - `/calendar?view=year&date=YYYY-MM-DD`
- History page at `/history` showing active, backlog, done, and deleted tasks.

### Weekly planning

- Weekly planning page at `/weekly-plan`.
- Input weekly capacity by day.
- Computes required task time for the selected week.
- Computes buffer or shortfall between available capacity and required task time.
- Shows time budget by quadrant.
- Groups tasks by weekday.

### Q2 focus and protection

- Weekly Plan includes a **Q2 Focus** panel.
- Highlights Q2 tasks for the selected week.
- Warns when a Q2 task is close to deadline and may become Q1.

### Energy-aware picking

- Each task has an energy level:
  - `low`
  - `medium`
  - `high`
- Dashboard suggests tasks based on the selected current energy level.

### Notifications

- Deadline notifications are intentionally **not** embedded in the main Matrix dashboard.
- A bell button `🔔` in the navigation opens the dedicated Notifications page at `/notifications`.
- Notifications are grouped into:
  - overdue tasks
  - tasks due today
  - tasks due tomorrow / within 1 day
- Notification task links jump back to the relevant Matrix quadrant.

## Project structure

```text
.
├── app/
│   ├── __init__.py
│   ├── core.py              # SQLite schema, auth helpers, task CRUD, planning, notifications
│   └── main.py              # FastAPI routes and app factory
├── static/
│   └── styles.css           # UI styles
├── templates/
│   ├── login.html
│   ├── dashboard.html       # Main Matrix page
│   ├── weekly_plan.html     # Weekly planning + Q2 focus
│   ├── notifications.html   # Dedicated deadline notification page
│   ├── calendar.html
│   ├── history.html
│   └── settings.html
├── tests/
│   ├── test_core.py
│   └── test_app.py
├── requirements.txt
├── .env.example
├── LICENSE
└── README.md
```

## Requirements

- Linux/macOS/WSL or a VPS running Ubuntu/Debian
- Python 3.11+ recommended
- `python3-venv`
- Optional for production:
  - `nginx`
  - `apache2-utils` for Basic Auth
  - `systemd`

## Local development

Clone the repository:

```bash
git clone https://github.com/Thailee2710/Personal-task-tracker-Eisenhower.git
cd Personal-task-tracker-Eisenhower
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

Edit `.env` and set strong values:

```bash
EISENHOWER_DB_PATH=./data/tasks.sqlite
EISENHOWER_ADMIN_USER=admin
EISENHOWER_ADMIN_PASSWORD=change-this-password
EISENHOWER_SECRET_KEY=replace-with-a-long-random-string
```

Generate a random secret key if needed:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

Run the app locally:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8090 --reload
```

Open:

```text
http://127.0.0.1:8090/
```

## Main routes

- `/login` — login page
- `/` — Matrix dashboard
- `/weekly-plan` — weekly capacity planning and Q2 protection
- `/notifications` — dedicated deadline notification page
- `/calendar` — deadline calendar
- `/history` — active/done/deleted task history
- `/settings` — in-app credential update page

## Running tests

```bash
source .venv/bin/activate
pytest tests -q
```

Expected current result:

```text
26 passed
```

The test suite covers:

- authentication and logout flow
- task creation, move, toggle, soft delete
- direct quadrant quick-add
- calendar views
- history page
- settings credential rotation
- weekly planning capacity/buffer calculations
- Q2 focus/protection warnings
- energy-aware suggestions
- dedicated Notifications page and bell navigation
- template readability for non-root systemd service users

## Production deployment on Ubuntu with systemd

The following example deploys the app to `/opt/eisenhower-task`, runs it as a dedicated Linux user, and exposes it locally on `127.0.0.1:8090` behind nginx.

### 1. Install OS packages

```bash
sudo apt update
sudo apt install -y git python3 python3-venv nginx apache2-utils
```

### 2. Create service user and app directory

```bash
sudo useradd --system --home /opt/eisenhower-task --shell /usr/sbin/nologin eisenhower || true
sudo mkdir -p /opt/eisenhower-task
sudo chown root:root /opt/eisenhower-task
```

### 3. Clone the app

```bash
sudo git clone https://github.com/Thailee2710/Personal-task-tracker-Eisenhower.git /opt/eisenhower-task
cd /opt/eisenhower-task
```

If the directory already exists:

```bash
cd /opt/eisenhower-task
sudo git pull
```

### 4. Create virtual environment

For systemd service users, prefer `--copies` so the venv does not depend on a root-only Python path:

```bash
cd /opt/eisenhower-task
sudo /usr/bin/python3 -m venv --copies .venv
sudo ./.venv/bin/pip install -r requirements.txt
```

### 5. Configure environment

```bash
sudo mkdir -p /opt/eisenhower-task/data
sudo chown eisenhower:eisenhower /opt/eisenhower-task/data

sudo cp .env.example .env
sudo nano .env
```

Example production `.env`:

```bash
EISENHOWER_DB_PATH=/opt/eisenhower-task/data/tasks.sqlite
EISENHOWER_ADMIN_USER=admin
EISENHOWER_ADMIN_PASSWORD=replace-with-a-strong-password
EISENHOWER_SECRET_KEY=replace-with-a-long-random-string
```

Protect the env file:

```bash
sudo chown root:eisenhower /opt/eisenhower-task/.env
sudo chmod 640 /opt/eisenhower-task/.env
```

### 6. Create systemd service

Create `/etc/systemd/system/eisenhower-task.service`:

```ini
[Unit]
Description=Eisenhower Task Logger
After=network.target

[Service]
Type=simple
User=eisenhower
Group=eisenhower
WorkingDirectory=/opt/eisenhower-task
EnvironmentFile=/opt/eisenhower-task/.env
ExecStart=/opt/eisenhower-task/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8090 --proxy-headers
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=/opt/eisenhower-task/data

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now eisenhower-task.service
sudo systemctl status eisenhower-task.service
```

Quick local check:

```bash
curl -I http://127.0.0.1:8090/
```

A `303` redirect to `/login` means the app is running.

### 7. Verify new template permissions

When adding new templates/static files on a server where the app runs as a non-root service user, make sure files are readable by the service:

```bash
cd /opt/eisenhower-task
sudo chmod 0644 templates/*.html static/*.css app/*.py
sudo ./.venv/bin/python -m pytest tests/test_app.py::test_templates_are_readable_by_service_user -q
```

## Nginx reverse proxy

### Option A: Simple reverse proxy

Create `/etc/nginx/sites-available/eisenhower-task`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name your-domain.example.com;

    client_max_body_size 8M;

    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable it:

```bash
sudo ln -s /etc/nginx/sites-available/eisenhower-task /etc/nginx/sites-enabled/eisenhower-task
sudo nginx -t
sudo systemctl reload nginx
```

### Option B: Add nginx Basic Auth

This gives you a second protection layer before the app login.

```bash
sudo mkdir -p /etc/nginx/eisenhower-task
sudo htpasswd -c /etc/nginx/eisenhower-task/.htpasswd your-basic-auth-user
```

Add these lines inside the nginx `server` block:

```nginx
auth_basic "Eisenhower Task Logger";
auth_basic_user_file /etc/nginx/eisenhower-task/.htpasswd;
```

Reload nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## HTTPS recommendation

If you expose the app publicly, use HTTPS. With a real domain pointed to your VPS:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.example.com
```

Without HTTPS, passwords are sent over plain HTTP. Use SSH tunnel or HTTPS for long-term usage.

## Updating an existing deployment

```bash
cd /opt/eisenhower-task
sudo git pull
sudo ./.venv/bin/pip install -r requirements.txt
sudo chmod 0644 templates/*.html static/*.css app/*.py
sudo systemctl restart eisenhower-task.service
sudo systemctl status eisenhower-task.service
```

Run tests after pulling if you want to verify locally:

```bash
cd /opt/eisenhower-task
sudo ./.venv/bin/python -m pytest tests -q
```

## Backup

The app stores data in SQLite. Back up the DB file regularly:

```bash
sudo sqlite3 /opt/eisenhower-task/data/tasks.sqlite ".backup '/opt/eisenhower-task/data/tasks-$(date +%F).sqlite'"
```

You can also copy the file while the app is stopped:

```bash
sudo systemctl stop eisenhower-task.service
sudo cp /opt/eisenhower-task/data/tasks.sqlite /root/tasks-backup-$(date +%F).sqlite
sudo systemctl start eisenhower-task.service
```

## Environment variables

- `EISENHOWER_DB_PATH`: SQLite database path
- `EISENHOWER_ADMIN_USER`: initial admin username used only when the user table is empty
- `EISENHOWER_ADMIN_PASSWORD`: initial admin password used only when the user table is empty
- `EISENHOWER_SECRET_KEY`: signing key for the session cookie

After you change username/password in-app, the database becomes the source of truth for login. The initial env username/password will not overwrite an existing user.

## Security notes

- Do not commit `.env`, SQLite databases, or credential files.
- Use a strong `EISENHOWER_SECRET_KEY`.
- Use HTTPS if the app is reachable over the public Internet.
- Consider nginx Basic Auth as an extra layer.
- Keep the backend bound to `127.0.0.1` and expose only nginx publicly.
- Public HTTP over an IP address is not encrypted; use HTTPS or a private tunnel for long-term usage.

## License

MIT License. See [LICENSE](LICENSE).
