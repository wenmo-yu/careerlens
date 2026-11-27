"""CareerLens agent plane: durable sessions/runs, pool, scheduler and CLI.

The scheduler owns admission and leases; each run executes in its own CLI
process; FastAPI and the database own facts. Nothing here generates answers.
"""

from app.runtime.agent.pool import Pool, Slot
from app.runtime.agent.scheduler import AgentScheduler, SchedulerConfig
from app.runtime.agent.store import RUN_EVENT_KINDS, AgentClaim

__all__ = [
    "AgentClaim",
    "AgentScheduler",
    "Pool",
    "RUN_EVENT_KINDS",
    "SchedulerConfig",
    "Slot",
]
