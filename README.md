# OkuDesk Laser Web App

Web app to convert SVG files into OKU Desk-compatible `.gco` (Smoothieware-modified dialect),
including the required `$M` metadata + **thumbnail preview** on the machine.

🌐 **Try it online**: [https://okulaser.bouh.space](https://okulaser.bouh.space)

- **GitLab**: `https://gitlab.com/Bootlessbear/okudesk-laser-web-app`
- **Buy me a coffee**: `https://buymeacoffee.com/bootlessbear`

---

## Why this project exists

This interface exists because the original macOS workflow for Oku Desk was abandoned. Many users were left without a reliable, maintained toolchain.

- **NomadTech discontinued the macOS software** (and long-term maintenance/support)
- **Lack of support** left users stuck with a "black box" workflow
- **Lack of respect** when users become dependent on a workflow that disappears

**Our goal**: a transparent, reproducible, documented workflow maintained by the community.

This project is **GPL-3.0-or-later** (compatible with NomadTech's GPLv2-or-later codebase). See `CREDITS.md` for explicit attributions.

---

## How it works

### Architecture

- **Frontend**: Vanilla HTML/CSS/JavaScript (no frameworks) — clean, fast, works offline
- **Backend**: Python Flask API that exposes G-code generation logic
- **Core logic**: Reverse-engineered from NomadTech's Inkscape extensions, validated on real hardware

### Key technical details

- **G-code dialect**: Custom Smoothieware variant with `$M` metadata headers
- **Thumbnail generation**: Pillow-based image encoding for machine preview
- **SVG parsing**: Handles transforms, arcs, basic shapes (converted to paths)
- **Coordinate system**: Handles SVG (top-left, Y-down) → Machine (bottom-left, Y-up) conversion
- **Raster mode**: Grayscale/dither support, safe mode for firmware stability, chunked pixel encoding

See `docs/RASTER.md` for raster technical details.

---

## Features

- **Vector cutting/engraving**: Upload SVG (multi-color → per-job settings)
- **Job management**: Reorder job colors (execution order), enable/disable per layer
- **Origin positioning**: Select 0,0 from corners, center, or **custom X,Y coordinates**
- **Material presets**: Quick settings for common materials (fabric, wood, acrylic, etc.)
- **Raster engraving**: PNG/JPG → `.gco` with grayscale/dither, gamma correction, safe mode
- **Workspace preview**: Visualize job placement on the 500×285mm bed
- **Hardware validated**: Output tested on real OKU Desk hardware

## Quick start

### Run locally (development)

```bash
cd backend-api-test
./start.sh
```

Then open `http://localhost:5001/` (or the port printed in the console).

### Deploy with Docker

See `deploy/DEPLOY_DOCKER_NGINX.md` for full instructions.

```bash
git clone https://gitlab.com/Bootlessbear/okudesk-laser-web-app.git
cd okudesk-laser-web-app
docker compose up -d --build
```

The app will be available at `http://127.0.0.1:8000/`.

## Configuration (hosted mode)

The UI reads `/api/config`. Set environment variables:

- `DONATE_URL` — Link to your donation page
- `GITLAB_URL` — Link to this repository
- `ENABLE_RASTER` — Set to `0` to disable raster (default: enabled)
- `PORT` — Backend port (default: 8000)

## Raster mode (in the same UI)

Raster is **enabled by default** and can be disabled server-side:

- **Enabled by default**: no configuration needed
- **Disable**: set `ENABLE_RASTER=0` and restart the backend/container (Raster button will be disabled in the UI)

How to access:

- In the main UI, use the **Vector / Raster** switch (Raster only appears if enabled)
- Direct URL: `/raster`
- Deep link: `/#raster`

Technical details: see `docs/RASTER.md`.

## Contributing

This project is maintained by the community. Contributions are welcome!

- **Found a bug?** Open an issue on GitLab
- **Want to add a feature?** Fork, make changes, and submit a merge request
- **Have questions?** Check the docs in `docs/` or open a discussion

## License

**GPL-3.0-or-later**. See `LICENSE`.  
See `CREDITS.md` for explicit attributions (including NomadTech’s GPLv2-or-later extensions).
