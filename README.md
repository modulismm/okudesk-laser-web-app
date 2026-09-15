# OkuDesk Laser Web App

Web app to convert SVG files into OKU Desk-compatible `.gco` (Smoothieware-modified dialect),
including the required `$M` metadata + **thumbnail preview** on the machine.

🌐 **Try it online**: [https://okulaser.bouh.space](https://okulaser.bouh.space)

- **GitHub**: `https://github.com/modulismm/okudesk-laser-web-app`
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

---

## Features

- **Vector cutting/scoring**: Upload SVG (multi-color → per-job settings)
- **Job management**: Reorder job colors (execution order), enable/disable per layer
- **Origin positioning**: Corners, center, or **custom X,Y** — plus drag-to-place on the bed
- **Material presets**: Quick settings for common materials (fabric, wood, acrylic, etc.)
- **Toolpath optimization**: Path ordering, per-pass direction alternation, adaptive curve
  flattening and line simplification — around 70–77% less rapid travel on scattered artwork,
  with cut geometry unchanged
- **Toolpath preview**: Renders the *emitted G-code* over the bed — cuts coloured by execution
  order, travel moves shown separately, with measured cut and travel distance
- **Workspace**: Zoom and pan, job bounds outline, artwork drawn in its own layer colours
- **Raster engraving**: PNG/JPEG/WEBP/GIF/BMP → `.gco` with grayscale/dither, gamma, safe mode.
  **SVG files are rasterized in the browser** at the chosen mm/pixel
- **Hardware validated**: Output tested on real OKU Desk hardware

## Quick start

### Run locally (development)

```bash
cd backend-api-test
./start.sh
```

Then open `http://localhost:8000/` (or set `PORT` to override).

### Deploy with Docker

See `deploy/DEPLOY_DOCKER_NGINX.md` for full instructions.

```bash
git clone https://github.com/modulismm/okudesk-laser-web-app.git
cd okudesk-laser-web-app
docker compose up -d --build
```

The app will be available at `http://127.0.0.1:8000/`.

## Configuration (hosted mode)

The UI reads `/api/config`. Set environment variables:

- `DONATE_URL` — Link to your donation page
- `GITLAB_URL` — Link to this repository (legacy name; the repo is on GitHub now)
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


## Tests

The backend has a pytest suite (golden-file G-code comparison, laser-safety guards, transforms,
SVG traversal, raster input validation):

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend-api-test/backend/requirements.txt pytest
.venv/bin/python -m pytest
```

There is also a toolpath benchmark that reports rapid travel, cut distance and estimated runtime
before and after optimization:

```bash
.venv/bin/python backend-api-test/backend/tests/benchmark_toolpath.py
```

## Contributing

This project is maintained by the community. Contributions are welcome!

- **Found a bug?** Open an issue on GitHub
- **Want to add a feature?** Fork, make changes, and submit a pull request
- **Have questions?** Open a discussion

## License

**GPL-3.0-or-later**. See `LICENSE`.  
See `CREDITS.md` for explicit attributions (including NomadTech’s GPLv2-or-later extensions).
