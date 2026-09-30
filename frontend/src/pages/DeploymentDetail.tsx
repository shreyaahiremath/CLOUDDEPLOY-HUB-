import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ACTIVE, api, type Deployment, type LogLine } from "../api";
import { WavyProgress } from "../components/charts";
import { confirmDialog } from "../components/Dialog";
import { IconExternal, IconRefresh, IconTrash } from "../components/icons";
import { RouteStrip } from "../components/RouteStrip";
import { Alert, CardSkeleton, CopyButton, ErrorState, HealthBadge, PageHead, ProviderMark, Spinner, StatusBadge } from "../components/ui";
import { timeAgo, useApi } from "../hooks";

interface Logs { hub_events: LogLine[]; provider_logs: LogLine[]; provider_error: string | null; provider_name: string }

export function DeploymentDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const dep = useApi<Deployment>(`/api/deployments/${id}`, { pollMs: 3000, shouldPoll: (d) => ACTIVE.includes(d.status) });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<string | null>(null);
  const logsRef = useRef<HTMLDivElement>(null);
  const d = dep.data;

  const act = async (key: string, fn: () => Promise<void>) => {
    setBusy(key); setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const destroy = () => act("destroy", async () => {
    const ok = await confirmDialog({
      title: "Destroy this deployment?", danger: true, confirmLabel: "Destroy",
      body: `The ${d?.provider_name} resource and its public URL will be deleted. This can't be undone.`,
    });
    if (!ok) return;
    dep.setData(await api<Deployment>(`/api/deployments/${id}/destroy`, { method: "POST" }));
  });
  const retry = () => act("retry", async () => {
    const n = await api<Deployment>(`/api/deployments/${id}/redeploy`, { method: "POST" });
    navigate(`/deployments/${n.id}`);
  });
  const recheck = () => act("health", async () => {
    const r = await api<{ healthy: boolean; detail: string }>(`/api/deployments/${id}/health`, { method: "POST" });
    setHealth(`${r.healthy ? "✓ Healthy" : "✗ Unreachable"}: ${r.detail}`);
    await dep.reload();
  });

  if (dep.loading && !d) return <div className="page"><CardSkeleton rows={6} /></div>;
  if (dep.error || !d) return <div className="page"><ErrorState message={dep.error ?? "Deployment not found."} onRetry={dep.reload} /></div>;
  const active = ACTIVE.includes(d.status);

  return (
    <div className="page">
      <PageHead
        title={<span className="row"><ProviderMark provider={d.provider} size={32} />{d.project_name}</span>}
        sub={<>{d.provider_name} · {d.plan} · started {timeAgo(d.created_at)}</>}
        actions={<StatusBadge status={d.status} />}
      />

      <section className="card stack lg">
        <RouteStrip d={d} />
        {active && <WavyProgress label={`Deployment ${d.status.toLowerCase().replace("_", " ")}`} />}
      </section>

      {d.status === "SUCCESS" && d.public_url && (
        <section className="card ticket stack">
          <h2>🎉 Deployment Successful</h2>
          <div className="big-url"><a href={d.public_url} target="_blank" rel="noreferrer">{d.public_url}</a></div>
          <div className="row">
            <a className="btn primary" href={d.public_url} target="_blank" rel="noreferrer"><IconExternal size={16} />Open Application</a>
            <CopyButton text={d.public_url} label="Copy URL" />
            <button className="btn" onClick={() => logsRef.current?.scrollIntoView({ behavior: "smooth" })}>View Logs</button>
            <button className="btn" onClick={recheck} disabled={busy !== null}>{busy === "health" ? <Spinner /> : <IconRefresh size={16} />}Check health</button>
          </div>
          {health && <p className="subtle">{health}</p>}
        </section>
      )}

      {d.status === "FAILED" && (
        <Alert tone="danger" title="Deployment Failed">
          <div className="stack" style={{ gap: 8 }}>
            <div><b>Provider:</b> {d.provider_name}</div>
            <div><b>Reason:</b> <span style={{ whiteSpace: "pre-wrap" }}>{d.error_message}</span></div>
            {d.suggested_fix && <div><b>Suggested fix:</b> {d.suggested_fix}</div>}
            <div className="row">
              <button className="btn sm" onClick={() => logsRef.current?.scrollIntoView({ behavior: "smooth" })}>View Logs</button>
              <button className="btn sm primary" onClick={retry} disabled={busy !== null}>{busy === "retry" ? <Spinner /> : "Try Again"}</button>
              <Link className="btn sm" to={`/projects/${d.project_id}/deploy/${d.provider}`}>Change settings</Link>
            </div>
          </div>
        </Alert>
      )}
      {active && <Alert tone="info">Status comes straight from {d.provider_name}'s API and refreshes automatically. You can leave this page; the deployment keeps running.</Alert>}
      {error && <Alert tone="danger">{error}</Alert>}

      <div className="grid cols-2" style={{ alignItems: "start" }}>
        <section className="card stack">
          <h2>Deployment Details</h2>
          <dl className="kv">
            <dt>Application</dt><dd><Link to={`/projects/${d.project_id}`}>{d.project_name}</Link></dd>
            <dt>GitHub</dt><dd>{d.repository ? <a href={`https://github.com/${d.repository}`} target="_blank" rel="noreferrer">@{d.repository}</a> : "Local upload"}</dd>
            {d.branch && <><dt>Branch</dt><dd className="mono">{d.branch}</dd></>}
            <dt>Platform</dt><dd>{d.provider_name}</dd>
            <dt>Plan</dt><dd>{d.plan}</dd>
            <dt>Status</dt><dd>{d.status === "SUCCESS" ? "LIVE" : d.status}{d.provider_status ? <span className="subtle"> · provider: {d.provider_status}</span> : null}</dd>
            <dt>Public URL</dt><dd>{d.public_url ? <a className="url" href={d.public_url} target="_blank" rel="noreferrer">{d.public_url}</a> : <span className="subtle">Not available yet</span>}</dd>
            <dt>Deployment ID</dt><dd className="mono">{d.deployment_id ?? "Pending"}</dd>
            <dt>Resource ID</dt><dd className="mono">{d.provider_resource_id ?? "Pending"}</dd>
            <dt>Health</dt><dd><HealthBadge d={d} />{d.health_detail && <div className="subtle">{d.health_detail}</div>}</dd>
            {d.run_url && <><dt>Workflow run</dt><dd><a href={d.run_url} target="_blank" rel="noreferrer">GitHub Actions run</a></dd></>}
            {Object.entries(d.links).map(([k, v]) => (
              <div key={k} style={{ display: "contents" }}><dt>{k.replace(/_/g, " ")}</dt><dd><a className="url" href={v} target="_blank" rel="noreferrer">{v}</a></dd></div>
            ))}
          </dl>
          <div className="row">
            {!active && d.status !== "DESTROYED" && <button className="btn" onClick={retry} disabled={busy !== null}><IconRefresh size={16} />Redeploy</button>}
            {!active && d.status !== "DESTROYED" && d.provider_resource_id && <button className="btn danger" onClick={destroy} disabled={busy !== null}>{busy === "destroy" ? <Spinner /> : <IconTrash size={16} />}Destroy Deployment</button>}
            {d.status === "DESTROYED" && <span className="subtle">This deployment was destroyed on {d.provider_name}.</span>}
          </div>
        </section>
        <section className="card stack">
          <h2>Timeline</h2>
          <ol className="stack" style={{ margin: 0, paddingLeft: 18, gap: 8, fontSize: 14 }}>
            {d.events?.map((e, i) => (
              <li key={i} style={{ color: e.level === "error" ? "var(--danger)" : e.level === "warn" ? "var(--warning)" : undefined }}>
                <span className="subtle mono">{new Date(e.ts).toLocaleTimeString()}</span> {e.message}
              </li>
            ))}
          </ol>
        </section>
      </div>

      <div ref={logsRef}><LogsPanel id={d.id} live={active} /></div>
    </div>
  );
}

function LogsPanel({ id, live }: { id: number; live: boolean }) {
  const logs = useApi<Logs>(`/api/deployments/${id}/logs`, { pollMs: 5000, shouldPoll: () => live });
  const [tab, setTab] = useState<"provider" | "hub">("provider");
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { if (live && box.current) box.current.scrollTop = box.current.scrollHeight; }, [logs.data, live]);
  const lines = tab === "provider" ? logs.data?.provider_logs : logs.data?.hub_events;

  return (
    <section className="card stack">
      <div className="card-head" style={{ marginBottom: 0 }}>
        <h2>Deployment Logs</h2>
        <button className="btn sm" onClick={() => void logs.reload()}><IconRefresh size={14} />Refresh</button>
      </div>
      <div className="tabs" role="tablist">
        <button className="tab" role="tab" aria-selected={tab === "provider"} onClick={() => setTab("provider")}>{logs.data?.provider_name ?? "Provider"} build logs</button>
        <button className="tab" role="tab" aria-selected={tab === "hub"} onClick={() => setTab("hub")}>CloudDeploy Hub events</button>
      </div>
      {logs.data?.provider_error && tab === "provider" && <Alert tone="warning">Could not fetch logs from the provider: {logs.data.provider_error}</Alert>}
      {logs.loading && !logs.data ? <CardSkeleton rows={4} /> : (
        <div className="logs" ref={box} tabIndex={0} aria-label="Log output">
          {!lines?.length ? <span className="ts">{tab === "provider" ? "No logs from the provider yet." : "No events yet."}</span> :
            lines.map((l, i) => (
              <div key={i} className="ln">
                <span className="ts">{l.ts ? new Date(l.ts).toLocaleTimeString() : ""}</span>
                <span className="src" title={l.source}>{l.source}</span>
                <span className={l.level === "error" ? "err" : l.level === "warn" ? "warn" : ""}>{l.message}</span>
              </div>
            ))}
        </div>
      )}
      <p className="subtle">Build logs are fetched live from the provider (or your GitHub Actions run). Nothing here is generated by CloudDeploy Hub except the "events" tab.</p>
    </section>
  );
}
