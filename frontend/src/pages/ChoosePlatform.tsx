import { Link, useParams } from "react-router-dom";
import type { Analysis, Verdict } from "../api";
import { IconCheck, IconInfo, IconX } from "../components/icons";
import { Alert, CardSkeleton, ErrorState, PageHead, ProviderMark } from "../components/ui";
import { useApi } from "../hooks";

const TONE = { compatible: "success", conditional: "warning", incompatible: "danger" } as const;
const LABEL = { compatible: "Compatible", conditional: "Needs adaptation", incompatible: "Not compatible" } as const;

export function ChoosePlatform() {
  const { id } = useParams();
  const { data, error, loading, reload } = useApi<{ analysis: Analysis | null; providers: Verdict[] }>(`/api/projects/${id}/compatibility`);

  return (
    <div className="page">
      <PageHead title="Choose Free Deployment Platform"
        sub={data?.analysis ? `${data.analysis.framework} · ${data.analysis.app_type}. Only platforms that can run this project are selectable.` : undefined}
        actions={<Link className="btn" to={`/projects/${id}`}>Back to analysis</Link>} />
      <Alert tone="info">Free plan available subject to each provider's current limits and terms. Free plans are not unlimited and can change.</Alert>
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data ? <div className="grid cols-3"><CardSkeleton /><CardSkeleton /><CardSkeleton /></div> : (
        <div className="grid cols-3">
          {data?.providers.map((v) => {
            const selectable = v.status !== "incompatible";
            const Icon = v.status === "compatible" ? IconCheck : v.status === "conditional" ? IconInfo : IconX;
            return (
              <article key={v.provider} className={`card provider-card ${selectable ? "" : "incompatible"}`}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <div className="row"><ProviderMark provider={v.provider} /><div><h3>{v.capability.name}</h3><span className="subtle">{v.capability.plan}</span></div></div>
                </div>
                <div className="row">
                  <span className={`badge ${TONE[v.status]}`}><Icon size={12} />{LABEL[v.status]}</span>
                  <span className="badge">FREE</span>
                </div>
                <div className="subtle">{v.capability.deployment_types.join(" · ")}</div>
                <ul className="reasons">{v.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                {v.needs_github_publish && selectable && <p className="subtle">Deploys from GitHub. You'll publish this upload to a repository first.</p>}
                {!v.configured && selectable && <p className="subtle" style={{ color: "var(--warning)" }}>Provider Not Configured: {v.missing_credentials.join(", ")}</p>}
                <div className="spacer" />
                {selectable ? (
                  <Link className={`btn ${v.status === "compatible" ? "primary" : ""}`} to={`/projects/${id}/deploy/${v.provider}`}>Select {v.capability.name}</Link>
                ) : <button className="btn" disabled aria-disabled="true">Not available for this project</button>}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
