"""
Unit tests for single-instance process lock mechanism.
"""
import pytest
from pathlib import Path
from automation.lock import ProcessLock, LockAcquisitionError

def test_lock_acquire_and_release(tmp_path: Path):
    lock_file = tmp_path / "test.lock"
    lock = ProcessLock(lock_file)

    assert not lock_file.exists()
    lock.acquire()
    assert lock_file.exists()

    lock.release()
    assert not lock_file.exists()

def test_lock_context_manager(tmp_path: Path):
    lock_file = tmp_path / "test.lock"

    with ProcessLock(lock_file):
        assert lock_file.exists()

    assert not lock_file.exists()

def test_lock_conflict_detection(tmp_path: Path):
    lock_file = tmp_path / "test.lock"
    lock1 = ProcessLock(lock_file)
    lock1.acquire()

    lock2 = ProcessLock(lock_file)
    with pytest.raises(LockAcquisitionError):
        lock2.acquire()

    lock1.release()
    # Now lock2 should be able to acquire
    lock2.acquire()
    assert lock_file.exists()
    lock2.release()
