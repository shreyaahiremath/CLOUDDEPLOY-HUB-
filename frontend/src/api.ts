// API client. The session token lives in localStorage and is sent as a Bearer header, because the
// frontend (Vercel) and API (Render) are on different sites and third-party cookies are unreliable.
const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";
const TOKEN_KEY = "cdh_token";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(token: string | null): void {
  try { token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public data?: unknown) { super(message); }
}

type Unauthorized = () => void;
let onUnauthorized: Unauthorized = () => {};
export function setUnauthorizedHandler(fn: Unauthorized) { onUnauthorized = fn; }

function messageFrom(data: unknown, status: number): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => (d as { msg?: string }).msg ?? String(d)).join(" ");
    if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: string }).message);
  }
  if (status === 0) return "Could not reach the CloudDeploy Hub API. Check that the backend is running.";
  return `Request failed (HTTP ${status}).`;
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let resp: Response;
  try {
    resp = await fetch(`${BASE}${path}`, { ...init, headers, body });
  } catch {
    throw new ApiError(0, messageFrom(null, 0));
  }
  if (resp.status === 204) return undefined as T;
  const data = await resp.json().catch(() => null);
  if (!resp.ok) {
    if (resp.status === 401 && token && !path.startsWith("/api/auth/")) {
      setToken(null);
      onUnauthorized();
    }
    throw new ApiError(resp.status, messageFrom(data, resp.status), data);
  }
  return data as T;
}

/* ---------- types ---------- */
export type Status = "QUEUED" | "VALIDATING" | "BUILDING" | "DEPLOYING" | "HEALTH_CHECKING" | "SUCCESS" | "FAILED" | "DESTROYING" | "DESTROYED";
export const ACTIVE: Status[] = ["QUEUED", "VALIDATING", "BUILDING", "DEPLOYING", "HEALTH_CHECKING", "DESTROYING"];

export interface User { id: number; email: string; name: string | null; avatar_url: string | null }

export interface Analysis {
  language: string; languages: string[]; framework: string; framework_key: string; app_type: string;
  build_files: string[]; has_dockerfile: boolean; dockerfile_issues: string[]; package_manager: string | null;
  install_command: string | null; build_command: string | null; output_dir: string | null; start_command: string | null;
  python_entry: string | null; static_export: boolean; needs_build: boolean; subprojects: string[]; notes: string[];
  root_dir: string; file_count: number;
}

export interface Deployment {
  id: number; project_id: number; project_name: string; github_username: string | null; repository: string | null;
  branch: string | null; source_type: string; provider: string; deployment_id: string | null; provider_resource_id: string | null;
  status: Status; provider_status: string | null; public_url: string | null; health_status: "unknown" | "healthy" | "unreachable";
  health_detail: string | null; error_message: string | null; suggested_fix: string | null; config: Record<string, unknown>;
  links: Record<string, string>; run_url: string | null; created_at: string; updated_at: string; finished_at: string | null;
  events?: { ts: string; level: string; message: string; source: string }[];
  provider_name?: string; plan?: string;
}

export interface Project {
  id: number; name: string; source_type: "upload" | "github"; repository: string | null; repo_private: boolean | null;
  branch: string | null; root_dir: string; framework: string | null; app_type: string | null; language: string | null;
  deployment_count: number; live_count: number; latest_deployment: Deployment | null; has_workspace: boolean;
  created_at: string; updated_at: string;
  analysis?: Analysis | null;
  upload_report?: { accepted_count: number; total_bytes: number; skipped_count: number; rejected: { path: string; reason: string; category: string }[] } | null;
  deployments?: Deployment[];
}

export interface Capability {
  key: string; name: string; plan: string; deployment_types: string[]; best_for: string[]; limitations: string[];
  url_pattern: string; requires_github_repo: boolean; env_vars: string[]; docs_url: string; pricing_url: string;
  build_strategy: string; free_plan_notice: string;
}

export interface ProviderInfo extends Capability {
  configured: boolean; missing_credentials: string[]; verified: boolean;
  verification: { deployment_id: number; public_url: string; verified_at: string } | null;
}

export interface Verdict {
  provider: string; status: "compatible" | "conditional" | "incompatible"; reasons: string[];
  needs_github_publish: boolean; capability: Capability; configured: boolean; missing_credentials: string[];
}

export interface GitHubStatus {
  oauth_configured: boolean; server_token_available: boolean; connected: boolean; entered_username: string | null;
  verified_login: string | null; avatar_url: string | null; auth_method: string | null; scopes: string[];
  connected_at: string | null; mismatch: boolean; mismatch_message: string | null; callback_url: string;
}

export interface Repo {
  owner: string; name: string; full_name: string; private: boolean; default_branch: string | null; description: string | null;
  language: string | null; updated_at: string | null; html_url: string; fork: boolean; archived: boolean;
}

export interface DeployConfig {
  branch?: string | null; name?: string | null; build_mode?: "native" | "docker"; install_command?: string | null;
  build_command?: string | null; output_dir?: string | null; start_command?: string | null; health_check_path?: string | null;
  env_vars?: Record<string, string>; acknowledge_conditional?: boolean;
}

export interface Preview {
  application: string; source: string; repository: string | null; branch: string | null; provider: string; provider_name: string;
  environment: string; compatibility: { status: string; reasons: string[] }; configured: boolean; missing_credentials: string[];
  errors: string[]; warnings: string[]; plan: Record<string, unknown>; notice: string; can_deploy: boolean;
}

export interface LogLine { ts: string | null; message: string; source: string; level: string }
