import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { SchemePicker } from "../components/Layout";
import { IconCheck, IconX } from "../components/icons";
import { Alert, CardSkeleton, CopyButton, ErrorState, PageHead } from "../components/ui";
import { useApi } from "../hooks";

interface SettingsData {
  backend_url: string; frontend_url: string; github_oauth_configured: boolean; github_callback_url: string;
  github_server_token: boolean; google_configured: boolean; dev_login: boolean;
  database: { database: string; ok: boolean; detail: string | null };
  env: Record<string, boolean>; limits: { max_upload_mb: number; max_file_mb: number; max_files: number };
}

export function Settings() {
  const { user, signOut } = useAuth();
  const { data, error, loading, reload } = useApi<SettingsData>("/api/settings");
  return (
    <div className="page">
      <PageHead title="Settings" sub="Your account and how this CloudDeploy Hub instance is configured." />
      <section className="card stack">
        <h2>Account</h2>
        <dl className="kv">
          <dt>Name</dt><dd>{user?.name ?? "n/a"}</dd>
          <dt>Email</dt><dd>{user?.email}</dd>
          <dt>Sign-in</dt><dd>Google</dd>
        </dl>
        <div className="row"><button className="btn" onClick={() => void signOut()}>Sign out</button><Link className="btn" to="/github">Manage GitHub connection</Link></div>
      </section>
      <section className="card stack">
        <h2>Appearance</h2>
        <p className="muted">Pick a colour. Every surface, button and chart re-tints from it, the way Material You themes a phone from its wallpaper.</p>
        <SchemePicker />
      </section>
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data ? <CardSkeleton rows={6} /> : data && (
        <>
          <section className="card stack">
            <h2>Server configuration</h2>
            <p className="muted">Secrets live only in the backend environment. This page shows whether each one is set, never its value.</p>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Variable</th><th>Status</th></tr></thead>
                <tbody>{Object.entries(data.env).map(([k, set]) => (
                  <tr key={k}><td className="mono">{k}</td><td>{set ? <span className="badge success"><IconCheck size={12} />Set</span> : <span className="badge"><IconX size={12} />Not set</span>}</td></tr>
                ))}</tbody>
              </table>
            </div>
            <dl className="kv">
              <dt>Database</dt><dd>{data.database.database}{data.database.ok ? "" : " (problem)"}</dd>
              <dt>Backend URL</dt><dd className="mono">{data.backend_url}</dd>
              <dt>Frontend URL</dt><dd className="mono">{data.frontend_url}</dd>
              <dt>GitHub OAuth callback</dt><dd className="row"><span className="mono">{data.github_callback_url}</span><CopyButton text={data.github_callback_url} /></dd>
              <dt>Upload limits</dt><dd>{data.limits.max_upload_mb} MB per project · {data.limits.max_file_mb} MB per file · {data.limits.max_files} files</dd>
            </dl>
            {data.database.detail && <Alert tone="danger" title="Database problem">{data.database.detail}</Alert>}
            {data.dev_login && <Alert tone="warning">DEV_LOGIN is enabled. Turn it off before exposing this backend publicly.</Alert>}
          </section>
        </>
      )}
    </div>
  );
}
