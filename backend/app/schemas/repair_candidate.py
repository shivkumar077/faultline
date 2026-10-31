import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RepairReviewDecision = Literal["reviewed", "rejected"]


class GenerateRepairCandidatesRequest(BaseModel):
    failure_report_ids: list[uuid.UUID] | None = Field(default=None, max_length=1000)


class RepairCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    failure_report_id: uuid.UUID
    analysis_run_id: uuid.UUID
    code_snapshot_id: uuid.UUID
    mutation_record_id: uuid.UUID | None
    snapshot_commit: str
    target_file: str
    original_source_sha256: str
    proposed_source_sha256: str
    original_expression: str
    replacement_expression: str
    repair_strategy: str
    explanation: str
    evidence_references: list[dict[str, object]]
    confidence_score: float = Field(ge=0.0, le=1.0)
    validation_status: str
    validation_error: str | None
    review_status: str
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RepairCandidateSkip(BaseModel):
    failure_report_id: uuid.UUID
    reason: str


class RepairGenerationResponse(BaseModel):
    analysis_run_id: uuid.UUID
    candidates: list[RepairCandidateResponse]
    skipped: list[RepairCandidateSkip]


class RepairPatchResponse(BaseModel):
    repair_candidate_id: uuid.UUID
    patch_content: str
    original_source_sha256: str
    proposed_source_sha256: str


class RepairCandidateReviewRequest(BaseModel):
    decision: RepairReviewDecision
