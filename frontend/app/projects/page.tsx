"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, FolderPlus, Search, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { dateTime, shortId } from "@/lib/format";
import type { Page, Project } from "@/lib/types";
import { notify } from "@/components/notifications";
import { Card, EmptyState, ErrorState, LoadingState, PageHeading } from "@/components/ui";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [page, setPage] = useState<Page<Project> | null>(null);
  const [current, setCurrent] = useState(1);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const load = useCallback(async () => {
    try {
      const result = await api.projects(current, 20);
      const details = await Promise.all(result.items.map((item) => api.project(item.id)));
      setPage({ ...result, items: details });
      setProjects(details);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load projects.");
    } finally { setLoading(false); }
  }, [current]);
  const retry = () => {
    setLoading(true);
    setError("");
    void load();
  };
  useEffect(() => { void Promise.resolve().then(load); }, [load]);
  const filtered = useMemo(
    () => projects.filter((project) => `${project.name} ${project.slug} ${project.description ?? ""}`.toLowerCase().includes(query.toLowerCase())),
    [projects, query],
  );
  async function createProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    try {
      await api.createProject({
        name: String(form.get("name")).trim(),
        description: String(form.get("description")).trim() || undefined,
        slug: String(form.get("slug")).trim() || undefined,
      });
      notify("Project created.");
      setCreating(false);
      await load();
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : "Project creation failed.", "error");
    } finally {
      setSaving(false);
    }
  }
  async function deleteProject(project: Project) {
    if (!window.confirm(`Delete "${project.name}" and all associated repository, snapshot, analysis, diagnosis and repair data? This cannot be undone.`)) return;
    try {
      await api.deleteProject(project.id);
      setProjects((items) => items.filter((item) => item.id !== project.id));
      await load();
      notify("Project and its associated data were deleted.");
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : "Project deletion failed.", "error");
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="WORKSPACE / PROJECTS"
        title="Projects"
        description="Organize repository connections, immutable snapshots, and analysis runs."
        action={<button className="editorial-btn-primary" onClick={() => setCreating((value) => !value)}><FolderPlus size={15} /> New project</button>}
      />
      {creating && (
        <Card className="form-card">
          <div className="section-heading"><div><p className="eyebrow">NEW PROJECT</p><h2>Project details</h2></div></div>
          <form className="form-grid" onSubmit={createProject}>
            <label>Project name<input name="name" required maxLength={255} placeholder="e.g. Payments service" /></label>
            <label>Slug <span className="muted">(optional)</span><input name="slug" maxLength={255} placeholder="payments-service" /></label>
            <label className="form-span">Description<textarea name="description" rows={3} placeholder="What are you evaluating?" /></label>
            <div className="form-actions form-span">
              <button className="editorial-btn-primary" disabled={saving}>{saving ? "Creating…" : "Create project"}</button>
              <button type="button" className="editorial-btn-secondary" onClick={() => setCreating(false)}>Cancel</button>
            </div>
          </form>
        </Card>
      )}
      <Card>
        <div className="list-toolbar">
          <div><p className="eyebrow">REGISTERED PROJECTS</p><h2>{loading ? "Loading…" : error ? "Unavailable" : `${page?.total ?? filtered.length} ${(page?.total ?? filtered.length) === 1 ? "project" : "projects"}`}</h2></div>
          <label className="search-field"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search this page" aria-label="Search projects on this page" /></label>
        </div>
        {loading && <LoadingState />}
        {error && <ErrorState message={error} retry={retry} />}
        {!loading && !error && !filtered.length && (
          <EmptyState
            title={query ? "No matching projects" : "A clean slate"}
            description={query ? "Try another name, slug, or description." : "Create a project to connect a repository and begin an analysis."}
          />
        )}
        {!loading && !error && filtered.length > 0 && (
          <div className="table-scroll"><table><thead><tr><th>PROJECT</th><th>REPOSITORIES</th><th>SNAPSHOTS</th><th>ANALYSES</th><th>UPDATED</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>{filtered.map((project) => <tr key={project.id}>
              <td><Link className="primary-cell" href={`/projects/${project.id}`}>{project.name}<small>{project.slug} · {shortId(project.id, 13)}</small></Link></td>
              <td>{project.repository_connections_count ?? "—"}</td><td>{project.code_snapshots_count ?? "—"}</td><td>{project.analysis_runs_count ?? "—"}</td>
              <td className="muted">{dateTime(project.updated_at)}</td>
              <td><div className="row-actions"><Link className="icon-button" href={`/projects/${project.id}`} aria-label={`Open ${project.name}`}><ArrowRight size={16} /></Link><button className="icon-button danger-hover" onClick={() => deleteProject(project)} aria-label={`Delete ${project.name}`}><Trash2 size={15} /></button></div></td>
            </tr>)}</tbody>
          </table></div>
        )}
        {page && page.total_pages > 1 && <div className="pagination"><span>Page {page.page} of {page.total_pages}</span><div><button className="editorial-btn-secondary" disabled={current <= 1 || loading} onClick={() => setCurrent((value) => value - 1)}>Previous</button><button className="editorial-btn-secondary" disabled={current >= page.total_pages || loading} onClick={() => setCurrent((value) => value + 1)}>Next</button></div></div>}
      </Card>
    </>
  );
}
