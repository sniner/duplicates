from pathlib import Path

import pytest

from duplicates import DupFinder, FileEntry


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    _write(tmp_path / "a/file1.txt", b"hello world")
    _write(tmp_path / "a/file1.bak", b"hello world")
    _write(tmp_path / "b/copy.txt", b"hello world")
    _write(tmp_path / "b/unique.txt", b"only one of me")
    _write(tmp_path / "a/other.txt", b"different content")
    _write(tmp_path / "b/other.bak", b"different content")
    _write(tmp_path / "a/solo.bin", b"\x00\x01\x02")
    return tmp_path


def _paths(entries: list[FileEntry]) -> set[Path]:
    return {e.path for e in entries}


def test_finds_duplicates_across_directories(tree: Path) -> None:
    uniq, dups = DupFinder().scan(tree)

    dup_paths = [_paths(group) for group in dups]
    assert {
        tree / "a/file1.txt",
        tree / "a/file1.bak",
        tree / "b/copy.txt",
    } in dup_paths
    assert {
        tree / "a/other.txt",
        tree / "b/other.bak",
    } in dup_paths

    assert _paths(uniq) == {
        tree / "b/unique.txt",
        tree / "a/solo.bin",
    }


def test_all_entries_carry_size_and_age(tree: Path) -> None:
    uniq, dups = DupFinder().scan(tree)
    everything = uniq + [e for group in dups for e in group]
    for entry in everything:
        assert entry.size >= 0
        assert entry.age > 0


def test_duplicates_have_matching_hashes(tree: Path) -> None:
    _, dups = DupFinder().scan(tree)
    for group in dups:
        hashes = {e.hash for e in group}
        assert len(hashes) == 1
        assert next(iter(hashes)) is not None


def test_empty_files_are_never_duplicates(tmp_path: Path) -> None:
    _write(tmp_path / "empty1", b"")
    _write(tmp_path / "empty2", b"")
    _write(tmp_path / "empty3", b"")

    uniq, dups = DupFinder().scan(tmp_path)

    assert dups == []
    assert len(uniq) == 3


def test_hidden_files_ignored_by_default(tmp_path: Path) -> None:
    _write(tmp_path / ".hidden", b"secret")
    _write(tmp_path / "visible", b"secret")

    uniq, _ = DupFinder().scan(tmp_path)
    assert _paths(uniq) == {tmp_path / "visible"}


def test_hidden_files_included_when_requested(tmp_path: Path) -> None:
    _write(tmp_path / ".hidden", b"secret")
    _write(tmp_path / "visible", b"secret")

    _, dups = DupFinder(ignore_hidden=False).scan(tmp_path)
    assert len(dups) == 1
    assert _paths(dups[0]) == {tmp_path / ".hidden", tmp_path / "visible"}


def test_symlinks_ignored_by_default(tmp_path: Path) -> None:
    target = _write(tmp_path / "target.txt", b"payload")
    (tmp_path / "link.txt").symlink_to(target)

    uniq, dups = DupFinder().scan(tmp_path)
    assert dups == []
    assert _paths(uniq) == {target}


def test_symlinks_followed_when_requested(tmp_path: Path) -> None:
    target = _write(tmp_path / "target.txt", b"payload")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    _, dups = DupFinder(ignore_symlinks=False).scan(tmp_path)
    assert len(dups) == 1
    assert _paths(dups[0]) == {target, link}


def test_missing_path_is_silently_skipped(tmp_path: Path) -> None:
    real = _write(tmp_path / "x", b"data")

    uniq, dups = DupFinder().scan(tmp_path / "nope", real)

    assert dups == []
    assert _paths(uniq) == {real}


def test_single_file_argument_works(tmp_path: Path) -> None:
    f = _write(tmp_path / "lone", b"once")
    uniq, dups = DupFinder().scan(f)
    assert dups == []
    assert _paths(uniq) == {f}
