import re
from dataclasses import dataclass, field

# Reusable keyword sets. Each panelist archetype in app/agents/roles.py picks
# one (or a combination) of these as its own focus vocabulary — the floor
# controller scores relevance/weakness per-panelist against whichever set
# that panelist was configured with, so these lists are data, not logic.
BACKEND_KEYWORDS = [
    "architecture", "algorithm", "database", "api", "latency", "scalability",
    "microservice", "cache", "distributed", "concurrency", "testing", "debug",
    "system design", "backend", "cloud", "aws", "gcp", "azure", "sql", "nosql",
    "framework", "library", "optimization", "queue", "throughput",
]

AI_ML_KEYWORDS = [
    "model", "training", "inference", "embedding", "llm", "rag", "fine-tun",
    "dataset", "gpu", "pytorch", "tensorflow", "transformer", "prompt",
    "evaluation", "hallucinat", "vector", "token", "accuracy", "f1",
    "precision", "recall", "overfit", "hyperparameter",
]

DEVOPS_KEYWORDS = [
    "kubernetes", "docker", "ci/cd", "pipeline", "terraform", "ansible",
    "incident", "uptime", "monitoring", "alert", "deploy", "rollback",
    "infrastructure", "cloud", "aws", "gcp", "azure", "scaling",
    "load balanc", "observability", "on-call", "automation", "outage",
]

FRONTEND_KEYWORDS = [
    "react", "component", "accessibility", "performance", "render", "css",
    "state management", "ui", "ux", "browser", "responsive", "bundle",
    "typescript", "webpack", "vite", "hydration", "animation",
]

DATA_SCIENCE_KEYWORDS = [
    "statistics", "hypothesis", "experiment", "a/b test", "regression",
    "clustering", "feature", "dataset", "model", "significance",
    "correlation", "bias", "sql", "pandas", "visualization", "pipeline",
]

RESEARCH_METHODOLOGY_KEYWORDS = [
    "hypothesis", "methodology", "novelty", "literature", "publication",
    "peer review", "experiment design", "related work", "contribution",
    "motivation", "research question",
]

RESEARCH_RIGOR_KEYWORDS = [
    "reproducib", "baseline", "ablation", "evaluation", "benchmark",
    "limitation", "significance", "validation", "robustness",
    "generalization", "control group", "confound",
]

HR_KEYWORDS = [
    "recruiting", "onboarding", "policy", "compliance", "employee relations",
    "retention", "engagement", "performance review", "conflict resolution",
    "diversity", "benefits", "offboarding", "talent", "headcount",
]

PRODUCT_KEYWORDS = [
    "roadmap", "prioritiz", "stakeholder", "metric", "user research",
    "a/b test", "feature", "launch", "backlog", "okr", "kpi", "persona",
    "go-to-market", "adoption", "retention",
]

IMPACT_KEYWORDS = [
    "reduced", "improved", "increased", "saved", "led", "owned", "launched",
    "shipped", "impact", "users", "revenue", "team", "mentored", "decided",
    "trade-off", "tradeoff", "stakeholder", "customer", "deadline", "prioritiz",
]

BEHAVIORAL_KEYWORDS = [
    "conflict", "disagree", "feedback", "collaborat", "communicat", "adapt",
    "motivat", "culture", "value", "coach", "peer", "compromise", "listen",
    "difficult conversation", "pushback", "relationship", "trust",
]

HEDGING_PATTERNS = [
    r"\bi think\b", r"\bmaybe\b", r"\bnot (really )?sure\b", r"\bi guess\b",
    r"\bkind of\b", r"\bsort of\b", r"\bprobably\b", r"\bi don't (remember|know)\b",
]

NUMBER_PATTERN = re.compile(r"\b\d+(\.\d+)?\s*(%|percent|ms|seconds?|x|k|million|thousand)?\b", re.I)


@dataclass
class Signals:
    lower_text: str = ""
    hedging: bool = False
    has_number: bool = False
    word_count: int = 0


def extract_signals(text: str) -> Signals:
    lower = text.lower()
    hedging = any(re.search(p, lower) for p in HEDGING_PATTERNS)
    has_number = bool(NUMBER_PATTERN.search(lower))
    return Signals(
        lower_text=lower,
        hedging=hedging,
        has_number=has_number,
        word_count=len(text.split()),
    )


def keyword_hits(lower_text: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if kw in lower_text)


def extract_claims(text: str) -> list[str]:
    claims = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        s = sentence.strip()
        if len(s.split()) < 4:
            continue
        low = s.lower()
        if any(kw in low for kw in IMPACT_KEYWORDS) or NUMBER_PATTERN.search(low):
            claims.append(s)
    return claims
