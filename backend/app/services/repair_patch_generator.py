"""Verify mutation metadata and produce a syntax-checked unified repair patch."""

import ast
import copy
import difflib
import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from app.models.mutation_record import MutationRecord


class RepairGenerationRejected(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class GeneratedRepairPatch:
    target_file: str
    original_source_sha256: str
    proposed_source_sha256: str
    original_expression: str
    replacement_expression: str
    repair_strategy: str
    patch_content: str


class RepairPatchGenerator:
    def generate(self, workspace: Path, mutation: MutationRecord) -> GeneratedRepairPatch:
        if not mutation.source_sha256:
            raise RepairGenerationRejected("source_hash_missing")
        target_path = self._resolve_target(workspace, mutation.target_file)
        try:
            raw_source = target_path.read_bytes()
            decoded_source = raw_source.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            raise RepairGenerationRejected("source_file_unreadable") from None

        source = decoded_source.replace("\r\n", "\n").replace("\r", "\n")
        original_hash = _sha256(source.encode("utf-8"))
        if original_hash != mutation.source_sha256:
            raise RepairGenerationRejected("source_hash_mismatch")
        try:
            tree = ast.parse(source, filename=mutation.target_file)
        except SyntaxError:
            raise RepairGenerationRejected("source_syntax_invalid") from None

        target_node = self._find_mutated_node(
            tree,
            mutation.line_number,
            mutation.col_offset,
            mutation.mutated_code,
        )
        original_expression, mutated_expression = self._parse_expressions(
            mutation.original_code,
            mutation.mutated_code,
        )
        if not self._mutation_is_supported(
            original_expression,
            mutated_expression,
            mutation.mutation_type,
        ):
            raise RepairGenerationRejected("unsupported_mutation")

        source_segment = ast.get_source_segment(source, target_node)
        strategy = (
            "exact_mutation_reversal"
            if source_segment == mutation.mutated_code
            else "ast_expression_restoration"
        )
        start = _source_offset(source, target_node.lineno, target_node.col_offset)
        end = _source_offset(source, target_node.end_lineno, target_node.end_col_offset)
        proposed_source = source[:start] + mutation.original_code + source[end:]
        try:
            ast.parse(proposed_source, filename=mutation.target_file)
        except SyntaxError:
            raise RepairGenerationRejected("candidate_syntax_invalid") from None

        patch = _unified_diff(source, proposed_source, mutation.target_file)
        if not patch or not _is_unified_patch(patch):
            raise RepairGenerationRejected("patch_validation_failed")
        self._validate_in_candidate_workspace(mutation.target_file, proposed_source)

        return GeneratedRepairPatch(
            target_file=mutation.target_file,
            original_source_sha256=original_hash,
            proposed_source_sha256=_sha256(proposed_source.encode("utf-8")),
            original_expression=mutation.mutated_code,
            replacement_expression=mutation.original_code,
            repair_strategy=strategy,
            patch_content=patch,
        )

    @staticmethod
    def _resolve_target(workspace: Path, raw_path: str) -> Path:
        if not raw_path or "\x00" in raw_path:
            raise RepairGenerationRejected("unsafe_source_path")
        normalized = raw_path.replace("\\", "/")
        relative = PurePosixPath(normalized)
        if (
            relative.is_absolute()
            or PureWindowsPath(raw_path).is_absolute()
            or PureWindowsPath(raw_path).drive
            or any(part in {"", ".", ".."} for part in relative.parts)
            or relative.suffix.casefold() != ".py"
        ):
            raise RepairGenerationRejected("unsafe_source_path")

        root = workspace.resolve()
        candidate = root.joinpath(*relative.parts)
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise RepairGenerationRejected("symlink_source_path")
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError):
            raise RepairGenerationRejected("source_file_missing_or_outside_snapshot") from None
        if not resolved.is_file():
            raise RepairGenerationRejected("source_file_missing_or_outside_snapshot")
        return resolved

    @staticmethod
    def _find_mutated_node(
        tree: ast.AST,
        line_number: int,
        col_offset: int | None,
        mutated_code: str,
    ) -> ast.expr:
        if col_offset is None:
            raise RepairGenerationRejected("mutation_ast_location_missing")
        matches = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.expr)
            and getattr(node, "lineno", None) == line_number
            and getattr(node, "col_offset", None) == col_offset
            and ast.unparse(node) == mutated_code
        ]
        if len(matches) != 1:
            raise RepairGenerationRejected(
                "mutation_ast_target_ambiguous" if matches else "mutation_ast_target_not_found"
            )
        return matches[0]

    @staticmethod
    def _parse_expressions(
        original_code: str,
        mutated_code: str,
    ) -> tuple[ast.expr, ast.expr]:
        try:
            original = ast.parse(original_code, mode="eval").body
            mutated = ast.parse(mutated_code, mode="eval").body
        except SyntaxError:
            raise RepairGenerationRejected("mutation_expression_invalid") from None
        return original, mutated

    @staticmethod
    def _mutation_is_supported(
        original: ast.expr,
        mutated: ast.expr,
        mutation_type: str,
    ) -> bool:
        if mutation_type == "comparison_operator":
            original_ops = [
                type(op).__name__
                for node in ast.walk(original)
                if isinstance(node, ast.Compare)
                for op in node.ops
            ]
            mutated_ops = [
                type(op).__name__
                for node in ast.walk(mutated)
                if isinstance(node, ast.Compare)
                for op in node.ops
            ]
            if not _one_supported_difference(
                original_ops,
                mutated_ops,
                {
                    ("Eq", "NotEq"),
                    ("NotEq", "Eq"),
                    ("Gt", "GtE"),
                    ("GtE", "Gt"),
                    ("Lt", "LtE"),
                    ("LtE", "Lt"),
                },
            ):
                return False
            return _operator_normalized_dump(original, ast.cmpop, ast.Eq) == (
                _operator_normalized_dump(mutated, ast.cmpop, ast.Eq)
            )

        if mutation_type == "boolean_operator":
            original_ops = [
                type(node.op).__name__
                for node in ast.walk(original)
                if isinstance(node, ast.BoolOp)
            ]
            mutated_ops = [
                type(node.op).__name__ for node in ast.walk(mutated) if isinstance(node, ast.BoolOp)
            ]
            if not _one_supported_difference(
                original_ops,
                mutated_ops,
                {("And", "Or"), ("Or", "And")},
            ):
                return False
            return _operator_normalized_dump(original, ast.boolop, ast.And) == (
                _operator_normalized_dump(mutated, ast.boolop, ast.And)
            )

        if mutation_type == "arithmetic_operator":
            original_ops = [
                type(node.op).__name__ for node in ast.walk(original) if isinstance(node, ast.BinOp)
            ]
            mutated_ops = [
                type(node.op).__name__ for node in ast.walk(mutated) if isinstance(node, ast.BinOp)
            ]
            if not _one_difference(original_ops, mutated_ops):
                return False
            return _operator_normalized_dump(original, ast.operator, ast.Add) == (
                _operator_normalized_dump(mutated, ast.operator, ast.Add)
            )

        if mutation_type == "numeric_boundary":
            if not isinstance(original, ast.Compare) or not isinstance(mutated, ast.Compare):
                return False
            original_values = _comparison_numeric_constants(original)
            mutated_values = _comparison_numeric_constants(mutated)
            if len(original_values) != len(mutated_values):
                return False
            changed = [
                (before, after)
                for before, after in zip(original_values, mutated_values, strict=True)
                if before != after
            ]
            if len(changed) != 1:
                return False
            all_original_values = _numeric_constants(original)
            all_mutated_values = _numeric_constants(mutated)
            if len(all_original_values) != len(all_mutated_values):
                return False
            all_changes = [
                (before, after)
                for before, after in zip(
                    all_original_values,
                    all_mutated_values,
                    strict=True,
                )
                if before != after
            ]
            if all_changes != changed:
                return False
            before, after = changed[0]
            if before is None or after is None or type(before) is not type(after):
                return False
            expected = (
                {before - 1, before + 1}
                if isinstance(before, int)
                else {round(before - 1, 4), round(before + 1, 4)}
            )
            if after not in expected:
                return False
            return _numeric_normalized_dump(original) == _numeric_normalized_dump(mutated)
        return False

    @staticmethod
    def _validate_in_candidate_workspace(target_file: str, proposed_source: str) -> None:
        with tempfile.TemporaryDirectory(prefix="faultline_repair_candidate_") as temp_dir:
            target = Path(temp_dir).joinpath(*PurePosixPath(target_file).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(proposed_source.encode("utf-8"))
            try:
                candidate_source = target.read_text(encoding="utf-8")
                ast.parse(candidate_source, filename=target_file)
            except (OSError, UnicodeDecodeError, SyntaxError):
                raise RepairGenerationRejected("candidate_syntax_invalid") from None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _source_offset(source: str, line_number: int, byte_column: int | None) -> int:
    if byte_column is None:
        raise RepairGenerationRejected("mutation_ast_location_invalid")
    lines = source.splitlines(keepends=True)
    if line_number < 1 or line_number > len(lines):
        raise RepairGenerationRejected("mutation_ast_location_invalid")
    line = lines[line_number - 1]
    try:
        prefix = line.encode("utf-8")[:byte_column].decode("utf-8")
    except UnicodeDecodeError:
        raise RepairGenerationRejected("mutation_ast_location_invalid") from None
    return sum(len(previous) for previous in lines[: line_number - 1]) + len(prefix)


def _one_difference(left: list[Any], right: list[Any]) -> bool:
    return len(left) == len(right) and sum(a != b for a, b in zip(left, right, strict=True)) == 1


def _one_supported_difference(
    left: list[str],
    right: list[str],
    allowed_pairs: set[tuple[str, str]],
) -> bool:
    if len(left) != len(right):
        return False
    differences = [
        (before, after) for before, after in zip(left, right, strict=True) if before != after
    ]
    return len(differences) == 1 and differences[0] in allowed_pairs


def _operator_normalized_dump(
    expression: ast.expr,
    operator_type: type[ast.AST],
    replacement_type: type[ast.AST],
) -> str:
    normalized = copy.deepcopy(expression)
    if operator_type is ast.cmpop:
        for node in ast.walk(normalized):
            if isinstance(node, ast.Compare):
                node.ops = [replacement_type() for _ in node.ops]  # type: ignore[abstract]
    elif operator_type is ast.boolop:
        for node in ast.walk(normalized):
            if isinstance(node, ast.BoolOp):
                node.op = replacement_type()  # type: ignore[abstract]
    elif operator_type is ast.operator:
        for node in ast.walk(normalized):
            if isinstance(node, ast.BinOp):
                node.op = replacement_type()  # type: ignore[abstract]
    return ast.dump(normalized, include_attributes=False)


def _comparison_numeric_constants(
    expression: ast.Compare,
) -> list[int | float | None]:
    operands = [expression.left, *expression.comparators]
    return [
        operand.value
        if isinstance(operand, ast.Constant)
        and isinstance(operand.value, (int, float))
        and not isinstance(operand.value, bool)
        else None
        for operand in operands
    ]


def _numeric_constants(expression: ast.expr) -> list[int | float]:
    return [
        node.value
        for node in ast.walk(expression)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ]


def _numeric_normalized_dump(expression: ast.expr) -> str:
    normalized = copy.deepcopy(expression)
    for node in ast.walk(normalized):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        ):
            node.value = 0
    return ast.dump(normalized, include_attributes=False)


def _unified_diff(original: str, proposed: str, target_file: str) -> str:
    lines = difflib.unified_diff(
        original.splitlines(),
        proposed.splitlines(),
        fromfile=f"a/{target_file}",
        tofile=f"b/{target_file}",
        lineterm="",
    )
    return "\n".join(lines) + "\n"


def _is_unified_patch(patch: str) -> bool:
    lines = patch.splitlines()
    return (
        len(lines) >= 3
        and lines[0].startswith("--- a/")
        and lines[1].startswith("+++ b/")
        and any(line.startswith("@@ ") for line in lines[2:])
    )
