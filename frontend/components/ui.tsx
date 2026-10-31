import Link from "next/link";
import type { ReactNode } from "react";
import { AlertCircle, ArrowRight, Inbox, LoaderCircle, PanelLeftClose } from "lucide-react";

export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {action && <div className="heading-action">{action}</div>}
    </div>
  );
}

export function PageBackLink({ href, children }: { href: string; children: string }) {
  return (
    <Link href={href} className="back-link">
      <PanelLeftClose size={14} /> {children}
    </Link>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`editorial-card card ${className}`}>{children}</section>;
}

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  const normalized = String(children).toLowerCase().replaceAll("_", "-");
  return <span className={`editorial-badge badge ${tone ?? normalized}`}>{children}</span>;
}

export function EmptyState({
  title,
  description,
  href,
  linkText,
}: {
  title: string;
  description: string;
  href?: string;
  linkText?: string;
}) {
  return (
    <div className="empty-state">
      <Inbox size={22} strokeWidth={1.5} />
      <h3>{title}</h3>
      <p>{description}</p>
      {href && linkText && (
        <Link className="text-link" href={href}>
          {linkText} <ArrowRight size={14} />
        </Link>
      )}
    </div>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="error-state" role="alert">
      <AlertCircle size={18} />
      <div>
        <strong>Couldn’t load this view</strong>
        <p>{message}</p>
        {retry && (
          <button className="editorial-btn-secondary" onClick={retry}>
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function LoadingState({ label = "Loading data…" }: { label?: string }) {
  return (
    <div className="loading-state" role="status" aria-label={label}>
      <div className="loading-indicator"><LoaderCircle className="spin" size={18} /><span>{label}</span></div>
      <div className="loading-skeleton" aria-hidden="true">
        <span /><span /><span />
      </div>
    </div>
  );
}

export function JsonDetails({
  label,
  value,
}: {
  label: string;
  value: unknown;
}) {
  if (value == null || value === "") return null;
  return (
    <details className="json-details">
      <summary>{label}</summary>
      <pre>{typeof value === "string" ? value : JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
