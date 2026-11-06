"""Memory of this process, in MB: the current resident size (used to stop an extraction that grows too much) and the peak."""

from __future__ import annotations

import sys


def rss_mb() -> int:
    """Resident size now, in MB. 0 when it cannot be read (the guard then does nothing rather than stopping on a guess)."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            c = Counters()
            c.cb = ctypes.sizeof(c)
            ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(ctypes.windll.kernel32.GetCurrentProcess()), ctypes.byref(c), c.cb)
            return int(c.WorkingSetSize / (1024 * 1024))
        if sys.platform.startswith("linux"):
            with open("/proc/self/statm", encoding="ascii") as f:
                pages = int(f.read().split()[1])
            import os
            return int(pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024))
        import resource  # macOS: only the peak is available
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024))
    except Exception:
        return 0


def peak_mb() -> int:
    """Highest resident size reached so far, in MB."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        c = Counters()
        c.cb = ctypes.sizeof(c)
        ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(ctypes.windll.kernel32.GetCurrentProcess()), ctypes.byref(c), c.cb)
        return int(c.PeakWorkingSetSize / (1024 * 1024))
    import resource
    kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(kb / 1024 / (1024 if sys.platform == "darwin" else 1))
