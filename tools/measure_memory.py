"""Measure what a resident Python GUI process actually costs.

    python tools/measure_memory.py

Windows only, deliberately: it is the platform the numbers in
``docs/measurements.md`` were taken on, and a cross-platform abstraction here
would hide which one you are looking at.

Three stages, because the interesting question is not "how big is the app" but
"how much of it is ours". The answer is that almost none of it is: the
interpreter and Tcl/Tk account for the whole figure, which is what
``docs/adr/0008-the-invariant-is-the-warm-path.md`` decided on.

Working set is not private commit, and Windows reports it generously. This is
enough to reject a 10 MB target. It is not enough to set a replacement floor --
see the residual section of ``docs/measurements.md``.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


class ProcessMemoryCounters(ctypes.Structure):
    """``PROCESS_MEMORY_COUNTERS``, from psapi.h."""

    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def working_set_mb() -> float:
    """This process's working set, in mebibytes.

    The argtypes matter. Without them ctypes guesses at the handle width, and
    on a 64-bit build the call quietly returns zero rather than failing.
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.K32GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    kernel32.K32GetProcessMemoryInfo.restype = wintypes.BOOL

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(ProcessMemoryCounters)
    ok = kernel32.K32GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(),
        ctypes.byref(counters),
        counters.cb,
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), "K32GetProcessMemoryInfo failed")
    # `ctypes` fields are `Any`, so this arithmetic and the number it
    # produces were unchecked -- in a file whose whole purpose is to put a
    # figure into `docs/measurements.md`.
    return float(counters.WorkingSetSize) / 1048576


def main() -> int:
    if sys.platform != "win32":
        print("This probe is Windows-only. See docs/measurements.md.")
        return 1

    print(f"python {sys.version.split()[0]}")
    print(f"baseline interpreter    : {working_set_mb():.1f} MB")

    import tkinter

    print(f"after import tkinter    : {working_set_mb():.1f} MB")

    root = tkinter.Tk()
    root.geometry("640x120")
    tkinter.Entry(root).pack(fill="x")
    root.update_idletasks()
    root.update()
    print(f"after Tk() + one Entry  : {working_set_mb():.1f} MB")
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
