# Ultimate Technical Drawing Plotter: Research and Architecture

Date: 2026-06-02

## Goal

Create an open, serviceable technical drawing plotter that produces dimensionally reliable A1/A0 CAD drawings with real vector motion, real pens, predictable line weights, and a modern print workflow.

The project should not try to beat commercial inkjet plotters at high-volume color printing. Instead, it should own the gap between them and hobby pen plotters: archival pen output, CAD-aware vector processing, excellent calibration, low consumable cost, and repairable mechanics.

## Existing Machine Study

| Machine class | Current examples | Advantages | Disadvantages | Design lesson |
| --- | --- | --- | --- | --- |
| Large-format CAD inkjet plotters | HP DesignJet, Canon imagePROGRAF, Epson SureColor T-Series | Fast, mature drivers, roll feed, cutters, CAD/PDF/HP-GL workflows, good text and line output, office-ready reliability | Proprietary ink/parts, printheads can clog, raster output rather than true pen motion, high upfront/maintenance cost, limited hackability | Copy their workflow, media handling, preview, security, and job management; do not copy their closed consumables model |
| Desktop pen plotters | AxiDraw, iDraw/UUNA TEK, vintage HP pen plotters | Real ink line quality, cheap consumables, simple mechanics, excellent for vector art, can use technical pens | Slow because plot time depends on total path length, usually manual paper placement, limited work area, no native CAD line-weight/layer system, pen drying and pressure variation | Use true vector plotting, but add CAD semantics, auto calibration, paper handling, and pen management |
| Cutting plotters | Graphtec FC series, Roland vinyl cutters | Strong roll media transport, registration marks, barcode/job workflows, long-length tracking, production reliability | Optimized for drag knives and signage, not technical pen drafting; pressure/tool behavior differs; software is sign/cut oriented | Steal roll tracking, registration mark sensing, barcode job linking, and offline operation ideas |
| Modular CNC/draw bots | OpenBuilds ACRO and similar GRBL frames | Flexible, affordable, large sizes, easy to customize, can attach pens/lasers/tools | Assembly/calibration burden, belt/frame stiffness limits, not turnkey for CAD drawings, safety issues if laser-capable | Use modular mechanical ideas, but design around drafting accuracy from the start |

## Application Study

Primary applications:

- Architecture, engineering, construction drawings: plans, elevations, sections, details, redline sets.
- Mechanical CAD and fabrication drawings: part drawings, exploded views, toleranced diagrams.
- GIS and civil drawings: site layouts, utility maps, contour overlays.
- Education and maker labs: visible vector motion, drafting fundamentals, CAD-to-machine workflows.
- Archival or presentation drawings: real technical pen output on vellum, tracing film, heavy paper, or specialty media.

Secondary applications:

- Pen testing and ink testing.
- Pattern marking on paper, thin card, fabric, leather, or templates.
- Generative art and plotter art.
- Labeling material samples, jigs, and shop drawings.

## Market Gap

Commercial CAD plotters are fast and practical, but closed and inkjet-based. Hobby pen plotters are beautiful and repairable, but small, slow, and manually operated. The winning project is a CAD-grade pen plotter with:

- Real vector paths, not only raster print dots.
- A modern job workflow: DXF/SVG/PDF/HP-GL import, preview, nesting, warnings.
- Automatic squareness, scale, skew, and pen-offset calibration.
- A stable A1-first mechanical platform that scales to A0.
- Vacuum/clip/pin workholding and optional roll handling.
- Swappable pen modules with controlled downforce.

## Ultimate Project Idea

Project name: VectorDraft X1

One-line concept: An open A1/A0 technical drawing plotter that combines CAD plotter workflow, pen-plotter line quality, closed-loop calibration, and serviceable modular hardware.

Target profile:

- Format: A1 flatbed baseline, A0/ARCH E stretch version.
- Drawing tools: technical pens, fineliners, pencils, markers, optional scriber.
- Line widths: mapped from CAD layers to physical pens, e.g. 0.13, 0.18, 0.25, 0.35, 0.50, 0.70 mm.
- Accuracy target: user-calibrated dimensional error <= +/-0.1% over full page, with better local repeatability for line work.
- Workflow: drag in DXF/SVG/PDF/HP-GL, assign layers to pens, preview, simulate, plot.
- Philosophy: repairable, open file formats, replaceable commodity pens, documented calibration.

