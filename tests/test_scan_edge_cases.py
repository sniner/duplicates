import os
from pathlib import Path

import pytest

from duplicates import DupFinder


def _paths(entries: list) -> set[Path]:
    return {e.path for e in entries}


def test_deep_directory_tree_does_not_recurse(tmp_path: Path) -> None:
    # Build a 200-level nested tree. The previous recursive implementation
    # would have hit sys.getrecursionlimit(); the iterative one must not.
    current = tmp_path
    for i in range(200):
        current = current / f"level{i}"
        current.mkdir()
    (current / "deep.txt").write_bytes(b"payload")
    (tmp_path / "shallow.txt").write_bytes(b"payload")

    uniq, dups, unreadable = DupFinder().scan(tmp_path)

    assert unreadable == []
    assert len(dups) == 1
    assert _paths(dups[0]) == {current / "deep.txt", tmp_path / "shallow.txt"}
    assert uniq == []


def test_symlink_cycle_with_follow_terminates(tmp_path: Path) -> None:
    inner = tmp_path / "inner"
    inner.mkdir()
    (inner / "data.txt").write_bytes(b"payload")
    # A symlink inside `inner` pointing back to `inner` would loop forever
    # without cycle detection.
    (inner / "back").symlink_to(inner)

    uniq, dups, unreadable = DupFinder(ignore_symlinks=False).scan(tmp_path)

    assert unreadable == []
    assert dups == []
    assert _paths(uniq) == {inner / "data.txt"}


@pytest.mark.skipif(os.geteuid() == 0, reason="chmod 000 has no effect for root")
def test_unreadable_file_appears_in_unreadable_list(tmp_path: Path) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(b"same content")
    b.write_bytes(b"same content")
    # Same size as a/b so the file becomes a fingerprint candidate.
    locked = tmp_path / "locked.bin"
    locked.write_bytes(b"same content")
    locked.chmod(0o000)

    try:
        uniq, dups, unreadable = DupFinder().scan(tmp_path)
    finally:
        locked.chmod(0o644)

    assert _paths(unreadable) == {locked}
    # a and b should still be detected as duplicates.
    assert len(dups) == 1
    assert _paths(dups[0]) == {a, b}


def test_broken_symlink_does_not_crash_when_following(tmp_path: Path) -> None:
    (tmp_path / "real.txt").write_bytes(b"data")
    (tmp_path / "broken").symlink_to(tmp_path / "does-not-exist")

    uniq, dups, unreadable = DupFinder(ignore_symlinks=False).scan(tmp_path)

    assert unreadable == []
    assert dups == []
    assert _paths(uniq) == {tmp_path / "real.txt"}
