"""Role catalog: what panel of interviewers gets assembled for a given job
role. Each entry defines 2-3 panelists (title, focus keywords, and which
prompt archetype to use). Panel size is capped at 3 to match the 3 TTS
voice slots configured in .env (see app/agora/tts_vendors.py) — a session's
panelists are assigned voice/UID slots by position, not by identity.

Add a new role by adding an entry to ROLE_CATALOG; nothing else in the
backend hardcodes role names — floor-controller scoring, Agora join, TTS
voice assignment, and the scorecard schema are all driven off this data.
"""

from dataclasses import dataclass, field

from app.evaluation.extractor import (
    AI_ML_KEYWORDS,
    BACKEND_KEYWORDS,
    BEHAVIORAL_KEYWORDS,
    DATA_SCIENCE_KEYWORDS,
    DEVOPS_KEYWORDS,
    FRONTEND_KEYWORDS,
    HR_KEYWORDS,
    IMPACT_KEYWORDS,
    PRODUCT_KEYWORDS,
    RESEARCH_METHODOLOGY_KEYWORDS,
    RESEARCH_RIGOR_KEYWORDS,
)

DOMAIN_LEAD_ARCHETYPE = "domain_lead"
HIRING_MANAGER_ARCHETYPE = "hiring_manager"
CULTURE_FIT_ARCHETYPE = "culture_fit"


@dataclass
class PanelistTemplate:
    title: str
    archetype: str  # picks which prompt template in prompts.py to format
    keywords: list[str]
    focus_description: str = ""  # only used by domain_lead archetype


@dataclass
class RoleConfig:
    key: str
    label: str  # shown in the frontend dropdown
    role_title: str  # human-readable, filled into every panelist's prompt
    panelists: list[PanelistTemplate] = field(default_factory=list)


def _domain_lead(title: str, keywords: list[str], focus: str) -> PanelistTemplate:
    return PanelistTemplate(title=title, archetype=DOMAIN_LEAD_ARCHETYPE, keywords=keywords, focus_description=focus)


def _hiring_manager() -> PanelistTemplate:
    return PanelistTemplate(title="Hiring Manager", archetype=HIRING_MANAGER_ARCHETYPE, keywords=IMPACT_KEYWORDS)


def _culture_fit() -> PanelistTemplate:
    return PanelistTemplate(title="Culture & Values Partner", archetype=CULTURE_FIT_ARCHETYPE, keywords=BEHAVIORAL_KEYWORDS)


ROLE_CATALOG: dict[str, RoleConfig] = {
    "software_engineer": RoleConfig(
        key="software_engineer",
        label="Software Engineer (General)",
        role_title="Software Engineer",
        panelists=[
            _domain_lead("Technical Lead", BACKEND_KEYWORDS, "architecture, implementation choices, trade-offs, debugging, and scale"),
            _hiring_manager(),
            _culture_fit(),
        ],
    ),
    "backend_engineer": RoleConfig(
        key="backend_engineer",
        label="Backend Engineer",
        role_title="Backend Engineer",
        panelists=[
            _domain_lead("Technical Lead", BACKEND_KEYWORDS, "API design, data modeling, scalability, and system reliability"),
            _hiring_manager(),
            _culture_fit(),
        ],
    ),
    "frontend_engineer": RoleConfig(
        key="frontend_engineer",
        label="Frontend Engineer",
        role_title="Frontend Engineer",
        panelists=[
            _domain_lead("Technical Lead", FRONTEND_KEYWORDS, "UI architecture, performance, accessibility, and state management"),
            _hiring_manager(),
            _culture_fit(),
        ],
    ),
    "ai_engineer": RoleConfig(
        key="ai_engineer",
        label="AI / ML Engineer",
        role_title="AI Engineer",
        panelists=[
            _domain_lead("AI Technical Lead", AI_ML_KEYWORDS, "model choices, training/inference trade-offs, evaluation, and data pipelines"),
            _hiring_manager(),
            _culture_fit(),
        ],
    ),
    "devops_engineer": RoleConfig(
        key="devops_engineer",
        label="DevOps / SRE Engineer",
        role_title="DevOps Engineer",
        panelists=[
            _domain_lead("Infrastructure Lead", DEVOPS_KEYWORDS, "deployment pipelines, infrastructure reliability, incident response, and automation"),
            _hiring_manager(),
            _culture_fit(),
        ],
    ),
    "data_scientist": RoleConfig(
        key="data_scientist",
        label="Data Scientist",
        role_title="Data Scientist",
        panelists=[
            _domain_lead("Technical Lead", DATA_SCIENCE_KEYWORDS, "statistical rigor, experiment design, modeling choices, and data quality"),
            _hiring_manager(),
            _culture_fit(),
        ],
    ),
    "research_scientist": RoleConfig(
        key="research_scientist",
        label="Research Scientist / ML Researcher",
        role_title="Research Scientist",
        panelists=[
            _domain_lead("Research Lead", RESEARCH_METHODOLOGY_KEYWORDS, "research motivation, methodology, novelty, and framing relative to prior work"),
            _domain_lead("Technical Reviewer", RESEARCH_RIGOR_KEYWORDS, "experimental rigor: baselines, ablations, reproducibility, and limitations"),
            _hiring_manager(),
        ],
    ),
    "product_manager": RoleConfig(
        key="product_manager",
        label="Product Manager",
        role_title="Product Manager",
        panelists=[
            _domain_lead("Product Lead", PRODUCT_KEYWORDS, "prioritization, roadmap trade-offs, metrics, and stakeholder alignment"),
            _hiring_manager(),
            _culture_fit(),
        ],
    ),
    "hr": RoleConfig(
        key="hr",
        label="HR / People Ops",
        role_title="HR Business Partner",
        panelists=[
            _domain_lead("HR Domain Lead", HR_KEYWORDS, "HR processes, compliance, employee lifecycle, and policy judgment"),
            _hiring_manager(),
            _culture_fit(),
        ],
    ),
}

DEFAULT_ROLE_KEY = "software_engineer"


def get_role(key: str) -> RoleConfig:
    return ROLE_CATALOG.get(key, ROLE_CATALOG[DEFAULT_ROLE_KEY])


def list_roles() -> list[dict]:
    return [
        {
            "key": r.key,
            "label": r.label,
            "panel_titles": [p.title for p in r.panelists],
        }
        for r in ROLE_CATALOG.values()
    ]
