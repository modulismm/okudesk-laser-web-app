# OkuDesk Laser Web App

Web app to convert SVG files into OKU Desk-compatible `.gco` (Smoothieware-modified dialect),
including the required `$M` metadata + **thumbnail preview** on the machine.

- **GitLab**: `https://gitlab.com/Bootlessbear/okudesk-laser-web-app`
- **Buy me a coffee**: `https://buymeacoffee.com/bootlessbear`

## Features

- Upload SVG (multi-color → per-job settings)
- Reorder job colors (execution order)
- Origin (0,0) selection (corners + center)
- Material presets (cut / engrave)
- Raster engraving (PNG/JPG → `.gco`) with presets + safe mode
- Output validated on OKU Desk hardware

## Run locally (recommended dev workflow)

```bash
cd backend-api-test
./start.sh
```

Then open:

- `http://localhost:5001/` (or the port printed in the console)

## Configure links (hosted mode)

The UI reads `/api/config`. On your server you can set:

- `DONATE_URL` (example: `https://buymeacoffee.com/bootlessbear`)
- `GITLAB_URL` (example: `https://gitlab.com/Bootlessbear/okudesk-laser-web-app`)

## Raster mode (in the same UI)

Raster is **enabled by default** and can be disabled server-side:

- **Enabled by default**: no configuration needed
- **Disable**: set `ENABLE_RASTER=0` and restart the backend/container (Raster button will be disabled in the UI)

How to access:

- In the main UI, use the **Vector / Raster** switch (Raster only appears if enabled)
- Direct URL: `/raster`
- Deep link: `/#raster`

Technical details: see `docs/RASTER.md`.

## License

**GPL-3.0-or-later**. See `LICENSE`.  
See `CREDITS.md` for explicit attributions (including NomadTech’s GPLv2-or-later extensions).
