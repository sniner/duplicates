from pathlib import Path

from duplicates import DupFinder, FileEntry

# Chosen so files are above the module's _PARTIAL_THRESHOLD (64 KiB) and the
# head/tail windows (4 KiB each) don't overlap or touch the middle marker.
LARGE = 70_000
SMALL = 1024


def _payload(
    size: int,
    *,
    head: bytes = b"",
    tail: bytes = b"",
    middle_offset: int | None = None,
    middle: bytes = b"",
) -> bytes:
    buf = bytearray(size)
    buf[: len(head)] = head
    if tail:
        buf[size - len(tail) :] = tail
    if middle_offset is not None and middle:
        buf[middle_offset : middle_offset + len(middle)] = middle
    return bytes(buf)


def _paths(entries: list[FileEntry]) -> set[Path]:
    return {e.path for e in entries}


def test_partial_separates_files_with_different_head(tmp_path: Path) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(_payload(LARGE, head=b"AAAA"))
    b.write_bytes(_payload(LARGE, head=b"BBBB"))

    uniq, dups, unreadable = DupFinder().scan(tmp_path)

    assert dups == []
    assert _paths(uniq) == {a, b}
    assert unreadable == []


def test_partial_separates_files_with_different_tail(tmp_path: Path) -> None:
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(_payload(LARGE, head=b"AAAA", tail=b"XXXX"))
    b.write_bytes(_payload(LARGE, head=b"AAAA", tail=b"YYYY"))

    uniq, dups, unreadable = DupFinder().scan(tmp_path)

    assert dups == []
    assert _paths(uniq) == {a, b}


def test_full_hash_resolves_partial_collision(tmp_path: Path) -> None:
    # Same head and tail; only a byte deep in the middle differs.
    # The partial pass keeps these together; the full SHA-256 must split them.
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(
        _payload(LARGE, head=b"AAAA", tail=b"ZZZZ", middle_offset=30_000, middle=b"X")
    )
    b.write_bytes(
        _payload(LARGE, head=b"AAAA", tail=b"ZZZZ", middle_offset=30_000, middle=b"Y")
    )

    uniq, dups, unreadable = DupFinder().scan(tmp_path)

    assert dups == []
    assert _paths(uniq) == {a, b}


def test_large_duplicates_are_detected(tmp_path: Path) -> None:
    payload = _payload(
        LARGE, head=b"AAAA", tail=b"ZZZZ", middle_offset=30_000, middle=b"M"
    )
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    a.write_bytes(payload)
    b.write_bytes(payload)

    uniq, dups, unreadable = DupFinder().scan(tmp_path)

    assert len(dups) == 1
    assert _paths(dups[0]) == {a, b}
    assert uniq == []
    # Confirmed duplicates carry a persisted full hash.
    for entry in dups[0]:
        assert entry.hash is not None
        assert len(entry.hash) == 64  # SHA-256 hex digest


def test_small_files_skip_partial_and_are_still_grouped(tmp_path: Path) -> None:
    # Both files are below _PARTIAL_THRESHOLD, so the partial pass is bypassed
    # and the full hash decides directly. A third same-size file with different
    # content must end up in uniq.
    same = _payload(SMALL, head=b"shared")
    other = _payload(SMALL, head=b"unique-content")
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    c = tmp_path / "c.bin"
    a.write_bytes(same)
    b.write_bytes(same)
    c.write_bytes(other)

    uniq, dups, unreadable = DupFinder().scan(tmp_path)

    assert len(dups) == 1
    assert _paths(dups[0]) == {a, b}
    assert _paths(uniq) == {c}
