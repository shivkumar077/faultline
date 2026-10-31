"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Boxes,
  CircleCheck,
  FileCode2,
  FolderKanban,
  GitBranch,
  ShieldCheck,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Analysis, Page, Project } from "@/lib/types";
import { dateTime, shortId } from "@/lib/format";
import { Card, EmptyState, ErrorState, LoadingState, PageHeading } from "@/components/ui";

type Dashboard = {
  projects: Project[];
  analyses: Analysis[];
  projectCount: number;
  analysisCount: number;
  repositories: number;
  mutations: number;
  diagnoses: number;
  repairs: number;
  evaluations: number;
};

async function allPages<T>(load: (page: number) => Promise<Page<T>>): Promise<Page<T>> {
  const first = await load(1);
  if (first.total_pages <= 1) return first;
  const remaining = await Promise.all(
    Array.from({ length: first.total_pages - 1 }, (_, index) => load(index + 2)),
  );
  const pages = [first, ...remaining];
  return { ...first, items: pages.flatMap((page) => page.items) };
}

async function loadDashboard(): Promise<Dashboard> {
  const [projectPage, analysisPage] = await Promise.all([
    allPages((page) => api.projects(page, 100)),
    allPages((page) => api.analyses(page, 100)),
  ]);
  const projects = projectPage.items;
  const analyses = analysisPage.items;
  const [projectDetails, analysisDetails] = await Promise.all([
    Promise.all(projects.map((item) => api.project(item.id))),
    Promise.all(analyses.map((item) => api.analysis(item.id))),
  ]);
  const repairPages = await Promise.all(
    analyses.map(async (item) => {
      const first = await api.repairs(item.id, 1, 100);
      if (first.total_pages <= 1) return first;
      const remaining = await Promise.all(
        Array.from({ length: first.total_pages - 1 }, (_, index) => api.repairs(item.id, index + 2, 100)),
      );
      return { ...first, items: [first, ...remaining].flatMap((page) => page.items) };
    }),
  );
  const repairs = repairPages.flatMap((page) => page.items);
  const evaluationPages = await Promise.all(
    repairs.map((item) => api.evaluations(item.id, 1, 1)),
  );
  return {
    projects: projectPage.items,
    analyses: analysisPage.items,
    projectCount: projectPage.total,
    analysisCount: analysisPage.total,
    repositories: projectDetails.reduce((sum, item) => sum + (item.repository_connections_count ?? 0), 0),
    mutations: analysisDetails.reduce((sum, item) => sum + (item.mutation_records_count ?? 0), 0),
    diagnoses: analysisDetails.reduce((sum, item) => sum + (item.failure_reports_count ?? 0), 0),
    repairs: repairPages.reduce((sum, page) => sum + page.total, 0),
    evaluations: evaluationPages.reduce((sum, page) => sum + page.total, 0),
  };
}

export default function OverviewPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const load = useCallback(() => {
    loadDashboard()
      .then(setData)
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "The dashboard could not be loaded."),
      )
      .finally(() => setLoading(false));
  }, []);
  const retry = () => {
    setLoading(true);
    setError("");
    load();
  };
  useEffect(() => { void Promise.resolve().then(load); }, [load]);

  return (
    <>
      <PageHeading
        eyebrow="FAULTLINE / WORKSPACE"
        title="Reliability, with evidence."
        description="A working view of repository analysis, failure diagnosis, and repair evaluation."
        action={
          <Link className="editorial-btn-primary" href="/projects">
            <FolderKanban size={15} /> Manage projects
          </Link>
        }
      />
      {loading && <LoadingState label="Reading workspace data…" />}
      {error && <ErrorState message={error} retry={retry} />}
      {data && (
        <>
          <div className="metric-grid">
            {[
              { label: "Projects", value: data.projectCount, icon: FolderKanban, href: "/projects" },
              { label: "Repositories", value: data.repositories, icon: GitBranch, href: "/projects" },
              { label: "Analysis runs", value: data.analysisCount, icon: Activity, href: "/analyses" },
              { label: "Mutations", value: data.mutations, icon: Boxes, href: "/analyses" },
              { label: "Diagnoses", value: data.diagnoses, icon: AlertTriangle, href: "/analyses" },
              { label: "Repair candidates", value: data.repairs, icon: FileCode2, href: "/analyses" },
              { label: "Evaluations", value: data.evaluations, icon: ShieldCheck, href: "/analyses" },
            ].map(({ label, value, icon: Icon, href }) => (
              <Link className="metric-card editorial-card" href={href} key={label}>
                <div className="metric-top">
                  <span>{label}</span>
                  <Icon size={16} />
                </div>
                <strong>{value.toLocaleString()}</strong>
                <span className="metric-foot">Live API total <ArrowUpRight size={13} /></span>
              </Link>
            ))}
          </div>
          <div className="dashboard-columns">
            <Card>
              <div className="section-heading">
                <div>
                  <p className="eyebrow">RECENT WORK</p>
                  <h2>Latest analyses</h2>
                </div>
                <Link className="text-link" href="/analyses">All analyses <ArrowUpRight size={14} /></Link>
              </div>
              {data.analyses.length ? (
                <div className="activity-list">
                  {[...data.analyses].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 6).map((analysis) => (
                    <Link className="activity-row" href={`/analyses/${analysis.id}`} key={analysis.id}>
                      <span className="activity-icon"><Activity size={15} /></span>
                      <span className="activity-main">
                        <strong>{analysis.name || `Analysis ${shortId(analysis.id)}`}</strong>
                        <small>{shortId(analysis.id, 13)} · {dateTime(analysis.created_at)}</small>
                      </span>
                      <span className={`status-text ${analysis.status.toLowerCase()}`}>{analysis.status}</span>
                    </Link>
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No analysis runs yet"
                  description="Connect a repository, capture a snapshot, then generate mutations to start a run."
                  href="/projects"
                  linkText="Set up a project"
                />
              )}
            </Card>
            <Card className="workflow-card">
              <p className="eyebrow">THE WORKFLOW</p>
              <h2>From source to evidence</h2>
              <ol className="workflow-list">
                <li><span>01</span><div><strong>Connect a repository</strong><small>Ingest a public GitHub branch into a commit-pinned snapshot.</small></div></li>
                <li><span>02</span><div><strong>Run mutation analysis</strong><small>Generate deterministic AST mutations, then execute tests in the isolated runner.</small></div></li>
                <li><span>03</span><div><strong>Diagnose and evaluate</strong><small>Compare test outcomes, inspect generated patches, and evaluate candidates.</small></div></li>
              </ol>
              <div className="note-line"><CircleCheck size={15} /> No activity is fabricated; totals are read from the API.</div>
            </Card>
          </div>
          <p className="muted footnote">Recent activity is limited to the analysis history exposed by the backend. Repository sync and evaluation event feeds are not currently available.</p>
        </>
      )}
    </>
  );
}
