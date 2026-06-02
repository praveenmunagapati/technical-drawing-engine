from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel
from serial import Serial
from serial.tools import list_ports


class SerialPortLike(Protocol):
    def write(self, data: bytes) -> int: ...

    def readline(self) -> bytes: ...


class StreamSettings(BaseModel):
    baudrate: int = 115200
    timeout_s: float = 2.0
    reset_after_open_s: float = 2.0
    send_soft_reset: bool = True


class StreamResult(BaseModel):
    port: str
    commands_sent: int
    errors: list[str] = []
    dry_run: bool = False


ProgressCallback = Callable[[int, str, str], None]


def available_ports() -> list[str]:
    return [port.device for port in list_ports.comports()]


def iter_gcode_commands(gcode: str | Iterable[str]) -> Iterable[str]:
    lines = gcode.splitlines() if isinstance(gcode, str) else gcode
    for line in lines:
        command = strip_gcode_comments(line).strip()
        if command:
            yield command


def strip_gcode_comments(line: str) -> str:
    no_paren = re.sub(r"\([^)]*\)", "", line)
    return no_paren.split(";", 1)[0].strip()


def stream_file(
    gcode_file: str | Path,
    *,
    port: str,
    settings: StreamSettings | None = None,
    dry_run: bool = False,
    progress: ProgressCallback | None = None,
) -> StreamResult:
    gcode = Path(gcode_file).read_text(encoding="utf-8")
    return stream_gcode(gcode, port=port, settings=settings, dry_run=dry_run, progress=progress)


def stream_gcode(
    gcode: str,
    *,
    port: str,
    settings: StreamSettings | None = None,
    dry_run: bool = False,
    progress: ProgressCallback | None = None,
) -> StreamResult:
    settings = settings or StreamSettings()
    commands = list(iter_gcode_commands(gcode))
    if dry_run:
        for index, command in enumerate(commands, start=1):
            if progress:
                progress(index, command, "dry-run")
        return StreamResult(port=port, commands_sent=len(commands), dry_run=True)

    with Serial(port=port, baudrate=settings.baudrate, timeout=settings.timeout_s) as serial_port:
        if settings.send_soft_reset:
            serial_port.write(b"\x18")
        if settings.reset_after_open_s > 0:
            time.sleep(settings.reset_after_open_s)
            _drain_startup(serial_port)
        return stream_commands(commands, serial_port, port=port, progress=progress)


def stream_commands(
    commands: Iterable[str],
    serial_port: SerialPortLike,
    *,
    port: str = "memory",
    progress: ProgressCallback | None = None,
) -> StreamResult:
    sent = 0
    errors: list[str] = []
    for index, command in enumerate(commands, start=1):
        serial_port.write((command + "\n").encode("ascii"))
        response = _wait_for_ack(serial_port)
        if progress:
            progress(index, command, response)
        sent += 1
        if response.lower().startswith("error"):
            errors.append(f"{command}: {response}")
            break
    return StreamResult(port=port, commands_sent=sent, errors=errors)


def _wait_for_ack(serial_port: SerialPortLike) -> str:
    while True:
        raw = serial_port.readline()
        if not raw:
            raise TimeoutError("Timed out waiting for controller response.")
        response = raw.decode("ascii", errors="replace").strip()
        if response.lower().startswith(("ok", "error")):
            return response


def _drain_startup(serial_port: SerialPortLike) -> None:
    while True:
        raw = serial_port.readline()
        if not raw:
            return
