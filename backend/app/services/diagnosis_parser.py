"""Deterministic parsing for pytest and unittest failure output."""

import re
from dataclasses import dataclass

_PYTEST_SUMMARY = re.compile(r"^(?:FAILED|ERROR)\s+(.+?)(?:\s+-\s+(.*))?$", re.MULTILINE)
_PYTEST_SECTION = re.compile(r"^_{5,}\s*(.*?)\s*_{5,}\s*$", re.MULTILINE)
_UNITTEST_HEADER = re.compile(r"^(?:FAIL|ERROR):\s*(.+?)\s*$", re.MULTILINE)
_PYTEST_FRAME = re.compile(r"^(.+?):(\d+): in (.+?)\s*$")
_PYTHON_FRAME = re.compile(r'^\s*File "(.+?)", line (\d+)(?:, in (.+?))?\s*$')
_EXCEPTION_LINE = re.compile(
    r"^(?:E\s+)?([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:Error|Exception|Failure|Interrupt|Exit|Warning))"
    r":(?:\s*(.*))?$"
)
_PYTEST_PASSED = re.compile(r"^\s*(.+?::[^\s]+)\s+PASSED\b", re.MULTILINE)
_UNITTEST_PASSED = re.compile(r"^(\S+\s+\([^)\n]+\))\s+\.\.\.\s+ok$", re.MULTILINE)


@dataclass(frozen=True)
class TracebackFrame:
    file_path: str
    line_number: int
    function_name: str | None = None
    source_line: str | None = None


@dataclass(frozen=True)
class ParsedFailure:
    test_identifier: str | None = None
    test_file: str | None = None
    test_class: str | None = None
    test_function: str | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    failing_assertion: str | None = None
    source_file: str | None = None
    source_line: int | None = None
    source_function: str | None = None
    traceback_frames: tuple[TracebackFrame, ...] = ()
    summary: str | None = None


@dataclass(frozen=True)
class ParsedTestOutput:
    failures: tuple[ParsedFailure, ...]
    passed_test_ids: tuple[str, ...]


def parse_failure_output(
    stdout: str | None,
    stderr: str | None,
    framework: str | None = None,
) -> ParsedTestOutput:
    """Extract observed test failures and explicitly named passing tests."""
    output = "\n".join(part for part in (stdout, stderr) if part)
    if not output:
        return ParsedTestOutput(failures=(), passed_test_ids=())

    is_unittest = framework == "unittest" or bool(_UNITTEST_HEADER.search(output))
    failures = _parse_unittest(output) if is_unittest else _parse_pytest(output)
    passed_pattern = _UNITTEST_PASSED if is_unittest else _PYTEST_PASSED
    passed_test_ids = tuple(match.group(1).strip() for match in passed_pattern.finditer(output))
    return ParsedTestOutput(failures=tuple(failures), passed_test_ids=passed_test_ids)


def _parse_pytest(output: str) -> list[ParsedFailure]:
    sections = _failure_sections(output, _PYTEST_SECTION)
    results: list[ParsedFailure] = []
    summary_matches = list(_PYTEST_SUMMARY.finditer(output))

    for match in summary_matches:
        test_identifier = match.group(1).strip()
        section = _matching_section(test_identifier, sections)
        details = section[1] if section else ""
        failure = _parse_failure_details(
            details,
            test_identifier=test_identifier,
            summary=match.group(2),
        )
        results.append(failure)

    if not results:
        for heading, details in sections:
            frames = _extract_frames(details)
            test_function = heading.strip() if heading.strip().startswith("test_") else None
            test_frame = next(
                (frame for frame in frames if frame.function_name == test_function),
                None,
            )
            test_file = test_frame.file_path if test_frame else None
            test_identifier = (
                f"{test_file}::{test_function}" if test_file and test_function else None
            )
            if frames or _extract_exception(details.splitlines()):
                results.append(
                    _parse_failure_details(
                        details,
                        test_identifier=test_identifier,
                    )
                )

    if not results and (
        "Traceback (most recent call last):" in output or _extract_exception(output.splitlines())[0]
    ):
        results.append(_parse_failure_details(output))
    return _deduplicate_failures(results)


def _parse_unittest(output: str) -> list[ParsedFailure]:
    sections = _failure_sections(output, _UNITTEST_HEADER)
    if not sections and "Traceback (most recent call last):" in output:
        sections = [("", output)]
    return _deduplicate_failures(
        [
            _parse_failure_details(
                details,
                test_identifier=header or None,
            )
            for header, details in sections
        ]
    )


def _failure_sections(output: str, pattern: re.Pattern[str]) -> list[tuple[str, str]]:
    matches = list(pattern.finditer(output))
    return [
        (
            match.group(1).strip(),
            output[
                match.end() : matches[index + 1].start()
                if index + 1 < len(matches)
                else len(output)
            ],
        )
        for index, match in enumerate(matches)
    ]


def _matching_section(
    test_identifier: str,
    sections: list[tuple[str, str]],
) -> tuple[str, str] | None:
    function_name = _test_function(test_identifier)
    for section in sections:
        heading, details = section
        if function_name and function_name in heading:
            return section
        if test_identifier in details:
            return section
    return None


