import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, type GitHubStatus, type Project, type Repo } from "../api";
import { IconCheck, IconGit, IconLock, IconSearch } from "../components/icons";
import { Alert, CardSkeleton, ErrorState, PageHead, Spinner } from "../components/ui";
import { timeAgo, useApi } from "../hooks";

export function GitHubPage() {
  const [params, setParams] = useSearchParams();
  const status = useApi<GitHubStatus>("/api/github/status");
  const [username, setUsername] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "danger" | "success" | "info"; text: string } | null>(null);
  const [browse, setBrowse] = useState(false);

  useEffect(() => {
    if (params.get("connected")) setMessage({ tone: "success", text: "GitHub account verified." });
    if (params.get("error")) setMessage({ tone: "danger", text: params.get("error")! });
    if (params.get("connected") || params.get("error")) setParams({}, { replace: true });
  }, [params, setParams]);
  useEffect(() => { if (status.data?.entered_username && !username) setUsername(status.data.entered_username); }, [status.data, username]);

  const s = status.data;
  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key); setMessage(null);
    try { await fn(); } catch (e) { setMessage({ tone: "danger", text: (e as Error).message }); } finally { setBusy(null); }
  };

  const connect = () => run("connect", async () => {
    if (username.trim()) status.setData(await api<GitHubStatus>("/api/github/username", { method: "POST", json: { username } }));
    const { authorize_url } = await api<{ authorize_url: string }>("/api/github/oauth/start");
    window.location.assign(authorize_url);
  });
  const saveUsername = () => run("username", async () => {
    status.setData(await api<GitHubStatus>("/api/github/username", { method: "POST", json: { username } }));
    setMessage({ tone: "info", text: `@${username.replace(/^@/, "")} saved as your GitHub username. A username alone is not authentication. Connect GitHub to verify it.` });
  });
  const serverToken = () => run("server", async () => { status.setData(await api<GitHubStatus>("/api/github/connect-server-token", { method: "POST" })); });
  const disconnect = () => run("disconnect", async () => { status.setData(await api<GitHubStatus>("/api/github/disconnect", { method: "POST" })); setBrowse(false); });

  return (
    <div className="page">
      <PageHead title="GitHub Integration" sub="Connect GitHub to deploy repositories and publish uploaded projects." />
      {message && <Alert tone={message.tone}>{message.text}</Alert>}
      {status.error && <ErrorState message={status.error} onRetry={status.reload} />}
      {status.loading && !s ? <CardSkeleton /> : s && (
        <div className="grid cols-2">
          <section className="card stack">
            <h2>GitHub Account</h2>
            {s.connected ? (
              <>
                <div className="row">
                  {s.avatar_url && <img className="avatar" src={s.avatar_url} alt="" style={{ width: 40, height: 40 }} />}
                  <div>
                    <div className="row" style={{ color: "var(--success)", fontWeight: 600 }}><IconCheck size={16} />GitHub account verified</div>
                    <div>Username: <b>@{s.verified_login}</b></div>
                  </div>
                </div>
                {s.mismatch && <Alert tone="warning" title="Username mismatch">{s.mismatch_message}</Alert>}
                <dl className="kv">
                  <dt>Status</dt><dd>✓ Connected{s.auth_method === "server_token" ? " (developer token)" : " via OAuth"}</dd>
                  <dt>Permissions</dt><dd className="mono">{s.scopes.join(", ") || "n/a"}</dd>
                  <dt>Connected</dt><dd>{timeAgo(s.connected_at)}</dd>
                </dl>
                <div className="row">
                  <button className="btn primary" onClick={() => setBrowse(true)}>View Repositories</button>
                  <button className="btn danger" onClick={disconnect} disabled={busy === "disconnect"}>{busy === "disconnect" ? <Spinner /> : "Disconnect"}</button>
                </div>
              </>
            ) : (
              <>
                <div className="field">
                  <label htmlFor="ghuser">GitHub Username</label>
                  <div className="input-prefix"><span>@</span>
                    <input id="ghuser" className="input" value={username} onChange={(e) => setUsername(e.target.value.replace(/^@/, ""))} placeholder="shreya-hiremath" autoComplete="username" />
                  </div>
                  <span className="hint">Used to confirm the right account signs in. It is not authentication by itself.</span>
                </div>
                <div className="row">
                  <button className="btn primary" onClick={connect} disabled={!s.oauth_configured || busy !== null}>
                    {busy === "connect" ? <Spinner /> : <IconGit size={16} />}Connect GitHub
                  </button>
                  <button className="btn" onClick={saveUsername} disabled={!username.trim() || busy !== null}>Save username</button>
                </div>
                <dl className="kv"><dt>Status</dt><dd>Not Connected{s.entered_username ? ` · username @${s.entered_username} saved` : ""}</dd></dl>
                {!s.oauth_configured && (
                  <Alert tone="warning" title="GitHub OAuth isn't configured on the backend">
                    Create a GitHub OAuth App and set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET. Callback URL: <code>{s.callback_url}</code>
                  </Alert>
                )}
                {s.server_token_available && <button className="btn sm" onClick={serverToken}>Use developer GITHUB_TOKEN (local only)</button>}
              </>
            )}
          </section>
          <section className="card stack">
            <h2>What Git2Live can do</h2>
            <ul className="muted" style={{ margin: 0, paddingLeft: 20, lineHeight: 1.8 }}>
              <li>List your repositories and branches (including private ones).</li>
              <li>Create a repository and push an uploaded project (you review the file list first).</li>
              <li>Add a deployment workflow for GitHub Pages / Cloudflare Pages when you choose those platforms.</li>
            </ul>
            <Alert tone="info" title="Your credentials stay server-side">
              The OAuth token is encrypted in the database and never sent to your browser. Git2Live never asks for your GitHub password. Disconnecting revokes the token.
            </Alert>
          </section>
        </div>
      )}
      {s?.connected && browse && <RepoPicker />}
    </div>
  );
}

