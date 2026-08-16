"""
Process lock manager to prevent concurrent batch automation runs.
"""
import os
import json
import time
from pathlib import Path
from typing import Optional

class LockAcquisitionError(RuntimeError):
    """Raised when another automation instance is already running."""
    pass

class ProcessLock:
    def __init__(self, lock_file: Optional[Path] = None):
        if lock_file is None:
            base_dir = Path(__file__).parent.parent.resolve()
            self.lock_file = base_dir / "automation.lock"
        else:
            self.lock_file = lock_file
        self.acquired = False

    def _is_process_alive(self, pid: int) -> bool:
        """Check if process with given PID is still running on Windows/Unix."""
        if pid <= 0:
            return False
        try:
            if os.name == 'nt':
                # Windows check using OpenProcess query
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                SYNCHRONIZE = 0x00100000
                handle = ctypes.windll.kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid
                )
                if handle == 0:
                    return False
                # Check exit code
                exit_code = ctypes.c_ulong()
                ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                ctypes.windll.kernel32.CloseHandle(handle)
                # STILL_ACTIVE = 259
                return exit_code.value == 259
            else:
                os.kill(pid, 0)
                return True
        except Exception:
            return False

    def acquire(self) -> None:
        """Acquire the lock or raise LockAcquisitionError."""
        if self.lock_file.exists():
            try:
                with open(self.lock_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                locked_pid = data.get("pid")
                if locked_pid and self._is_process_alive(locked_pid):
                    raise LockAcquisitionError(
                        f"Another generation job is already running (PID: {locked_pid}, started: {data.get('time')})."
                    )
            except (json.JSONDecodeError, OSError):
                # Malformed or stale lock, can overwrite
                pass

        # Write current process info atomically
        lock_data = {
            "pid": os.getpid(),
            "time": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        try:
            temp_file = self.lock_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(lock_data, f, indent=2)
            temp_file.replace(self.lock_file)
            self.acquired = True
        except Exception as e:
            raise LockAcquisitionError(f"Could not create lock file: {e}")

    def release(self) -> None:
        """Release the lock if acquired."""
        if self.acquired and self.lock_file.exists():
            try:
                self.lock_file.unlink(missing_ok=True)
            except OSError:
                pass
            self.acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
