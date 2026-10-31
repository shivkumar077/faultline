"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Activity, AlertTriangle, Boxes, CirclePlay, FileCode2, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import type { Analysis, Execution, Mutation } from "@/lib/types";
import { dateTime, duration, shortId } from "@/lib/format";
import { notify } from "@/components/notifications";
import { Badge, Card, EmptyState, ErrorState, JsonDetails, LoadingState, PageBackLink, PageHeading } from "@/components/ui";

export default function AnalysisDetailPage() {
  const { analysisId } = useParams<{ analysisId: string }>();
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [mutations, setMutations] = useState<Mutation[]>([]);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const load = useCallback(async () => {
    try {
      const [a, m, e] = await Promise.all([api.analysis(analysisId), api.mutations(analysisId), api.executions(analysisId)]);
      setAnalysis(a); setMutations(m.items); setExecutions(e.items);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Analysis could not be loaded."); }
    finally { setLoading(false); }
  }, [analysisId]);
  const retry = () => {
    setLoading(true);
    setError("");
    void load();
  };
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  async function execute() {
    if (!window.confirm("Start baseline and mutant test execution in the configured isolated Docker runner? This may take several minutes.")) return;
    setBusy("execute");
    try {
      const result = await api.execute(analysisId);
      notify(`Execution completed with status ${result.status}.`);
      await load();
    } catch (reason) { notify(reason instanceof Error ? reason.message : "Execution could not be started.", "error"); }
    finally { setBusy(""); }
  }
  async function diagnose() {
    setBusy("diagnose");
    try {
      const result = await api.diagnose(analysisId);
      notify(`Diagnosis complete: ${result.reports.length} evidence-backed report(s).`);
      await load();
    } catch (reason) { notify(reason instanceof Error ? reason.message : "Diagnosis failed.", "error"); }
    finally { setBusy(""); }
  }
  async function generateRepairs() {
    setBusy("repairs");
    try {
      const result = await api.generateRepairs(analysisId);
      notify(`${result.candidates.length} repair candidate(s) generated; ${result.skipped.length} diagnosis(es) were not eligible.`);
      await load();
    } catch (reason) { notify(reason instanceof Error ? reason.message : "Repair generation failed.", "error"); }
    finally { setBusy(""); }
  }
  if (loading) return <LoadingState />;
  if (!analysis || error) return <ErrorState message={error || "Analysis not found."} retry={retry} />;
  const baseline = executions.find((item) => item.kind === "baseline");
  const latestExecution = executions[executions.length - 1];
  const killed = executions.filter((item) => item.kind === "mutation" && item.status.toUpperCase() === "KILLED").length;
  const survived = executions.filter((item) => item.kind === "mutation" && item.status.toUpperCase() === "SURVIVED").length;
  const scoreDenominator = killed + survived;
  const mutationScore = scoreDenominator ? `${((killed / scoreDenominator) * 100).toFixed(2)}%` : "—";
  return <>
    <PageBackLink href="/analyses">All analyses</PageBackLink>
    <PageHeading eyebrow={`ANALYSIS / ${shortId(analysis.id, 13)}`} title={analysis.name ?? "Analysis run"} description={`Snapshot ${shortId(analysis.code_snapshot_id, 13)} · Created ${dateTime(analysis.created_at)}`} action={<Badge>{analysis.status}</Badge>} />
    <div className="detail-stats">
      <div><strong>{analysis.mutation_records_count ?? mutations.length}</strong><span>Mutation records</span></div>
      <div><strong>{analysis.failure_reports_count ?? 0}</strong><span>Diagnosis reports</span></div>
      <div><strong>{executions.filter((item) => item.kind === "mutation").length}</strong><span>Mutant executions</span></div>
      <div><strong>{mutationScore}</strong><span>Mutation score · {killed} killed / {survived} survived</span></div>
    </div>
    <div className="action-strip">
      <button className="editorial-btn-primary" disabled={busy !== ""} onClick={() => void execute()}><CirclePlay size={15} />{busy === "execute" ? "Executing…" : "Execute tests"}</button>
      <button className="editorial-btn-secondary" disabled={busy !== "" || executions.length === 0} title={executions.length === 0 ? "Run tests before diagnosing" : undefined} onClick={() => void diagnose()}><AlertTriangle size={15} />{busy === "diagnose" ? "Diagnosing…" : "Diagnose failures"}</button>
      <button className="editorial-btn-secondary" disabled={busy !== "" || (analysis.failure_reports_count ?? 0) === 0} title={(analysis.failure_reports_count ?? 0) === 0 ? "Generate diagnoses before repair candidates" : undefined} onClick={() => void generateRepairs()}><FileCode2 size={15} />{busy === "repairs" ? "Generating…" : "Generate repairs"}</button>
      <Link className="editorial-btn-secondary" href={`/analyses/${analysis.id}/diagnoses`}><AlertTriangle size={15} /> View diagnoses</Link>
      <Link className="editorial-btn-secondary" href={`/analyses/${analysis.id}/repairs`}><ShieldCheck size={15} /> Repair candidates</Link>
    </div>
    <div className="content-grid">
      <Card><div className="section-heading"><div><p className="eyebrow">MUTATION PLAN</p><h2>{mutations.length} recorded mutations</h2></div><Boxes size={18} /></div>
        {!mutations.length ? <EmptyState title="No mutations recorded" description="Mutation records are generated from the source snapshot when the analysis is created." /> :
          <div className="table-scroll"><table><thead><tr><th>TARGET</th><th>TYPE</th><th>LINE</th><th>STATUS</th><th>EXPRESSION CHANGE</th></tr></thead><tbody>{mutations.slice(0, 100).map((mutation) => <tr key={mutation.id}><td className="primary-cell mono">{mutation.target_file}<small>{shortId(mutation.id, 13)}</small></td><td>{mutation.mutation_type}</td><td>{mutation.line_number}</td><td><Badge>{mutation.status}</Badge></td><td><details className="json-details"><summary>Inspect change</summary><div className="diff-pair"><div><span>ORIGINAL</span><pre>{mutation.original_code}</pre></div><div><span>MUTATED</span><pre>{mutation.mutated_code}</pre></div></div></details></td></tr>)}</tbody></table></div>}
        {analysis.summary && <JsonDetails label="Mutation plan and score details" value={analysis.summary} />}
      </Card>
      <Card><div className="section-heading"><div><p className="eyebrow">TEST EXECUTION</p><h2>Runs</h2></div><Activity size={18} /></div>
        {!executions.length ? <EmptyState title="Tests have not run" description="Execution uses the backend’s configured Docker runner. No target code runs in the browser." /> :
          <div className="stack-list">{executions.map((item) => <div className="execution-item" key={item.id}><div className="execution-heading"><div><strong>{item.kind === "baseline" ? "Baseline" : `Mutant ${shortId(item.mutation_record_id ?? item.id)}`}</strong><small>{shortId(item.id, 13)} · {duration(item.duration_ms)}</small></div><Badge>{item.timed_out ? "timeout" : item.status}</Badge></div>{item.infrastructure_error && <div className="inline-alert"><AlertTriangle size={14} />{item.infrastructure_error}</div>}<JsonDetails label="Execution output" value={[item.stdout && `STDOUT\n${item.stdout}`, item.stderr && `STDERR\n${item.stderr}`].filter(Boolean).join("\n\n") || "No output was captured."} /></div>)}</div>}
        {baseline && latestExecution && <p className="muted footnote">Baseline: {baseline.status} · Latest record: {latestExecution.status}</p>}
      </Card>
    </div>
    <Card><div className="section-heading"><div><p className="eyebrow">ANALYSIS METADATA</p><h2>Run details</h2></div></div><div className="metadata-strip compact"><div><span>ANALYSIS ID</span><strong title={analysis.id}>{analysis.id}</strong></div><div><span>SNAPSHOT ID</span><strong title={analysis.code_snapshot_id}>{analysis.code_snapshot_id}</strong></div><div><span>STARTED</span><strong>{dateTime(analysis.started_at)}</strong></div><div><span>COMPLETED</span><strong>{dateTime(analysis.completed_at)}</strong></div></div></Card>
  </>;
}
