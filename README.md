# VectorDraft

VectorDraft is the software platform for the VectorDraft X1 technical drawing plotter. It combines a CAD-aware vector processing pipeline with PlotCAD Studio, a modern web UI for drag-and-drop plotting.

## What It Does

- **Imports** SVG, DXF, PDF vector paths, and a practical HP-GL subset.
- **Normalizes** drawings into a millimeter-based vector document with layer and pen metadata.
- **Cleans** duplicate points, removes zero-length paths, and optionally simplifies tiny path noise.
- **Merges** contiguous segments on the same layer to reduce pen lifts.
- **Sorts** paths to reduce pen-up travel (nearest-neighbor optimization).
- **Detects** out-of-bounds paths and generates warnings.
- **Maps** layers and colors to physical pen profiles (ISO technical pen widths: 0.13–0.70 mm).
- **Exports** GRBL/FluidNC-style G-code with pen-change pauses, dwell, and estimated plot time.
- **Generates** PNG previews (CLI) and interactive SVG previews (web UI).
- **Applies** affine calibration profiles for scale, skew, rotation, and registration offsets.
- **Streams** G-code to GRBL/FluidNC-style controllers over serial.
- **Serves** PlotCAD Studio: a web UI for drag-and-drop jobs, layer/pen mapping, preview, plot control, and live machine status.

Coordinate convention: origin at the page's upper-left, X right, Y down.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Quick Start — Web UI

```powershell
vectordraft serve
```

Opens PlotCAD Studio in your browser at `http://127.0.0.1:8000`. Drag and drop SVG/DXF/PDF/HP-GL files to create jobs, preview drawings, configure pen mappings, and start plotting.

## Quick Start — CLI

```powershell
vectordraft demo examples
vectordraft inspect examples\demo_house.svg
vectordraft preview examples\demo_house.svg examples\demo_house.png
vectordraft export examples\demo_house.svg examples\demo_house.gcode --preview examples\demo_house_export.png
```

## CLI Reference

```powershell
vectordraft inspect drawing.svg
vectordraft preview drawing.dxf preview.png --page A1
vectordraft export drawing.pdf drawing.gcode --page A1 --curve-step-mm 0.75 --simplify-mm 0.02
vectordraft export drawing.svg drawing.gcode --pen-library pens.json --calibration calibration.json
vectordraft calibration create calibration.json --scale-x 1.0008 --scale-y 0.9996 --offset-x-mm 2.5
vectordraft pen-library create pens.json --preset iso
vectordraft pen-library inspect pens.json
vectordraft ports
vectordraft stream drawing.gcode COM3 --dry-run
vectordraft serve --host 0.0.0.0 --port 8000
```

Supported page presets: `A4`, `A3`, `A2`, `A1`, `A0`, `ARCH_D`, `ARCH_E`.

## Architecture

- `vectordraft.model`: page, path, pen, machine, job, and pen library data structures.
- `vectordraft.importers`: loads external formats (SVG, DXF, PDF, HP-GL) into a shared model.
- `vectordraft.optimizer`: cleanup, simplification, merge, out-of-bounds detection, and path sorting.
- `vectordraft.calibration`: affine calibration profiles and document transforms.
- `vectordraft.gcode`: converts optimized paths into machine motion with plot time estimation.
- `vectordraft.serial_stream`: serial sender for GRBL/FluidNC-style controllers.
- `vectordraft.preview`: renders plot previews with Matplotlib (CLI).
- `vectordraft.svg_preview`: generates SVG previews for the web UI.
- `vectordraft.job_manager`: disk-based job queue with state machine.
- `vectordraft.server`: FastAPI web server for PlotCAD Studio.
- `vectordraft.cli`: Typer command line interface.

## Next Engineering Steps

- Add camera-based calibration wizard.
- Add dashed/dotted line-type rendering in G-code.
- Add roll-feed media handling module.
- Add multi-pen changer firmware integration.
