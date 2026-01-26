# Deploy (Docker + Nginx)

This is the recommended way to run the app on a VPS / home server.

## 1) Clone the repo

```bash
git clone git@gitlab.com:Bootlessbear/okudesk-laser-web-app.git
cd okudesk-laser-web-app
```

## 2) Configure environment

```bash
cp .env.example .env
```

Edit `.env` if you want to change:
- `DONATE_URL`
- `GITLAB_URL`
- `PORT` (default 8000)
- `ENABLE_RASTER` (set to `1` to enable raster UI + API)

## 3) Start the container

```bash
docker compose up -d --build
```

The web app should be reachable locally at `http://127.0.0.1:8000/`.

## 4) Nginx reverse proxy

Copy `deploy/nginx-bouh.space.conf` into your Nginx config, then:

```bash
nginx -t && sudo systemctl reload nginx
```

## 5) Updates

```bash
git pull
docker compose up -d --build
```

## Raster mode

Raster generation is **enabled by default**. To disable it:

- Set `ENABLE_RASTER=0` in `.env`, then restart:

```bash
docker compose up -d --build
```

(The Raster button will be disabled in the UI when disabled)

Notes:

- Raster UI is available at `/raster` and is also embedded into the main UI via the **Vector / Raster** switch.
- The API endpoint is `/api/generate-raster` (only available when enabled).

