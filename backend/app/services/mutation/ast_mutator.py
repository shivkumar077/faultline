import ast
import copy
import hashlib
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("faultline.mutation")

SKIPPED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "vendor",
    ".next",
    "coverage",
    "migrations",
    "alembic",
}

COMPARISON_MAP: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
}


@dataclass(frozen=True)
class CandidateMutation:
    mutation_id: str
    target_file: str
    mutation_type: str
    line_number: int
    col_offset: int
    original_code: str
    mutated_code: str
    operator_name: str


@dataclass
class MutationPlan:
    snapshot_commit: str
    random_seed: int
    total_candidates: int
    generated_count: int
    supported_language: str
    operators_used: list[str]
    mutations: list[CandidateMutation]
    skipped_files: list[dict[str, str]]
    file_hashes: dict[str, str]

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "snapshot_commit": self.snapshot_commit,
            "random_seed": self.random_seed,
            "total_candidates": self.total_candidates,
            "generated_mutations": self.generated_count,
            "supported_language": self.supported_language,
            "operators_used": self.operators_used,
            "skipped_files": self.skipped_files,
            "file_hashes": self.file_hashes,
            "manifest": [
                {
                    "mutation_id": m.mutation_id,
                    "target_file": m.target_file,
                    "mutation_type": m.mutation_type,
                    "line_number": m.line_number,
                    "col_offset": m.col_offset,
                    "original_code": m.original_code,
                    "mutated_code": m.mutated_code,
                    "operator_name": m.operator_name,
                }
                for m in self.mutations
            ],
        }


