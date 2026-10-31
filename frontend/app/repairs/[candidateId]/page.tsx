"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowRight, Check, Clipboard, ShieldCheck, X } from "lucide-react";
import { api } from "@/lib/api";
import type { Patch, RepairCandidate } from "@/lib/types";
import { dateTime, percent, shortId } from "@/lib/format";
import { notify } from "@/components/notifications";
import { Badge, Card, ErrorState, JsonDetails, LoadingState, PageBackLink, PageHeading } from "@/components/ui";

export default function RepairDetailPage() {
  const { candidateId } = useParams<{ candidateId: string }>();
  const [candidate, setCandidate] = useState<RepairCandidate | null>(null);
  const [patch, setPatch] = useState<Patch | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const [item, diff] = await Promise.all([api.repair(candidateId), api.patch(candidateId)]);
      setCandidate(item); setPatch(diff);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Candidate details could not be loaded."); }
    finally { setLoading(false); }
  }, [candidateId]);
  const retry = () => {
    setLoading(true);
    setError("");
    void load();
  };
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  async function review(decision: "reviewed" | "rejected") {
    const text = decision === "rejected" ? "Reject this generated repair candidate?" : "Mark this candidate reviewed? This does not mean it is correct or verified.";
    if (!window.confirm(text)) return;
    setBusy(true);
    try { setCandidate(await api.reviewRepair(candidateId, decision)); notify(`Candidate marked ${decision}.`); }
    catch (reason) { notify(reason instanceof Error ? reason.message : "Review update failed.", "error"); }
    finally { setBusy(false); }
  }
  async function copyPatch() {
    if (!patch) return;
    try { await navigator.clipboard.writeText(patch.patch_content); notify("Unified diff copied."); }
    catch { notify("Clipboard access was denied by the browser.", "error"); }
  }
  if (loading) return <LoadingState />;
  if (!candidate || !patch || error) return <ErrorState message={error || "Candidate not found."} retry={retry} />;
  const diffRows = patch.patch_content.split(/\r?\n/);
  return <>
    <PageBackLink href={`/analyses/${candidate.analysis_run_id}/repairs`}>Repair candidates</PageBackLink>
    <PageHeading eyebrow={`REPAIR CANDIDATE / ${shortId(candidate.id, 13)}`} title={candidate.target_file} description={candidate.explanation} action={<Badge>{candidate.review_status}</Badge>} />
    <div className="action-strip"><Link className="editorial-btn-primary" href={`/repairs/${candidate.id}/evaluations`}><ShieldCheck size={15} /> Evaluate candidate <ArrowRight size={14} /></Link><button className="editorial-btn-secondary" disabled={busy || candidate.review_status === "reviewed"} onClick={() => void review("reviewed")}><Check size={15} /> Mark reviewed</button><button className="editorial-btn-secondary danger-button" disabled={busy || candidate.review_status === "rejected"} onClick={() => void review("rejected")}><X size={15} /> Reject candidate</button><button className="editorial-btn-secondary" onClick={() => void copyPatch()}><Clipboard size={15} /> Copy diff</button></div>
    <div className="detail-stats">
      <div><strong>{candidate.repair_strategy}</strong><span>Strategy</span></div><div><strong>{percent(candidate.confidence_score)}</strong><span>Confidence</span></div><div><strong>{candidate.validation_status}</strong><span>Patch validation</span></div><div><strong>{dateTime(candidate.created_at)}</strong><span>Generated</span></div>
    </div>
    {candidate.validation_error && <div className="inline-alert"><X size={15} />{candidate.validation_error}</div>}
    <Card><div className="diff-toolbar"><div><p className="eyebrow">UNIFIED DIFF · PROPOSED CHANGE</p><strong>{candidate.target_file}</strong></div><span className="muted">{diffRows.filter((line) => line.startsWith("+") && !line.startsWith("+++")).length} additions · {diffRows.filter((line) => line.startsWith("-") && !line.startsWith("---")).length} deletions</span></div>
      <div className="diff-view" role="region" aria-label="Unified diff" tabIndex={0}>{diffRows.map((line, index) => <div className={`diff-line ${line.startsWith("+") ? "diff-add" : line.startsWith("-") ? "diff-remove" : line.startsWith("@@") ? "diff-hunk" : ""}`} key={index}><span className="diff-number">{line.startsWith("+") ? "+" : line.startsWith("-") ? "−" : " "}</span><code>{line || " "}</code></div>)}</div>
      <div className="diff-pair"><div><span>ORIGINAL EXPRESSION</span><pre>{candidate.original_expression}</pre></div><div><span>REPLACEMENT EXPRESSION</span><pre>{candidate.replacement_expression}</pre></div></div>
    </Card>
    <div className="content-grid">
      <Card><p className="eyebrow">SOURCE INTEGRITY</p><h2>Snapshot and hashes</h2><dl className="detail-list"><dt>Snapshot commit</dt><dd className="mono">{candidate.snapshot_commit}</dd><dt>Original SHA-256</dt><dd className="mono break-all">{candidate.original_source_sha256}</dd><dt>Proposed SHA-256</dt><dd className="mono break-all">{candidate.proposed_source_sha256}</dd><dt>Associated diagnosis</dt><dd><Link className="text-link" href={`/diagnoses/${candidate.failure_report_id}`}>{shortId(candidate.failure_report_id, 18)} <ArrowRight size={13} /></Link></dd></dl></Card>
      <Card><p className="eyebrow">EVIDENCE</p><h2>Candidate rationale</h2><p className="prose">{candidate.explanation}</p><p className="muted">A generated patch is neither applied to the connected repository nor considered a verified repair.</p><JsonDetails label="Evidence references" value={candidate.evidence_references} /></Card>
    </div>
  </>;
}
