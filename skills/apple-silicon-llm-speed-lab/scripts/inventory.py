"""Sanitized, read-only hardware inventory. No model loads, network or stress tests."""
from __future__ import annotations

import argparse
import csv
import ctypes
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


def command(argv, timeout=8):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def mac_sysctl(name):
    """Read in THIS Python process: a spawned universal sysctl may run translated."""
    try:
        library = ctypes.CDLL(None, use_errno=True)
        function = library.sysctlbyname
        function.argtypes = [ctypes.c_char_p, ctypes.c_void_p,
                             ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t]
        function.restype = ctypes.c_int
        length = ctypes.c_size_t()
        key = name.encode("ascii")
        if function(key, None, ctypes.byref(length), None, 0) != 0 or not 0 < length.value <= 4096:
            return None
        buffer = ctypes.create_string_buffer(length.value)
        if function(key, buffer, ctypes.byref(length), None, 0) != 0:
            return None
        return buffer.raw[:length.value]
    except (AttributeError, OSError):
        return None


def mac_gpu_records(raw):
    data = json.loads(raw or "{}")
    allowed = ("sppci_model", "sppci_cores", "spdisplays_metal", "spdisplays_vram",
               "spdisplays_vram_shared", "spdisplays_vendor")
    # Never return nested display objects, serial numbers or device identifiers.
    return [{key: item[key] for key in allowed if isinstance(item.get(key), (str, int))}
            for item in data.get("SPDisplaysDataType", []) if isinstance(item, dict)]


def linux_memory(raw):
    allowed = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}
    return {key.rstrip(":"): int(value) * 1024 for line in raw.splitlines()
            if len(parts := line.split()) == 3
            for key, value, unit in [parts]
            if key.rstrip(":") in allowed and value.isdigit() and unit == "kB"}


def nvidia_records(raw):
    result = []
    for row in csv.reader(io.StringIO(raw or "")):
        if len(row) == 4:
            result.append({"name": row[0].strip(), "memory_total_mib": number(row[1].strip()),
                           "memory_free_mib": number(row[2].strip()), "driver": row[3].strip()})
    return result


def windows_records(raw):
    data = json.loads(raw or "{}")
    gpus = data.get("gpus") or []
    if isinstance(gpus, dict):
        gpus = [gpus]
    return {"cpu": data.get("cpu"), "memory_bytes": number(data.get("memory_bytes")),
            "gpus": [{k: g[k] for k in ("Name", "AdapterRAM", "DriverVersion") if k in g}
                     for g in gpus if isinstance(g, dict)],
            "memory_caveat": "Display-adapter RAM may be incomplete; verify with serving runtime."}


def collect(disk_path="."):
    system = platform.system()
    report = {"version": 1, "os": system, "os_release": platform.release(),
              "probe_process_architecture": platform.machine(), "python_version": platform.python_version(),
              "logical_cpu_count": os.cpu_count(), "gpus": [], "unknown_probes": []}
    disk = shutil.disk_usage(disk_path)
    report["disk"] = {"total_bytes": disk.total, "free_bytes": disk.free,
                      "bandwidth_measured": False}
    if system == "Darwin":
        for key, sysctl in (("cpu", "machdep.cpu.brand_string"), ("memory_bytes", "hw.memsize"),
                            ("physical_cpu_count", "hw.physicalcpu"), ("arm64_capable", "hw.optional.arm64"),
                            ("probe_rosetta_translated", "sysctl.proc_translated")):
            value = mac_sysctl(sysctl)
            report[key] = (value.rstrip(b"\x00").decode("utf-8", errors="replace") if key == "cpu"
                           else int.from_bytes(value, byteorder="little")) if value else None
            if value is None:
                report["unknown_probes"].append(key)
        raw = command(["/usr/sbin/system_profiler", "SPDisplaysDataType", "-json"], timeout=12)
        try:
            report["gpus"] = mac_gpu_records(raw)
        except (ValueError, TypeError):
            report["unknown_probes"].append("mac_gpu_parse")
        report["unified_memory_note"] = "On Apple Silicon, system RAM is shared; do not add it to GPU VRAM."
    elif system == "Linux":
        try:
            report["memory"] = linux_memory(Path("/proc/meminfo").read_text())
            report["memory_bytes"] = report["memory"].get("MemTotal")
        except OSError:
            report["unknown_probes"].append("linux_memory")
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    report["cpu"] = line.split(":", 1)[1].strip()
                    break
        except OSError:
            report["unknown_probes"].append("linux_cpu")
        lspci = shutil.which("lspci")
        if lspci:
            raw = command([lspci]) or ""
            report["display_controllers"] = [line.split(": ", 1)[-1] for line in raw.splitlines()
                                              if any(label in line for label in ("VGA compatible", "3D controller", "Display controller"))]
    elif system == "Windows":
        shell = shutil.which("powershell") or shutil.which("pwsh")
        if shell:
            query = ("$c=Get-CimInstance Win32_ComputerSystem; $p=Get-CimInstance Win32_Processor; "
                     "$g=@(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion); "
                     "@{cpu=@($p.Name);memory_bytes=$c.TotalPhysicalMemory;gpus=$g}|ConvertTo-Json -Depth 4 -Compress")
            try:
                report.update(windows_records(command([shell, "-NoProfile", "-NonInteractive", "-Command", query])))
            except (ValueError, TypeError):
                report["unknown_probes"].append("windows_hardware")
    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        report["nvidia_gpus"] = nvidia_records(command([
            nvidia, "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader,nounits"]))
    if not report["gpus"] and not report.get("nvidia_gpus"):
        report["unknown_probes"].append("gpu_runtime_memory")
    report["packages_in_probe_python_only"] = {}
    for package in ("mlx", "mlx-lm", "mlx-vlm", "torch", "vllm", "llama-cpp-python", "coremltools"):
        try:
            report["packages_in_probe_python_only"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    report["limits"] = ["No model or accelerator benchmark was run.",
                        "Missing data means unknown, not absent hardware.",
                        "Probe-process architecture/packages may differ from the serving runtime.",
                        "NPU/ANE execution support must be verified in the runtime separately."]
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disk-path", default=".", help="Existing filesystem to query; path is not exported")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        report = collect(args.disk_path)
        if args.out:
            from bench import write_new_report
            write_new_report(args.out, report)
        print(json.dumps(report, indent=2))
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"error_type": type(error).__name__, "detail": "Inventory incomplete; no private system output exported."}))
        raise SystemExit(2)
