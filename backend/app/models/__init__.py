"""SQLAlchemy ORM models.

All model classes are imported here so that ``import app.models`` registers every
table on ``Base.metadata``. Alembic's env.py and the migration runner rely on this
for autogenerate comparison and legacy schema adoption.
"""

from app.models.access_token import AccessToken
from app.models.account_deletion import AccountDeletionReceipt
from app.models.audit import AuditEvent
from app.models.career_report import CareerReport
from app.models.conversation import ConversationMessage, ConversationThread
from app.models.evaluation import EvaluationRun
from app.models.evidence import Evidence
from app.models.job_analysis import JobAnalysis
from app.models.profile import ProfileItem
from app.models.profile_update import ProfileUpdateProposal

__all__ = [
    "AccessToken",
    "AccountDeletionReceipt",
    "AuditEvent",
    "CareerReport",
    "ConversationThread",
    "ConversationMessage",
    "EvaluationRun",
    "Evidence",
    "JobAnalysis",
    "ProfileItem",
    "ProfileUpdateProposal",
]
