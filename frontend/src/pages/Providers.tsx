import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type ProviderInfo } from "../api";
import { IconCheck } from "../components/icons";
import { Alert, CardSkeleton, ErrorState, PageHead, ProviderMark, Spinner } from "../components/ui";
import { useApi } from "../hooks";

export function Providers() {
  const { data, error, loading, reload } = useApi<ProviderInfo[]>("/api/providers");
  const [checks, setChecks] = useState<Record<string, { ok: boolean; account: string | null; error: string | null } | "busy">>({});

  const check = async (key: string) => {
    setChecks((c) => ({ ...c, [key]: "busy" }));
    try { const r = await api<{ ok: boolean; account: string | null; error: string | null }>(`/api/providers/${key}/check`, { method: "POST" }); setChecks((c) => ({ ...c, [key]: r })); }
    catch (e) { setChecks((c) => ({ ...c, [key]: { ok: false, account: null, error: (e as Error).message } })); }
  };

  return (
    <div className="page">
      <PageHead title="Free Deployment Platforms" sub="Only platforms with a free deployment option. No paid or credit-based infrastructure." />
      <Alert tone="info" title="About free plans">
        Free plan available subject to the provider's current limits and terms. Free plans are not unlimited, may sleep or spin down, and providers can change them at any time.
      </Alert>
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data ? <div className="grid cols-2"><CardSkeleton /><CardSkeleton /></div> : (
        <div className="grid cols-2">
          {data?.map((p) => {
            const c = checks[p.key];
            return (
              <article key={p.key} className="card stack">
                <div className="row"><ProviderMark provider={p.key} /><div><h2>{p.name}</h2><span className="subtle">{p.plan}</span></div></div>
                <div className="row">
                  <span className={`badge ${p.configured ? "success" : "warning"}`}>{p.configured ? "Configured" : "Provider Not Configured"}</span>
                  <span className={`badge ${p.verified ? "live" : ""}`}>{p.verified ? <><IconCheck size={12} />End-to-end verified</> : "Not yet verified end-to-end"}</span>
                </div>
                <dl className="kv">
                  <dt>Deployment types</dt><dd>{p.deployment_types.join(", ")}</dd>
                  <dt>Best for</dt><dd>{p.best_for.join(", ")}</dd>
                  <dt>URL</dt><dd className="mono">{p.url_pattern}</dd>
                  <dt>How it deploys</dt><dd>{p.build_strategy}</dd>
                  <dt>Needs GitHub repo</dt><dd>{p.requires_github_repo ? "Yes" : "No, uploads work directly"}</dd>
                  {p.env_vars.length > 0 && <><dt>Backend settings</dt><dd className="mono">{p.env_vars.join(", ")}</dd></>}
                  {p.verification && <><dt>Verified by</dt><dd><Link to={`/deployments/${p.verification.deployment_id}`}>deployment #{p.verification.deployment_id}</Link> · <a className="url" href={p.verification.public_url} target="_blank" rel="noreferrer">{p.verification.public_url}</a></dd></>}
                </dl>
                <details><summary><b>Free-plan limitations</b></summary><ul className="reasons" style={{ marginTop: 8 }}>{p.limitations.map((l) => <li key={l}>{l}</li>)}</ul></details>
                <div className="row">
                  <button className="btn sm" onClick={() => void check(p.key)} disabled={c === "busy"}>{c === "busy" ? <Spinner /> : "Test connection"}</button>
                  <a className="btn sm ghost" href={p.pricing_url} target="_blank" rel="noreferrer">Current pricing</a>
                  <a className="btn sm ghost" href={p.docs_url} target="_blank" rel="noreferrer">Docs</a>
                </div>
                {c && c !== "busy" && (c.ok ? <Alert tone="success">Connected{c.account ? ` as ${c.account}` : ""}.</Alert> : <Alert tone="danger">{c.error}</Alert>)}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
