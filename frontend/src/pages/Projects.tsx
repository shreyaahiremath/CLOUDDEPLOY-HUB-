import { Link } from "react-router-dom";
import type { Project } from "../api";
import { IconFolder, IconGit, IconPlus, IconUpload } from "../components/icons";
import { CardSkeleton, Empty, ErrorState, PageHead, StatusBadge } from "../components/ui";
import { timeAgo, useApi } from "../hooks";

export function Projects() {
  const { data, error, loading, reload } = useApi<Project[]>("/api/projects");
  return (
    <div className="page">
      <PageHead title="My Projects" sub="Applications you've added from GitHub or uploaded from your computer."
        actions={<Link className="btn primary" to="/projects/new"><IconPlus size={16} />Add Project</Link>} />
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data ? <div className="grid cols-3"><CardSkeleton /><CardSkeleton /><CardSkeleton /></div> :
        data && data.length === 0 ? (
          <Empty icon={<IconFolder />} title="No projects yet" action={<Link className="btn primary" to="/projects/new">Add your first project</Link>}>
            Add a GitHub repository or upload a project folder. CloudDeploy Hub detects the framework and shows which free platforms can run it.
          </Empty>
        ) : (
          <div className="grid cols-3">
            {data?.map((p) => (
              <article key={p.id} className="card stack">
                <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div style={{ minWidth: 0 }}>
                    <h3 style={{ overflowWrap: "anywhere" }}><Link to={`/projects/${p.id}`} style={{ color: "inherit" }}>{p.name}</Link></h3>
                    <div className="subtle">{p.framework ?? "Not analyzed"}{p.app_type ? ` · ${p.app_type}` : ""}</div>
                  </div>
                  {p.latest_deployment && <StatusBadge status={p.latest_deployment.status} />}
                </div>
                <div className="row subtle">
                  {p.repository ? <><IconGit size={14} />GitHub: {p.repository}</> : <><IconUpload size={14} />Local upload</>}
                </div>
                <div className="row subtle">
                  <span>Deployments: <b style={{ color: "var(--text)" }}>{p.deployment_count}</b></span>
                  <span>·</span><span>Updated {timeAgo(p.updated_at)}</span>
                </div>
                <div className="row">
                  <Link className="btn primary sm" to={`/projects/${p.id}/deploy`}>Deploy</Link>
                  <Link className="btn sm" to={`/projects/${p.id}`}>Details</Link>
                </div>
              </article>
            ))}
          </div>
        )}
    </div>
  );
}
