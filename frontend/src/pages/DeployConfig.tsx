import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type DeployConfig as Config, type Deployment, type Preview, type Project } from "../api";
import { IconRocket } from "../components/icons";
import { Alert, CardSkeleton, ErrorState, PageHead, ProviderMark, Spinner, providerName } from "../components/ui";
import { useApi } from "../hooks";

type EnvRow = { key: string; value: string };

export function DeployConfig() {
  const { id, provider = "" } = useParams();
  const navigate = useNavigate();
  const project = useApi<Project>(`/api/projects/${id}`);
  const [cfg, setCfg] = useState<Config>({ build_mode: "native" });
  const [env, setEnv] = useState<EnvRow[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const config = useMemo<Config>(() => ({
    ...cfg,
    env_vars: Object.fromEntries(env.filter((r) => r.key.trim()).map((r) => [r.key.trim(), r.value])),
    acknowledge_conditional: ack,
  }), [cfg, env, ack]);

  // Debounced live preview: validation + exactly what will be created.
  useEffect(() => {
    const t = window.setTimeout(async () => {
      try { setPreview(await api<Preview>(`/api/projects/${id}/preview`, { method: "POST", json: { provider, config } })); setPreviewError(null); }
      catch (e) { setPreviewError((e as Error).message); }
    }, 350);
    return () => window.clearTimeout(t);
  }, [id, provider, config]);

  const set = (k: keyof Config) => (e: { target: { value: string } }) => setCfg((c) => ({ ...c, [k]: e.target.value || null }));
  const a = project.data?.analysis;
  const conditional = preview?.compatibility.status === "conditional";
  const deploy = async () => {
    setBusy(true); setError(null);
    try {
      const d = await api<Deployment>(`/api/projects/${id}/deployments`, { method: "POST", json: { provider, config } });
      navigate(`/deployments/${d.id}`);
    } catch (e) { setError((e as Error).message); setBusy(false); }
  };

  if (project.loading && !project.data) return <div className="page"><CardSkeleton rows={6} /></div>;
  if (project.error || !project.data) return <div className="page"><ErrorState message={project.error ?? "Not found"} /></div>;
  const p = project.data;
  const plan = preview?.plan ?? {};
  const showStart = provider === "render" && a?.app_type !== "Static Frontend" && a?.app_type !== "Frontend";

  return (
    <div className="page">
      <PageHead title={<span className="row"><ProviderMark provider={provider} size={32} />Deploy to {providerName(provider)}</span>}
        sub={`${p.name} · ${a?.framework ?? "Unknown framework"}`}
        actions={<Link className="btn" to={`/projects/${id}/deploy`}>Change platform</Link>} />

      <div className="grid cols-2" style={{ alignItems: "start" }}>
        <section className="card stack">
          <h2>Deployment Configuration</h2>
          <div className="field">
            <label htmlFor="dname">Deployment name</label>
            <input id="dname" className="input" placeholder={p.name.toLowerCase().replace(/\s+/g, "-")} onChange={set("name")} maxLength={60} />
            <span className="hint">Used for the provider's project/service name, which usually becomes part of the URL.</span>
          </div>
          {p.repository && (
            <div className="field"><label htmlFor="dbranch">Branch</label>
              <input id="dbranch" className="input mono" placeholder={p.branch ?? "main"} onChange={set("branch")} /></div>
          )}
          {provider === "render" && a?.app_type !== "Static Frontend" && a?.app_type !== "Frontend" && (
            <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="label">Build</legend>
              <label className="check"><input type="radio" checked={cfg.build_mode !== "docker"} onChange={() => setCfg((c) => ({ ...c, build_mode: "native" }))} />Native runtime{a?.has_dockerfile ? "" : " (recommended)"}</label>
              <label className="check"><input type="radio" checked={cfg.build_mode === "docker"} onChange={() => setCfg((c) => ({ ...c, build_mode: "docker" }))} />Docker{a?.has_dockerfile ? " (uses your Dockerfile)" : " (generate a Dockerfile)"}</label>
            </fieldset>
          )}
          <details>
            <summary><b>Build settings</b> <span className="subtle">(detected values are used when empty)</span></summary>
            <div className="stack" style={{ marginTop: 12 }}>
              <div className="field"><label htmlFor="inst">Install command</label><input id="inst" className="input mono" placeholder={a?.install_command ?? ""} onChange={set("install_command")} /></div>
              <div className="field"><label htmlFor="bld">Build command</label><input id="bld" className="input mono" placeholder={a?.build_command ?? "none"} onChange={set("build_command")} /></div>
              <div className="field"><label htmlFor="out">Output directory</label><input id="out" className="input mono" placeholder={a?.output_dir ?? ""} onChange={set("output_dir")} /></div>
              {showStart && <div className="field"><label htmlFor="start">Start command</label><input id="start" className="input mono" placeholder={a?.start_command ?? ""} onChange={set("start_command")} /></div>}
              <div className="field"><label htmlFor="hc">Health check path</label><input id="hc" className="input mono" placeholder={a?.app_type === "Backend API" ? "/health, then /" : "/"} onChange={set("health_check_path")} /></div>
            </div>
          </details>
          {(provider === "render" || provider === "vercel") && (
            <details>
              <summary><b>Environment variables</b> <span className="subtle">({env.length})</span></summary>
              <div className="stack" style={{ marginTop: 12 }}>
                {env.map((row, i) => (
                  <div key={i} className="row" style={{ flexWrap: "nowrap" }}>
                    <input className="input mono" aria-label="Name" placeholder="NAME" value={row.key} onChange={(e) => setEnv(env.map((r, j) => j === i ? { ...r, key: e.target.value } : r))} />
                    <input className="input mono" aria-label="Value" placeholder="value" type="password" value={row.value} onChange={(e) => setEnv(env.map((r, j) => j === i ? { ...r, value: e.target.value } : r))} />
                    <button className="btn ghost sm" aria-label="Remove variable" onClick={() => setEnv(env.filter((_, j) => j !== i))}>✕</button>
                  </div>
                ))}
                <button className="btn sm" onClick={() => setEnv([...env, { key: "", value: "" }])}>Add variable</button>
                <span className="hint">Sent directly to the provider. CloudDeploy Hub stores them with the deployment's configuration.</span>
              </div>
            </details>
          )}
        </section>

        <section className="card stack">
          <h2>Deployment Preview</h2>
          {previewError && <Alert tone="danger">{previewError}</Alert>}
          {!preview ? <Spinner label="Preparing preview" /> : (
            <>
              <dl className="kv">
                <dt>Application</dt><dd>{preview.application}</dd>
                <dt>Source</dt><dd>{preview.source}{preview.repository ? ` · ${preview.repository}` : ""}</dd>
                <dt>Provider</dt><dd>{preview.provider_name}</dd>
                <dt>Plan</dt><dd>{String(plan.plan ?? "Free")}</dd>
                <dt>Resource</dt><dd>{String(plan.resource ?? "")}</dd>
                <dt>Build</dt><dd>{String(plan.build ?? "")}</dd>
                {preview.branch && <><dt>Branch</dt><dd className="mono">{preview.branch}</dd></>}
                {plan.build_command ? <><dt>Build command</dt><dd className="mono">{String(plan.build_command)}</dd></> : null}
                {plan.start_command ? <><dt>Start command</dt><dd className="mono">{String(plan.start_command)}</dd></> : null}
                {plan.output_dir || plan.publish_path ? <><dt>Output</dt><dd className="mono">{String(plan.output_dir ?? plan.publish_path)}</dd></> : null}
                {plan.base_path ? <><dt>Base path</dt><dd className="mono">{String(plan.base_path)}</dd></> : null}
                <dt>Environment</dt><dd>{preview.environment}</dd>
              </dl>
              {Array.isArray(plan.repository_changes) && plan.repository_changes.length > 0 && (
                <Alert tone="info" title="Changes to your repository">
                  <ul>{(plan.repository_changes as string[]).map((c) => <li key={c}><code>{c}</code></li>)}</ul>
                </Alert>
              )}
              {["generated_dockerfile", "generated_workflow", "generated_netlify_toml"].map((k) => plan[k] ? (
                <details key={k}><summary><b>{k === "generated_dockerfile" ? "Generated Dockerfile" : k === "generated_workflow" ? "Generated GitHub Actions workflow" : "Generated netlify.toml"}</b></summary>
                  <pre className="code" style={{ marginTop: 8 }}>{String(plan[k])}</pre></details>
              ) : null)}
              {preview.errors.length > 0 && <Alert tone="danger" title="Can't deploy yet"><ul>{preview.errors.map((e) => <li key={e}>{e}</li>)}</ul></Alert>}
              {!preview.configured && <Alert tone="warning" title="Provider Not Configured">Missing: {preview.missing_credentials.join(", ")}. {preview.missing_credentials.some((m) => m.includes("GitHub")) ? <Link to="/github">Connect GitHub</Link> : "Ask the administrator to add them on the backend."}</Alert>}
              {preview.warnings.length > 0 && <Alert tone="warning"><ul>{preview.warnings.map((w) => <li key={w}>{w}</li>)}</ul></Alert>}
              {conditional && (
                <label className="check"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                  I understand this project needs adaptation to run on {preview.provider_name}: {preview.compatibility.reasons.join(" ")}</label>
              )}
              <p className="subtle">{preview.notice}</p>
              {error && <Alert tone="danger">{error}</Alert>}
              <button className="btn primary lg" onClick={deploy} disabled={busy || !preview.can_deploy || (conditional && !ack)}>
                {busy ? <Spinner label="Submitting" /> : <><IconRocket size={18} />Deploy Now</>}
              </button>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
