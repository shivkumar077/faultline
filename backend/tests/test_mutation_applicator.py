from pathlib import Path

import pytest

from app.core.exceptions import ValidationException
from app.services.sandbox.mutation_applicator import MutationApplicator


def test_mutation_applicator_rejects_sibling_path_with_workspace_prefix(tmp_path: Path):
    workspace_path = tmp_path / "workspace"
    outside_path = tmp_path / "workspace-outside"
    workspace_path.mkdir()
    outside_path.mkdir()
    target_file = outside_path / "target.py"
    target_file.write_text("value = 1\n", encoding="utf-8")

    with pytest.raises(ValidationException, match="Path traversal detected"):
        MutationApplicator().apply_mutation(
            workspace_path=workspace_path,
            target_file="../workspace-outside/target.py",
            line_number=1,
            original_code="1",
            mutated_code="2",
        )

    assert target_file.read_text(encoding="utf-8") == "value = 1\n"
