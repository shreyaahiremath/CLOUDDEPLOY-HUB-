import { useEffect, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { HubOrbit } from "../components/charts";
import { Logo } from "../components/Logo";
import { GoogleMark } from "../components/icons";
import { Alert, Spinner } from "../components/ui";
import { useApi } from "../hooks";

interface AuthConfig { google_configured: boolean; dev_login: boolean; google_redirect_uri: string }

export function Login() {
  const { user } = useAuth();
  const location = useLocation();
  const config = useApi<AuthConfig>("/api/auth/config");
  const { signIn } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>((location.state as { error?: string } | null)?.error ?? null);

  if (user) return <Navigate to={(location.state as { from?: string } | null)?.from ?? "/"} replace />;

  const google = async () => {
    setBusy(true); setError(null);
    try {
      const { authorize_url } = await api<{ authorize_url: string }>("/api/auth/google/start");
      window.location.assign(authorize_url);
    } catch (e) { setError((e as Error).message); setBusy(false); }
  };
  const dev = async () => {
    setBusy(true);
    try { const r = await api<{ token: string }>("/api/auth/dev-login", { method: "POST" }); await signIn(r.token); }
    catch (e) { setError((e as Error).message); setBusy(false); }
  };

  return (
    <div className="login">
      <section className="login-art" aria-hidden="true">
        <div className="brand" style={{ color: "inherit", padding: 0 }}><Logo size={40} />Git2Live</div>
        <div className="stack lg">
          <h1>One project. Five free clouds. Real URLs.</h1>
          <p>Bring your own app from GitHub or your laptop. Git2Live analyzes it, shows which free platforms can actually run it, deploys it through each provider's official API, and checks that the live URL answers.</p>
        </div>
        <HubOrbit />
      </section>
      <section className="login-panel">
        <div className="login-box">
          <h2 style={{ fontSize: 24 }}>Sign in</h2>
          <p className="muted">Your projects, GitHub connection and deployment history are private to your account.</p>
          {error && <Alert tone="danger">{error}</Alert>}
          {config.loading ? <Spinner label="Checking sign-in options" /> : config.error ? (
            <Alert tone="danger" title="Can't reach the API">{config.error}</Alert>
          ) : (
            <>
              <button className="btn lg block google-btn" onClick={google} disabled={busy || !config.data?.google_configured}>
                {busy ? <span className="spinner" aria-hidden="true" /> : <GoogleMark />}Continue with Google
              </button>
              {!config.data?.google_configured && (
                <Alert tone="warning" title="Google sign-in isn't configured yet">
                  Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET on the backend. Authorized redirect URI: <code>{config.data?.google_redirect_uri}</code>
                </Alert>
              )}
              {config.data?.dev_login && (
                <button className="btn block" onClick={dev} disabled={busy}>Continue as local developer</button>
              )}
            </>
          )}
          <p className="subtle">Git2Live never asks for your GitHub or Google password.</p>
        </div>
      </section>
    </div>
  );
}

export function AuthCallback() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const ran = useRef(false);
  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    const params = new URLSearchParams(window.location.hash.slice(1));
    window.history.replaceState(null, "", window.location.pathname); // drop the token from the address bar
    const token = params.get("token");
    if (token) void signIn(token).then(() => navigate("/", { replace: true }));
    else navigate("/login", { replace: true, state: { error: params.get("error") ?? "Sign-in did not complete." } });
  }, [signIn, navigate]);
  return <div style={{ display: "grid", placeItems: "center", height: "100vh" }}><span className="spinner lg" role="status" aria-label="Signing you in" /></div>;
}
