"""Wake task definition: shape, guard rails, and no implicit registration."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.runtime import windows_tasks


def test_wake_task_declares_wake_and_least_privilege():
    task = windows_tasks.build_wake_task(
        Path(r"C:\Program Files\CareerLens\CareerLens.exe"),
        interval_minutes=30,
        now=datetime(2026, 11, 28, 12, 0, tzinfo=UTC),
    )
    xml = task.xml
    assert "<WakeToRun>true</WakeToRun>" in xml
    assert "<RunLevel>LeastPrivilege</RunLevel>" in xml
    assert "<LogonType>InteractiveToken</LogonType>" in xml
    assert "<Interval>PT30M</Interval>" in xml
    # The action starts the real host, not a one-shot reconciler: waking the
    # machine must lead to a process that can execute the due plan.
    assert "<Arguments>--autostart</Arguments>" in xml
    assert "CareerLens.exe" in xml
    assert task.arguments == "--autostart"


def test_start_boundary_is_in_the_future_and_minute_aligned():
    now = datetime(2026, 11, 28, 12, 0, 30, tzinfo=UTC)
    task = windows_tasks.build_wake_task(Path("C:/app/CareerLens.exe"), now=now)
    boundary = task.xml.split("<StartBoundary>")[1].split("</StartBoundary>")[0]
    parsed = datetime.fromisoformat(boundary)
    assert parsed.second == 0
    assert parsed.replace(tzinfo=UTC) > now.replace(microsecond=0)


@pytest.mark.parametrize("minutes", [4, 24 * 60 + 1])
def test_interval_is_bounded(minutes):
    with pytest.raises(windows_tasks.WakeTaskError):
        windows_tasks.build_wake_task(Path("C:/app/CareerLens.exe"), interval_minutes=minutes)


def test_registration_requires_confirmation(tmp_path):
    task = windows_tasks.build_wake_task(tmp_path / "CareerLens.exe")
    with pytest.raises(windows_tasks.WakeTaskError):
        windows_tasks.register(task)
    with pytest.raises(windows_tasks.WakeTaskError):
        windows_tasks.unregister()


def test_registration_is_windows_only(tmp_path, monkeypatch):
    task = windows_tasks.build_wake_task(tmp_path / "CareerLens.exe")
    monkeypatch.setattr(windows_tasks.sys, "platform", "linux")
    assert windows_tasks.supported() is False
    with pytest.raises(windows_tasks.WakeTaskError):
        windows_tasks.register(task, confirm=True)


def test_xml_escapes_the_command_path(tmp_path):
    task = windows_tasks.build_wake_task(tmp_path / "A & B" / "CareerLens.exe")
    assert "A &amp; B" in task.xml


def test_supported_matches_platform():
    assert windows_tasks.supported() is (sys.platform == "win32")


def test_default_interval_is_half_hour():
    task = windows_tasks.build_wake_task(Path("C:/app/CareerLens.exe"))
    assert task.interval_minutes == 30
    assert timedelta(minutes=task.interval_minutes) == timedelta(minutes=30)
