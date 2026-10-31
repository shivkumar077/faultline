import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.code_snapshot import CodeSnapshot
from app.repositories.code_snapshot_repository import code_snapshot_repository
from app.schemas.code_snapshot import CodeSnapshotResponse
from app.services.ingestion_service import ingestion_service
from app.services.repository_service import repository_service


class SnapshotService:
    def __init__(self):
        self.repo = code_snapshot_repository
        self.repo_service = repository_service
        self.ingestion = ingestion_service

    def sync_repository(self, db: Session, repository_id: uuid.UUID) -> CodeSnapshotResponse:
        """Safely ingest repository, generate/return snapshot, and update status."""
        conn = self.repo_service.get_repository_model(db, repository_id)

        conn.status = "syncing"
        db.commit()

        try:
            commit_hash, inventory = self.ingestion.ingest(conn.repository_url, conn.branch)

            # Prevent duplicate snapshot creation if this commit has already been captured
            existing = self.repo.get_by_project_and_commit(db, conn.project_id, commit_hash)
            if existing:
                conn.status = "connected"
                conn.last_synced_at = datetime.now(UTC)
                db.commit()
                return CodeSnapshotResponse.model_validate(existing)

            snapshot = self.repo.create(
                db,
                obj_in={
                    "project_id": conn.project_id,
                    "repository_connection_id": conn.id,
                    "commit_hash": commit_hash,
                    "branch": conn.branch,
                    "file_tree_summary": inventory,
                    "status": "captured",
                },
            )
            conn.status = "connected"
            conn.last_synced_at = datetime.now(UTC)
            db.commit()
            db.refresh(snapshot)
            return CodeSnapshotResponse.model_validate(snapshot)

        except Exception:
            conn.status = "error"
            db.commit()
            raise

    def list_repository_snapshots(
        self, db: Session, repository_id: uuid.UUID
    ) -> Sequence[CodeSnapshotResponse]:
        # Verify repository connection exists
        self.repo_service.get_repository_model(db, repository_id)
        snapshots = self.repo.get_by_repository(db, repository_id)
        return [CodeSnapshotResponse.model_validate(s) for s in snapshots]

    def get_snapshot(self, db: Session, snapshot_id: uuid.UUID) -> CodeSnapshotResponse:
        snapshot = self.repo.get(db, snapshot_id)
        if not snapshot:
            raise NotFoundException(resource="CodeSnapshot", identifier=snapshot_id)
        return CodeSnapshotResponse.model_validate(snapshot)

    def get_snapshot_model(self, db: Session, snapshot_id: uuid.UUID) -> CodeSnapshot:
        snapshot = self.repo.get(db, snapshot_id)
        if not snapshot:
            raise NotFoundException(resource="CodeSnapshot", identifier=snapshot_id)
        return snapshot


snapshot_service = SnapshotService()