export function RepoPicker({ onPicked }: { onPicked?: (p: Project) => void }) {
  const navigate = useNavigate();
  const repos = useApi<{ total: number; repositories: Repo[] }>("/api/github/repos");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Repo | null>(null);
  const [branches, setBranches] = useState<string[] | null>(null);
  const [branch, setBranch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const list = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (repos.data?.repositories ?? []).filter((r) => !term || r.full_name.toLowerCase().includes(term) || (r.description ?? "").toLowerCase().includes(term));
  }, [repos.data, q]);

  const pick = async (r: Repo) => {
    setSelected(r); setBranches(null); setError(null);
    try {
      const b = await api<{ default_branch: string; branches: string[] }>(`/api/github/repos/${r.owner}/${r.name}/branches`);
      setBranches(b.branches); setBranch(b.default_branch ?? b.branches[0] ?? "");
    } catch (e) { setError((e as Error).message); }
  };
  const use = async () => {
    if (!selected) return;
    setBusy(true); setError(null);
    try {
      const p = await api<Project>("/api/projects/github", { method: "POST", json: { owner: selected.owner, repo: selected.name, branch } });
      if (onPicked) onPicked(p); else navigate(`/projects/${p.id}`, { state: { justAdded: true } });
    } catch (e) { setError((e as Error).message); setBusy(false); }
  };

  return (
    <section className="card stack">
      <div className="card-head" style={{ marginBottom: 0 }}>
        <h2>Your GitHub Repositories</h2>
        {repos.data && <span className="subtle">{repos.data.total} repositories</span>}
      </div>
      <div className="field">
        <label htmlFor="repo-search">Search repositories</label>
        <div className="input-prefix"><span><IconSearch size={16} /></span>
          <input id="repo-search" className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="weather-api" />
        </div>
      </div>
      {repos.error && <ErrorState message={repos.error} onRetry={repos.reload} />}
      {repos.loading ? <CardSkeleton rows={4} /> : (
        <div className="stack" role="radiogroup" aria-label="Repository" style={{ maxHeight: 420, overflowY: "auto", gap: 8 }}>
          {list.length === 0 && <p className="muted">No repositories match "{q}".</p>}
          {list.map((r) => (
            <label key={r.full_name} className={`list-item ${selected?.full_name === r.full_name ? "selected" : ""}`}>
              <input type="radio" name="repo" checked={selected?.full_name === r.full_name} onChange={() => void pick(r)} />
              <div style={{ minWidth: 0, flex: 1 }}>
                <div className="row"><b>{r.name}</b>{r.private && <span className="badge"><IconLock size={12} />Private</span>}{r.archived && <span className="badge">Archived</span>}</div>
                <div className="subtle" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {r.owner}{r.language ? ` · ${r.language}` : ""} · updated {timeAgo(r.updated_at)}{r.description ? ` · ${r.description}` : ""}
                </div>
              </div>
            </label>
          ))}
        </div>
      )}
      {selected && (
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div className="field" style={{ minWidth: 200 }}>
            <label htmlFor="branch">Branch</label>
            {branches ? (
              <select id="branch" className="input" value={branch} onChange={(e) => setBranch(e.target.value)}>
                {branches.map((b) => <option key={b}>{b}</option>)}
              </select>
            ) : <Spinner label="Loading branches" />}
          </div>
          <button className="btn primary" onClick={use} disabled={!branches || busy}>{busy ? <Spinner label="Analyzing" /> : "Use This Repository"}</button>
        </div>
      )}
      {error && <Alert tone="danger">{error}</Alert>}
    </section>
  );
}
