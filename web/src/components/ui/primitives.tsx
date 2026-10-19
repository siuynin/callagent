import type { ReactNode } from "react";

// Server-safe building blocks mirroring plan/template helpers (head, stats, card, table, badge).

export function PageHead({ title, sub, actions }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="pagehead">
      <div>
        <div className="eyebrow">VOICE AGENT WORKSPACE</div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  );
}

export type Stat = { label: string; value: ReactNode; foot?: ReactNode };

const MINI = [9, 16, 12, 21, 17, 25, 20, 28];

export function Stats({ items }: { items: Stat[] }) {
  return (
    <div className="grid stats">
      {items.map((s, i) => (
        <div key={s.label} className="card pad" style={{ position: "relative" }}>
          <div className="statlabel">{s.label}</div>
          <div className="statvalue">{s.value}</div>
          {s.foot && <div className="statfoot">{s.foot}</div>}
          {/* decorative bars from the template's polishUI */}
          <div className="statmini" aria-hidden="true">
            {MINI.map((h, n) => (
              <i key={n} style={{ height: h - (i % 2) * 3 }} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function Card({ title, action, children, id }: { title: ReactNode; action?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="card" id={id}>
      <div className="cardhead">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function DataTable({ heads, children, responsive }: { heads: string[]; children: ReactNode; responsive?: boolean }) {
  return (
    <div className={`tablewrap${responsive ? " responsive" : ""}`}>
      <table>
        <thead>
          <tr>
            {heads.map((h, i) => (
              <th key={i}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export type Tone = "green" | "amber" | "red" | "neutral";

export function Pill({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`pill${tone === "neutral" ? "" : ` ${tone}`}`}>{children}</span>;
}

export function Notice({ tone, children, role }: { tone?: "warn" | "bad"; children: ReactNode; role?: "status" | "alert" }) {
  return (
    <div className={`notice${tone ? ` ${tone}` : ""}`} role={role}>
      <span aria-hidden="true">◌</span>
      <div>{children}</div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Skeleton({ label }: { label: string }) {
  return <div className="skeleton" role="status" aria-label={label} />;
}
