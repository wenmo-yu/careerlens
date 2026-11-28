"""SQLAlchemy ORM models.

All model classes are imported here so that ``import app.models`` registers every
table on ``Base.metadata``. Alembic's env.py and the migration runner rely on this
for autogenerate comparison and legacy schema adoption.
"""

from app.models.access_token import AccessToken
from app.models.account_deletion import AccountDeletionReceipt, DeletionWork
from app.models.agent import (
    AgentApproval,
    AgentArtifact,
    AgentMessage,
    AgentRuntimeSlot,
    AgentSession,
    AgentToolLedger,
)
from app.models.assessment import AssessmentResult, UserConstraint
from app.models.audit import AuditEvent
from app.models.career_report import CareerReport
from app.models.conversation import ConversationMessage, ConversationThread
from app.models.evaluation import EvaluationRun
from app.models.evidence import Evidence
from app.models.index_generation import IndexGeneration
from app.models.job_analysis import JobAnalysis
from app.models.learning import LearningProgress, SavedJob
from app.models.multi import AgentTask, AgentTaskBudgetUse, AgentTeamMessage
from app.models.parsed_block import ParsedBlock
from app.models.profile import ProfileItem
from app.models.profile_extension import DimensionDefinition, ProfileExtension
from app.models.profile_suppression import ProfileSuppression
from app.models.profile_update import ProfileUpdateProposal
from app.models.run import AgentRun, EvidenceIndexWork, RunEvent, RunScope, RunStep
from app.models.schedule import AgentSchedule, AgentScheduleOccurrence
from app.models.source_document import SourceDocument
from app.models.wiki import WikiPage, WikiRevision

__all__ = [
    "AccessToken",
    "AgentApproval",
    "AgentArtifact",
    "AgentMessage",
    "AgentToolLedger",
    "AgentRun",
    "AgentRuntimeSlot",
    "AgentSession",
    "AccountDeletionReceipt",
    "DeletionWork",
    "AssessmentResult",
    "UserConstraint",
    "DimensionDefinition",
    "ProfileExtension",
    "AuditEvent",
    "CareerReport",
    "ConversationThread",
    "ConversationMessage",
    "EvaluationRun",
    "Evidence",
    "EvidenceIndexWork",
    "IndexGeneration",
    "JobAnalysis",
    "LearningProgress",
    "SavedJob",
    "AgentSchedule",
    "AgentScheduleOccurrence",
    "AgentTask",
    "AgentTaskBudgetUse",
    "AgentTeamMessage",
    "ParsedBlock",
    "ProfileItem",
    "ProfileSuppression",
    "ProfileUpdateProposal",
    "RunEvent",
    "RunScope",
    "RunStep",
    "SourceDocument",
    "WikiPage",
    "WikiRevision",
]
