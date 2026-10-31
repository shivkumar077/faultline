import ast
import hashlib
from pathlib import Path

import pytest

from app.core.exceptions import ValidationException
from app.services.mutation.ast_mutator import PythonAstMutator
from app.services.sandbox.mutation_applicator import MutationApplicator


def _apply(workspace: Path, target: str, original: str, mutated: str, source_hash: str):
    source = (workspace / target).read_text(encoding="utf-8")
    node = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Compare) and ast.unparse(node) == original
    )
    return MutationApplicator().apply_mutation(
        workspace_path=workspace,
        target_file=target,
        line_number=node.lineno,
        col_offset=node.col_offset,
        original_code=original,
        mutated_code=mutated,
        source_sha256=source_hash,
    )


def test_mutation_applicator_applies_exact_ast_expression(tmp_path: Path):
    source = "first = check == 1\nsecond = check == 1\n"
    target = tmp_path / "module.py"
    target.write_text(source, encoding="utf-8")

    _apply(
        tmp_path,
        "module.py",
        "check == 1",
        "check != 1",
        hashlib.sha256(source.encode()).hexdigest(),
    )

    assert target.read_text(encoding="utf-8") == "first = check != 1\nsecond = check == 1\n"


def test_mutation_applicator_rejects_source_hash_mismatch(tmp_path: Path):
    target = tmp_path / "module.py"
    target.write_text("value = a == b\n", encoding="utf-8")

    with pytest.raises(ValidationException, match="Source hash mismatch"):
        _apply(tmp_path, "module.py", "a == b", "a != b", "0" * 64)


def test_generated_numeric_mutation_has_exact_expression_position(tmp_path: Path):
    source = "def eligible(age):\n    return age >= 18\n"
    target = tmp_path / "module.py"
    target.write_text(source, encoding="utf-8")
    plan = PythonAstMutator().generate_mutations(tmp_path, "a" * 40)
    mutation = next(item for item in plan.mutations if item.mutation_type == "numeric_boundary")

    MutationApplicator().apply_mutation(
        workspace_path=tmp_path,
        target_file=mutation.target_file,
        line_number=mutation.line_number,
        col_offset=mutation.col_offset,
        original_code=mutation.original_code,
        mutated_code=mutation.mutated_code,
        source_sha256=plan.file_hashes[mutation.target_file],
    )

    assert (
        ast.unparse(ast.parse(target.read_text(encoding="utf-8"))).find(mutation.mutated_code) >= 0
    )


def test_mutation_applicator_rejects_stale_or_ambiguous_source(tmp_path: Path):
    source = "if a == b:\n    return True\n"
    (tmp_path / "module.py").write_text(source, encoding="utf-8")
    applicator = MutationApplicator()

    with pytest.raises(ValidationException, match="exactly one AST expression"):
        applicator.apply_mutation(
            workspace_path=tmp_path,
            target_file="module.py",
            line_number=2,
            col_offset=0,
            original_code="a == b",
            mutated_code="a != b",
            source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        )


def test_mutation_applicator_rejects_ambiguous_ast_anchor(tmp_path: Path):
    source = "value\n"
    (tmp_path / "module.py").write_text(source, encoding="utf-8")

    with pytest.raises(ValidationException, match="found 2"):
        MutationApplicator().apply_mutation(
            workspace_path=tmp_path,
            target_file="module.py",
            line_number=1,
            col_offset=0,
            original_code="value",
            mutated_code="other",
            source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        )


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
            col_offset=0,
            original_code="1",
            mutated_code="2",
            source_sha256=hashlib.sha256(b"value = 1\n").hexdigest(),
        )

    assert target_file.read_text(encoding="utf-8") == "value = 1\n"
