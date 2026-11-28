"""Windows wake timer registration (M2 leftover), code-only.

Why this exists: durable schedules only fire while a scheduler process is
alive. Autostart handles "after login"; this handles "the machine is asleep at
the due time". Windows exposes that through Task Scheduler's ``WakeToRun``.

Design constraints:
- Never registered implicitly. ``register()`` requires ``confirm=True`` and a
  Windows host; there is no code path from app startup to registration.
- Runs as the interactive user with least privilege, not as SYSTEM and not with
  ``HighestAvailable``: a wake task that needs elevation cannot start silently
  and would be invisible in the user's Task Scheduler.
- The action starts the desktop host with ``--autostart`` so it lands in the
  tray and the scheduler can actually execute the due plan. Waking the machine
  and only reconciling would enqueue runs nobody can run.
- Battery behaviour is permissive (``DisallowStartIfOnBatteries=false``) because
  a laptop on battery is the normal case for a personal career assistant.

Verified here: XML shape and guard rails. Not verified: a real sleep/wake cycle,
DST transitions, or behaviour when the user is logged out. Those need a real
machine and are listed as gaps.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

TASK_NAME = "CareerLens Wake"
DEFAULT_INTERVAL_MINUTES = 30


class WakeTaskError(RuntimeError):
    """Registration refused or failed."""


@dataclass(frozen=True)
class WakeTask:
    name: str
    command: str
    arguments: str
    interval_minutes: int
    xml: str


def _start_boundary(now: datetime | None = None) -> str:
    moment = (now or datetime.now(UTC)).astimezone()
    # Round up to the next minute so the task never starts in the past.
    moment = (moment + timedelta(minutes=1)).replace(second=0, microsecond=0)
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def build_wake_task(
    exe: Path,
    *,
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    name: str = TASK_NAME,
    now: datetime | None = None,
) -> WakeTask:
    """Build the WakeToRun task definition. Pure: no I/O, no registration."""

    if interval_minutes < 5 or interval_minutes > 24 * 60:
        raise WakeTaskError("interval_minutes must be between 5 and 1440")
    if not str(exe).strip():
        raise WakeTaskError("exe path is required")
    command = str(exe)
    arguments = "--autostart"
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>CareerLens</Author>
    <Description>Wakes the machine so due career plans can run.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{_start_boundary(now)}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
      <Repetition>
        <Interval>PT{interval_minutes}M</Interval>
        <Duration>P1D</Duration>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(command)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
    </Exec>
  </Actions>
</Task>
"""
    return WakeTask(
        name=name,
        command=command,
        arguments=arguments,
        interval_minutes=interval_minutes,
        xml=xml,
    )


def supported() -> bool:
    return sys.platform == "win32"


def register(task: WakeTask, *, confirm: bool = False) -> None:
    """Create/replace the task. Refuses unless the caller explicitly confirms."""

    if not confirm:
        raise WakeTaskError("registration requires explicit confirmation")
    if not supported():
        raise WakeTaskError("wake tasks are only supported on Windows")
    path = Path(tempfile_path())
    # schtasks reads UTF-16 XML; write it as such to avoid mojibake in names.
    path.write_text(task.xml, encoding="utf-16")
    try:
        completed = subprocess.run(
            ["schtasks", "/Create", "/TN", task.name, "/XML", str(path), "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        path.unlink(missing_ok=True)
    if completed.returncode != 0:
        raise WakeTaskError(
            (completed.stderr or completed.stdout or "schtasks failed").strip()
        )


def unregister(*, name: str = TASK_NAME, confirm: bool = False) -> None:
    if not confirm:
        raise WakeTaskError("unregistration requires explicit confirmation")
    if not supported():
        raise WakeTaskError("wake tasks are only supported on Windows")
    subprocess.run(
        ["schtasks", "/Delete", "/TN", name, "/F"], capture_output=True, check=False
    )


def tempfile_path() -> str:
    from tempfile import gettempdir

    return str(Path(gettempdir()) / "careerlens-wake-task.xml")
