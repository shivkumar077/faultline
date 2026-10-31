import hashlib
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.core.exceptions import FaultlineException, ValidationException
from app.models.analysis_run import AnalysisRun
from app.models.code_snapshot import CodeSnapshot
from app.models.mutation_record import MutationRecord
from app.models.project import Project
from app.models.repository_connection import RepositoryConnection
from app.repositories.baseline_execution_repository import baseline_execution_repository
from app.services.execution_service import ExecutionService
from app.services.sandbox.baseline_runner import BaselineRunOutput
from app.services.sandbox.docker_runtime import ContainerResult, DockerRuntime

SOURCE = "value = check == 1\n"


class FakeMaterializer:
    def __init__(self):
        self.workspaces: list[Path] = []

    @contextmanager
    def materialized_workspace(self, repository_url: str, commit_hash: str):
        with tempfile.TemporaryDirectory(prefix="faultline-test-") as directory:
            workspace = Path(directory)
            (workspace / "module.py").write_text(SOURCE, encoding="utf-8")
            self.workspaces.append(workspace)
            yield workspace


class FakeBaselineRunner:
    def __init__(self, status="passed"):
        self.status = status

    def run_baseline(self, workspace_path: Path, *, timeout_seconds=None):
        return BaselineRunOutput(
            command="python -m pytest -q --tb=short -p no:cacheprovider",
            status=self.status,
            exit_code=0 if self.status == "passed" else 1,
            stdout="1 passed" if self.status == "passed" else "1 failed",
            stderr="",
            duration_ms=10,
            framework="pytest",
            test_files_count=1,
            passed_count=1 if self.status == "passed" else 0,
            failed_count=0 if self.status == "passed" else 1,
            skipped_count=0,
        )


class FakeRuntime:
    APPROVED_COMMANDS = DockerRuntime.APPROVED_COMMANDS

    def __init__(self, results):
        self.results = iter(results)
        self.calls = 0

    def run_in_container(self, workspace, command, *, timeout_seconds=None):
        self.calls += 1
        assert (workspace / "module.py").read_text(encoding="utf-8") == "value = check != 1\n"
        return next(self.results)


def _result(exit_code: int, *, timed_out: bool = False) -> ContainerResult:
    return ContainerResult(
        exit_code=exit_code,
        stdout="1 failed" if exit_code else "1 passed",
        stderr="",
        duration_ms=20,
        timed_out=timed_out,
    )


def _analysis_with_mutations(db_session, count=5):
    project = Project(name="Execution project", slug=f"exec-{uuid.uuid4().hex[:8]}")
    db_session.add(project)
    db_session.flush()
    connection = RepositoryConnection(
        project_id=project.id,
        repository_url="https://github.com/example/repo",
        branch="main",
    )
    db_session.add(connection)
    db_session.flush()
    snapshot = CodeSnapshot(
        project_id=project.id,
        repository_connection_id=connection.id,
        commit_hash="a" * 40,
        branch="main",
    )
    db_session.add(snapshot)
    db_session.flush()
    analysis = AnalysisRun(
        project_id=project.id,
        code_snapshot_id=snapshot.id,
        status="completed",
        summary={"manifest": [{"mutation_id": "original"}]},
    )
    db_session.add(analysis)
    db_session.flush()
    source_hash = hashlib.sha256(SOURCE.encode("utf-8")).hexdigest()
    mutations = []
    for index in range(count):
        mutations.append(
            MutationRecord(
                analysis_run_id=analysis.id,
                mutation_type="comparison_operator",
                target_file="module.py",
                line_number=2 if index == 4 else 1,
                col_offset=8,
                source_sha256="0" * 64 if index == 4 else source_hash,
                original_code="check == 1",
                mutated_code="check != 1",
                status="applied",
            )
        )
    db_session.add_all(mutations)
    db_session.commit()
    return analysis


def test_execution_service_persists_all_classifications_and_score(db_session):
    analysis = _analysis_with_mutations(db_session)
    materializer = FakeMaterializer()
    runtime = FakeRuntime(
        [
            _result(1),
            _result(0),
            _result(-15, timed_out=True),
            _result(125),
        ]
    )
    service = ExecutionService(
        runner=FakeBaselineRunner(),
        runtime=runtime,
        materializer=materializer,
    )

    response = service.execute_analysis(db_session, analysis.id)

    statuses = [item.status for item in response.execution_results]
    assert statuses == ["KILLED", "SURVIVED", "TIMEOUT", "ERROR", "INVALID"]
    assert response.summary["total_mutations"] == 5
    assert response.summary["killed"] == 1
    assert response.summary["survived"] == 1
    assert response.summary["timed_out"] == 1
    assert response.summary["errored"] == 1
    assert response.summary["invalid"] == 1
    assert response.summary["mutation_score"] == 50.0
    assert response.baseline.passed_count == 1
    assert response.status == "completed"
    assert runtime.calls == 4
    assert len(materializer.workspaces) == 6
    assert len(set(materializer.workspaces)) == len(materializer.workspaces)
    assert all(not workspace.exists() for workspace in materializer.workspaces)
    assert SOURCE == "value = check == 1\n"
    assert not any("C:\\" in (item.stdout or "") for item in response.execution_results)


