"""Strict AST-anchored mutation application for isolated workspaces."""

import ast
import hashlib
import logging
from pathlib import Path

from app.core.exceptions import ValidationException

logger = logging.getLogger("faultline.sandbox.mutation_applicator")


class MutationApplicator:
    """Apply one manifest mutation only when its source is an exact match."""

    def apply_mutation(
        self,
        workspace_path: Path,
        target_file: str,
        line_number: int,
        col_offset: int | None,
        original_code: str,
        mutated_code: str,
        source_sha256: str,
    ) -> Path:
        """Validate source hash and replace the uniquely located AST expression."""
        resolved_workspace = workspace_path.resolve()
        target_path = (resolved_workspace / target_file).resolve()
        if not target_path.is_relative_to(resolved_workspace):
            raise ValidationException(f"Path traversal detected: {target_file} escapes workspace.")
        if not target_path.is_file():
            raise ValidationException(f"Target file does not exist in workspace: {target_file}")

        source_bytes = target_path.read_bytes()
        try:
            source = target_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationException(
                f"Mutation target is not valid UTF-8 Python: {target_file}"
            ) from exc
        actual_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if actual_hash != source_sha256:
            raise ValidationException(f"Source hash mismatch for mutation target: {target_file}")
        try:
            tree = ast.parse(source, filename=target_file)
        except SyntaxError as exc:
            raise ValidationException(
                f"Mutation target is not valid UTF-8 Python: {target_file}"
            ) from exc

        matches = [
            node
            for node in ast.walk(tree)
            if getattr(node, "lineno", None) == line_number
            and (col_offset is None or getattr(node, "col_offset", None) == col_offset)
            and ast.unparse(node) == original_code
            and getattr(node, "end_lineno", None) is not None
            and getattr(node, "end_col_offset", None) is not None
        ]
        if len(matches) != 1:
            raise ValidationException(
                f"Mutation source must match exactly one AST expression; found {len(matches)}."
            )

        try:
            replacement_tree = ast.parse(mutated_code, mode="eval")
        except SyntaxError as exc:
            raise ValidationException(f"Mutated expression is invalid Python: {exc.msg}") from exc
        if not isinstance(replacement_tree.body, ast.expr):
            raise ValidationException("Mutation replacement must be a Python expression.")

        node = matches[0]
        lines = source_bytes.splitlines(keepends=True)
        start = sum(len(part) for part in lines[: line_number - 1]) + col_offset
        end_line = node.end_lineno
        end_column = node.end_col_offset
        if end_line is None or end_column is None or end_line > len(lines):
            raise ValidationException("Mutation source position is outside the target file.")
        end = sum(len(part) for part in lines[: end_line - 1]) + end_column
        new_source = source_bytes[:start] + mutated_code.encode("utf-8") + source_bytes[end:]

        try:
            ast.parse(new_source.decode("utf-8"), filename=target_file)
        except (UnicodeDecodeError, SyntaxError) as exc:
            raise ValidationException(
                f"Mutation produced invalid Python syntax in {target_file}."
            ) from exc

        target_path.write_bytes(new_source)
        logger.info("Applied validated mutation to %s:%d", target_file, line_number)
        return target_path


mutation_applicator = MutationApplicator()
