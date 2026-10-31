"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowRight, CircleHelp } from "lucide-react";
import { api } from "@/lib/api";
import type { Diagnosis } from "@/lib/types";
import { percent, shortId } from "@/lib/format";
import { notify } from "@/components/notifications";
import { Badge, Card, EmptyState, ErrorState, LoadingState, PageBackLink, PageHeading } from "@/components/ui";

export default function DiagnosesPage() {
  const { analysisId } = useParams<{ analysisId: string }>();
  const [items, setItems] = useState<Diagnosis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.diagnoses(analysisId).then((page) => setItems(page.items)).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Diagnosis reports could not be loaded.")).finally(() => setLoading(false));
  }, [analysisId]);
  const retry = () => {
    setLoading(true);
    setError("");
    load();
  };
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  async function runDiagnosis() {
    setBusy(true);
    try {
      const result = await api.diagnose(analysisId);
      setItems(result.reports);
      notify(`Diagnosis completed: ${result.reports.length} report(s).`);
    } catch (reason) { notify(reason instanceof Error ? reason.message : "Diagnosis failed.", "error"); }
    finally { setBusy(false); }
  }
  return <>
    <PageBackLink href={`/analyses/${analysisId}`}>Analysis workspace</PageBackLink>
    <PageHeading eyebrow="FAILURE ANALYSIS" title="Diagnosis reports" description="Baseline-to-mutant comparisons, traceback evidence, and explicitly qualified attribution." action={<button className="editorial-btn-primary" onClick={() => void runDiagnosis()} disabled={busy}>{busy ? "Diagnosing…" : "Run diagnosis"}</button>} />
    <div className="note-line"><CircleHelp size={15} /> Confidence indicates evidence strength, not proof of causation. The backend labels inferred attribution separately.</div>
    <Card><div className="list-toolbar"><div><p className="eyebrow">PERSISTED REPORTS</p><h2>{loading ? "Loading…" : error ? "Unavailable" : `${items.length} ${items.length === 1 ? "report" : "reports"}`}</h2></div></div>
      {loading && <LoadingState />}{error && <ErrorState message={error} retry={retry} />}
      {!loading && !error && !items.length && <EmptyState title="No diagnosis reports" description="Run execution first, then compare mutant results against the persisted baseline." href={`/analyses/${analysisId}`} linkText="Open analysis" />}
      {!loading && !error && !!items.length && <div className="table-scroll"><table><thead><tr><th>FAILURE</th><th>CATEGORY</th><th>SEVERITY</th><th>CONFIDENCE</th><th>TEST</th><th /></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><Link className="primary-cell" href={`/diagnoses/${item.id}`}>{item.title}<small>{shortId(item.id, 13)}</small></Link></td><td><Badge>{item.category ?? item.failure_type}</Badge></td><td><Badge>{item.severity}</Badge></td><td>{percent(item.confidence_score)}</td><td className="mono">{item.affected_test ?? item.test_identifier ?? "Unknown"}</td><td><Link className="icon-button" href={`/diagnoses/${item.id}`} aria-label="Inspect diagnosis"><ArrowRight size={15} /></Link></td></tr>)}</tbody></table></div>}
    </Card>
  </>;
}
