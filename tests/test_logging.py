import logging
from pathlib import Path

import pytest

from duplicates import DupFinder
from duplicates.dupfinder import _human_size, _Progress

LOGGER = "duplicates.dupfinder"


class TestHumanSize:
    @pytest.mark.parametrize(
        "n,expected",
        [
            (0, "0.0 B"),
            (512, "512.0 B"),
            (1024, "1.0 KiB"),
            (1536, "1.5 KiB"),
            (5 * 1024 * 1024, "5.0 MiB"),
            (3 * 1024**3, "3.0 GiB"),
            (2 * 1024**4, "2.0 TiB"),
        ],
    )
    def test_formatting(self, n: int, expected: str) -> None:
        assert _human_size(n) == expected


class TestProgressThrottle:
    def test_warmup_suppresses_first_call(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger=LOGGER)
        p = _Progress(interval=0.01, warmup=10.0)
        p.tick("should not appear")
        assert "should not appear" not in caplog.text

    def test_emits_after_warmup(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger=LOGGER)
        # Negative warmup → next_emit is in the past → first tick emits.
        p = _Progress(interval=10.0, warmup=-1.0)
        p.tick("first")
        p.tick("second")
        # Second tick is inside the next 10 s interval — suppressed.
        assert "first" in caplog.text
        assert "second" not in caplog.text


class TestPhaseMarkers:
    def test_scan_emits_phase_markers(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / "a").write_bytes(b"same")
        (tmp_path / "b").write_bytes(b"same")
        caplog.set_level(logging.INFO, logger=LOGGER)

        DupFinder().scan(tmp_path)

        text = caplog.text
        assert "Scanning 1 path(s)" in text
        assert "Discovered 2 file(s)" in text
        assert "Full-hashing 2 file(s)" in text

    def test_no_hash_phase_when_no_candidates(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Different sizes → no hash phase at all.
        (tmp_path / "a").write_bytes(b"x")
        (tmp_path / "b").write_bytes(b"xy")
        caplog.set_level(logging.INFO, logger=LOGGER)

        DupFinder().scan(tmp_path)

        text = caplog.text
        assert "Partial-hashing" not in text
        assert "Full-hashing" not in text


class TestPerFileHashLog:
    def test_full_hash_logs_path_and_size(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        a.write_bytes(b"matching")
        b.write_bytes(b"matching")
        caplog.set_level(logging.INFO, logger=LOGGER)

        DupFinder().scan(tmp_path)

        msgs = [r.message for r in caplog.records]
        assert any("Full-hashing" in m and str(a) in m and "8.0 B" in m for m in msgs)
        assert any("Full-hashing" in m and str(b) in m and "8.0 B" in m for m in msgs)


class TestQuietByDefault:
    def test_ignored_entries_are_debug_not_info(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Hidden files + a symlink: both used to spam at INFO; they now log
        # at DEBUG and stay out of --verbose output.
        (tmp_path / "regular").write_bytes(b"x")
        (tmp_path / ".hidden").write_bytes(b"x")
        (tmp_path / "link").symlink_to(tmp_path / "regular")
        caplog.set_level(logging.INFO, logger=LOGGER)

        DupFinder().scan(tmp_path)

        text = caplog.text
        assert "Ignoring symlink" not in text
        assert "Ignoring hidden" not in text
