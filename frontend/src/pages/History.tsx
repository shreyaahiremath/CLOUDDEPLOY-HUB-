import { Link, useSearchParams } from "react-router-dom";
import { ACTIVE, type Deployment } from "../api";
import { IconHistory } from "../components/icons";
import { CardSkeleton, Empty, ErrorState, HealthBadge, PageHead, ProviderMark, StatusBadge, providerName, PROVIDER_META } from "../components/ui";
import { useApi } from "../hooks";

const STATUSES = ["SUCCESS", "FAILED", "BUILDING", "DEPLOYING", "DESTROYED"];

export function History() {
  const [params, setParams] = useSearchParams();
  const provider = params.get("provider") ?? "";
  const status = params.get("status") ?? "";
  const qs = new URLSearchParams({ ...(provider && { provider }), ...(status && { status }) }).toString();
  const { data, error, loading, reload } = useApi<Deployment[]>(`/api/deployments${qs ? `?${qs}` : ""}`, {
    pollMs: 5000, shouldPoll: (rows) => rows.some((r) => ACTIVE.includes(r.status)),
  });
  const setFilter = (k: string, v: string) => { const n = new URLSearchParams(params); if (v) n.set(k, v); else n.delete(k); setParams(n); };

  return (
    <div className="page">
      <PageHead title="Deployment History" sub="Every deployment, with the provider's real deployment ID and URL." />
      <div className="row">
        <div className="field"><label htmlFor="fp">Platform</label>
          <select id="fp" className="input" value={provider} onChange={(e) => setFilter("provider", e.target.value)}>
            <option value="">All platforms</option>
            {Object.entries(PROVIDER_META).map(([k, m]) => <option key={k} value={k}>{m.name}</option>)}
          </select></div>
        <div className="field"><label htmlFor="fs">Status</label>
          <select id="fs" className="input" value={status} onChange={(e) => setFilter("status", e.target.value)}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select></div>
      </div>
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data ? <CardSkeleton rows={5} /> : data && data.length === 0 ? (
        <Empty icon={<IconHistory />} title={qs ? "No deployments match these filters" : "No deployments yet"}
          action={<Link className="btn primary" to="/projects">Deploy a project</Link>} />
      ) : (
        <div className="card table-wrap" style={{ padding: 0 }}>
          <table className="table">
            <thead><tr><th>Application</th><th>GitHub</th><th>Platform</th><th>Status</th><th>Health</th><th>Public URL</th><th>Deployment ID</th><th>Created</th></tr></thead>
            <tbody>
              {data?.map((d) => (
                <tr key={d.id}>
                  <td><Link to={`/deployments/${d.id}`}><b>{d.project_name}</b></Link></td>
                  <td className="subtle">{d.repository ? `@${d.repository}` : "Upload"}{d.branch ? ` · ${d.branch}` : ""}</td>
                  <td><span className="row" style={{ flexWrap: "nowrap" }}><ProviderMark provider={d.provider} size={22} />{providerName(d.provider)}</span></td>
                  <td><StatusBadge status={d.status} /></td>
                  <td><HealthBadge d={d} /></td>
                  <td>{d.public_url ? <a className="url" href={d.public_url} target="_blank" rel="noreferrer">{d.public_url.replace(/^https:\/\//, "")}</a> : <span className="subtle">none</span>}</td>
                  <td className="mono subtle">{d.deployment_id ?? "pending"}</td>
                  <td className="subtle">{new Date(d.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
