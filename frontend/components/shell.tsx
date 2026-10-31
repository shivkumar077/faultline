"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity,
  ChevronRight,
  CircleGauge,
  FileCode2,
  FolderKanban,
  Menu,
  ShieldCheck,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { shortId } from "@/lib/format";
import { ToastViewport } from "@/components/notifications";

const navigation = [
  { href: "/", label: "Overview", icon: CircleGauge, exact: true },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/analyses", label: "Analyses", icon: Activity },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [apiStatus, setApiStatus] = useState<"checking" | "connected" | "offline">("checking");
  useEffect(() => {
    let active = true;
    const check = () => {
      api.health().then(
        () => { if (active) setApiStatus("connected"); },
        () => { if (active) setApiStatus("offline"); },
      );
    };
    check();
    const timer = window.setInterval(check, 30_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);
  const segments = pathname.split("/").filter(Boolean);
  const breadcrumbs: { label: string; href?: string }[] = [{ label: "Faultline", href: "/" }];
  if (segments[0] === "projects") {
    breadcrumbs.push({ label: "Projects", href: "/projects" });
    if (segments[1]) breadcrumbs.push({ label: `Project ${shortId(segments[1])}`, href: pathname });
  } else if (segments[0] === "snapshots") {
    breadcrumbs.push({ label: "Projects", href: "/projects" });
    if (segments[1]) breadcrumbs.push({ label: `Snapshot ${shortId(segments[1])}` });
  } else if (segments[0] === "analyses") {
    breadcrumbs.push({ label: "Analyses", href: "/analyses" });
    if (segments[1]) breadcrumbs.push({ label: `Analysis ${shortId(segments[1])}`, href: `/analyses/${segments[1]}` });
    if (segments[2] === "diagnoses") breadcrumbs.push({ label: "Diagnoses", href: pathname });
    if (segments[2] === "repairs") breadcrumbs.push({ label: "Repair candidates", href: pathname });
  } else if (segments[0] === "diagnoses") {
    breadcrumbs.push({ label: "Diagnoses", href: "/analyses" });
    if (segments[1]) breadcrumbs.push({ label: `Report ${shortId(segments[1])}` });
  } else if (segments[0] === "repairs") {
    breadcrumbs.push({ label: "Analyses", href: "/analyses" });
    if (segments[1]) breadcrumbs.push({ label: `Candidate ${shortId(segments[1])}`, href: `/repairs/${segments[1]}` });
    if (segments[2] === "evaluations") breadcrumbs.push({ label: "Evaluations", href: pathname });
    if (segments[3]) breadcrumbs.push({ label: `Evaluation ${shortId(segments[3])}` });
  }
  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
        <Link className="brand" href="/" onClick={() => setMobileOpen(false)}>
          <span className="brand-mark">F</span>
          <span>
            <strong>Faultline</strong>
            <small>Reliability workspace</small>
          </span>
        </Link>
        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navigation.map(({ href, label, icon: Icon, exact }) => {
            const active = exact ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`nav-link ${active ? "active" : ""}`}
                aria-current={active ? "page" : undefined}
                onClick={() => setMobileOpen(false)}
              >
                <Icon size={17} strokeWidth={1.7} />
                <span>{label}</span>
                {active && <ChevronRight className="nav-chevron" size={14} />}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <ShieldCheck size={16} />
            <span>Deterministic analysis. Evidence-led repairs.</span>
          </div>
          <div className="sidebar-version">FAULTLINE · API v1</div>
        </div>
      </aside>
      {mobileOpen && (
        <button
          aria-label="Close navigation"
          className="mobile-backdrop"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <div className="main-column">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
            onClick={() => setMobileOpen((open) => !open)}
          >
            {mobileOpen ? <X size={19} /> : <Menu size={19} />}
          </button>
          <nav className="breadcrumbs" aria-label="Breadcrumbs">
            {breadcrumbs.map((crumb, index) => (
              <span className="breadcrumb-item" key={`${crumb.label}-${index}`}>
                {index > 0 && <ChevronRight size={13} aria-hidden="true" />}
                {crumb.href && index < breadcrumbs.length - 1 ? <Link href={crumb.href}>{crumb.label}</Link> : <strong aria-current="page">{crumb.label}</strong>}
              </span>
            ))}
          </nav>
          <a className="api-indicator" href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"}/docs`} target="_blank" rel="noreferrer" aria-label={`API ${apiStatus}; open API documentation in a new tab`}>
            <span className={`status-dot ${apiStatus}`} />
            API {apiStatus}
            <FileCode2 size={14} />
          </a>
        </header>
        <main className="main-content">{children}</main>
      </div>
      <ToastViewport />
    </div>
  );
}
