"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import type { Evaluation, RepairCandidate } from "@/lib/types";
import { dateTime, duration, shortId } from "@/lib/format";
import { Badge, Card, ErrorState, JsonDetails, LoadingState, PageBackLink, PageHeading } from "@/components/ui";

export default function EvaluationDetailPage() {
  const { candidateId, evaluationId } = useParams<{ candidateId: string; evaluationId: string }>();
  const [candidate, setCandidate] = useState<RepairCandidate | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const [candidateResult, evaluationResult] = await Promise.all([
        api.repair(candidateId),
        api.evaluation(evaluationId),
      ]);
      if (evaluationResult.repair_candidate_id !== candidateId) {
        throw new Error("This evaluation does not belong to the requested repair candidate.");
      }
      setCandidate(candidateResult);
      setEvaluation(evaluationResult);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Evaluation could not be loaded.");
    } finally { setLoading(false); }
  }, [candidateId, evaluationId]);
  const retry = () => {
    setLoading(true);
    setError("");
    void load();
  };
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  if (loading) return <LoadingState />;
  if (!candidate || !evaluation || error) return <ErrorState message={error || "Evaluation not found."} retry={retry} />;
  const evidence = evaluation.evidence;
  const newFailures = Array.isArray(evidence.new_candidate_failure_ids)
    ? evidence.new_candidate_failure_ids.filter((item): item is string => typeof item === "string")
    : null;
  return <>
    <PageBackLink href={`/repairs/${candidate.id}/evaluations`}>Evaluation history</PageBackLink>
    <PageHeading eyebrow={`EVALUATION / ${shortId(evaluation.id, 13)}`} title="Repair evaluation record" description={`Created ${dateTime(evaluation.created_at)} · Duration ${duration(evaluation.duration_ms)}.`} action={<Badge>{evaluation.status}</Badge>} />
    <div className="metadata-strip"><div><span>REPAIR CANDIDATE</span><strong>{shortId(candidate.id, 16)}</strong></div><div><span>BASELINE EXECUTION</span><strong>{evaluation.baseline_execution_id ? shortId(evaluation.baseline_execution_id, 16) : "Unavailable"}</strong></div><div><span>EXIT CODE</span><strong>{evaluation.exit_code ?? "—"}</strong></div><div><span>COMPLETED</span><strong>{dateTime(evaluation.completed_at)}</strong></div></div>
    <div className="content-grid">
      <Card><p className="eyebrow">LOCAL TEST VERDICT</p><h2>{evaluation.status}</h2><p className="muted">Test results from the backend’s isolated candidate evaluation. This verdict is independent of any optional ForgeFit run.</p><div className="detail-stats"><div><strong>{evaluation.passed_count ?? "—"}</strong><span>Passed</span></div><div><strong>{evaluation.failed_count ?? "—"}</strong><span>Failed</span></div><div><strong>{evaluation.skipped_count ?? "—"}</strong><span>Skipped</span></div><div><strong>{evaluation.error_code ?? "—"}</strong><span>Error code</span></div></div><JsonDetails label="Local execution evidence" value={evaluation.evidence} /></Card>
      <Card><p className="eyebrow">FORGEFIT RESILIENCE</p><h2>{evaluation.forgefit_status}</h2><p className="muted">Optional resilience result from ForgeFit, when requested and configured. It does not imply the patch passed local tests.</p><dl className="detail-list"><dt>ForgeFit run ID</dt><dd>{evaluation.forgefit_run_id ?? "—"}</dd><dt>ForgeFit error</dt><dd>{evaluation.forgefit_error_code ?? "—"}</dd></dl><JsonDetails label="ForgeFit result payload" value={evaluation.forgefit_result} /></Card>
    </div>
    <Card><p className="eyebrow">BASELINE-TO-CANDIDATE COMPARISON</p><h2>Regression evidence</h2><p className="muted">These are the identifiers and classifications returned by the evaluation service; missing data is not inferred.</p><div className="comparison-grid"><div><span>Baseline status</span><strong>{typeof evidence.baseline_status === "string" ? evidence.baseline_status : "Not available"}</strong></div><div><span>Original mutant status</span><strong>{typeof evidence.mutant_status === "string" ? evidence.mutant_status : "Not available"}</strong></div><div><span>Diagnosed test</span><strong>{typeof evidence.diagnosed_test === "string" ? evidence.diagnosed_test : "Not identified"}</strong></div><div><span>Diagnosed test outcome</span><strong>{typeof evidence.diagnosed_test_state === "string" ? evidence.diagnosed_test_state.replaceAll("_", " ") : "Not available"}</strong></div><div className="comparison-wide"><span>New candidate failure IDs</span>{newFailures === null ? <strong>Not available</strong> : newFailures.length ? <ul>{newFailures.map((failure) => <li className="mono" key={failure}>{failure}</li>)}</ul> : <strong>None reported</strong>}</div></div></Card>
    {evaluation.error_code && <div className="inline-alert"><ShieldCheck size={15} />Evaluation error code: {evaluation.error_code}</div>}
    <Card><p className="eyebrow">REPAIR CONTEXT</p><h2>{candidate.target_file}</h2><p className="muted">{candidate.repair_strategy} · Generated candidate, not an automatically applied change.</p><Link className="text-link" href={`/repairs/${candidate.id}`}><ArrowLeft size={14} /> Return to candidate and diff</Link></Card>
  </>;
}
