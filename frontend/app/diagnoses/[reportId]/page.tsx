"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowRight, FileCode2, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import type { Diagnosis } from "@/lib/types";
import { dateTime, percent, shortId } from "@/lib/format";
import { notify } from "@/components/notifications";
import { Badge, Card, ErrorState, JsonDetails, LoadingState, PageBackLink, PageHeading } from "@/components/ui";

export default function DiagnosisDetailPage() {
  const { reportId } = useParams<{ reportId: string }>();
  const router = useRouter();
  const [report, setReport] = useState<Diagnosis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.diagnosis(reportId).then(setReport).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Diagnosis could not be loaded.")).finally(() => setLoading(false));
  }, [reportId]);
  const retry = () => {
    setLoading(true);
    setError("");
    load();
  };
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  async function generateRepair() {
    if (!report) return;
    setBusy(true);
    try {
      const result = await api.generateDiagnosisRepair(report.analysis_run_id, report.id);
      if (result.candidates[0]) {
        notify("Repair candidate generated; it still requires review and independent evaluation.");
        router.push(`/repairs/${result.candidates[0].id}`);
      } else notify(result.skipped[0]?.reason ?? "No repair candidate was produced.", "error");
    } catch (reason) { notify(reason instanceof Error ? reason.message : "Repair generation failed.", "error"); }
    finally { setBusy(false); }
  }
  if (loading) return <LoadingState />;
  if (!report || error) return <ErrorState message={error || "Diagnosis not found."} retry={retry} />;
  return <>
    <PageBackLink href={`/analyses/${report.analysis_run_id}/diagnoses`}>Diagnosis reports</PageBackLink>
    <PageHeading eyebrow={`DIAGNOSIS / ${shortId(report.id, 13)}`} title={report.title} description={report.failure_summary ?? report.comparison_summary ?? "Evidence captured from the baseline-to-mutant comparison."} action={<button className="editorial-btn-primary" disabled={busy || report.category !== "introduced_failure"} title={report.category !== "introduced_failure" ? "Repair generation is available only for eligible introduced failures." : undefined} onClick={() => void generateRepair()}><FileCode2 size={15} />{busy ? "Generating…" : "Generate repair candidate"}</button>} />
    <div className="diagnosis-callout"><ShieldAlert size={18} /><div><strong>{report.causal_attribution === "confirmed" ? "Confirmed evidence" : "Inferred attribution"}</strong><p>{report.causal_attribution ? `Attribution: ${report.causal_attribution.replaceAll("_", " ")}. ` : ""}Correlation is not certainty. Review the baseline comparison and source evidence before treating this mutation as causal.</p></div><div className="confidence"><strong>{percent(report.confidence_score)}</strong><span>confidence</span></div></div>
    <div className="metadata-strip"><div><span>CATEGORY</span><Badge>{report.category ?? report.failure_type}</Badge></div><div><span>SEVERITY</span><Badge>{report.severity}</Badge></div><div><span>TEST</span><strong>{report.affected_test ?? report.test_identifier ?? "Not identified"}</strong></div><div><span>CREATED</span><strong>{dateTime(report.created_at)}</strong></div></div>
    <div className="content-grid">
      <Card><p className="eyebrow">ROOT-CAUSE ANALYSIS</p><h2>What the evidence suggests</h2><p className="prose">{report.root_cause_analysis ?? "The backend did not provide a root-cause explanation for this report."}</p>{report.suggested_repair && <div className="remediation-box"><strong>Suggested remediation</strong><p>{report.suggested_repair}</p></div>}<p className="muted">Suggestions are guidance only; this view does not apply or validate code changes.</p></Card>
      <Card><p className="eyebrow">EXCEPTION DETAILS</p><h2>{report.exception_type ?? "Exception unavailable"}</h2><p className="prose">{report.exception_message ?? "No exception message was captured."}</p>{report.failing_assertion && <div className="code-block"><span>FAILING ASSERTION</span><pre>{report.failing_assertion}</pre></div>}</Card>
    </div>
    <div className="content-grid">
      <Card><p className="eyebrow">SOURCE & MUTATION</p><h2>Relevant location</h2><dl className="detail-list"><dt>Failure source</dt><dd>{report.source_file ?? "Unknown"}{report.source_line ? `:${report.source_line}` : ""}</dd><dt>Source function</dt><dd>{report.source_function ?? "Unknown"}</dd><dt>Mutated file</dt><dd>{report.mutation_file ?? "Unknown"}{report.mutation_line ? `:${report.mutation_line}` : ""}</dd><dt>Test file</dt><dd>{report.test_file ?? "Unknown"}</dd><dt>Test function</dt><dd>{report.test_function ?? "Unknown"}</dd><dt>Mutation record</dt><dd>{report.mutation_record_id ? shortId(report.mutation_record_id, 18) : "Not linked"}</dd></dl>
        {report.original_expression && <div className="diff-pair"><div><span>BASELINE EXPRESSION</span><pre>{report.original_expression}</pre></div><div><span>MUTATED EXPRESSION</span><pre>{report.mutated_expression ?? "Unavailable"}</pre></div></div>}</Card>
      <Card><p className="eyebrow">COMPARISON</p><h2>Baseline to mutant</h2><p className="prose">{report.comparison_summary ?? "No comparison narrative is available."}</p><div className="link-row"><Link className="text-link" href={`/analyses/${report.analysis_run_id}`}>Open analysis workspace <ArrowRight size={14} /></Link></div></Card>
    </div>
    <Card><p className="eyebrow">SUPPORTING MATERIAL</p><h2>Evidence and traceback</h2><JsonDetails label="Evidence references" value={report.evidence} /><JsonDetails label="Traceback frames" value={report.traceback_frames} /></Card>
  </>;
}
