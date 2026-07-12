# Lumivision

A self-hosted, invite-only **vision board** for sharing images, videos and links with a small
circle — wrapped in a polished, high-tech dark UI (glassmorphism, purple/gold gradients,
animated transitions) inspired by the Luminatus visual language.

## Features

- **Boards** with three visibility levels:
  - **Private** — only the creator, collaborators, and admins can see it
  - **Registered Users** — every signed-in user can see it
  - **Public** — viewable by anyone on the internet, always read-only
- **Collaborators**: board owners pick specific members who may add content to their
  board — everyone else views only. Collaborators can also see private boards they're on
- **Assets**: image uploads, video uploads (mp4/webm/mov) with automatic poster-frame
  thumbnails (ffmpeg), YouTube/Vimeo embeds, and rich links with automatically fetched
  Open Graph previews
- **Themes**: 7 built-in themes (4 dark, 3 light). Each user picks an app-wide theme on
  their Account page; board creators can force a theme on a board for every viewer.
  Default: Purple & Gold (dark)
- Assets can live on **multiple boards** at once and carry **categories** used to filter
  within a board (animated chip filtering)
- **Masonry layout** with entrance animations, hover glow, and a **lightbox** viewer with
  keyboard/arrow navigation
- **Drag & drop**: drop files anywhere on a board to upload; board owners drag cards to
  reorder — or use the touch-friendly **Arrange** mode on mobile
- **Account self-service**: theme picker and password change; admins can set any user's
  password and promote other accounts to Admin from the Users page
- Every board (`/b/<slug>/`) and asset (`/a/<id>/`) has a **clean shareable URL**
- **Invite-only registration**: admins generate unique URLs (`/join/<token>/`) with a role,
  optional expiry and usage limit
- **Three roles** — Admin (manage users/invites, moderate content), Member (post assets,
  create boards, delete own content), Viewer (view only)
- Users can only delete assets **they posted**; deleting an asset removes its files from disk
- Board covers: upload an image that replaces the board name on the dashboard
- Django **admin panel** at `/admin/` as a back-office safety net
- Single Docker container, SQLite + uploads in one mounted volume — trivial to back up

## Quick start (Docker)

```bash
git clone <this repo> lumivision && cd lumivision
cp .env.example .env
nano .env          # set LUMIVISION_ADMIN_PASSWORD and your hostname at minimum
docker compose up -d --build
```

Compose reads `.env` automatically and refuses to start until
`LUMIVISION_ADMIN_PASSWORD` is set. Because `.env` is gitignored, your settings survive
`git pull` untouched.

Open `http://your-server:8018`, sign in with the admin credentials from `.env`,
then go to **Invites** to generate registration links for your circle.

All persistent state (SQLite database, uploads, generated secret key) lives in `./data`.
Back that directory up and you've backed up everything.

### Environment variables (set in `.env`)

| Variable | Default | Purpose |
| --- | --- | --- |
| `LUMIVISION_ADMIN_PASSWORD` | **required** | First-run admin password (account created once; changing it later has no effect) |
| `LUMIVISION_ADMIN_USER` | `admin` | First-run admin username |
| `LUMIVISION_HOST_PORT` | `8018` | Host port the container is published on |
| `LUMIVISION_ALLOWED_HOSTS` | `*` | Comma-separated hostnames, e.g. `vision.example.com` |
| `LUMIVISION_TRUSTED_ORIGINS` | – | **Required behind HTTPS**, e.g. `https://vision.example.com` |
| `LUMIVISION_SECRET_KEY` | auto | Auto-generated and persisted in the data volume if unset |
| `LUMIVISION_MAX_UPLOAD_MB` | `250` | Per-file upload cap |
| `LUMIVISION_WORKERS` | `3` | Gunicorn worker count |
| `LUMIVISION_TIME_ZONE` | `UTC` | Display timezone |
| `LUMIVISION_DEBUG` | `0` | Set `1` only for local development |

## Running behind Virtualmin

1. Create the virtual server (e.g. `vision.example.com`) with SSL.
2. Enable proxying to the container — Virtualmin: *Server Configuration → Edit Proxy Website*,
   or add to the Apache config:
   ```apache
   ProxyPreserveHost On
   ProxyPass        / http://127.0.0.1:8018/
   ProxyPassReverse / http://127.0.0.1:8018/
   RequestHeader set X-Forwarded-Proto "https"
   ```
   `ProxyPreserveHost On` is required — without it Apache forwards `Host: 127.0.0.1`
   and Django's ALLOWED_HOSTS check returns 400. `RequestHeader` needs mod_headers
   (`a2enmod headers`).
3. Set in `.env`:
   ```dotenv
   LUMIVISION_ALLOWED_HOSTS=vision.example.com
   LUMIVISION_TRUSTED_ORIGINS=https://vision.example.com
   ```
4. `docker compose up -d` and you're live.

## Local development

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Linux/macOS: .venv/bin/pip
$env:LUMIVISION_DEBUG = "1"
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py createsuperuser
.venv\Scripts\python manage.py runserver
```

## Roles & permissions

| Action | Admin | Member | Viewer | Public |
| --- | :-: | :-: | :-: | :-: |
| View public boards | ✔ | ✔ | ✔ | ✔ |
| View registered-user boards | ✔ | ✔ | ✔ | – |
| Create boards | ✔ | ✔ | – | – |
| Post assets to own/collaborated boards | ✔ | ✔ | – | – |
| Delete own assets | ✔ | ✔ | – | – |
| Delete anyone's assets / boards | ✔ | – | – | – |
| Generate invites, manage users | ✔ | – | – | – |

## URL map

- `/` dashboard · `/b/<slug>/` board · `/a/<id>/` asset permalink
- `/join/<token>/` invite registration · `/accounts/login/` sign in
- `/manage/invites/` · `/manage/users/` (admin) · `/admin/` Django admin
