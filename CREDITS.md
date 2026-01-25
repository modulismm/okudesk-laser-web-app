# Credits / Attributions

This project exists to provide an open, reproducible workflow to generate OKU Desk `.gco` files from SVG.

## NomadTech / Oku Desk Inkscape extensions

We reverse-engineered the OKU Desk G-code dialect and thumbnail metadata primarily by studying the original NomadTech Inkscape extensions:

- `2.1_Nomadtech-OkuDesk_Contornos.py` (vector)
- `2.1_Nomadtech-OkuDesk_Raster.py` (raster)

Those scripts are licensed under **GNU GPL v2 or later** (as stated in their headers).  
This repository is published under **GPL-3.0-or-later** to remain compatible.

## Upstream projects cited by NomadTech scripts

The NomadTech scripts themselves cite (among others):

- Nick Drobchenko (CNC club)
- hugomatic (`gcode.py`)
- Aaron Spike (various Inkscape extension utilities)
- TurnkeyTyranny / TurnkeyLaserExporter (for raster exporter lineage)

## Other open-source inspiration

During research we reviewed common laser toolchains (LaserWeb, Deepnest, etc.) to identify best practices
and optimizations, but the core output format work was validated against the OKU Desk reference `.gco` files.

