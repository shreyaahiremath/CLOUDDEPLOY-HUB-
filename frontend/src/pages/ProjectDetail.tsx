import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, type Project } from "../api";
import { IconGit, IconRefresh, IconRocket, IconTrash } from "../components/icons";
import { Alert, CardSkeleton, ErrorState, PageHead, Spinner } from "../components/ui";
import { formatBytes, useApi } from "../hooks";
import { RecentTable } from "./Dashboard";

export function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const project = useApi<Project>(`/api/projects/${id}`);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rootDir, setRootDir] = useState<string | null>(null);

  const p = project.data;
  const a = p?.analysis;

  const act = async (key: string, fn: () => Promise<void>) => {
    setBusy(key); setError(null);
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const reanalyze = () => act("analyze", async () => { project.setData(await api<Project>(`/api/projects/${id}/analyze`, { method: "POST" })); });
  const saveRoot = () => act("root", async () => {
    project.setData(await api<Project>(`/api/projects/${id}`, { method: "PATCH", json: { root_dir: rootDir ?? "" } }));
    setRootDir(null);
  });
  const remove = () => act("delete", async () => {
    if (!window.confirm(`Delete project "${p?.name}"? Its uploaded files and deployment history will be removed.`)) return;
    await api(`/api/projects/${id}`, { method: "DELETE" });
    navigate("/projects");
  });

  if (project.loading && !p) return <div className="page"><CardSkeleton rows={6} /></div>;
  if (project.error || !p) return <div className="page"><ErrorState message={project.error ?? "Project not found."} onRetry={project.reload} /></div>;

  return (
    <div className="page">
      <PageHead
        title={p.name}
        sub={p.repository ? <>GitHub: <a href={`https://github.com/${p.repository}`} target="_blank" rel="noreferrer">{p.repository}</a> · branch {p.branch}</> : "Local project upload"}
        actions={<>
          <button className="btn" onClick={reanalyze} disabled={busy !== null}>{busy === "analyze" ? <Spinner /> : <IconRefresh size={16} />}Analyze again</button>
          <Link className="btn primary" to={`/projects/${p.id}/deploy`}><IconRocket size={16} />Choose Platform</Link>
        </>}
      />
      {(location.state as { justAdded?: boolean } | null)?.justAdded && <Alert tone="success">Project added and analyzed. Review the analysis, then choose a platform.</Alert>}
      {error && <Alert tone="danger">{error}</Alert>}

      <section className="card stack">
        <h2>Project Analysis</h2>
        {!a ? <p className="muted">Not analyzed yet.</p> : (
          <>
            <div className="grid stats">
              <Fact label="Language" value={a.language} />
              <Fact label="Framework" value={a.framework} />
              <Fact label="Application type" value={a.app_type} />
              <Fact label="Files" value={String(a.file_count)} />
            </div>
            <dl className="kv">
              <dt>Build files</dt><dd>{a.build_files.length ? a.build_files.map((f) => <code key={f} style={{ marginRight: 8 }}>{f}</code>) : "None detected"}</dd>
              <dt>Dockerfile</dt><dd>{a.has_dockerfile ? (a.dockerfile_issues.length ? "Found, with issues" : "Found and valid") : "Not present (can be generated for Docker deploys)"}</dd>
              {a.install_command && <><dt>Install</dt><dd className="mono">{a.install_command}</dd></>}
              {a.build_command && <><dt>Build</dt><dd className="mono">{a.build_command}</dd></>}
              {a.output_dir && <><dt>Output directory</dt><dd className="mono">{a.output_dir}</dd></>}
              {a.start_command && <><dt>Start</dt><dd className="mono">{a.start_command}</dd></>}
              {a.python_entry && <><dt>App entry</dt><dd className="mono">{a.python_entry}</dd></>}
            </dl>
            {a.dockerfile_issues.length > 0 && <Alert tone="warning" title="Dockerfile issues"><ul>{a.dockerfile_issues.map((i) => <li key={i}>{i}</li>)}</ul></Alert>}
            {a.notes.length > 0 && <Alert tone="info" title="Notes"><ul>{a.notes.map((n) => <li key={n}>{n}</li>)}</ul></Alert>}
            <div className="row" style={{ alignItems: "flex-end" }}>
              <div className="field" style={{ minWidth: 240 }}>
                <label htmlFor="rootdir">Root directory</label>
                <input id="rootdir" className="input mono" list="subprojects" value={rootDir ?? p.root_dir} onChange={(e) => setRootDir(e.target.value)} placeholder="(repository root)" />
                <datalist id="subprojects">{a.subprojects.map((s) => <option key={s} value={s} />)}</datalist>
                <span className="hint">For monorepos, point to the folder that contains the app.</span>
              </div>
              <button className="btn" onClick={saveRoot} disabled={rootDir === null || busy !== null}>{busy === "root" ? <Spinner /> : "Save and re-analyze"}</button>
            </div>
          </>
        )}
      </section>

      {p.source_type === "upload" && <PublishCard project={p} onPublished={(np) => project.setData(np)} />}

      {p.upload_report && p.upload_report.rejected.length > 0 && (
        <details className="card">
          <summary><b>{p.upload_report.rejected.length} file(s) were excluded during upload</b></summary>
          <ul className="muted" style={{ marginTop: 12 }}>{p.upload_report.rejected.map((r) => <li key={r.path}><code>{r.path}</code>: {r.reason}</li>)}</ul>
        </details>
      )}

      <section className="card">
        <div className="card-head"><h2>Deployments</h2><Link className="btn sm primary" to={`/projects/${p.id}/deploy`}>Deploy</Link></div>
        {p.deployments?.length ? <RecentTable rows={p.deployments} /> : <p className="muted">No deployments yet. Choose a platform to deploy this project.</p>}
      </section>

      <section className="card row" style={{ justifyContent: "space-between" }}>
        <div><b>Delete project</b><div className="subtle">Removes uploaded files and history. Destroy live deployments first.</div></div>
        <button className="btn danger" onClick={remove} disabled={busy !== null}><IconTrash size={16} />Delete project</button>
      </section>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div className="stat"><span className="label">{label}</span><span style={{ fontWeight: 600, fontSize: 17 }}>{value}</span></div>;
}

interface PublishPreview {
  files: { path: string; size: number; generated: boolean }[]; total_bytes: number;
  excluded: { path: string; reason: string }[]; skipped_count: number; suggested_name: string; connected_login: string | null;
}

function PublishCard({ project, onPublished }: { project: Project; onPublished: (p: Project) => void }) {
  const [open, setOpen] = useState(false);
  const preview = useApi<PublishPreview>(open && !project.repository ? `/api/projects/${project.id}/github/preview` : null);
  const [repoName, setRepoName] = useState("");
  const [priv, setPriv] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  if (project.repository) {
    return <Alert tone="success" title="Published to GitHub">This upload is linked to <a href={`https://github.com/${project.repository}`} target="_blank" rel="noreferrer">{project.repository}</a>. All platforms can deploy it.</Alert>;
  }
  const publish = async () => {
    setBusy(true); setError(null);
    try {
      const r = await api<{ html_url: string; project: Project }>(`/api/projects/${project.id}/github/publish`, {
        method: "POST", json: { repo_name: repoName || preview.data?.suggested_name, private: priv },
      });
      setDone(r.html_url); onPublished(r.project);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <section className="card stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div><h2>Publish Project to GitHub</h2><p className="muted">Render, GitHub Pages and Cloudflare Pages deploy from a GitHub repository.</p></div>
        {!open && <button className="btn" onClick={() => setOpen(true)}><IconGit size={16} />Prepare publish</button>}
      </div>
      {open && (preview.loading ? <CardSkeleton /> : preview.error ? <ErrorState message={preview.error} /> : preview.data && (
        <>
          {!preview.data.connected_login && <Alert tone="warning">Connect GitHub first on the <Link to="/github">GitHub page</Link>.</Alert>}
          <div className="grid cols-2">
            <div className="field">
              <label htmlFor="reponame">GitHub Repository Name</label>
              <input id="reponame" className="input mono" value={repoName || preview.data.suggested_name} onChange={(e) => setRepoName(e.target.value)} pattern="[A-Za-z0-9._-]+" />
              <span className="hint">Created under @{preview.data.connected_login ?? "your account"}.</span>
            </div>
            <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="label">Visibility</legend>
              <label className="check"><input type="radio" checked={priv} onChange={() => setPriv(true)} />Private</label>
              <label className="check"><input type="radio" checked={!priv} onChange={() => setPriv(false)} />Public (needed for free GitHub Pages)</label>
            </fieldset>
          </div>
          <details open>
            <summary><b>{preview.data.files.length} files will be uploaded ({formatBytes(preview.data.total_bytes)})</b></summary>
            <ul className="mono" style={{ maxHeight: 220, overflow: "auto", margin: "8px 0 0" }}>
              {preview.data.files.map((f) => <li key={f.path}>{f.path}{f.generated && <span className="badge info" style={{ marginLeft: 8 }}>added</span>}</li>)}
            </ul>
          </details>
          {preview.data.excluded.length > 0 && <p className="subtle">Not uploaded: {preview.data.excluded.map((e) => e.path).join(", ")} (secrets, .env or executables).</p>}
          {error && <Alert tone="danger">{error}</Alert>}
          {done ? <Alert tone="success">Published: <a href={done} target="_blank" rel="noreferrer">{done}</a></Alert> : (
            <button className="btn primary" onClick={publish} disabled={busy || !preview.data.connected_login}>{busy ? <Spinner label="Publishing" /> : "Publish Project to GitHub"}</button>
          )}
        </>
      ))}
    </section>
  );
}
