# VectorDraft

VectorDraft is the first software MVP for the technical drawing plotter project. It keeps our own code small by leaning on mature Python libraries for CAD/vector parsing, geometry work, plotting previews, validation, and CLI ergonomics.

## What It Does Now

- Imports SVG, DXF, PDF vector paths, and a practical HP-GL subset.
- Normalizes drawings into a simple millimeter-based vector document.
- Cleans duplicate points and optionally simplifies tiny path noise.
- Sorts paths to reduce pen-up travel.
- Exports GRBL/FluidNC-style G-code.
- Generates PNG previews before plotting.
- Applies affine calibration profiles for scale, skew, rotation, and registration offsets.
- Streams G-code to GRBL/FluidNC-style controllers over serial.
- Provides a CLI for inspection, preview, and export.

Coordinate convention for this MVP: origin at the page's upper-left, X right, Y down. The machine can be mounted/calibrated to match that convention, or a later transform can flip to lower-left.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Try The Demo

```powershell
vectordraft demo examples
vectordraft inspect examples\demo_house.svg
vectordraft preview examples\demo_house.svg examples\demo_house.png
vectordraft export examples\demo_house.svg examples\demo_house.gcode --preview examples\demo_house_export.png
```

## CLI

```powershell
vectordraft inspect drawing.svg
vectordraft preview drawing.dxf preview.png --page A1
vectordraft export drawing.pdf drawing.gcode --page A1 --curve-step-mm 0.75 --simplify-mm 0.02
vectordraft calibration create calibration.json --scale-x 1.0008 --scale-y 0.9996 --offset-x-mm 2.5
vectordraft export drawing.svg drawing.gcode --calibration calibration.json
vectordraft ports
vectordraft stream drawing.gcode COM3 --dry-run
```

Supported page presets: `A4`, `A3`, `A2`, `A1`, `A0`, `ARCH_D`, `ARCH_E`.

## Architecture

- `vectordraft.importers`: loads external formats into a shared model.
- `vectordraft.model`: page, path, pen, machine, and job data structures.
- `vectordraft.optimizer`: cleanup, simplification, and nearest-path sorting.
- `vectordraft.calibration`: affine calibration profiles and document transforms.
- `vectordraft.gcode`: converts optimized paths into machine motion.
- `vectordraft.serial_stream`: serial sender for GRBL/FluidNC-style acknowledgements.
- `vectordraft.preview`: renders plot previews with Matplotlib.
- `vectordraft.cli`: Typer command line interface.

## Next Engineering Steps

- Add pen profiles per layer/color with speed/downforce/dwell.
- Add a web UI for drag-and-drop jobs and live machine status.
- Add a camera-based calibration wizard.
