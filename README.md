# Lumivision

A self-hosted, invite-only **vision board** for sharing images, videos and links with your
circle — wrapped in a polished dark UI with glassmorphism, animated transitions, and a
built-in theme system. Runs as a single Docker container with all state in one volume.

## Features

- **Boards** with three visibility levels — Private, Registered Users, or fully **Public**
  (view-only, shareable with anyone)
- **Collaborators**: board owners choose which members may add content; collaborators can
  also see private boards they're invited to
- **Assets**: image uploads, video uploads with automatic poster-frame thumbnails (ffmpeg),
  YouTube/Vimeo embeds, and rich links with auto-fetched Open Graph previews
- Assets can live on **multiple boards** and carry **categories** for animated filtering
  within a board
- **Masonry layout**, hover glow, entrance animations, and a **lightbox** viewer with
  keyboard navigation
- **Drag & drop** uploads and reordering, plus a touch-friendly **Arrange** mode on mobile
- **Themes**: 7 built-in looks (4 dark, 3 light). Every user picks their own app-wide
  theme; boards can force a theme for all viewers. Default: Royal (dark)
- **Invite-only registration**: generate unique URLs with a role, optional expiry, and
  usage limit — no open signup
- **Three roles**: Admin, Member, Viewer, plus per-user profile pictures, self-service
  password change, and admin password reset
- Clean shareable URLs for every board (`/b/<slug>/`) and asset (`/a/<id>/`) with Open
  Graph tags for link unfurling
- Deleting an asset removes its files from disk; users can only delete what they posted
- Django admin at `/admin/` as a back-office for administrators

## Quick start

