"""HY4-D: display modes and module switches.

A profile mode changes what is shown and the soft ordering of suggestions. It
never changes stored facts, the match score, or which Evidence is valid.
Preferences live in ``user_constraints``; interview stories live in
``profile_extensions`` so each story can anchor to real Evidence IDs.
"""

MODES = ("job_search", "career_change", "capability_audit", "learning_plan", "minimal")
MODE_LABELS = {
    "job_search": "求职冲刺",
    "career_change": "转行探索",
    "capability_audit": "能力盘点",
    "learning_plan": "学习计划",
    "minimal": "极简模式",
}
DEFAULT_MODULES = {
    "skill_matrix": True,
    "experience_timeline": True,
    "interest": True,
    "target_role": True,
    "evidence_health": True,
    "work_values": False,
    "constraints": False,
    "custom_dimensions": False,
    "learning_progress": False,
    "interview_stories": False,
}


def normalise_mode(value: str | None) -> str:
    return value if value in MODES else "job_search"


def default_modules() -> dict[str, bool]:
    return dict(DEFAULT_MODULES)
