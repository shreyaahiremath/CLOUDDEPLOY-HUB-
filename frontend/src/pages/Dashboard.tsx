import { Link } from "react-router-dom";
import type { Deployment } from "../api";
import { useAuth } from "../auth";
import { IconCheck, IconGit, IconPlus, IconRocket } from "../components/icons";
import { CardSkeleton, Empty, ErrorState, PageHead, ProviderMark, StatusBadge, providerName } from "../components/ui";
import { timeAgo, useApi } from "../hooks";

interface Stats {
  projects: number; deployments: number; successful: number; failed: number; in_progress: number; live: number;
  github_connected: boolean; github_login: string | null; free_platforms: number; configured_platforms: number; recent: Deployment[];
}

export function Dashboard() {
  const { user } = useAuth();
  const { data, error, loading, reload } = useApi<Stats>("/api/stats", { pollMs: 5000, shouldPoll: (s) => s.in_progress > 0 });
  const first = user?.name?.split(" ")[0];

  return (
    <div className="page">
      <PageHead
        title={first ? `Welcome, ${first}` : "Welcome"}
        sub="Deploy your own project to free cloud platforms and get a real public URL."
        actions={<Link className="btn primary" to="/projects/new"><IconPlus size={16} />Add Project</Link>}
      />
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data ? <CardSkeleton rows={2} /> : data && (
        <>
          <section className="grid stats" aria-label="Summary">
            <Stat label="Projects" value={data.projects} to="/projects" />
            <Stat label="Deployments" value={data.deployments} to="/deployments" />
            <Stat label="Successful" value={data.successful} to="/deployments?status=SUCCESS" />
            <Stat label="Failed" value={data.failed} to="/deployments?status=FAILED" />
            <Link to="/github" className="card tight stat" style={{ color: "inherit", textDecoration: "none" }}>
              <span className="value" style={{ fontSize: 24, color: data.github_connected ? "var(--success)" : "var(--text-3)" }}>
                {data.github_connected ? <><IconCheck size={22} /> @{data.github_login}</> : "Not connected"}
              </span>
              <span className="label">Connected GitHub</span>
            </Link>
            <Stat label={`Free platforms (${data.configured_platforms} configured)`} value={data.free_platforms} to="/providers" />
          </section>

          {!data.github_connected && data.projects === 0 && (
            <div className="card">
              <div className="stack">
                <h2>Get your first app live</h2>
                <ol className="muted" style={{ margin: 0, paddingLeft: 20, lineHeight: 1.9 }}>
                  <li><Link to="/github">Connect GitHub</Link> to deploy a repository, or <Link to="/projects/new">upload a project folder</Link>.</li>
                  <li>Review the analysis: CloudDeploy Hub only offers platforms that can actually run your app.</li>
                  <li>Choose a free platform, check the preview, and select <b>Deploy Now</b>.</li>
                </ol>
              </div>
            </div>
          )}

          <section className="card">
            <div className="card-head">
              <h2>Recent deployments</h2>
              <Link to="/deployments" className="btn sm ghost">View all</Link>
            </div>
            {data.recent.length === 0 ? (
              <Empty icon={<IconRocket />} title="No deployments yet" action={<Link className="btn primary" to="/projects">Choose a project to deploy</Link>}>
                Each deployment shows its real provider status, logs, and the public URL once it's healthy.
              </Empty>
            ) : <RecentTable rows={data.recent} />}
          </section>
          {!data.github_connected && data.projects > 0 && (
            <Link to="/github" className="card tight row" style={{ color: "inherit" }}><IconGit /> Connect GitHub to deploy repositories and use Render, GitHub Pages and Cloudflare Pages.</Link>
          )}
        </>
      )}
    </div>
  );
}

function Stat({ label, value, to }: { label: string; value: number; to: string }) {
  return (
    <Link to={to} className="card tight stat" style={{ color: "inherit", textDecoration: "none" }}>
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
              <td><span className="row"><ProviderMark provider={d.provider} size={24} />{providerName(d.provider)}</span></td>
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
