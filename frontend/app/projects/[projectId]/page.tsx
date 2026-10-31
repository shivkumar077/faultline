"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, GitBranch, Plus, RefreshCw, ScanSearch } from "lucide-react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { dateTime, shortId } from "@/lib/format";
import type { Analysis, Project, Repository, Snapshot } from "@/lib/types";
import { notify } from "@/components/notifications";
import { Badge, Card, EmptyState, ErrorState, LoadingState, PageBackLink, PageHeading } from "@/components/ui";

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [snapshots, setSnapshots] = useState<Record<string, Snapshot[]>>({});
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showConnect, setShowConnect] = useState(false);
  const [busy, setBusy] = useState("");
  const load = useCallback(async () => {
    try {
      const [projectData, repoData, analysisData] = await Promise.all([
        api.project(projectId), api.repositories(projectId), api.analyses(1, 100, projectId),
      ]);
      setProject(projectData); setRepositories(repoData);
      setAnalyses(await Promise.all(analysisData.items.map((analysis) => api.analysis(analysis.id))));
      const snapshotPairs = await Promise.all(repoData.map(async (repo) => [repo.id, await api.snapshots(repo.id)] as const));
      setSnapshots(Object.fromEntries(snapshotPairs));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load this project.");
    } finally { setLoading(false); }
  }, [projectId]);
  const retry = () => {
    setLoading(true);
    setError("");
    void load();
  };
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  async function connect(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy("connect");
    try {
      await api.connectRepository(projectId, {
        repository_url: String(form.get("repository_url")).trim(),
        branch: String(form.get("branch")).trim() || "main",
      });
      notify("Repository connected."); setShowConnect(false); await load();
    } catch (reason) { notify(reason instanceof Error ? reason.message : "Repository connection failed.", "error"); }
    finally { setBusy(""); }
  }
  async function sync(id: string) {
    setBusy(id);
    try {
      await api.syncRepository(id); notify("Repository snapshot captured."); await load();
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : "Repository synchronization failed.", "error");
      await load();
    } finally { setBusy(""); }
  }
  if (loading) return <LoadingState />;
  if (error || !project) return <ErrorState message={error || "Project not found."} retry={retry} />;
  const allSnapshots = repositories.flatMap((repo) => (snapshots[repo.id] ?? []).map((snapshot) => ({ ...snapshot, repo })));
  return <>
    <PageBackLink href="/projects">All projects</PageBackLink>
    <PageHeading eyebrow={`PROJECT / ${project.slug}`} title={project.name} description={project.description || "Repository connections, snapshots and analysis runs for this project."} action={<button className="editorial-btn-primary" onClick={() => setShowConnect((value) => !value)}><Plus size={15} /> Connect repository</button>} />
    <div className="detail-stats">
      <div><strong>{repositories.length}</strong><span>Repositories</span></div><div><strong>{allSnapshots.length}</strong><span>Snapshots</span></div><div><strong>{analyses.length}</strong><span>Analysis runs</span></div><div><strong>{project.status}</strong><span>Project status</span></div>
    </div>
    {showConnect && <Card className="form-card"><div className="section-heading"><div><p className="eyebrow">GITHUB</p><h2>Connect a public repository</h2></div></div><p className="muted">The backend ingests the selected branch. Private repository credentials are not supported by this API.</p><form className="form-grid" onSubmit={connect}><label className="form-span">Repository URL<input name="repository_url" required type="url" pattern="https://github\.com/[^/]+/[^/]+/?"
      placeholder="https://github.com/owner/repository" title="Enter a public GitHub repository HTTPS URL" /></label><label>Branch<input name="branch" required defaultValue="main" maxLength={255} /></label><div className="form-actions"><button className="editorial-btn-primary" disabled={busy === "connect"}>{busy === "connect" ? "Connecting…" : "Connect repository"}</button><button type="button" className="editorial-btn-secondary" onClick={() => setShowConnect(false)}>Cancel</button></div></form></Card>}
    <div className="content-grid">
      <Card><div className="section-heading"><div><p className="eyebrow">SOURCE CONNECTIONS</p><h2>Repositories</h2></div></div>
        {!repositories.length ? <EmptyState title="No repositories connected" description="Connect a public GitHub repository to capture its current source snapshot." /> :
          <div className="stack-list">{repositories.map((repo) => <div className="repository-row" key={repo.id}><div className="repo-icon"><GitBranch size={16} /></div><div className="grow"><a className="primary-cell external-link" href={repo.repository_url} target="_blank" rel="noreferrer">{repo.repository_url}<small>Branch: {repo.branch} · Last sync: {dateTime(repo.last_synced_at)}</small></a><Badge>{repo.status}</Badge></div><button className="editorial-btn-secondary" disabled={busy === repo.id} onClick={() => void sync(repo.id)}><RefreshCw size={14} className={busy === repo.id ? "spin" : ""} /> {busy === repo.id ? "Syncing…" : "Sync"}</button></div>)}</div>}
      </Card>
      <Card><div className="section-heading"><div><p className="eyebrow">CAPTURED SOURCE</p><h2>Snapshots</h2></div></div>
        {!allSnapshots.length ? <EmptyState title="No snapshots yet" description="Sync a connected repository to capture a commit-pinned source inventory." /> :
          <div className="stack-list">{allSnapshots.slice(0, 8).map(({ repo, ...snapshot }) => <Link className="activity-row" href={`/snapshots/${snapshot.id}`} key={snapshot.id}><span className="activity-icon"><ScanSearch size={15} /></span><span className="activity-main"><strong>{repo.repository_url.split("/").slice(-2).join("/")}</strong><small>{snapshot.branch} · {shortId(snapshot.commit_hash, 13)} · {dateTime(snapshot.created_at)}</small></span><Badge>{snapshot.status}</Badge><ArrowRight size={15} /></Link>)}</div>}
      </Card>
    </div>
    <Card><div className="section-heading"><div><p className="eyebrow">ANALYSIS HISTORY</p><h2>Analysis runs</h2></div><Link className="text-link" href="/analyses">All analyses <ArrowRight size={14} /></Link></div>
      {!analyses.length ? <EmptyState title="No analyses" description="Capture a snapshot and generate mutations to create the first analysis." /> :
        <div className="table-scroll"><table><thead><tr><th>ANALYSIS</th><th>STATUS</th><th>MUTATIONS</th><th>DIAGNOSES</th><th>CREATED</th><th /></tr></thead><tbody>{analyses.map((analysis) => <tr key={analysis.id}><td><Link className="primary-cell" href={`/analyses/${analysis.id}`}>{analysis.name ?? shortId(analysis.id)}<small>{shortId(analysis.id, 13)}</small></Link></td><td><Badge>{analysis.status}</Badge></td><td>—</td><td>—</td><td className="muted">{dateTime(analysis.created_at)}</td><td><Link className="icon-button" href={`/analyses/${analysis.id}`} aria-label="Open analysis"><ArrowRight size={15} /></Link></td></tr>)}</tbody></table></div>}
    </Card>
  </>;
}
