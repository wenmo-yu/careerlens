"""User-level daemon: process supervision, not business logic.

The daemon owns OS processes and the control pipe only. Runs, sessions,
approvals and evidence stay with FastAPI and the business database.
"""

from .contract import Contract, load_contract
from .control_ipc import ControlPlane, DaemonInfo, Session
from .lifecycle import DaemonConfig, run_daemon
from .supervisor import Role, Supervisor

__all__ = [
    "Contract",
    "ControlPlane",
    "DaemonConfig",
    "DaemonInfo",
    "Role",
    "Session",
    "Supervisor",
    "load_contract",
    "run_daemon",
]
