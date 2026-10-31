"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Search } from "lucide-react";
import { api } from "@/lib/api";
import type { Analysis, Page } from "@/lib/types";
import { dateTime, shortId } from "@/lib/format";
import { Badge, Card, EmptyState, ErrorState, LoadingState, PageHeading } from "@/components/ui";

export default function AnalysesPage() {
  const [page, setPage] = useState<Page<Analysis> | null>(null);
  const [current, setCurrent] = useState(1);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    api.analyses(current, 20).then(setPage).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load analyses.")).finally(() => setLoading(false));
  }, [current]);
  const retry = () => {
    setLoading(true);
    setError("");
    load();
  };
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  const items = (page?.items ?? []).filter((item) => `${item.name ?? ""} ${item.id} ${item.status}`.toLowerCase().includes(query.toLowerCase()));
  return <>
    <PageHeading eyebrow="WORKSPACE / ANALYSIS" title="Analysis runs" description="Mutation plans, test executions, failure diagnoses, and repair candidates." />
    <Card><div className="list-toolbar"><div><p className="eyebrow">RUN HISTORY</p><h2>{loading ? "Loading…" : error ? "Unavailable" : `${page?.total ?? 0} runs`}</h2></div><label className="search-field"><Search size={16} /><input aria-label="Search analyses on this page" placeholder="Search this page" value={query} onChange={(event) => setQuery(event.target.value)} /></label></div>
      {loading && <LoadingState />}{error && <ErrorState message={error} retry={retry} />}
      {!loading && !error && !items.length && <EmptyState title={query ? "No matching analyses" : "No runs to show"} description="Create an analysis by opening a captured repository snapshot and generating mutations." href="/projects" linkText="Browse projects" />}
      {!loading && !error && !!items.length && <div className="table-scroll"><table><thead><tr><th>ANALYSIS</th><th>STATUS</th><th>CREATED</th><th>STARTED</th><th>COMPLETED</th><th /></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><Link className="primary-cell" href={`/analyses/${item.id}`}>{item.name ?? `Analysis ${shortId(item.id)}`}<small>{shortId(item.id, 16)}</small></Link></td><td><Badge>{item.status}</Badge></td><td className="muted">{dateTime(item.created_at)}</td><td className="muted">{dateTime(item.started_at)}</td><td className="muted">{dateTime(item.completed_at)}</td><td><Link className="icon-button" href={`/analyses/${item.id}`} aria-label="Open analysis"><ArrowRight size={15} /></Link></td></tr>)}</tbody></table></div>}
      {page && page.total_pages > 1 && <div className="pagination"><span>Page {page.page} of {page.total_pages}</span><div><button className="editorial-btn-secondary" disabled={current <= 1 || loading} onClick={() => { setLoading(true); setError(""); setCurrent((value) => value - 1); }}>Previous</button><button className="editorial-btn-secondary" disabled={current >= page.total_pages || loading} onClick={() => { setLoading(true); setError(""); setCurrent((value) => value + 1); }}>Next</button></div></div>}
    </Card>
  </>;
}
