"""Unit tests for dex_studio.utils formatting helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from dex_studio.utils import (
    fmt_bytes,
    fmt_cron,
    fmt_run_row,
    fmt_ts,
    fmt_ts_iso,
    status_color,
)


class TestFmtTs:
    def test_utc_iso_string_converts_to_local(self) -> None:
        ts = "2026-01-15T12:00:00+00:00"
        result = fmt_ts(ts)
        assert result != "—"
        assert ":" in result  # has time component

    def test_z_suffix_handled(self) -> None:
        ts = "2026-01-15T12:00:00Z"
        result = fmt_ts(ts)
        assert result != "—"

    def test_none_returns_dash(self) -> None:
        assert fmt_ts(None) == "—"

    def test_empty_string_returns_dash(self) -> None:
        assert fmt_ts("") == "—"

    def test_dash_returns_dash(self) -> None:
        assert fmt_ts("-") == "—"

    def test_invalid_string_returns_dash(self) -> None:
        assert fmt_ts("not-a-date") == "—"

    def test_format_contains_month_and_time(self) -> None:
        ts = "2026-06-15T14:30:00+00:00"
        result = fmt_ts(ts)
        # Result is "Mon DD HH:MM" in local time — check colon exists
        assert ":" in result
        assert len(result) > 5


class TestFmtTsIso:
    def test_utc_iso_returns_local_formatted(self) -> None:
        ts = "2026-01-15T12:00:00+00:00"
        result = fmt_ts_iso(ts)
        assert result != "—"
        assert "-" in result
        assert ":" in result

    def test_none_returns_dash(self) -> None:
        assert fmt_ts_iso(None) == "—"

    def test_format_is_yyyy_mm_dd_hh_mm(self) -> None:
        ts = "2026-06-15T00:00:00+00:00"
        result = fmt_ts_iso(ts)
        # "YYYY-MM-DD HH:MM"
        parts = result.split(" ")
        assert len(parts) == 2
        date_part, time_part = parts
        assert len(date_part) == 10
        assert date_part.count("-") == 2
        assert len(time_part) == 5
        assert time_part.count(":") == 1

    def test_z_suffix_handled(self) -> None:
        ts = "2026-06-15T10:30:00Z"
        result = fmt_ts_iso(ts)
        assert result != "—"


class TestFmtCron:
    def test_hourly_shortcut(self) -> None:
        assert fmt_cron("@hourly") == "Hourly"

    def test_daily_shortcut(self) -> None:
        assert fmt_cron("@daily") == "Daily"

    def test_weekly_shortcut(self) -> None:
        assert fmt_cron("@weekly") == "Weekly"

    def test_monthly_shortcut(self) -> None:
        assert fmt_cron("@monthly") == "Monthly"

    def test_every_5_min(self) -> None:
        assert fmt_cron("*/5 * * * *") == "Every 5 min"

    def test_every_2_hours(self) -> None:
        assert fmt_cron("0 */2 * * *") == "Every 2 hours"

    def test_daily_midnight(self) -> None:
        assert fmt_cron("0 0 * * *") == "Daily at midnight"

    def test_weekly_sunday(self) -> None:
        assert fmt_cron("0 0 * * 0") == "Weekly (Sun)"

    def test_custom_expression_passthrough(self) -> None:
        expr = "15 3 * * 1"
        assert fmt_cron(expr) == expr

    def test_empty_returns_dash(self) -> None:
        assert fmt_cron("") == "—"

    def test_dash_returns_dash(self) -> None:
        assert fmt_cron("—") == "—"


class TestFmtBytes:
    def test_none_returns_dash(self) -> None:
        assert fmt_bytes(None) == "—"

    def test_bytes(self) -> None:
        assert fmt_bytes(512) == "512.0 B"

    def test_kilobytes(self) -> None:
        assert fmt_bytes(2048) == "2.0 KB"

    def test_megabytes(self) -> None:
        assert fmt_bytes(5 * 1024 * 1024) == "5.0 MB"

    def test_gigabytes(self) -> None:
        assert fmt_bytes(3 * 1024 * 1024 * 1024) == "3.0 GB"


class TestFmtRunRow:
    def _make_run(
        self, pipeline_name: str = "test", success: bool = True, duration_ms: float | None = 500.0
    ) -> MagicMock:
        r = MagicMock()
        r.pipeline_name = pipeline_name
        r.success = success
        r.duration_ms = duration_ms
        r.timestamp = "2026-06-15T12:00:00+00:00"
        return r

    def test_success_run(self) -> None:
        row = fmt_run_row(self._make_run(success=True))
        assert row["status"] == "success"
        assert row["name"] == "test"
        assert row["type"] == "pipeline"

    def test_failed_run(self) -> None:
        row = fmt_run_row(self._make_run(success=False))
        assert row["status"] == "error"

    def test_duration_ms_formatted(self) -> None:
        row = fmt_run_row(self._make_run(duration_ms=1500.0))
        assert row["duration"] == "1.5s"

    def test_duration_ms_sub_second(self) -> None:
        row = fmt_run_row(self._make_run(duration_ms=250.0))
        assert row["duration"] == "250ms"

    def test_duration_none_is_dash(self) -> None:
        row = fmt_run_row(self._make_run(duration_ms=None))
        assert row["duration"] == "—"

    def test_extra_fields_merged(self) -> None:
        row = fmt_run_row(self._make_run(), trigger="manual", io="10 rows")
        assert row["trigger"] == "manual"
        assert row["io"] == "10 rows"

    def test_started_field_is_formatted_timestamp(self) -> None:
        row = fmt_run_row(self._make_run())
        assert row["started"] != "—"
        assert "-" in row["started"] or ":" in row["started"]


class TestStatusColor:
    def test_ok_states(self) -> None:
        for s in ("ok", "healthy", "active", "success", "available", "production", "passed"):
            assert status_color(s) == "green"

    def test_warning_states(self) -> None:
        for s in ("warning", "warn", "staging", "running"):
            assert status_color(s) == "orange"

    def test_error_states(self) -> None:
        for s in ("error", "failed", "failure", "offline", "critical"):
            assert status_color(s) == "red"

    def test_unknown_returns_gray(self) -> None:
        assert status_color("unknown") == "gray"
        assert status_color("") == "gray"

    def test_case_insensitive(self) -> None:
        assert status_color("SUCCESS") == "green"
        assert status_color("ERROR") == "red"
