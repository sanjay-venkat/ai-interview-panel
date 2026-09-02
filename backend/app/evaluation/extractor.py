import re
from dataclasses import dataclass, field

TECH_KEYWORDS = [
    "architecture", "algorithm", "database", "api", "latency", "scalability",
    "rag", "llm", "model", "deploy", "kubernetes", "docker", "microservice",
    "cache", "vector", "embedding", "pipeline", "distributed", "concurrency",
    "testing", "debug", "system design", "backend", "frontend", "cloud", "aws",
    "gcp", "azure", "sql", "nosql", "framework", "library", "optimization",
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
    topics: list[str] = field(default_factory=list)
    tech_hits: int = 0
    impact_hits: int = 0
    behavioral_hits: int = 0
    hedging: bool = False
    has_number: bool = False
    word_count: int = 0


def extract_signals(text: str) -> Signals:
    lower = text.lower()
    topics = [kw for kw in TECH_KEYWORDS if kw in lower]
    tech_hits = len(topics)
    impact_hits = sum(1 for kw in IMPACT_KEYWORDS if kw in lower)
    behavioral_hits = sum(1 for kw in BEHAVIORAL_KEYWORDS if kw in lower)
    hedging = any(re.search(p, lower) for p in HEDGING_PATTERNS)
    has_number = bool(NUMBER_PATTERN.search(lower))
    return Signals(
        topics=topics,
        tech_hits=tech_hits,
        impact_hits=impact_hits,
        behavioral_hits=behavioral_hits,
        hedging=hedging,
        has_number=has_number,
        word_count=len(text.split()),
    )


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
