from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy models."""
    pass


# Import all models to ensure they are registered on Base.metadata
from app.models.analysis_run import AnalysisRun  # noqa: E402
from app.models.baseline_execution import BaselineExecution  # noqa: E402
from app.models.code_snapshot import CodeSnapshot  # noqa: E402
from app.models.execution_result import ExecutionResult  # noqa: E402
from app.models.failure_report import FailureReport  # noqa: E402
from app.models.mutation_record import MutationRecord  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.repository_connection import RepositoryConnection  # noqa: E402

__all__ = [
    "Base",
    "Project",
    "RepositoryConnection",
    "CodeSnapshot",
    "AnalysisRun",
    "BaselineExecution",
    "MutationRecord",
    "ExecutionResult",
    "FailureReport",
]
