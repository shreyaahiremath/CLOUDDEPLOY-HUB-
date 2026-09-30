import { Link, useSearchParams } from "react-router-dom";
import { ACTIVE, type Deployment } from "../api";
import { IconCheck, IconHistory } from "../components/icons";
import { CardSkeleton, Empty, ErrorState, HealthBadge, PageHead, ProviderMark, StatusBadge, providerName, PROVIDER_META } from "../components/ui";
import { useApi } from "../hooks";

const STATUSES = ["SUCCESS", "FAILED", "BUILDING", "DEPLOYING", "DESTROYED"];
const LABELS: Record<string, string> = { SUCCESS: "Live", FAILED: "Failed", BUILDING: "Building", DEPLOYING: "Deploying", DESTROYED: "Destroyed" };

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
      <div className="stack">
        <div className="chips" role="group" aria-label="Filter by platform">
          <button className="chip" aria-pressed={!provider} onClick={() => setFilter("provider", "")}>{!provider && <IconCheck size={16} />}All platforms</button>
          {Object.entries(PROVIDER_META).map(([k, m]) => (
            <button key={k} className="chip" aria-pressed={provider === k} onClick={() => setFilter("provider", provider === k ? "" : k)}>
              {provider === k && <IconCheck size={16} />}{m.name}
            </button>
          ))}
        </div>
        <div className="chips" role="group" aria-label="Filter by status">
          <button className="chip" aria-pressed={!status} onClick={() => setFilter("status", "")}>{!status && <IconCheck size={16} />}All statuses</button>
          {STATUSES.map((s) => (
            <button key={s} className="chip" aria-pressed={status === s} onClick={() => setFilter("status", status === s ? "" : s)}>
              {status === s && <IconCheck size={16} />}{LABELS[s]}
            </button>
          ))}
        </div>
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