## System Architecture

### 1. Mechanical Architecture

Recommended geometry: fixed flatbed with moving Cartesian gantry.

Why this over roll-feed-only: flatbed workholding gives better geometry, less skew, and easier calibration for technical drawings. Roll feed can be added later as a module.

Core modules:

- Rigid frame: aluminum extrusion or steel base, cross-braced, adjustable leveling feet.
- Bed: flat MDF/aluminum honeycomb/vacuum plenum with replaceable spoil/plot mat.
- Workholding: vacuum zones plus registration pins and low-profile magnetic/clip rails.
- X axis: lightweight gantry beam on linear rails.
- Y axis: dual synchronized drives, one on each side, to prevent racking.
- Motion drive: closed-loop steppers or servos; belts are acceptable for A1, rack-and-pinion or ballscrew/rack hybrid for A0/pro version.
- Sensors: homing switches, end stops, paper presence, cover/interlock if any laser/scriber module is supported.
- Toolhead: quick-change pen carriage with spring compliance and measured downforce.
- Pen station: 6-8 capped pen docks, physical pen ID slots, wipe/test pad.
- Optional modules: roll-feed cassette, automatic cross-cutter, scanner/camera bridge, light table bed.

### 2. Toolhead Architecture

The toolhead is the heart of the machine.

- Pen lift: small linear actuator or voice-coil style lift, not a loose hobby servo.
- Downforce: adjustable spring/flexure with load cell or calibrated displacement.
- Tip calibration: camera-based or contact-based tip offset measurement after pen changes.
- Pen adapters: ISO technical pen sleeve, fineliner sleeve, pencil holder, marker holder.
- Caps: parked pens should be capped to reduce drying.
- Test strokes: every job begins with a small hidden line test on a margin/waste area.

### 3. Electronics Architecture

Two-board design:

- Motion MCU: STM32/ESP32 class controller running grblHAL, FluidNC, or a plotter-focused firmware fork.
- Host computer: Raspberry Pi/CM-class SBC or mini PC running the web UI, file processing, preview, camera calibration, and job queue.

Electronics modules:

- Closed-loop stepper/servo drivers.
- 24 V motion power rail; isolated 5 V/3.3 V logic.
- Toolhead I/O board for lift actuator, load cell, camera, pen sensors, LEDs.
- Bed vacuum controller with pressure sensor and zone valves.
- Emergency stop and pause/resume buttons.
- USB, Ethernet, Wi-Fi optional; offline plotting from USB is a good production feature.

### 4. Firmware Architecture

Firmware responsibilities:

- Deterministic XY motion and acceleration planning.
- Pen up/down timing with dwell and pressure confirmation.
- Homing, squaring, soft limits, and workspace transforms.
- Feed hold, resume, pause for pen replacement, and job recovery.
- Machine status streaming to the host.

Command layer:

- Internal output should be G-code-like for real-time motion.
- Import should support DXF, SVG, PDF vectors, and HP-GL/2 where possible.
- HP-GL-style pen numbers are useful because CAD plotter workflows already understand pen/layer mapping.

### 5. Software Architecture

Application name: PlotCAD Studio

Pipeline:

1. Import: DXF, SVG, PDF, HP-GL/2.
2. Normalize: convert all geometry to millimeters, flatten transforms, preserve layers/colors/line types.
3. CAD semantics: map layers/colors/line widths to physical pens.
4. Geometry cleanup: merge line segments, remove duplicates, detect out-of-bounds, simplify tiny artifacts.
5. Plot optimization: sort paths, reduce pen-up travel, group by pen, handle dashed lines and hatches.
6. Preview: full-page vector preview, estimated plot time, pen usage, warnings.
7. Calibration compensation: apply scale, skew, backlash, and paper registration correction.
8. Output: stream motion commands to firmware; save job package for replay.

Recommended stack:

- Backend: Python for CAD/vector processing.
- Libraries: ezdxf for DXF, vpype-like pipeline for vector optimization, shapely/clipper-style geometry operations, PDF vector extraction through a maintained PDF renderer/parser.
- Frontend: local web app with drag-and-drop jobs, layer/pen table, preview, queue, calibration wizard.
- Device API: WebSocket status stream plus REST endpoints for jobs, calibration, and settings.

### 6. Calibration Architecture

