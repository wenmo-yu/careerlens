"""Windows AppContainer sandbox for the agent CLI / MCP executor (T14/T16).

The agent CLI is a local process, but "local" is not a security boundary: a
prompt-injected tool call must not be able to read the user's SSH keys, rewrite
the registry, or phone home. This module runs a child inside an AppContainer
with no capabilities:

- no ``internetClient``: outbound network is denied by the OS, not by us;
- filesystem access only where we explicitly grant the container SID;
- no registry writes to the user hive;
- loopback is exempted per-SID so the CLI can still reach the local API.

Scope: this is the *execution* boundary. Admission policy (which tools may run)
lives in ``mcp_connectors``; approval/idempotency lives in ``tool_ledger``.

Only one-shot execution is implemented (blocking, output to temp files). The
scheduler's persistent JSONL CLI needs pipe inheritance and is not wired here
yet; see ``docs/adr/0029-appcontainer-sandbox.md`` for the exact gap.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

PROFILE = "careerlens-agent"
DEFAULT_TIMEOUT_SECONDS = 30

ERROR_ALREADY_EXISTS = 183


class SandboxUnavailable(RuntimeError):
    """The sandbox cannot be created on this host."""


@dataclass(frozen=True)
class SandboxResult:
    ok: bool
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "stdout": self.stdout[-4000:],
            "stderr": self.stderr[-4000:],
            "timed_out": self.timed_out,
        }


def supported() -> bool:
    return sys.platform == "win32"


# --- SID / profile ------------------------------------------------------------


def _userenv():
    dll = ctypes.WinDLL("userenv", use_last_error=True)
    if not getattr(dll, "_careerlens_typed", False):
        dll.CreateAppContainerProfile.restype = ctypes.c_long
        dll.CreateAppContainerProfile.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        dll.DeriveAppContainerSidFromAppContainerName.restype = ctypes.c_long
        dll.DeriveAppContainerSidFromAppContainerName.argtypes = [
            ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        dll.DeleteAppContainerProfile.restype = ctypes.c_long
        dll.DeleteAppContainerProfile.argtypes = [ctypes.c_wchar_p]
        dll._careerlens_typed = True
    return dll


def _advapi32():
    dll = ctypes.WinDLL("advapi32", use_last_error=True)
    if not getattr(dll, "_careerlens_typed", False):
        dll.ConvertSidToStringSidW.restype = ctypes.c_int
        dll.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
        dll.ConvertStringSidToSidW.restype = ctypes.c_int
        dll.ConvertStringSidToSidW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)]
        dll.FreeSid.restype = ctypes.c_void_p
        dll.FreeSid.argtypes = [ctypes.c_void_p]
        dll.GetNamedSecurityInfoW.restype = ctypes.c_long
        dll.GetNamedSecurityInfoW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        dll.SetEntriesInAclW.restype = ctypes.c_long
        dll.SetEntriesInAclW.argtypes = [
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        dll.SetNamedSecurityInfoW.restype = ctypes.c_long
        dll.SetNamedSecurityInfoW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        dll._careerlens_typed = True
    return dll


def _kernel32():
    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    if not getattr(dll, "_careerlens_typed", False):
        from ctypes import wintypes

        dll.CreateFileW.restype = wintypes.HANDLE
        dll.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        dll.CreateProcessW.restype = wintypes.BOOL
        dll.CreateProcessW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        for name in ("WaitForSingleObject",):
            getattr(dll, name).restype = wintypes.DWORD
            getattr(dll, name).argtypes = [wintypes.HANDLE, wintypes.DWORD]
        dll.GetExitCodeProcess.restype = wintypes.BOOL
        dll.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        dll.TerminateProcess.restype = wintypes.BOOL
        dll.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        dll.CloseHandle.restype = wintypes.BOOL
        dll.CloseHandle.argtypes = [wintypes.HANDLE]
        dll.LocalFree.restype = ctypes.c_void_p
        dll.LocalFree.argtypes = [ctypes.c_void_p]
        dll.InitializeProcThreadAttributeList.restype = wintypes.BOOL
        dll.InitializeProcThreadAttributeList.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        dll.UpdateProcThreadAttribute.restype = wintypes.BOOL
        dll.UpdateProcThreadAttribute.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        dll.DeleteProcThreadAttributeList.restype = None
        dll.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
        dll._careerlens_typed = True
    return dll


def _check_hresult(result: int, action: str) -> None:
    # S_OK is 0; S_FALSE (1) means "already exists" for profile creation.
    if result not in (0, 1):
        raise SandboxUnavailable(f"{action} failed with HRESULT 0x{result & 0xFFFFFFFF:08X}")


def _call(*args: str) -> subprocess.CompletedProcess:
    """Run a Windows CLI tool and decode its (localized) output safely."""

    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def sid_to_string(sid: int) -> str:
    advapi32 = _advapi32()
    converted = ctypes.c_wchar_p()
    if not advapi32.ConvertSidToStringSidW(ctypes.c_void_p(sid), ctypes.byref(converted)):
        raise SandboxUnavailable(f"ConvertSidToStringSidW failed: {ctypes.get_last_error()}")
    try:
        return str(converted.value)
    finally:
        _kernel32().LocalFree(converted)


def derive_sid(name: str = PROFILE) -> str | None:
    """Return the container SID as a string, or None if the profile is absent."""

    sid = ctypes.c_void_p()
    result = _userenv().DeriveAppContainerSidFromAppContainerName(
        ctypes.c_wchar_p(name), ctypes.byref(sid)
    )
    if result != 0 or not sid:
        return None
    try:
        return sid_to_string(sid.value)
    finally:
        _advapi32().FreeSid(ctypes.c_void_p(sid.value))


def ensure_profile(name: str = PROFILE) -> str:
    """Create the AppContainer profile if needed and return its SID."""

    if not supported():
        raise SandboxUnavailable("AppContainer is Windows-only")
    sid = ctypes.c_void_p()
    userenv = _userenv()
    result = userenv.CreateAppContainerProfile(
        ctypes.c_wchar_p(name),
        ctypes.c_wchar_p("CareerLens Agent"),
        ctypes.c_wchar_p("Sandbox for the CareerLens agent CLI and MCP tools"),
        None,
        0,
        ctypes.byref(sid),
    )
    if result == 1 and not sid:
        # Already existed but no SID was returned; derive it instead.
        derived = derive_sid(name)
        if derived is None:
            raise SandboxUnavailable("profile exists but its SID cannot be derived")
        return derived
    if (result & 0xFFFFFFFF) == 0x800700B7:  # ERROR_ALREADY_EXISTS as HRESULT
        derived = derive_sid(name)
        if derived is None:
            raise SandboxUnavailable("profile exists but its SID cannot be derived")
        return derived
    _check_hresult(result, "CreateAppContainerProfile")
    try:
        return sid_to_string(sid.value)
    finally:
        if sid:
            _advapi32().FreeSid(ctypes.c_void_p(sid.value))


def delete_profile(name: str = PROFILE) -> bool:
    if not supported():
        return False
    result = _userenv().DeleteAppContainerProfile(ctypes.c_wchar_p(name))
    return result == 0


# --- ACL / loopback -----------------------------------------------------------


def grant(path: Path, sid: str, *, permissions: str = "(OI)(CI)(RX)") -> None:
    """Give the container read/execute on a directory (or file)."""

    completed = _call("icacls", str(path), "/grant", f"*{sid}:{permissions}")
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise SandboxUnavailable(f"icacls grant failed for {path}: {detail}")


def has_grant(path: Path, sid: str) -> bool:
    """Whether the container SID already has an ACE on this path."""

    completed = _call("icacls", str(path))
    return sid in (completed.stdout or "")


class _TRUSTEE_W(ctypes.Structure):
    _fields_ = [
        ("pMultipleTrustee", ctypes.c_void_p),
        ("MultipleTrusteeOperation", ctypes.c_int),
        ("TrusteeForm", ctypes.c_int),
        ("TrusteeType", ctypes.c_int),
        ("ptstrName", ctypes.c_void_p),
    ]


class _EXPLICIT_ACCESS_W(ctypes.Structure):
    _fields_ = [
        ("grfAccessPermissions", ctypes.c_ulong),
        ("grfAccessMode", ctypes.c_int),
        ("grfInheritance", ctypes.c_ulong),
        ("Trustee", _TRUSTEE_W),
    ]


FILE_TRAVERSE = 0x00000020
FILE_READ_ATTRIBUTES = 0x00000080
GRANT_ACCESS = 1
NO_INHERITANCE = 0
TRUSTEE_IS_SID = 0
TRUSTEE_IS_UNKNOWN = 0
SE_FILE_OBJECT = 1
DACL_SECURITY_INFORMATION = 0x00000004


def add_traverse_ace(path: Path, sid: str) -> bool:
    """Add a non-inheriting traverse ACE via the ACL API.

    ``icacls /grant`` on a directory with a huge tree (``D:/work``,
    ``node_modules``) can sit for minutes because it also walks inherited ACEs.
    ``SetNamedSecurityInfoW`` with a single ``NO_INHERITANCE`` ACE does exactly
    one object and returns immediately, which is what a traverse grant needs.
    """

    if not supported():
        raise SandboxUnavailable("AppContainer is Windows-only")
    advapi32 = _advapi32()
    kernel32 = _kernel32()
    sid_ptr = ctypes.c_void_p()
    if not advapi32.ConvertStringSidToSidW(ctypes.c_wchar_p(sid), ctypes.byref(sid_ptr)):
        raise SandboxUnavailable("ConvertStringSidToSidW failed")

    old_dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    try:
        status = advapi32.GetNamedSecurityInfoW(
            ctypes.c_wchar_p(str(path)),
            SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION,
            None,
            None,
            ctypes.byref(old_dacl),
            None,
            ctypes.byref(descriptor),
        )
        if status != 0:
            raise SandboxUnavailable(f"GetNamedSecurityInfoW failed: {status}")

        trustee = _TRUSTEE_W(
            None,
            TRUSTEE_IS_SID,
            TRUSTEE_IS_SID,
            TRUSTEE_IS_UNKNOWN,
            ctypes.cast(sid_ptr, ctypes.c_void_p),
        )
        entry = _EXPLICIT_ACCESS_W(
            FILE_TRAVERSE | FILE_READ_ATTRIBUTES,
            GRANT_ACCESS,
            NO_INHERITANCE,
            trustee,
        )
        new_dacl = ctypes.c_void_p()
        status = advapi32.SetEntriesInAclW(1, ctypes.byref(entry), old_dacl, ctypes.byref(new_dacl))
        if status != 0:
            raise SandboxUnavailable(f"SetEntriesInAclW failed: {status}")
        try:
            status = advapi32.SetNamedSecurityInfoW(
                ctypes.c_wchar_p(str(path)),
                SE_FILE_OBJECT,
                DACL_SECURITY_INFORMATION,
                None,
                None,
                new_dacl,
                None,
            )
            if status != 0:
                raise SandboxUnavailable(f"SetNamedSecurityInfoW failed: {status}")
        finally:
            kernel32.LocalFree(new_dacl)
        return True
    finally:
        if descriptor:
            kernel32.LocalFree(descriptor)
        if sid_ptr:
            advapi32.FreeSid(sid_ptr)


def grant_chain(path: Path, sid: str, *, recursive: bool = True) -> list[Path]:
    """Grant read/execute along the ancestor chain and on the leaf.

    Windows checks traverse permission on every directory in the path, so
    granting only the leaf produces "cannot find executable" errors that look
    like a missing file. Ancestors get a **non-inheriting** ``(RX)`` — enough to
    traverse and list, not enough to read files sitting in them. Only the leaf
    gets inheritance, which is what a runtime directory needs.

    The drive root is intentionally skipped: the container must never read a
    whole volume.
    """

    added: list[Path] = []
    leaf = Path(path).resolve()
    if not has_grant(leaf, sid):
        # Inheritance flags are only valid on containers; a file gets (RX).
        if leaf.is_dir():
            grant(leaf, sid, permissions="(OI)(CI)(RX)" if recursive else "(RX)")
        else:
            grant(leaf, sid, permissions="(RX)")
        added.append(leaf)
    current = leaf.parent
    while current.parent != current:
        if not has_grant(current, sid):
            grant(current, sid, permissions="(RX)")
            added.append(current)
        current = current.parent
    return added


def revoke_chain(paths: list[Path], sid: str) -> None:
    for path in paths:
        revoke(path, sid)


def revoke(path: Path, sid: str) -> None:
    _call("icacls", str(path), "/remove:g", f"*{sid}")


def loopback_exempt(sid: str) -> None:
    """Allow this container SID to reach 127.0.0.1 only.

    External destinations remain blocked because no capability is granted; the
    exemption lifts the loopback restriction, nothing else.
    """

    _call("CheckNetIsolation", "LoopbackExempt", "-a", f"-p={sid}")


def loopback_unexempt(sid: str) -> None:
    _call("CheckNetIsolation", "LoopbackExempt", "-d", f"-p={sid}")


# --- process launch -----------------------------------------------------------


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("lpReserved", ctypes.c_wchar_p),
        ("lpDesktop", ctypes.c_wchar_p),
        ("lpTitle", ctypes.c_wchar_p),
        ("dwX", ctypes.c_ulong),
        ("dwY", ctypes.c_ulong),
        ("dwXSize", ctypes.c_ulong),
        ("dwYSize", ctypes.c_ulong),
        ("dwXCountChars", ctypes.c_ulong),
        ("dwYCountChars", ctypes.c_ulong),
        ("dwFillAttribute", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("wShowWindow", ctypes.c_ushort),
        ("cbReserved2", ctypes.c_ushort),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", ctypes.c_void_p),
        ("hStdOutput", ctypes.c_void_p),
        ("hStdError", ctypes.c_void_p),
    ]


class _STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", _STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", ctypes.c_ulong)]


class _SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", ctypes.c_void_p),
        ("Capabilities", ctypes.POINTER(_SID_AND_ATTRIBUTES)),
        ("CapabilityCount", ctypes.c_ulong),
        ("Reserved", ctypes.c_ulong),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", ctypes.c_void_p),
        ("hThread", ctypes.c_void_p),
        ("dwProcessId", ctypes.c_ulong),
        ("dwThreadId", ctypes.c_ulong),
    ]


STARTF_USESTDHANDLES = 0x00000100
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_NO_WINDOW = 0x08000000
# Required when lpEnvironment is a UTF-16 block; without it CreateProcessW
# rejects the environment with ERROR_INVALID_PARAMETER (87).
CREATE_UNICODE_ENVIRONMENT = 0x00000400
PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
INFINITE = 0xFFFFFFFF
WAIT_TIMEOUT = 258
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
CREATE_ALWAYS = 2
FILE_ATTRIBUTE_NORMAL = 0x80


# Variables the container needs to start a process at all. USERPROFILE /
# APPDATA / LOCALAPPDATA are not optional: without them CreateProcessW inside an
# AppContainer fails with ERROR_ENVVAR_NOT_FOUND (203). Everything else — keys,
# tokens, PYTHONPATH additions from the host — is deliberately not copied.
ENV_WHITELIST = (
    "SystemRoot",
    "windir",
    "SystemDrive",
    "ComSpec",
    "PATH",
    "PATHEXT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "ALLUSERSPROFILE",
    "PUBLIC",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
)


def _environment_block(extra: dict[str, str] | None = None) -> ctypes.Array:
    """Build the child environment from an explicit whitelist.

    A blank slate is what keeps secrets out of the sandbox; the whitelist is
    what keeps Windows able to load a user profile and start a process.
    """

    base = {
        key: os.environ[key]
        for key in ENV_WHITELIST
        if os.environ.get(key)
    }
    base.setdefault("SystemRoot", r"C:\Windows")
    base.setdefault("windir", base["SystemRoot"])
    base.setdefault("TEMP", r"C:\Windows\Temp")
    base.setdefault("TMP", base["TEMP"])
    base["PYTHONIOENCODING"] = "utf-8"
    base["PYTHONUTF8"] = "1"
    base.update(extra or {})
    block = "".join(f"{key}={value}\0" for key, value in base.items()) + "\0"
    # Size is inferred: passing len(block) would truncate the terminating NUL
    # and CreateProcessW fails with ERROR_ENVVAR_NOT_FOUND (203).
    return ctypes.create_unicode_buffer(block)


def run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    profile: str = PROFILE,
) -> SandboxResult:
    """Run one command inside the AppContainer and capture its output.

    Output goes to temp files rather than pipes: inherited pipe handles need
    ``PROC_THREAD_ATTRIBUTE_HANDLE_LIST`` and a stricter inheritance model, and
    one-shot execution is all the sandbox probe and MCP tools need today.
    """

    if not supported():
        raise SandboxUnavailable("AppContainer is Windows-only")
    sid_string = ensure_profile(profile)
    sid_ptr = ctypes.c_void_p()
    if not _advapi32().ConvertStringSidToSidW(ctypes.c_wchar_p(sid_string), ctypes.byref(sid_ptr)):
        raise SandboxUnavailable("ConvertStringSidToSidW failed")

    kernel32 = _kernel32()
    work = Path(cwd)
    stamp = uuid.uuid4().hex[:12]
    out_path = work / f".sandbox-{stamp}.out"
    err_path = work / f".sandbox-{stamp}.err"

    class _SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", ctypes.c_ulong),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", ctypes.c_int),
        ]

    attributes = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), None, 1)
    handles = []
    try:
        for path in (out_path, err_path):
            handle = kernel32.CreateFileW(
                ctypes.c_wchar_p(str(path)),
                GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                ctypes.byref(attributes),
                CREATE_ALWAYS,
                FILE_ATTRIBUTE_NORMAL,
                None,
            )
            if not handle or handle == -1:
                raise SandboxUnavailable(f"cannot create capture file: {path}")
            handles.append(handle)

        size = ctypes.c_size_t(0)
        kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        attribute_list = ctypes.cast(buffer, ctypes.c_void_p)
        if not kernel32.InitializeProcThreadAttributeList(
            attribute_list, 1, 0, ctypes.byref(size)
        ):
            raise SandboxUnavailable("InitializeProcThreadAttributeList failed")

        capabilities = _SECURITY_CAPABILITIES(sid_ptr, None, 0, 0)
        if not kernel32.UpdateProcThreadAttribute(
            attribute_list,
            0,
            PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
            ctypes.byref(capabilities),
            ctypes.sizeof(capabilities),
            None,
            None,
        ):
            raise SandboxUnavailable("UpdateProcThreadAttribute failed")

        startup = _STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(_STARTUPINFOEXW)
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput = None
        startup.StartupInfo.hStdOutput = handles[0]
        startup.StartupInfo.hStdError = handles[1]
        startup.lpAttributeList = attribute_list

        command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
        environment = _environment_block(env)
        info = _PROCESS_INFORMATION()
        created = kernel32.CreateProcessW(
            None,
            command_line,
            None,
            None,
            1,
            EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT,
            ctypes.cast(environment, ctypes.c_void_p),
            ctypes.c_wchar_p(str(work)),
            ctypes.byref(startup),
            ctypes.byref(info),
        )
        if not created:
            raise SandboxUnavailable(f"CreateProcessW failed: {ctypes.get_last_error()}")

        try:
            waited = kernel32.WaitForSingleObject(info.hProcess, int(timeout * 1000))
            timed_out = waited == WAIT_TIMEOUT
            if timed_out:
                kernel32.TerminateProcess(info.hProcess, 1)
                kernel32.WaitForSingleObject(info.hProcess, 5000)
            code = ctypes.c_ulong(0)
            kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
        finally:
            kernel32.CloseHandle(info.hThread)
            kernel32.CloseHandle(info.hProcess)
            kernel32.DeleteProcThreadAttributeList(attribute_list)

        # Release our handles before reading: they were opened with write
        # access, and Windows would reject the read otherwise.
        for handle in handles:
            kernel32.CloseHandle(handle)
        handles.clear()
        stdout = out_path.read_text(encoding="utf-8", errors="replace") if out_path.exists() else ""
        stderr = err_path.read_text(encoding="utf-8", errors="replace") if err_path.exists() else ""
        return SandboxResult(
            ok=(not timed_out and code.value == 0),
            exit_code=None if timed_out else int(code.value),
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
        )
    finally:
        for handle in handles:
            kernel32.CloseHandle(handle)
        out_path.unlink(missing_ok=True)
        err_path.unlink(missing_ok=True)
        if sid_ptr:
            _advapi32().FreeSid(sid_ptr)


def status() -> dict:
    """Describe availability without creating anything."""

    if not supported():
        return {"supported": False, "reason": "windows_only", "profile": PROFILE}
    sid = None
    try:
        sid = derive_sid(PROFILE)
    except OSError as exc:  # pragma: no cover - defensive
        return {"supported": True, "ready": False, "reason": str(exc), "profile": PROFILE}
    return {
        "supported": True,
        "ready": sid is not None,
        "profile": PROFILE,
        "sid": sid,
    }


def render(result: SandboxResult) -> str:
    return json.dumps(result.as_dict(), ensure_ascii=False)


# --- async piped execution (scheduler CLI) ------------------------------------

HANDLE_FLAG_INHERIT = 0x00000001


class SandboxProcess:
    """Subset of ``asyncio.subprocess.Process`` the scheduler relies on."""

    def __init__(self, pid: int, handle: int, stdin, stdout, stderr) -> None:
        self.pid = pid
        self._handle = handle
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.returncode: int | None = None
        self._pumps: list = []
        self._files: list = []

    async def wait(self) -> int:
        import asyncio

        if self.returncode is not None:
            return self.returncode
        kernel32 = _kernel32()
        await asyncio.to_thread(kernel32.WaitForSingleObject, self._handle, INFINITE)
        self.returncode = self._exit_code()
        return self.returncode

    def _exit_code(self) -> int:
        code = ctypes.c_ulong(0)
        _kernel32().GetExitCodeProcess(self._handle, ctypes.byref(code))
        return int(code.value)

    def terminate(self) -> None:
        _kernel32().TerminateProcess(self._handle, 1)

    def kill(self) -> None:
        self.terminate()

    def close(self) -> None:
        for task in self._pumps:
            task.cancel()
        for file in self._files:
            try:
                file.close()
            except OSError:
                pass
        if self.stdin is not None:
            try:
                self.stdin.close()
            except OSError:
                pass
        if self._handle:
            _kernel32().CloseHandle(self._handle)
            self._handle = 0


def _pipe(inherit_child_end: bool):
    """Create a pipe; only the end the child needs is inheritable."""

    kernel32 = _kernel32()
    read_handle = ctypes.c_void_p()
    write_handle = ctypes.c_void_p()

    class _SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", ctypes.c_ulong),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", ctypes.c_int),
        ]

    attributes = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), None, 1)
    if not kernel32.CreatePipe(
        ctypes.byref(read_handle), ctypes.byref(write_handle), ctypes.byref(attributes), 0
    ):
        raise SandboxUnavailable(f"CreatePipe failed: {ctypes.get_last_error()}")
    child, parent = (
        (read_handle, write_handle) if inherit_child_end else (write_handle, read_handle)
    )
    kernel32.SetHandleInformation(parent, HANDLE_FLAG_INHERIT, 0)
    return int(child.value), int(parent.value)


class _StreamPump:
    """Feed a StreamReader from a blocking pipe on a worker thread.

    The Proactor loop refuses synchronous pipe handles (WinError 87), and
    ``CreateProcessW`` rejects ``HANDLE_LIST`` here (87 as well). Blocking reads
    on a thread keep the scheduler's async surface without fighting either.
    """

    def __init__(self, fileobj, reader) -> None:
        self._file = fileobj
        self._reader = reader

    async def run(self) -> None:
        import asyncio

        try:
            while True:
                chunk = await asyncio.to_thread(self._file.read, 65536)
                if not chunk:
                    break
                self._reader.feed_data(chunk)
        except (OSError, ValueError):
            pass
        finally:
            self._reader.feed_eof()


class _StdinPump:
    """StreamWriter-compatible sink flushing on a worker thread."""

    def __init__(self, fileobj) -> None:
        self._file = fileobj
        self._buffer = bytearray()
        self._closing = False

    def write(self, data: bytes) -> None:
        self._buffer.extend(data)

    async def drain(self) -> None:
        import asyncio

        if not self._buffer:
            return
        payload = bytes(self._buffer)
        self._buffer.clear()
        await asyncio.to_thread(self._file.write, payload)
        await asyncio.to_thread(self._file.flush)

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            self._file.close()
        except OSError:
            pass

    def is_closing(self) -> bool:
        return self._closing

    async def wait_closed(self) -> None:
        return None


async def popen(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    profile: str = PROFILE,
) -> SandboxProcess:
    """Start ``argv`` inside the AppContainer with JSONL pipes.

    Only the child's three pipe ends are inheritable, and the parent ends are
    cleared right after ``CreatePipe``; ``CreateProcessW`` runs with
    ``bInheritHandles=TRUE`` plus ``STARTF_USESTDHANDLES``.
    """

    if not supported():
        raise SandboxUnavailable("AppContainer is Windows-only")
    import asyncio
    import ctypes.wintypes as wintypes
    import msvcrt
    import os

    sid_string = ensure_profile(profile)
    sid_ptr = ctypes.c_void_p()
    if not _advapi32().ConvertStringSidToSidW(ctypes.c_wchar_p(sid_string), ctypes.byref(sid_ptr)):
        raise SandboxUnavailable("ConvertStringSidToSidW failed")

    kernel32 = _kernel32()
    # _pipe returns (child_end, parent_end); the child end stays inheritable.
    stdin_child, stdin_parent = _pipe(inherit_child_end=True)
    stdout_child, stdout_parent = _pipe(inherit_child_end=False)
    stderr_child, stderr_parent = _pipe(inherit_child_end=False)
    child_ends = [stdin_child, stdout_child, stderr_child]
    parent_ends = [stdin_parent, stdout_parent, stderr_parent]

    size = ctypes.c_size_t(0)
    kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    buffer = ctypes.create_string_buffer(size.value)
    attribute_list = ctypes.cast(buffer, ctypes.c_void_p)
    if not kernel32.InitializeProcThreadAttributeList(attribute_list, 1, 0, ctypes.byref(size)):
        raise SandboxUnavailable("InitializeProcThreadAttributeList failed")

    capabilities = _SECURITY_CAPABILITIES(sid_ptr, None, 0, 0)
    if not kernel32.UpdateProcThreadAttribute(
        attribute_list,
        0,
        PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
        ctypes.byref(capabilities),
        ctypes.sizeof(capabilities),
        None,
        None,
    ):
        raise SandboxUnavailable("UpdateProcThreadAttribute(security) failed")

    startup = _STARTUPINFOEXW()
    startup.StartupInfo.cb = ctypes.sizeof(_STARTUPINFOEXW)
    startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES
    startup.StartupInfo.hStdInput = wintypes.HANDLE(stdin_child)
    startup.StartupInfo.hStdOutput = wintypes.HANDLE(stdout_child)
    startup.StartupInfo.hStdError = wintypes.HANDLE(stderr_child)
    startup.lpAttributeList = attribute_list

    command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
    environment = _environment_block(env)
    info = _PROCESS_INFORMATION()
    created = kernel32.CreateProcessW(
        None,
        command_line,
        None,
        None,
        1,
        EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT,
        ctypes.cast(environment, ctypes.c_void_p),
        ctypes.c_wchar_p(str(cwd)),
        ctypes.byref(startup),
        ctypes.byref(info),
    )
    last_error = ctypes.get_last_error()
    for handle in child_ends:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
    kernel32.DeleteProcThreadAttributeList(attribute_list)
    if sid_ptr:
        _advapi32().FreeSid(sid_ptr)
    if not created:
        for handle in parent_ends:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
        raise SandboxUnavailable(f"CreateProcessW failed: {last_error}")
    kernel32.CloseHandle(info.hThread)

    loop = asyncio.get_running_loop()
    stdout_reader = asyncio.StreamReader(limit=1 << 20, loop=loop)
    stderr_reader = asyncio.StreamReader(limit=1 << 20, loop=loop)
    out_file = os.fdopen(msvcrt.open_osfhandle(stdout_parent, os.O_RDONLY | os.O_BINARY), "rb", 0)
    err_file = os.fdopen(msvcrt.open_osfhandle(stderr_parent, os.O_RDONLY | os.O_BINARY), "rb", 0)
    in_file = os.fdopen(msvcrt.open_osfhandle(stdin_parent, os.O_WRONLY | os.O_BINARY), "wb", 0)

    process = SandboxProcess(
        int(info.dwProcessId),
        int(info.hProcess),
        _StdinPump(in_file),
        stdout_reader,
        stderr_reader,
    )
    process._files = [out_file, err_file, in_file]
    process._pumps = [
        asyncio.create_task(_StreamPump(out_file, stdout_reader).run()),
        asyncio.create_task(_StreamPump(err_file, stderr_reader).run()),
    ]
    return process
