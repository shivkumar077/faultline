"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowRight, FileCode2 } from "lucide-react";
import { api } from "@/lib/api";
import type { RepairCandidate } from "@/lib/types";
import { percent, shortId } from "@/lib/format";
import { notify } from "@/components/notifications";
import { Badge, Card, EmptyState, ErrorState, LoadingState, PageBackLink, PageHeading } from "@/components/ui";

export default function RepairsPage() {
  const { analysisId } = useParams<{ analysisId: string }>();
  const [items, setItems] = useState<RepairCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.repairs(analysisId).then((page) => setItems(page.items)).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Repair candidates could not be loaded.")).finally(() => setLoading(false));
  }, [analysisId]);
  const retry = () => {
    setLoading(true);
    setError("");
    load();
  };
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  async function generate() {
    setBusy(true);
    try {
      const result = await api.generateRepairs(analysisId);
      setItems(result.candidates);
      notify(`${result.candidates.length} candidate(s) generated; ${result.skipped.length} diagnosis(es) skipped.`);
    } catch (reason) { notify(reason instanceof Error ? reason.message : "Candidate generation failed.", "error"); }
    finally { setBusy(false); }
  }
  return <>
    <PageBackLink href={`/analyses/${analysisId}`}>Analysis workspace</PageBackLink>
    <PageHeading eyebrow="REPAIR REVIEW" title="Repair candidates" description="Generated unified diffs are proposals, not verified fixes. Review source hashes, evidence, and evaluation results." action={<button className="editorial-btn-primary" disabled={busy} onClick={() => void generate()}><FileCode2 size={15} />{busy ? "Generating…" : "Generate candidates"}</button>} />
    <Card><div className="list-toolbar"><div><p className="eyebrow">CANDIDATES</p><h2>{loading ? "Loading…" : error ? "Unavailable" : `${items.length} ${items.length === 1 ? "candidate" : "candidates"}`}</h2></div></div>
      {loading && <LoadingState />}{error && <ErrorState message={error} retry={retry} />}
      {!loading && !error && !items.length && <EmptyState title="No repair candidates" description="Candidates require eligible, persisted introduced-failure diagnoses." href={`/analyses/${analysisId}/diagnoses`} linkText="Inspect diagnoses" />}
      {!loading && !error && !!items.length && <div className="table-scroll"><table><thead><tr><th>TARGET</th><th>STRATEGY</th><th>VALIDATION</th><th>REVIEW</th><th>CONFIDENCE</th><th /></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><Link className="primary-cell mono" href={`/repairs/${item.id}`}>{item.target_file}<small>{shortId(item.id, 13)} · {shortId(item.proposed_source_sha256, 13)}</small></Link></td><td>{item.repair_strategy}</td><td><Badge>{item.validation_status}</Badge></td><td><Badge>{item.review_status}</Badge></td><td>{percent(item.confidence_score)}</td><td><Link className="icon-button" href={`/repairs/${item.id}`} aria-label="Inspect candidate"><ArrowRight size={15} /></Link></td></tr>)}</tbody></table></div>}
    </Card>
  </>;
}
