"""GPU, temperature and battery readings.

Where the numbers come from:
  * NVIDIA graphics cards: the `nvidia-smi` tool that ships with the NVIDIA driver.
  * Any CPU/GPU temperature: LibreHardwareMonitor (free, third-party) if it is
    running with its "Remote Web Server" turned on. Windows itself doesn't
    expose CPU temperatures to normal programs.
  * Battery: Windows, through psutil.
"""
import json
import re
import subprocess
import urllib.request
from dataclasses import dataclass

import psutil

from .utils import IS_WINDOWS

LHM_URL = "http://localhost:8085/data.json"

NVIDIA_FIELDS = ("name,utilization.gpu,temperature.gpu,memory.used,"
                 "memory.total,power.draw,fan.speed")


@dataclass
class Sensor:
    hardware: str
    group: str       # Temperatures, Load, Clocks, Fans, Powers…
    name: str
    value: float
    unit: str
    maximum: float = None


# ---- NVIDIA ---------------------------------------------------------------------
def _number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None          # "[N/A]" and friends


def parse_nvidia_smi(output):
    """Parse `nvidia-smi --query-gpu=... --format=csv,noheader,nounits`."""
    gpus = []
    for line in (output or "").strip().splitlines():
        cells = [c.strip() for c in line.split(",")]
        if len(cells) < 7 or not cells[0]:
            continue
        gpus.append({
            "name": cells[0], "util": _number(cells[1]), "temp": _number(cells[2]),
            "mem_used": _number(cells[3]), "mem_total": _number(cells[4]),
            "power": _number(cells[5]), "fan": _number(cells[6]),
        })
    return gpus


def query_nvidia(timeout=3):
    """List of NVIDIA GPUs, or None if there's no NVIDIA driver/tool."""
    flags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
    try:
        done = subprocess.run(
            ["nvidia-smi", f"--query-gpu={NVIDIA_FIELDS}",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=timeout, creationflags=flags)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return parse_nvidia_smi(done.stdout) or None


# ---- LibreHardwareMonitor -----------------------------------------------------------
_GROUPS = {"Temperatures", "Load", "Clocks", "Powers", "Fans", "Voltages",
           "Data", "Controls", "Throughput", "Factors", "Levels", "SmallData"}
_VALUE = re.compile(r"^\s*(-?[\d.,]+)\s*(.*?)\s*$")


def _parse_value(text):
    match = _VALUE.match(text or "")
    if not match:
        return None, ""
    raw = match.group(1)
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):       # 1.234,5  (comma is the decimal)
            raw = raw.replace(".", "").replace(",", ".")
        else:                                     # 1,234.5
            raw = raw.replace(",", "")
    elif "," in raw:
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+", raw):
            raw = raw.replace(",", "")            # 1,203  -> thousands separator
        else:
            raw = raw.replace(",", ".")           # 55,5   -> decimal comma
    try:
        return float(raw), match.group(2)
    except ValueError:
        return None, ""


def parse_lhm(tree):
    """Flatten LibreHardwareMonitor's data.json into a list of Sensor."""
    sensors = []

    def walk(node, hardware):
        text = node.get("Text", "")
        children = node.get("Children") or []
        if text in _GROUPS:
            for leaf in children:
                value, unit = _parse_value(leaf.get("Value"))
                if value is None:
                    continue
                maximum, _unit = _parse_value(leaf.get("Max"))
                sensors.append(Sensor(hardware or "", text, leaf.get("Text", ""),
                                      value, unit, maximum))
            return
        for child in children:
            walk(child, text if children and text else hardware)

    for top in (tree.get("Children") or []):
        for machine_child in (top.get("Children") or []):
            walk(machine_child, machine_child.get("Text", ""))
    return sensors


def query_lhm(url=LHM_URL, timeout=1.5):
    """Sensors from a running LibreHardwareMonitor web server, or None."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return parse_lhm(json.loads(response.read().decode("utf-8")))
    except (OSError, ValueError):
        return None


_CPU_WORDS = ("intel", "amd", "ryzen", "core", "cpu", "xeon", "threadripper")
_GPU_WORDS = ("nvidia", "geforce", "radeon", "gpu", "arc", "rtx", "gtx")


def _temps(sensors, words):
    return [s for s in sensors if s.group == "Temperatures"
            and any(w in s.hardware.lower() for w in words)]


def pick_cpu_temp(sensors):
    """The most representative CPU temperature, or None."""
    candidates = _temps(sensors, _CPU_WORDS)
    for wanted in ("package", "tctl", "tdie", "average"):
        for sensor in candidates:
            if wanted in sensor.name.lower():
                return sensor
    return candidates[0] if candidates else None


def pick_gpu(sensors):
    """GPU summary from LibreHardwareMonitor sensors (used when there's no NVIDIA tool)."""
    temps = _temps(sensors, _GPU_WORDS)
    loads = [s for s in sensors if s.group == "Load"
             and any(w in s.hardware.lower() for w in _GPU_WORDS)]
    if not temps and not loads:
        return None
    core_load = next((s for s in loads if "core" in s.name.lower()), None) \
        or (loads[0] if loads else None)
    core_temp = next((s for s in temps if "core" in s.name.lower()), None) \
        or (temps[0] if temps else None)
    hardware = (core_temp or core_load).hardware
    return {"name": hardware, "util": core_load.value if core_load else None,
            "temp": core_temp.value if core_temp else None,
            "mem_used": None, "mem_total": None, "power": None, "fan": None}


def psutil_temperatures():
    """Temperatures psutil can see (Linux/macOS; Windows usually returns nothing)."""
    reader = getattr(psutil, "sensors_temperatures", None)
    if reader is None:
        return []
    try:
        data = reader()
    except Exception:
        return []
    return [Sensor(chip, "Temperatures", entry.label or chip, entry.current, "°C",
                   entry.high) for chip, entries in data.items() for entry in entries]


def battery():
    """{'percent', 'plugged', 'minutes_left'} or None on a desktop PC."""
    reader = getattr(psutil, "sensors_battery", None)
    try:
        info = reader() if reader else None
    except Exception:
        return None
    if info is None:
        return None
    left = info.secsleft
    minutes = left // 60 if isinstance(left, int) and left >= 0 else None
    return {"percent": info.percent, "plugged": bool(info.power_plugged),
            "minutes_left": minutes}


def read_all():
    """Everything the Hardware page shows, gathered in one go (run off the UI thread)."""
    gpus = query_nvidia()
    sensors = query_lhm()
    source = "LibreHardwareMonitor" if sensors is not None else ""
    if sensors is None:
        sensors = psutil_temperatures()
        source = "System sensors" if sensors else ""
    if not gpus:
        fallback = pick_gpu(sensors)
        gpus = [fallback] if fallback else []
    return {"gpus": gpus, "sensors": sensors, "source": source,
            "cpu_temp": pick_cpu_temp(sensors), "battery": battery()}
