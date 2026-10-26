import re

from app.services.clause_seed import DEMO_CLAUSES

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "my",
        "not",
        "of",
        "on",
        "or",
        "the",
        "to",
        "what",
        "when",
        "whether",
        "with",
        "would",
        "was",
        "were",
        "that",
        "this",
        "there",
    }
)


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in STOPWORDS and len(token) >= 3
    }


def retrieve_clauses(question: str, limit: int = 3) -> list[dict[str, str]]:
    if limit < 1:
        raise ValueError("limit must be positive")

    question_tokens = tokenize(question)
    if not question_tokens:
        return []

    scored_clauses = []
    for clause in DEMO_CLAUSES:
        clause_tokens = tokenize(clause["title"] + " " + clause["summary"])
        score = len(question_tokens & clause_tokens)
        if score > 0:
            scored_clauses.append((score, clause))

    scored_clauses.sort(key=lambda item: (-item[0], item[1]["clause_id"]))
    return [clause for _, clause in scored_clauses[:limit]]