Requires Docker (the compose plugin is convenient but optional — see
[Without compose](#without-compose-docker-run) below).

```bash
mkdir lumivision && cd lumivision
curl -O https://raw.githubusercontent.com/bradqui/Lumivision/main/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/bradqui/Lumivision/main/.env.example
nano .env          # set LUMIVISION_ADMIN_PASSWORD and your hostname at minimum
docker compose up -d
```

That pulls the published image from `ghcr.io/bradqui/lumivision`, creates the admin
account on first start, and serves on port **8018** (change with `LUMIVISION_HOST_PORT`).

Sign in, then open **Invites** to generate registration links for your circle.

All persistent state (SQLite database, uploads, auto-generated secret key) lives in
`./data`. **Backing up that one directory backs up everything.**

### Updating

```bash
docker compose pull && docker compose up -d
```

Database migrations run automatically at container start.

### Without compose (docker run)

The image is self-contained — compose is not required:

```bash
mkdir -p lumivision/data && cd lumivision
docker run -d --name lumivision \
  --restart unless-stopped \
  -p 8018:8000 \
  -v "$(pwd)/data:/data" \
  -e LUMIVISION_ADMIN_PASSWORD='change-me-now' \
  -e LUMIVISION_ALLOWED_HOSTS='vision.example.com' \
  -e LUMIVISION_TRUSTED_ORIGINS='https://vision.example.com' \
  ghcr.io/bradqui/lumivision:latest
```

Only `LUMIVISION_ADMIN_PASSWORD` is required on the first run (it creates the admin
account); every variable from the configuration table below works the same way. If you
prefer a file, `docker run --env-file .env …` accepts the same `.env` format.

To update:

```bash
docker pull ghcr.io/bradqui/lumivision:latest
docker stop lumivision && docker rm lumivision
docker run …   # same command as above — state lives in ./data, not the container
```

This also covers container managers like Portainer, Unraid, or Synology: point them at
`ghcr.io/bradqui/lumivision:latest`, map a volume to `/data`, map a host port of your
choice (e.g. `8018`) to **container port 8000**, and set the environment variables.
(The app always listens on 8000 inside the container; `8018` in the examples is the
host-side port your reverse proxy talks to.)

## Configuration (`.env`)

| Variable | Default | Purpose |
| --- | --- | --- |
| `LUMIVISION_ADMIN_PASSWORD` | **required** | First-run admin password (account created once; later changes have no effect) |
| `LUMIVISION_ADMIN_USER` | `admin` | First-run admin username |
| `LUMIVISION_HOST_PORT` | `8018` | Host port the container publishes |
| `LUMIVISION_ALLOWED_HOSTS` | `*` | Comma-separated hostnames, e.g. `vision.example.com` |
| `LUMIVISION_TRUSTED_ORIGINS` | – | **Required behind HTTPS**, e.g. `https://vision.example.com` |
| `LUMIVISION_SECRET_KEY` | auto | Auto-generated and persisted in the data volume if unset |
| `LUMIVISION_MAX_UPLOAD_MB` | `250` | Per-file upload cap |
| `LUMIVISION_WORKERS` | `3` | Gunicorn worker count |
| `LUMIVISION_TIME_ZONE` | `UTC` | Display timezone |
| `LUMIVISION_COOKIE_SECURE` | `1` | Set `0` only if serving over plain HTTP (e.g. LAN-only) |
| `LUMIVISION_LOGIN_ATTEMPT_LIMIT` | `6` | Failed sign-ins (per account+IP) before temporary lockout |
| `LUMIVISION_LOGIN_COOLOFF_MINUTES` | `15` | How long a lockout lasts |
| `LUMIVISION_DEBUG` | `0` | Set `1` only for local development |

## Running a second instance (demo, staging, …)

Multiple Lumivision instances can share one host, but Docker namespaces **compose
project names** and **container names** host-wide — and compose derives its project
name from the *directory basename*. Two instances in directories both named
`lumivision` (even under different users) are treated as the *same* project, and
`docker compose up` for one will take over the other's containers.

For each additional instance, use its own directory with its own `docker-compose.yml`,
`.env`, and `data/`, and set three values in that instance's `.env`:

```dotenv
COMPOSE_PROJECT_NAME=lumivision-demo    # unique per instance
LUMIVISION_CONTAINER_NAME=lumivision-demo
LUMIVISION_HOST_PORT=8019               # any free host port
```

Also avoid `--remove-orphans` unless you're sure the project namespace is clean — it
deletes containers compose believes are abandoned, which is exactly the failure mode
of a project-name collision.

## Running behind a reverse proxy

Lumivision expects to sit behind your web server, which terminates TLS and proxies to the
container. Two things matter regardless of server:

1. **Preserve the original `Host` header** — otherwise Django's host validation returns 400.
2. **Send `X-Forwarded-Proto`** so the app knows the request was HTTPS.

Set in `.env`:

```dotenv
LUMIVISION_ALLOWED_HOSTS=vision.example.com
LUMIVISION_TRUSTED_ORIGINS=https://vision.example.com
```

### nginx

```nginx
server {
    listen 443 ssl;
    server_name vision.example.com;
    # ssl_certificate ...; ssl_certificate_key ...;

    client_max_body_size 300m;

    location / {
        proxy_pass http://127.0.0.1:8018;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

server {
    listen 80;
    server_name vision.example.com;
    return 301 https://$host$request_uri;
}
```

### Apache

```apache
<VirtualHost *:443>
    ServerName vision.example.com
    # SSLEngine on; SSLCertificateFile ...

    ProxyPreserveHost On
    ProxyPass        / http://127.0.0.1:8018/
    ProxyPassReverse / http://127.0.0.1:8018/
    RequestHeader set X-Forwarded-Proto "https"
</VirtualHost>

<VirtualHost *:80>
    ServerName vision.example.com
    RewriteEngine On
    RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [R=301,L]
</VirtualHost>
```

Requires `mod_proxy`, `mod_proxy_http`, `mod_headers`, and `mod_rewrite`.

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

## Development

```bash
git clone https://github.com/bradqui/Lumivision.git && cd Lumivision
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export LUMIVISION_DEBUG=1                            # Windows: $env:LUMIVISION_DEBUG="1"
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Run the test suite with `python manage.py test`. CI runs tests and a production static
build on every push and pull request.

To run the container built from local source instead of the published image:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

## Releasing (maintainers)

Tag a version and push it — GitHub Actions builds a multi-arch image (amd64 + arm64) and
publishes it to GHCR as `latest`, `X.Y`, and `X.Y.Z`:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and pull requests welcome; please
use GitHub's private vulnerability reporting for security issues.

## License

[MIT](LICENSE)
