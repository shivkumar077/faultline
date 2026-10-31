"""Safe AST and code mutation applicator for isolated workspaces."""

import ast
import logging
from pathlib import Path

from app.core.exceptions import ValidationException

logger = logging.getLogger("faultline.sandbox.mutation_applicator")


class MutationApplicator:
    """Applies code mutations into an isolated workspace directory."""

    def apply_mutation(
        self,
        workspace_path: Path,
        target_file: str,
        line_number: int,
        original_code: str,
        mutated_code: str,
    ) -> Path:
        """Apply a mutation to a file within the workspace.

        Args:
            workspace_path: Base directory of the isolated workspace.
            target_file: Relative path to the target python file.
            line_number: 1-indexed line number where mutation occurs.
            original_code: The code snippet to be replaced.
            mutated_code: The replacement mutated snippet.

        Returns:
            The Path of the modified file.

        Raises:
            ValidationException: If path escapes workspace, file not found, or invalid syntax.
        """
        # Security: Prevent directory traversal
        resolved_ws = workspace_path.resolve()
        target_path = (workspace_path / target_file).resolve()

        if not target_path.is_relative_to(resolved_ws):
            raise ValidationException(f"Path traversal detected: {target_file} escapes workspace.")

        if not target_path.is_file():
            raise ValidationException(f"Target file does not exist in workspace: {target_file}")

        content = target_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines(keepends=True)

        if not (1 <= line_number <= len(lines)):
            raise ValidationException(
                f"Line number {line_number} is out of bounds for "
                f"{target_file} ({len(lines)} lines)."
            )

        # Attempt replacement on target line
        applied = False
        target_idx = line_number - 1

        if original_code in lines[target_idx]:
            lines[target_idx] = lines[target_idx].replace(original_code, mutated_code, 1)
            applied = True
        else:
            # Fallback: search adjacent lines within small window
            start_idx = max(0, target_idx - 3)
            end_idx = min(len(lines), target_idx + 4)
            for idx in range(start_idx, end_idx):
                if original_code in lines[idx]:
                    lines[idx] = lines[idx].replace(original_code, mutated_code, 1)
                    applied = True
                    break

        if not applied:
            # Full content fallback if multiline or slight offset
            if original_code in content:
                content = content.replace(original_code, mutated_code, 1)
                new_content = content
            else:
                raise ValidationException(
                    f"Original code snippet '{original_code}' not found near "
                    f"line {line_number} of {target_file}."
                )
        else:
            new_content = "".join(lines)

        # Verify syntactic validity of the mutated file
        try:
            ast.parse(new_content, filename=target_file)
        except SyntaxError as exc:
            raise ValidationException(
                f"Mutation produced invalid Python syntax in {target_file}: {exc}"
            ) from exc

        # Write mutated content to isolated workspace file
        target_path.write_text(new_content, encoding="utf-8")
        logger.info(
            "Applied mutation to %s:%d: '%s' -> '%s'",
            target_file,
            line_number,
            original_code,
            mutated_code,
        )
        return target_path


mutation_applicator = MutationApplicator()