def _parse_failure_details(
    details: str,
    *,
    test_identifier: str | None = None,
    summary: str | None = None,
) -> ParsedFailure:
    lines = details.splitlines()
    frames = _extract_frames(details)
    exception_type, exception_message = _extract_exception(lines)
    if not exception_type and summary:
        exception_type, exception_message = _extract_exception([summary])
    test_file, test_class, test_function = _test_parts(test_identifier)
    assertion = _extract_assertion(lines, frames)
    test_file = test_file or next(
        (
            frame.file_path
            for frame in frames
            if test_function and frame.function_name == test_function
        ),
        None,
    )
    non_test_frames = [
        frame
        for frame in frames
        if (not test_file or not _same_path(frame.file_path, test_file))
        and not _is_framework_frame(frame.file_path)
    ]
    if non_test_frames:
        source_frame = non_test_frames[-1]
    elif test_file:
        source_frame = next(
            (frame for frame in reversed(frames) if _same_path(frame.file_path, test_file)),
            None,
        )
    else:
        source_frame = next(
            (frame for frame in reversed(frames) if not _is_framework_frame(frame.file_path)),
            None,
        )
    failure_summary = (
        f"{exception_type}: {exception_message}"
        if exception_type and exception_message
        else exception_type or exception_message or (summary.strip() if summary else None)
    )
    return ParsedFailure(
        test_identifier=test_identifier,
        test_file=test_file,
        test_class=test_class,
        test_function=test_function,
        exception_type=exception_type,
        exception_message=exception_message,
        failing_assertion=assertion,
        source_file=source_frame.file_path if source_frame else None,
        source_line=source_frame.line_number if source_frame else None,
        source_function=source_frame.function_name if source_frame else None,
        traceback_frames=tuple(frames),
        summary=failure_summary,
    )


def _extract_frames(output: str) -> list[TracebackFrame]:
    lines = output.splitlines()
    frames: list[TracebackFrame] = []
    for index, line in enumerate(lines):
        match = _PYTHON_FRAME.match(line)
        if match:
            path, line_number, function = match.groups()
        else:
            match = _PYTEST_FRAME.match(line.strip())
            if not match:
                continue
            path, line_number, function = match.groups()

        source_line = None
        for candidate in lines[index + 1 : index + 3]:
            candidate = candidate.strip()
            if not candidate:
                continue
            if candidate.startswith(("File ", "Traceback ", "E ")):
                candidate = candidate.removeprefix("E ").strip()
            if _EXCEPTION_LINE.match(candidate) or _PYTEST_FRAME.match(candidate):
                break
            source_line = candidate or None
            break
        frames.append(
            TracebackFrame(
                file_path=path,
                line_number=int(line_number),
                function_name=function.strip() if function else None,
                source_line=source_line,
            )
        )
    return frames


def _extract_exception(lines: list[str]) -> tuple[str | None, str | None]:
    for line in reversed(lines):
        candidate = line.strip()
        if candidate.startswith("E "):
            candidate = candidate[2:].strip()
        match = _EXCEPTION_LINE.match(candidate)
        if match:
            return match.group(1), match.group(2) or ""
    return None, None


def _extract_assertion(
    lines: list[str],
    frames: list[TracebackFrame],
) -> str | None:
    for line in lines:
        candidate = line.strip()
        if candidate.startswith("E "):
            candidate = candidate[2:].strip()
            if candidate.startswith(("assert ", "assert(")):
                return candidate
    for line in lines:
        candidate = line.strip()
        if candidate.startswith("E "):
            candidate = candidate[2:].strip()
        if candidate.startswith("assert ") or candidate.startswith("assert("):
            return candidate
        if ".assert" in candidate:
            return candidate
    return next(
        (
            frame.source_line
            for frame in reversed(frames)
            if frame.source_line and frame.source_line.lstrip().startswith(("assert ", "assert("))
        ),
        None,
    )


def _test_parts(
    test_identifier: str | None,
) -> tuple[str | None, str | None, str | None]:
    if not test_identifier:
        return None, None, None
    if " (" in test_identifier and test_identifier.endswith(")"):
        function_name = test_identifier.split(" (", 1)[0]
        module_path = test_identifier.rsplit("(", 1)[-1][:-1].split(".")
        class_name = module_path[-1] if len(module_path) > 1 else None
        return None, class_name, function_name or None
    parts = test_identifier.split("::")
    if len(parts) < 2:
        return None, None, None
    test_file = parts[0] or None
    function_name = parts[-1].split("[", 1)[0] or None
    test_class = parts[-2] if len(parts) > 2 else None
    return test_file, test_class, function_name


def _test_function(test_identifier: str) -> str | None:
    return _test_parts(test_identifier)[2]


def _same_path(first: str, second: str) -> bool:
    first = first.replace("\\", "/").lstrip("./").casefold()
    second = second.replace("\\", "/").lstrip("./").casefold()
    return first == second or first.endswith(f"/{second}")


def _is_framework_frame(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/").casefold()
    return any(marker in normalized for marker in ("/unittest/", "/_pytest/", "/pluggy/"))


def _deduplicate_failures(failures: list[ParsedFailure]) -> list[ParsedFailure]:
    seen: set[tuple[str | None, str | None, str | None]] = set()
    unique: list[ParsedFailure] = []
    for failure in failures:
        key = (
            failure.test_identifier,
            failure.exception_type,
            failure.exception_message,
        )
        if key not in seen:
            seen.add(key)
            unique.append(failure)
    return unique
