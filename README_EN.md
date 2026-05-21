# TG-SignPulse

> A Telegram multi-account automation panel for check-ins, action workflows, and keyword monitoring.

[中文说明](README.md) · [Health Checks](#health-checks) · [Changelog](#changelog)

TG-SignPulse is a Telegram automation panel. It helps you manage multiple accounts, run auto check-in tasks, and monitor execution logs from a web UI.

> AI-powered: AI actions (vision/math) are integrated and can be used directly in task workflows.

## What Is This Project For?

- Manage multiple Telegram accounts in one place (phone code or QR code login)
- Automate check-ins, message sending, and button clicking with fixed or random-range schedules
- 8 action types including AI vision, AI math solving, and keyword monitoring
- Run check-ins inside specific Telegram group topics (Thread/Topic)
- Real-time WebSocket log streaming with per-run flow details and latest bot replies
- Clipboard bulk task import/export, global proxy fallback, failure notifications, and keyword monitoring
- Run reliably on a VPS for long-term automation

## Highlights

- **Multi-account management**: Phone code or QR code login, per-account proxy support
- **8 action types**: Send Text, Send Dice, Click Button, AI Vision→Click Button, AI Vision→Send Text, AI Calculate→Send Text, AI Calculate→Click Button, Keyword Monitor
- **Two scheduling modes**: Fixed CRON time or randomized execution within a time window
- **Topic check-ins**: Send and filter replies by specific Thread/Topic in Telegram forum groups
- **Notifications**: Telegram Bot for task failures, invalid sessions, and login alerts; keyword matches support Telegram Bot, Bark, or custom URL
- **Real-time logs**: WebSocket live log streaming, history auto-retained for 3 days
- **Task migration**: Export all tasks to clipboard, paste-import with automatic duplicate skipping
- **Panel security**: JWT auth + TOTP two-factor authentication
- **Docker-first deployment**: Docker / Docker Compose ready, auto-adapts to mounted directory UID/GID

## Feature Map

| Area | Capability |
| --- | --- |
| Account management | Multi-account login (phone/QR), per-account proxy, status checks, re-login, TOTP 2FA |
| Task workflows | Fixed CRON / random-range schedules, 8 action types, action interval, auto-delete messages |
| Topic support | Send and filter replies by Telegram group `Thread ID` |
| Keyword monitoring | Contains / regex matching, push notification or continue action sequence on match |
| Notifications | Global: Telegram Bot (failures / invalid session / login); Keyword match: Telegram Bot / Bark / custom URL |
| Operations | Docker deployment, persistent data directory, health checks, config version migration, import/export |

## Beginner Deployment (3 Steps)

1. Install Docker
2. Run the container command below
3. Open `http://YOUR_SERVER_IP:8080` in a browser and log in

Default credentials:
- Username: `admin`
- Password: `admin123`

### One-command Deploy

```bash
docker run -d \
  --name tg-signpulse \
  --restart unless-stopped \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  -e TZ=Asia/Shanghai \
  -e APP_SECRET_KEY=your_secret_key \
  ghcr.io/akasls/tg-signpulse:latest
```

If you use a reverse proxy, bind locally only:

```bash
-p 127.0.0.1:8080:8080
```

### Docker Compose (Optional)

```yaml
services:
  app:
    image: ghcr.io/akasls/tg-signpulse:latest
    container_name: tg-signpulse
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
    environment:
      - TZ=Asia/Shanghai
      - APP_SECRET_KEY=your_secret_key
```

## Data Directory & Permissions

- Default data directory: `/data`
- If `/data` is not writable, app falls back to `/tmp/tg-signpulse` (non-persistent)
- New images can auto-adapt runtime UID/GID to `/data` owner in most VPS setups (usually no need for `chmod 777`)

Container checks:

```bash
id
ls -ld /data
touch /data/.probe && rm /data/.probe
```

## Common Environment Variables

- `APP_SECRET_KEY`: panel secret key (strongly recommended)
- `ADMIN_PASSWORD`: initial default password for the admin user (strongly recommended, otherwise defaults to insecure `admin123`)
- `APP_HOST`: API listening interface (defaults to `127.0.0.1` for security; use `0.0.0.0` if exposing container globally)
- `APP_DATA_DIR`: custom data directory (higher priority than panel setting)
- `TG_PROXY`: Telegram connection proxy; you can also configure a global proxy in the panel
- `TG_SESSION_MODE`: `file` (default) or `string` (recommended on arm64)
- `TG_SESSION_NO_UPDATES`: set `1` to enable `no_updates` (`string` mode only)
- `TG_GLOBAL_CONCURRENCY`: global concurrency limit (default `1`)
- `APP_TOTP_VALID_WINDOW`: panel 2FA tolerance window

## Custom Data Directory

You can set the data directory in two ways:

1. Panel: `System Settings -> Global Sign-in Settings -> Data Directory`
2. Env var: `APP_DATA_DIR=/your/path`

Notes:
- Restart backend service after changing it
- The path must be writable and mounted as persistent volume

## Local Development

- Python 3.12 is recommended; supported versions are Python `>=3.10,<3.14`
- Python 3.14 or newer is not recommended because the Telegram/Pydantic runtime dependencies are not fully compatible yet
- The frontend uses Node.js 20; run `npm ci` inside `frontend/`

## Common Panel Settings

In `System Settings -> Global Sign-in Settings`, you can configure:

- Global Proxy: used by login, chat refresh, and task execution when an account has no dedicated proxy
- Telegram Bot Notifications: set Bot Token and target Chat ID to receive failed-task, invalid-account-session, or keyword-match alerts
- Data Directory: stores sessions, logs, database, and task files

On the account task page, you can:

- Fill in `Topic / Thread ID` so a task only runs inside a specific Telegram group topic
- Add `Keyword Monitor` to an ordered action sequence, then choose Telegram Bot, Forward, Bark, or custom URL from the `Push Channel` dropdown
- Forward, Bark, and custom URL parameters are only shown after selecting the matching push channel
- Click the top-right export icon to copy all tasks of the current account to the clipboard
- Click the top-right paste/import action to bulk-import tasks from the clipboard while skipping duplicates

## Health Checks

- `GET /healthz`: quick health endpoint
- `GET /readyz`: readiness endpoint

## Project Structure

```text
backend/      FastAPI backend and scheduler
tg_signer/    Telegram automation core
frontend/     Next.js management panel
```

## Changelog

### 2026-05-21

- **Automatic task retry**: If a sign-in task fails due to network timeout or other errors, it will be retried once after 10 minutes. Retries are skipped when the account session is invalid, and a retried task will not produce a second retry on failure.
- **Range-mode delay via DateTrigger**: The random delay within the execution window now uses an APScheduler `DateTrigger` instead of `asyncio.sleep`, so the scheduled run survives a process restart.
- **Simplified success notification**: Removed the log tail from notifications; only the account name, task name, and sign-in reply are included.

### 2026-05-12

- **Fix task execution 500 error**: A local `logger` assignment inside the `except` block of `run_task_with_logs` caused an `UnboundLocalError` throughout the function; the redundant assignment has been removed.
- **Range-mode catchup on task save**: Creating, editing, or re-enabling a range-mode task now immediately schedules a one-shot run if the current time falls within the window and the task has not run today.

## Acknowledgements

This project is forked from [akasls/TG-SignPulse](https://github.com/akasls/TG-SignPulse), which itself is based on [amchii/tg-signer](https://github.com/amchii/tg-signer). Thanks to both authors for their open-source work.

Tech stack: FastAPI, Uvicorn, APScheduler, Pyrogram/Kurigram, Next.js, Tailwind CSS, OpenAI SDK.