class PythonAstMutator:
    def __init__(self, default_max_mutations: int = 100):
        self.default_max_mutations = default_max_mutations

    def collect_file_mutations(
        self, file_path: Path, rel_path: str, source: str
    ) -> tuple[list[tuple[CandidateMutation, ast.AST]], str]:
        """Parse source into AST and collect all valid candidate mutations."""
        tree = ast.parse(source, filename=rel_path)
        file_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
        candidates: list[tuple[CandidateMutation, ast.AST]] = []

        seen_positions: set[tuple[int, int, str]] = set()

        for node in ast.walk(tree):
            # Operator A: Comparison operators (==, !=, >, >=, <, <=)
            if isinstance(node, ast.Compare):
                for idx, op in enumerate(node.ops):
                    op_cls = type(op)
                    if op_cls in COMPARISON_MAP:
                        target_op = COMPARISON_MAP[op_cls]
                        pos_key = (node.lineno, node.col_offset, f"cmp_{idx}")
                        if pos_key in seen_positions:
                            continue
                        seen_positions.add(pos_key)

                        orig_snippet = ast.unparse(node)

                        mutated_tree = copy.deepcopy(tree)
                        # Locate corresponding node in copy
                        for sub in ast.walk(mutated_tree):
                            if (
                                isinstance(sub, ast.Compare)
                                and sub.lineno == node.lineno
                                and sub.col_offset == node.col_offset
                            ):
                                sub.ops[idx] = target_op()
                                break

                        mutated_snippet = ast.unparse(sub)
                        mid = hashlib.sha256(
                            f"{rel_path}:{node.lineno}:{node.col_offset}:cmp:{idx}:{target_op.__name__}".encode()
                        ).hexdigest()[:16]

                        candidates.append(
                            (
                                CandidateMutation(
                                    mutation_id=mid,
                                    target_file=rel_path,
                                    mutation_type="comparison_operator",
                                    line_number=node.lineno,
                                    col_offset=node.col_offset,
                                    original_code=orig_snippet,
                                    mutated_code=mutated_snippet,
                                    operator_name=f"{op_cls.__name__}_to_{target_op.__name__}",
                                ),
                                mutated_tree,
                            )
                        )

                # Operator C: Numeric boundary in comparison (e.g. 10 -> 9, 10 -> 11)
                nums_to_check: list[tuple[ast.AST, str]] = []
                if isinstance(node.left, ast.Constant) and isinstance(
                    node.left.value, (int, float)
                ) and not isinstance(node.left.value, bool):
                    nums_to_check.append((node.left, "left"))

                for c_idx, comp in enumerate(node.comparators):
                    if isinstance(comp, ast.Constant) and isinstance(
                        comp.value, (int, float)
                    ) and not isinstance(comp.value, bool):
                        nums_to_check.append((comp, f"comp_{c_idx}"))

                for num_node, pos_label in nums_to_check:
                    val = num_node.value  # type: ignore[attr-defined]
                    for delta, delta_name in [(-1, "decrement"), (1, "increment")]:
                        new_val = val + delta if isinstance(val, int) else round(val + delta, 4)
                        pos_key = (num_node.lineno, num_node.col_offset, f"num_{delta_name}")
                        if pos_key in seen_positions:
                            continue
                        seen_positions.add(pos_key)

                        orig_snippet = ast.unparse(node)

                        mutated_tree = copy.deepcopy(tree)
                        for sub in ast.walk(mutated_tree):
                            if (
                                isinstance(sub, ast.Compare)
                                and sub.lineno == node.lineno
                                and sub.col_offset == node.col_offset
                            ):
                                if pos_label == "left":
                                    sub.left = ast.Constant(value=new_val)
                                else:
                                    c_i = int(pos_label.split("_")[1])
                                    sub.comparators[c_i] = ast.Constant(value=new_val)
                                break

                        mutated_snippet = ast.unparse(sub)
                        mid = hashlib.sha256(
                            f"{rel_path}:{num_node.lineno}:{num_node.col_offset}:boundary:{delta_name}:{new_val}".encode()
                        ).hexdigest()[:16]

                        candidates.append(
                            (
                                CandidateMutation(
                                    mutation_id=mid,
                                    target_file=rel_path,
                                    mutation_type="numeric_boundary",
                                    line_number=num_node.lineno,
                                    col_offset=num_node.col_offset,
                                    original_code=orig_snippet,
                                    mutated_code=mutated_snippet,
                                    operator_name=f"numeric_{delta_name}",
                                ),
                                mutated_tree,
                            )
                        )

            # Operator B: Boolean operators (and <-> or)
            elif isinstance(node, ast.BoolOp):
                orig_op_cls = type(node.op)
                new_op_cls: type[ast.boolop] | None = None
                if isinstance(node.op, ast.And):
                    new_op_cls = ast.Or
                elif isinstance(node.op, ast.Or):
                    new_op_cls = ast.And

                if new_op_cls is not None:
                    pos_key = (node.lineno, node.col_offset, "bool_op")
                    if pos_key in seen_positions:
                        continue
                    seen_positions.add(pos_key)

                    orig_snippet = ast.unparse(node)

                    mutated_tree = copy.deepcopy(tree)
                    for sub in ast.walk(mutated_tree):
                        if (
                            isinstance(sub, ast.BoolOp)
                            and sub.lineno == node.lineno
                            and sub.col_offset == node.col_offset
                        ):
                            sub.op = new_op_cls()
                            break

                    mutated_snippet = ast.unparse(sub)
                    mid = hashlib.sha256(
                        f"{rel_path}:{node.lineno}:{node.col_offset}:bool:{orig_op_cls.__name__}_to_{new_op_cls.__name__}".encode()
                    ).hexdigest()[:16]

                    candidates.append(
                        (
                            CandidateMutation(
                                mutation_id=mid,
                                target_file=rel_path,
                                mutation_type="boolean_operator",
                                line_number=node.lineno,
                                col_offset=node.col_offset,
                                original_code=orig_snippet,
                                mutated_code=mutated_snippet,
                                operator_name=f"{orig_op_cls.__name__}_to_{new_op_cls.__name__}",
                            ),
                            mutated_tree,
                        )
                    )

        return candidates, file_sha256

    def generate_mutations(
        self,
        workspace_dir: Path,
        commit_hash: str,
        seed: int = 42,
        max_mutations: int | None = None,
    ) -> MutationPlan:
        """Scan workspace, gather candidates, verify syntax, and select deterministically."""
        limit = max_mutations if max_mutations is not None else self.default_max_mutations
        all_candidates: list[tuple[CandidateMutation, ast.AST]] = []
        skipped_files: list[dict[str, str]] = []
        file_hashes: dict[str, str] = {}
        operators_used_set: set[str] = set()

        # 1. Discover all Python files with stable sorting
        py_files: list[Path] = []
        for p in workspace_dir.rglob("*.py"):
            parts = set(p.relative_to(workspace_dir).parts)
            if not parts.intersection(SKIPPED_DIRS):
                py_files.append(p)
        py_files.sort(key=lambda p: p.relative_to(workspace_dir).as_posix())

        # 2. Parse and collect candidates from each file
        for py_path in py_files:
            rel_path = py_path.relative_to(workspace_dir).as_posix()
            try:
                source = py_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                skipped_files.append({"file": rel_path, "reason": f"Read error: {exc}"})
                continue

            try:
                file_candidates, f_hash = self.collect_file_mutations(py_path, rel_path, source)
                file_hashes[rel_path] = f_hash
                all_candidates.extend(file_candidates)
            except SyntaxError as exc:
                err_msg = f"SyntaxError: {exc.msg} at line {exc.lineno}"
                skipped_files.append({"file": rel_path, "reason": err_msg})
            except Exception as exc:
                skipped_files.append({"file": rel_path, "reason": f"Parse error: {exc}"})

        # 3. Deterministic selection with configurable seed
        total_candidates = len(all_candidates)
        rng = random.Random(seed)

        if total_candidates > limit:
            # Deterministic sample
            selected_candidates = rng.sample(all_candidates, limit)
        else:
            selected_candidates = list(all_candidates)

        # Stable sort selected mutations by file and position
        selected_candidates.sort(
            key=lambda item: (
                item[0].target_file,
                item[0].line_number,
                item[0].col_offset,
                item[0].mutation_type,
            )
        )

        # 4. Verify syntax validity of every selected mutation
        final_mutations: list[CandidateMutation] = []
        for cand, mutated_tree in selected_candidates:
            try:
                mutated_source = ast.unparse(mutated_tree)
                ast.parse(mutated_source)  # Verify validity
                final_mutations.append(cand)
                operators_used_set.add(cand.mutation_type)
            except Exception as exc:
                logger.warning(
                    "Generated mutation %s produced invalid syntax: %s",
                    cand.mutation_id,
                    exc,
                )

        return MutationPlan(
            snapshot_commit=commit_hash,
            random_seed=seed,
            total_candidates=total_candidates,
            generated_count=len(final_mutations),
            supported_language="python",
            operators_used=sorted(operators_used_set),
            mutations=final_mutations,
            skipped_files=skipped_files,
            file_hashes=file_hashes,
        )


python_ast_mutator = PythonAstMutator()