Calibration must be a first-class feature, not a hidden maintenance step.

Calibration routines:

- Axis scale: plot a known grid, measure with camera or user input.
- Squareness/skew: use registration fiducials and camera detection.
- Pen tip offset: plot/read cross marks for each pen.
- Paper placement: detect corner/edge/fiducials before plotting.
- Pressure: run pen-down force test and adjust actuator setpoint.
- Backlash and belt stretch: compensate through motion model and measured grid error map.

### 7. Data Model

Job package:

- Source file and normalized vector document.
- Units, page size, origin, margins.
- Layer list, pen assignments, stroke widths, colors, line styles.
- Calibration profile used.
- Toolpath plan.
- Estimated duration and pen changes.
- Machine/firmware version.

Pen profile:

- Pen ID, nominal width, color, tool type.
- Downforce, speed, acceleration, dwell.
- Max uncapped time.
- Preferred paper/media.

Machine profile:

- Workspace dimensions.
- Axis steps/mm or encoder scale.
- Soft limits.
- Calibration matrix/error map.
- Tool changer layout.

## First Build Roadmap

Phase 0: A3 proof of concept

- Single pen, fixed bed, GRBL/FluidNC style controller.
- Import SVG/DXF, plot G-code, basic preview.
- Validate line quality, pen pressure, and path optimization.

Phase 1: A1 engineering prototype

- Rigid flatbed frame, dual Y drive, vacuum/clip workholding.
- Camera-assisted calibration.
- Layer-to-pen mapping, job preview, estimated plot time.
- Manual pen changes with reliable pause/resume.

Phase 2: A1 production prototype

- 6-8 pen changer with caps.
- Test-stroke station and pen offset calibration.
- Offline USB job packages.
- Enclosure/cover, e-stop, clean cable routing.

Phase 3: A0/pro version

- Larger frame, stronger drive system, roll-feed module, automatic cutter.
- Job queue, barcode/fiducial support, optional scanning/checking workflow.

## Key Risks

- A0 stiffness and belt stretch can destroy dimensional accuracy if the frame is underbuilt.
- Pen pressure is harder than it looks; technical pens need consistent contact without nib damage.
- Plot time can become very long for dense hatches, text, and duplicated CAD geometry.
- PDF import can be messy because PDFs may contain text, raster elements, clipped paths, and transformed geometry.
- Automatic pen changing adds mechanical complexity; manual pen change is safer for the first prototype.
- Paper humidity, curl, and media thickness affect accuracy.

## Design Principles

- Flatbed first for accuracy; roll feed later for throughput.
- True vector plotting with CAD-aware line semantics.
- Calibration visible in the UI and stored per machine/media profile.
- Commodity pens and repairable parts.
- Open job packages so drawings can be reproduced later.
- Build A1 before A0; scale only after motion and calibration are proven.

## Sources Consulted

- HP DesignJet technical plotters: https://www.hp.com/us-en/printers/large-format/designjet-technical-plotters.html
- HP DesignJet T650 36-in specification PDF: https://pcb.inc.hp.com/dc/api/spec-sheet/ww-en/33508855/pdf/5hb10a.pdf
- HP Click Print solutions: https://www.hp.com/us-en/printers/large-format/click.html
- Canon imagePROGRAF TM specifications: https://canon.jp/biz/product/printer/imageprograf/lineup/tm355-tm350-tm340-tm255-tm250-tm240/spec
- Canon Direct Print Plus guide: https://ij.manual.canon/ij/webmanual/DirectPrintPlus/W/CO/EN/DPPL/dl002.html
- Epson SureColor T3770E specification sheet: https://mediaserver.goepson.com/ImConvServlet/imconv/e0f583099a031db46154c2081088913162024b43/original?assetDescr=SureColor+T3770E+Specification+Sheet.pdf
- AxiDraw machines and workflow: https://www.axidraw.com/
- Graphtec FC9000 cutting plotter: https://www.graphteccorp.com/cutting/fc9000/
- OpenBuilds ACRO system: https://us.openbuilds.com/openbuilds-acro-system/
- OpenBuilds A1 ACRO Draw Bot: https://builds.openbuilds.com/builds/a1-acro-draw-bot.10605/
- OpenBuilds CAM/CONTROL: https://software.openbuilds.com/
- vpype plotter vector processing documentation: https://vpype.readthedocs.io/en/stable/
