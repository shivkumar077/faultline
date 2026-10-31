"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Boxes, GitCommitHorizontal } from "lucide-react";
import { api } from "@/lib/api";
import { dateTime, shortId } from "@/lib/format";
import type { Snapshot } from "@/lib/types";
import { notify } from "@/components/notifications";
import { Badge, Card, ErrorState, JsonDetails, LoadingState, PageBackLink, PageHeading } from "@/components/ui";

export default function SnapshotPage() {
  const { snapshotId } = useParams<{ snapshotId: string }>();
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [inventoryPage, setInventoryPage] = useState(1);
  const [fileSearch, setFileSearch] = useState("");
  const load = useCallback(() => {
    api.snapshot(snapshotId).then(setSnapshot).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Snapshot could not be loaded.")).finally(() => setLoading(false));
  }, [snapshotId]);
  const retry = () => {
    setLoading(true);
    setError("");
    load();
  };
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  async function generate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const seed = Number(form.get("seed"));
    const max_mutations = Number(form.get("max_mutations"));
    if (!Number.isInteger(seed) || !Number.isInteger(max_mutations) || max_mutations < 1 || max_mutations > 500) {
      notify("Seed must be an integer and mutation count must be between 1 and 500.", "error"); return;
    }
    setBusy(true);
    try {
      const analysis = await api.generateMutations(snapshotId, { seed, max_mutations });
      notify("Mutation analysis created."); router.push(`/analyses/${analysis.id}`);
    } catch (reason) { notify(reason instanceof Error ? reason.message : "Mutation generation failed.", "error"); }
    finally { setBusy(false); }
  }
  if (loading) return <LoadingState />;
  if (!snapshot || error) return <ErrorState message={error || "Snapshot not found."} retry={retry} />;
  const inventory = snapshot.file_tree_summary ?? {};
  const allFiles = Array.isArray(inventory.files) ? inventory.files : [];
  const filteredFiles = allFiles.filter((file) => {
    const item = typeof file === "object" && file !== null ? file as Record<string, unknown> : {};
    return String(item.path ?? "").toLowerCase().includes(fileSearch.toLowerCase());
  });
  const inventoryPageSize = 20;
  const filePageCount = Math.max(1, Math.ceil(filteredFiles.length / inventoryPageSize));
  const files = filteredFiles.slice((inventoryPage - 1) * inventoryPageSize, inventoryPage * inventoryPageSize);
  const languageDistribution = typeof inventory.language_distribution === "object" && inventory.language_distribution !== null
    ? inventory.language_distribution as Record<string, number>
    : {};
  return <>
    <PageBackLink href={`/projects/${snapshot.project_id}`}>Project</PageBackLink>
    <PageHeading eyebrow="SOURCE SNAPSHOT" title={`Snapshot ${shortId(snapshot.id)}`} description="Immutable inventory captured from a specific repository commit." />
    <div className="metadata-strip"><div><span>COMMIT</span><strong title={snapshot.commit_hash}>{shortId(snapshot.commit_hash, 18)}</strong><GitCommitHorizontal size={15} /></div><div><span>BRANCH</span><strong>{snapshot.branch}</strong></div><div><span>STATUS</span><Badge>{snapshot.status}</Badge></div><div><span>CAPTURED</span><strong>{dateTime(snapshot.created_at)}</strong></div></div>
    <div className="detail-stats">
      <div><strong>{String(inventory.total_files ?? allFiles.length)}</strong><span>Files indexed</span></div>
      <div><strong>{String(inventory.total_directories ?? "—")}</strong><span>Directories</span></div>
      <div><strong>{Object.keys(languageDistribution).length}</strong><span>Languages detected</span></div>
      <div><strong>{String(inventory.total_size_bytes ?? "—")}</strong><span>Total bytes</span></div>
    </div>
    {Object.keys(languageDistribution).length > 0 && <div className="language-list" aria-label="Language distribution">{Object.entries(languageDistribution).sort((a, b) => b[1] - a[1]).map(([language, share]) => <span className="language-chip" key={language}>{language}<strong>{share}%</strong></span>)}</div>}
    <div className="content-grid">
      <Card><div className="section-heading"><div><p className="eyebrow">SOURCE INVENTORY</p><h2>{filteredFiles.length || "No"} files</h2></div><Boxes size={18} /></div>
        {allFiles.length ? <><div className="list-toolbar"><span className="muted">{filteredFiles.length} of {allFiles.length} files</span><label className="search-field"><input aria-label="Filter source files by path" placeholder="Filter paths" value={fileSearch} onChange={(event) => { setFileSearch(event.target.value); setInventoryPage(1); }} /></label></div><div className="table-scroll"><table><thead><tr><th>PATH</th><th>EXTENSION</th><th>SIZE</th><th>SHA-256</th></tr></thead><tbody>{files.map((file, index) => {
          const item = typeof file === "object" && file !== null ? file as Record<string, unknown> : {};
          return <tr key={`${String(item.path ?? index)}`}><td className="mono">{String(item.path ?? "File")}</td><td>{String(item.extension ?? "—")}{item.is_binary ? " · binary" : ""}</td><td>{String(item.size_bytes ?? "—")}</td><td className="mono">{String(item.sha256 ?? "—")}</td></tr>;
        })}</tbody></table></div>{filePageCount > 1 && <div className="pagination"><span>Page {inventoryPage} of {filePageCount}</span><div><button className="editorial-btn-secondary" disabled={inventoryPage <= 1} onClick={() => setInventoryPage((page) => page - 1)}>Previous</button><button className="editorial-btn-secondary" disabled={inventoryPage >= filePageCount} onClick={() => setInventoryPage((page) => page + 1)}>Next</button></div></div>}</> : <p className="muted">The snapshot inventory was returned by the backend but does not expose a `files` array in a recognized shape. Inspect the captured metadata below.</p>}
        <JsonDetails label="Inspect complete inventory metadata" value={inventory} />
      </Card>
      <Card><p className="eyebrow">NEXT STEP</p><h2>Generate mutations</h2><p className="muted">Create deterministic AST-based mutations from this exact snapshot. This starts an analysis run; execution is a separate action.</p>
        <form className="form-grid single-column" onSubmit={generate}><label>Deterministic seed<input name="seed" type="number" defaultValue={42} required /></label><label>Maximum mutations<input name="max_mutations" type="number" min={1} max={500} defaultValue={100} required /></label><button className="editorial-btn-primary" disabled={busy}>{busy ? "Generating…" : "Generate mutations"}</button></form>
      </Card>
    </div>
    <div className="note-line"><GitCommitHorizontal size={15} /> Snapshot ID {snapshot.id} · Commit {snapshot.commit_hash}</div>
    <Link className="text-link" href={`/projects/${snapshot.project_id}`}>Back to project</Link>
  </>;
}
