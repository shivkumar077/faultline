"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Activity, ExternalLink, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import type { Evaluation, Page, RepairCandidate } from "@/lib/types";
import { dateTime, duration, shortId } from "@/lib/format";
import { notify } from "@/components/notifications";
import { Badge, Card, EmptyState, ErrorState, JsonDetails, LoadingState, PageBackLink, PageHeading } from "@/components/ui";

export default function EvaluationsPage() {
  const { candidateId } = useParams<{ candidateId: string }>();
  const [candidate, setCandidate] = useState<RepairCandidate | null>(null);
  const [history, setHistory] = useState<Page<Evaluation> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [forgefit, setForgefit] = useState(false);
  const [allowExternal, setAllowExternal] = useState(false);
  const load = useCallback(async () => {
    try {
      const [c, evaluations] = await Promise.all([api.repair(candidateId), api.evaluations(candidateId)]);
      setCandidate(c); setHistory(evaluations);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Evaluation history could not be loaded."); }
    finally { setLoading(false); }
  }, [candidateId]);
  const retry = () => {
    setLoading(true);
    setError("");
    void load();
  };
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  async function evaluate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const timeout = Number(form.get("timeout_seconds"));
    if (!Number.isInteger(timeout) || timeout < 1 || timeout > 3600) {
      notify("Timeout must be a whole number from 1 to 3600 seconds.", "error"); return;
    }
    if (forgefit && allowExternal && !window.confirm("This optional ForgeFit scenario targets an external URL you have authorization to test. Continue?")) return;
    setBusy(true);
    try {
      const scenario = forgefit ? {
        target_url: String(form.get("target_url")).trim(),
        request_count: Number(form.get("request_count")),
        timeout_seconds: Number(form.get("request_timeout")),
        artificial_latency_ms: Number(form.get("artificial_latency_ms")),
        failure_probability: Number(form.get("failure_probability")),
        total_deadline_seconds: Number(form.get("total_deadline_seconds")),
        allow_external: allowExternal,
        authorized_acknowledgement: allowExternal && form.get("authorized_acknowledgement") === "on",
        seed: form.get("seed") === "" ? undefined : Number(form.get("seed")),
      } : undefined;
      if (forgefit && !scenario?.target_url) { notify("Enter a target URL for the ForgeFit scenario.", "error"); return; }
      const result = await api.evaluate(candidateId, {
        timeout_seconds: timeout,
        ...(scenario ? { forgefit_scenario: scenario } : {}),
      });
      notify(`Evaluation recorded: ${result.status}. ForgeFit: ${result.forgefit_status}.`);
      await load();
    } catch (reason) { notify(reason instanceof Error ? reason.message : "Evaluation request failed.", "error"); }
    finally { setBusy(false); }
  }
  if (loading) return <LoadingState />;
  if (!candidate || error) return <ErrorState message={error || "Candidate not found."} retry={retry} />;
  return <>
    <PageBackLink href={`/repairs/${candidate.id}`}>Repair candidate</PageBackLink>
    <PageHeading eyebrow="INDEPENDENT VALIDATION" title="Repair evaluation" description={`Evaluate the generated patch in an isolated workspace. Candidate ${shortId(candidate.id, 13)}.`} />
    <div className="note-line"><ShieldCheck size={15} /> Local test verdict and optional ForgeFit resilience results are tracked independently. A generated patch is not a verified repair.</div>
    <div className="content-grid">
      <Card><p className="eyebrow">START AN EVALUATION</p><h2>Run candidate tests</h2><p className="muted">The backend applies this patch only to its isolated snapshot workspace and runs tests via the approved Docker runner.</p>
        <form className="form-grid single-column" onSubmit={evaluate}><label>Test timeout (seconds)<input name="timeout_seconds" type="number" min={1} max={3600} defaultValue={300} required /></label>
          <label className="checkbox-row"><input type="checkbox" checked={forgefit} onChange={(event) => setForgefit(event.target.checked)} /> Include optional ForgeFit resilience scenario</label>
          {forgefit && <div className="scenario-panel">
            <p className="muted">ForgeFit must be configured on the backend. Its result does not change the local test verdict.</p>
            <label>Authorized target URL<input name="target_url" type="url" required={forgefit} placeholder="https://service.example/health" /></label>
            <div className="form-grid two-col"><label>Request count<input name="request_count" type="number" min={1} max={1000} defaultValue={10} /></label><label>Request timeout (s)<input name="request_timeout" type="number" min={0.01} max={120} step={0.1} defaultValue={5} /></label><label>Artificial latency (ms)<input name="artificial_latency_ms" type="number" min={0} max={60000} defaultValue={0} /></label><label>Failure probability<input name="failure_probability" type="number" min={0} max={1} step={0.01} defaultValue={0} /></label><label>Total deadline (s)<input name="total_deadline_seconds" type="number" min={0.01} max={3600} step={0.1} defaultValue={30} /></label><label>Deterministic seed<input name="seed" type="number" placeholder="Optional" /></label></div>
            <label className="checkbox-row"><input type="checkbox" checked={allowExternal} onChange={(event) => setAllowExternal(event.target.checked)} /> This target is external to my environment and I am authorized to run this scenario.</label>
            {allowExternal && <label className="checkbox-row"><input name="authorized_acknowledgement" type="checkbox" required /> I acknowledge that I have permission to send test traffic to this target.</label>}
          </div>}
          <button className="editorial-btn-primary" disabled={busy}><Activity size={15} />{busy ? "Evaluation running…" : "Start evaluation"}</button>
        </form>
      </Card>
      <Card><p className="eyebrow">CANDIDATE</p><h2>{candidate.target_file}</h2><div className="detail-list"><span>Strategy</span><strong>{candidate.repair_strategy}</strong><span>Validation</span><strong>{candidate.validation_status}</strong><span>Review</span><strong>{candidate.review_status}</strong></div><Link className="text-link" href={`/repairs/${candidate.id}`}>Inspect patch and hashes <ExternalLink size={14} /></Link></Card>
    </div>
    <Card><div className="section-heading"><div><p className="eyebrow">PERSISTED RESULTS</p><h2>{history?.total ?? 0} evaluations</h2></div></div>
      {!history?.items.length ? <EmptyState title="No evaluations yet" description="Start an evaluation to compare baseline and candidate test outcomes." /> :
        <div className="stack-list">{history.items.map((item) => <details className="evaluation-row" key={item.id}><summary><span className="evaluation-summary"><strong>{dateTime(item.created_at)}</strong><small>{shortId(item.id, 13)} · {duration(item.duration_ms)}</small></span><Badge>{item.status}</Badge><span className="result-counts">Passed {item.passed_count ?? "—"} · Failed {item.failed_count ?? "—"} · Skipped {item.skipped_count ?? "—"}</span><span className="evaluation-forgefit">ForgeFit: {item.forgefit_status}</span></summary><div className="evaluation-detail"><Link className="text-link" href={`/repairs/${candidate.id}/evaluations/${item.id}`}>Open evaluation record <ExternalLink size={14} /></Link><dl className="detail-list"><dt>Exit code</dt><dd>{item.exit_code ?? "—"}</dd><dt>Error code</dt><dd>{item.error_code ?? "—"}</dd><dt>Completed</dt><dd>{dateTime(item.completed_at)}</dd><dt>Baseline execution</dt><dd>{item.baseline_execution_id ?? "—"}</dd><dt>Mutant result</dt><dd>{item.mutant_execution_result_id ?? "—"}</dd></dl><JsonDetails label="Local evaluation evidence" value={item.evidence} /><div className="forgefit-result"><strong>ForgeFit resilience</strong><p>Status: {item.forgefit_status} · Run: {item.forgefit_run_id ?? "—"} · Error: {item.forgefit_error_code ?? "—"}</p><JsonDetails label="ForgeFit result" value={item.forgefit_result} /></div></div></details>)}</div>}
    </Card>
  </>;
}
