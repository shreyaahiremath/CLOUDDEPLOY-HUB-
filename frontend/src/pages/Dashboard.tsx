import { Link } from "react-router-dom";
import type { Deployment } from "../api";
import { useAuth } from "../auth";
import { AreaChart, Donut, HubOrbit, ProviderBars, WavyProgress, type DayPoint } from "../components/charts";
import { IconCheck, IconGit, IconPlus, IconRocket } from "../components/icons";
import { CardSkeleton, Empty, ErrorState, ProviderMark, StatusBadge, providerName } from "../components/ui";
import { timeAgo, useApi } from "../hooks";

interface Stats {
  projects: number; deployments: number; successful: number; failed: number; in_progress: number; live: number;
  github_connected: boolean; github_login: string | null; free_platforms: number; configured_platforms: number; recent: Deployment[];
  timeline: DayPoint[]; by_provider: { provider: string; name: string; total: number; success: number }[];
}

export function Dashboard() {
  const { user } = useAuth();
  const { data, error, loading, reload } = useApi<Stats>("/api/stats", { pollMs: 5000, shouldPoll: (s) => s.in_progress > 0 });
  const first = user?.name?.split(" ")[0];

  return (
    <div className="page">
      <section className="card hero">
        <div className="stack lg">
          <div className="stack">
            <h1>{first ? `Welcome, ${first}` : "Welcome"}</h1>
            <p>One project, five free clouds. CloudDeploy Hub analyzes your app, deploys it through the platform's real API and hands back the live URL.</p>
          </div>
          <div className="row">
            <Link className="btn primary lg" to="/projects/new"><IconPlus size={18} />Add Project</Link>
            <Link className="btn tonal lg" to="/projects"><IconRocket size={18} />Deploy a project</Link>
          </div>
        </div>
        <HubOrbit />
      </section>

      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data ? <div className="grid cols-3"><CardSkeleton /><CardSkeleton /><CardSkeleton /></div> : data && (
        <>
          {data.in_progress > 0 && (
            <Link to="/deployments" className="card tight stack" style={{ color: "inherit" }}>
              <span><b>{data.in_progress}</b> deployment{data.in_progress === 1 ? "" : "s"} in progress. Status updates live from the provider.</span>
              <WavyProgress label="Deployments in progress" />
            </Link>
          )}

          <section className="grid stats" aria-label="Summary">
            <Stat label="Projects" value={data.projects} to="/projects" />
            <Stat label="Deployments" value={data.deployments} to="/deployments" />
            <Stat label="Successful" value={data.successful} to="/deployments?status=SUCCESS" />
            <Stat label="Failed" value={data.failed} to="/deployments?status=FAILED" />
            <Stat label={`Free platforms · ${data.configured_platforms} configured`} value={data.free_platforms} to="/providers" />
            <Link to="/github" className="card tight stat stat-tile" style={{ color: "inherit", textDecoration: "none" }}>
              <span className="value" style={{ fontSize: 15, fontWeight: 500, lineHeight: "42px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: data.github_connected ? "var(--success)" : "var(--text-2)" }}>
                {data.github_connected ? <><IconCheck size={18} /> @{data.github_login}</> : "Not connected"}
              </span>
              <span className="label">Connected GitHub</span>
            </Link>
          </section>

          <section className="grid charts" aria-label="Deployment charts">
            <div className="card chart-card">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div><h2>Deployments</h2><span className="subtle">Last 14 days</span></div>
                <div className="legend">
                  <span><i style={{ background: "var(--md-primary)" }} />All</span>
                  <span><i style={{ background: "var(--md-tertiary)" }} />Live</span>
                </div>
              </div>
              <AreaChart data={data.timeline} />
              {data.deployments === 0 && <span className="subtle">Your deployments will draw this line as they happen.</span>}
            </div>
            <div className="card chart-card">
              <div><h2>Success rate</h2><span className="subtle">Finished deployments</span></div>
              <Donut success={data.successful} failed={data.failed} />
              <div className="legend" style={{ justifyContent: "center" }}>
                <span><i style={{ background: "var(--md-primary)" }} />{data.successful} live</span>
                <span><i style={{ background: "var(--danger)" }} />{data.failed} failed</span>
              </div>
            </div>
            <div className="card chart-card">
              <div><h2>By platform</h2><span className="subtle">Where your deployments went</span></div>
              <ProviderBars items={data.by_provider} />
            </div>
          </section>

          <section className="card">
            <div className="card-head">
              <h2>Recent deployments</h2>
              <Link to="/deployments" className="btn sm ghost">View all</Link>
            </div>
            {data.recent.length === 0 ? (
              <Empty icon={<IconRocket />} title="No deployments yet" action={<Link className="btn primary" to="/projects/new">Add your first project</Link>}>
                Each deployment shows its real provider status, logs, and the public URL once it's healthy.
              </Empty>
            ) : <RecentTable rows={data.recent} />}
          </section>
          {!data.github_connected && (
            <Link to="/github" className="card tight row" style={{ color: "inherit" }}><IconGit /> Connect GitHub to deploy repositories and use Render, GitHub Pages and Cloudflare Pages.</Link>
          )}
        </>
      )}
    </div>
  );
}

function Stat({ label, value, to }: { label: string; value: number; to: string }) {
  return (
    <Link to={to} className="card tight stat stat-tile" style={{ color: "inherit", textDecoration: "none" }}>
      <span className="value">{value}</span>
      <span className="label">{label}</span>
    </Link>
  );
}

export function RecentTable({ rows }: { rows: Deployment[] }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr><th>Application</th><th>Platform</th><th>Status</th><th>URL</th><th>Started</th></tr></thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.id}>
              <td><Link to={`/deployments/${d.id}`}><b>{d.project_name}</b></Link>{d.repository && <div className="subtle">{d.repository}</div>}</td>
              <td><span className="row" style={{ flexWrap: "nowrap" }}><ProviderMark provider={d.provider} size={24} />{providerName(d.provider)}</span></td>
              <td><StatusBadge status={d.status} /></td>
              <td>{d.public_url && d.status === "SUCCESS" ? <a className="url" href={d.public_url} target="_blank" rel="noreferrer">{d.public_url.replace(/^https:\/\//, "")}</a> : <span className="subtle">No URL yet</span>}</td>
              <td className="subtle">{timeAgo(d.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