def test_execution_service_failed_baseline_skips_mutants(db_session):
    analysis = _analysis_with_mutations(db_session, count=1)
    runtime = FakeRuntime([])
    service = ExecutionService(
        runner=FakeBaselineRunner(status="failed"),
        runtime=runtime,
        materializer=FakeMaterializer(),
    )

    response = service.execute_analysis(db_session, analysis.id)

    assert response.status == "failed"
    assert response.execution_results == []
    assert response.summary["mutation_score"] is None
    assert response.summary["total_mutations"] == 1
    assert runtime.calls == 0


def test_execution_service_prevents_duplicate_execution(db_session):
    analysis = _analysis_with_mutations(db_session, count=0)
    service = ExecutionService(
        runner=FakeBaselineRunner(),
        runtime=FakeRuntime([]),
        materializer=FakeMaterializer(),
    )
    service.execute_analysis(db_session, analysis.id)

    with pytest.raises(FaultlineException) as exc:
        service.execute_analysis(db_session, analysis.id)

    assert exc.value.status_code == 409
    assert exc.value.error_code == "EXECUTION_ALREADY_STARTED"


def test_execution_service_zero_denominator_is_null(db_session):
    analysis = _analysis_with_mutations(db_session, count=0)
    service = ExecutionService(
        runner=FakeBaselineRunner(),
        runtime=FakeRuntime([]),
        materializer=FakeMaterializer(),
    )

    response = service.execute_analysis(db_session, analysis.id)

    assert response.summary["mutation_score"] is None


def test_execution_service_uses_existing_mutation_manifest_for_legacy_rows(db_session):
    analysis = _analysis_with_mutations(db_session, count=1)
    mutation = analysis.mutation_records[0]
    mutation.col_offset = None
    mutation.source_sha256 = None
    analysis.summary = {
        "file_hashes": {"module.py": hashlib.sha256(SOURCE.encode()).hexdigest()},
        "manifest": [
            {
                "target_file": "module.py",
                "line_number": 1,
                "col_offset": 8,
                "mutation_type": "comparison_operator",
                "original_code": "check == 1",
                "mutated_code": "check != 1",
            }
        ],
    }
    db_session.commit()
    runtime = FakeRuntime([_result(0)])
    service = ExecutionService(
        runner=FakeBaselineRunner(),
        runtime=runtime,
        materializer=FakeMaterializer(),
    )

    response = service.execute_analysis(db_session, analysis.id)

    assert response.execution_results[0].status == "SURVIVED"


def test_execution_service_persists_failed_baseline_infrastructure(db_session):
    analysis = _analysis_with_mutations(db_session, count=0)

    class UnavailableRunner:
        def run_baseline(self, workspace_path, *, timeout_seconds=None):
            raise FaultlineException(
                status_code=503,
                detail="Docker is unavailable",
                error_code="DOCKER_UNAVAILABLE",
            )

    service = ExecutionService(
        runner=UnavailableRunner(),
        runtime=FakeRuntime([]),
        materializer=FakeMaterializer(),
    )
    with pytest.raises(FaultlineException) as exc:
        service.execute_analysis(db_session, analysis.id)

    baseline = baseline_execution_repository.get_by_analysis(db_session, analysis.id)
    db_session.refresh(analysis)
    assert exc.value.error_code == "DOCKER_UNAVAILABLE"
    assert baseline.status == "error"
    assert baseline.infrastructure_error == "DOCKER_UNAVAILABLE"
    assert analysis.status == "failed"


def test_mutant_materialization_error_is_not_classified_as_invalid(db_session):
    analysis = _analysis_with_mutations(db_session, count=1)

    class FailsForMutantMaterializer(FakeMaterializer):
        @contextmanager
        def materialized_workspace(self, repository_url: str, commit_hash: str):
            if self.workspaces:
                raise ValidationException("snapshot materialization failed")
            with super().materialized_workspace(repository_url, commit_hash) as workspace:
                yield workspace

    service = ExecutionService(
        runner=FakeBaselineRunner(),
        runtime=FakeRuntime([]),
        materializer=FailsForMutantMaterializer(),
    )

    response = service.execute_analysis(db_session, analysis.id)

    result = response.execution_results[0]
    assert result.status == "ERROR"
    assert result.infrastructure_error == "VALIDATION_ERROR"
