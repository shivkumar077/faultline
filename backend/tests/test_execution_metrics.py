import pytest

from app.services.execution_metrics import classify_mutation, summarize_mutations


@pytest.mark.parametrize(
    ("exit_code", "timed_out", "output_limited", "applied", "expected", "error"),
    [
        (1, False, False, True, "KILLED", None),
        (0, False, False, True, "SURVIVED", None),
        (-1, True, False, True, "TIMEOUT", None),
        (1, False, True, True, "ERROR", "OUTPUT_LIMIT_EXCEEDED"),
        (125, False, False, True, "ERROR", "DOCKER_RUN_FAILED"),
        (None, False, False, True, "ERROR", "DOCKER_RUN_FAILED"),
        (1, False, False, False, "INVALID", None),
    ],
)
def test_classify_mutation_outcomes(exit_code, timed_out, output_limited, applied, expected, error):
    assert classify_mutation(
        exit_code=exit_code,
        timed_out=timed_out,
        output_limited=output_limited,
        mutation_applied=applied,
    ) == (expected, error)


def test_mutation_summary_excludes_error_timeout_and_invalid_from_score():
    summary = summarize_mutations(5, ["KILLED", "SURVIVED", "TIMEOUT", "ERROR", "INVALID"])

    assert summary == {
        "total_mutations": 5,
        "killed": 1,
        "survived": 1,
        "timed_out": 1,
        "errored": 1,
        "invalid": 1,
        "mutation_score": 50.0,
    }
    assert summarize_mutations(0, [])["mutation_score"] is None
