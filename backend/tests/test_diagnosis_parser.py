from app.services.diagnosis_parser import parse_failure_output

PYTEST_FAILURE = """=================================== FAILURES ===================================
____________________________ test_total ____________________________
tests/test_math.py:8: in test_total
    assert multiply(2, 3) == 7
E   AssertionError: expected 7
E   assert 6 == 7
=========================== short test summary info ============================
FAILED tests/test_math.py::test_total - AssertionError: expected 7
"""

UNITTEST_FAILURE = """FAIL: test_total (tests.test_math.TestMath)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/workspace/tests/test_math.py", line 8, in test_total
    self.assertEqual(multiply(2, 3), 7)
AssertionError: 6 != 7
"""


def test_parse_pytest_failure_and_test_summary():
    parsed = parse_failure_output(PYTEST_FAILURE, None, "pytest")

    assert len(parsed.failures) == 1
    failure = parsed.failures[0]
    assert failure.test_identifier == "tests/test_math.py::test_total"
    assert failure.test_file == "tests/test_math.py"
    assert failure.test_function == "test_total"
    assert failure.exception_type == "AssertionError"
    assert failure.exception_message == "expected 7"
    assert failure.failing_assertion == "assert 6 == 7"
    assert failure.source_file == "tests/test_math.py"
    assert failure.source_line == 8
    assert failure.source_function == "test_total"
    assert failure.summary == "AssertionError: expected 7"


def test_parse_unittest_error_and_python_traceback():
    parsed = parse_failure_output(None, UNITTEST_FAILURE, "unittest")

    assert len(parsed.failures) == 1
    failure = parsed.failures[0]
    assert failure.test_identifier == "test_total (tests.test_math.TestMath)"
    assert failure.test_class == "TestMath"
    assert failure.test_function == "test_total"
    assert failure.exception_type == "AssertionError"
    assert failure.exception_message == "6 != 7"
    assert failure.traceback_frames[0].file_path == "/workspace/tests/test_math.py"
    assert failure.traceback_frames[0].line_number == 8
    assert failure.source_line == 8
    assert failure.test_file == "/workspace/tests/test_math.py"


def test_parse_pytest_short_summary_without_traceback():
    parsed = parse_failure_output(
        "FAILED tests/test_x.py::test_value - TypeError: invalid operand",
        None,
        "pytest",
    )

    assert len(parsed.failures) == 1
    assert parsed.failures[0].exception_type == "TypeError"
    assert parsed.failures[0].exception_message == "invalid operand"
    assert parsed.failures[0].traceback_frames == ()


def test_parse_unittest_error_output_and_truncated_pytest_exception():
    unittest = parse_failure_output(
        "ERROR: test_load (tests.test_loader.TestLoader)\n"
        "Traceback (most recent call last):\n"
        '  File "/workspace/tests/test_loader.py", line 14, in test_load\n'
        "    load_config()\n"
        "FileNotFoundError: missing config\n",
        None,
        "unittest",
    )
    truncated = parse_failure_output("E   TypeError: invalid operand", None, "pytest")

    assert unittest.failures[0].test_class == "TestLoader"
    assert unittest.failures[0].exception_type == "FileNotFoundError"
    assert unittest.failures[0].exception_message == "missing config"
    assert len(truncated.failures) == 1
    assert truncated.failures[0].exception_type == "TypeError"


def test_parse_truncated_and_empty_output_without_inventing_fields():
    truncated = parse_failure_output(
        'Traceback (most recent call last):\n  File "/workspace/app.py", line 19, in run\n',
        None,
    )
    empty = parse_failure_output("", None)

    assert len(truncated.failures) == 1
    assert truncated.failures[0].source_file == "/workspace/app.py"
    assert truncated.failures[0].source_line == 19
    assert truncated.failures[0].exception_type is None
    assert truncated.failures[0].test_identifier is None
    assert truncated.failures[0].test_file is None
    assert empty.failures == ()
    assert empty.passed_test_ids == ()


def test_parse_explicit_passing_test_identifiers():
    parsed = parse_failure_output(
        "tests/test_math.py::test_total PASSED\n",
        None,
        "pytest",
    )

    assert parsed.passed_test_ids == ("tests/test_math.py::test_total",)
