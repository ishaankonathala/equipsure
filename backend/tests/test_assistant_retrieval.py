from copy import deepcopy

import pytest

from app.services.assistant_retrieval import retrieve_clauses, tokenize
from app.services.clause_seed import DEMO_CLAUSES


def test_tokenize_drops_stopwords_and_short_tokens():
    assert tokenize("What is the claim for a fridge?") == {"claim", "fridge"}


def test_wear_question_retrieves_wear_clause():
    results = retrieve_clauses("Is wear and tear covered?")

    assert results[0]["clause_id"] == "DEMO-EXC-01"


def test_notification_question_retrieves_reporting_clause():
    results = retrieve_clauses("How soon must I notify the insurer?")

    assert "DEMO-REP-01" in {clause["clause_id"] for clause in results}


def test_unrelated_question_returns_nothing():
    assert retrieve_clauses("Tell me a joke about penguins") == []


def test_empty_question_returns_nothing():
    assert retrieve_clauses("") == []


def test_limit_is_respected():
    assert len(retrieve_clauses("damage repair claim insurer", limit=2)) <= 2


def test_invalid_limit_rejected():
    with pytest.raises(ValueError, match="limit must be positive"):
        retrieve_clauses("damage", limit=0)


def test_results_are_stable():
    question = "damage repair claim insurer"

    assert retrieve_clauses(question) == retrieve_clauses(question)


def test_does_not_mutate_source():
    original_clauses = deepcopy(DEMO_CLAUSES)

    retrieve_clauses("damage repair claim insurer")

    assert DEMO_CLAUSES == original_clauses