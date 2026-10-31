"""Deterministic mutant outcome classification and score calculations."""

from collections.abc import Iterable
from typing import TypedDict


class MutationSummary(TypedDict):
    total_mutations: int
    killed: int
    survived: int
    timed_out: int
    errored: int
    invalid: int
    mutation_score: float | None


def classify_mutation(
    *,
    exit_code: int | None,
    timed_out: bool,
    output_limited: bool,
    mutation_applied: bool,
) -> tuple[str, str | None]:
    """Classify only executed, valid mutants as killed or survived."""
    if not mutation_applied:
        return "INVALID", None
    if output_limited:
        return "ERROR", "OUTPUT_LIMIT_EXCEEDED"
    if timed_out:
        return "TIMEOUT", None
    if exit_code is None or exit_code in {125, 126, 127}:
        return "ERROR", "DOCKER_RUN_FAILED"
    if exit_code == 0:
        return "SURVIVED", None
    return "KILLED", None


def summarize_mutations(total: int, outcomes: Iterable[str]) -> MutationSummary:
    """Calculate the score using killed/survived outcomes only."""
    statuses = list(outcomes)
    killed = statuses.count("KILLED")
    survived = statuses.count("SURVIVED")
    denominator = killed + survived
    return {
        "total_mutations": total,
        "killed": killed,
        "survived": survived,
        "timed_out": statuses.count("TIMEOUT"),
        "errored": statuses.count("ERROR"),
        "invalid": statuses.count("INVALID"),
        "mutation_score": round(killed / denominator * 100, 2) if denominator else None,
    }
