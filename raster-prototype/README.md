# Raster prototype (separate)

This is an **isolated** raster MVP so we can iterate safely without touching the main production app.

## Run (local)

```bash
cd raster-prototype
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open:

- `http://127.0.0.1:8010/raster`

## Run (Docker)

```bash
cd raster-prototype
docker compose up -d --build
```

Open:

- `http://127.0.0.1:8010/raster`

## Notes

- Prototype: left-to-right scan only, basic thresholding, no dithering yet.
- Output includes OKU `$M` metadata + `$MT` thumbnail preview.

