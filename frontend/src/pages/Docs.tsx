import { NavLink, useParams } from "react-router-dom";
import { Markdown } from "../components/Markdown";
import { CardSkeleton, ErrorState, PageHead } from "../components/ui";
import { useApi } from "../hooks";

const DOCS: [string, string][] = [
  ["readme", "Overview"],
  ["deployment-guide", "Deployment guide"],
  ["github-integration", "GitHub integration"],
  ["provider-guide", "Provider guide"],
  ["architecture", "Architecture"],
  ["troubleshooting", "Troubleshooting"],
  ["project-report-content", "Project report"],
  ["faqs", "FAQs"],
];

export function DocPage({ fixed }: { fixed?: string }) {
  const params = useParams();
  const name = fixed ?? params.name ?? "readme";
  const { data, error, loading, reload } = useApi<{ markdown: string }>(`/api/docs/${name}`);
  const title = DOCS.find(([k]) => k === name)?.[1] ?? "Documentation";

  return (
    <div className="page">
      <PageHead title={fixed === "faqs" ? "FAQs" : "Documentation"} sub={fixed ? undefined : title} />
      {!fixed && (
        <nav className="row" aria-label="Documents">
          {DOCS.map(([k, label]) => (
            <NavLink key={k} to={`/docs/${k}`} className={() => `btn sm ${k === name ? "primary" : ""}`}>{label}</NavLink>
          ))}
        </nav>
      )}
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data ? <CardSkeleton rows={8} /> : data && <section className="card"><Markdown source={data.markdown} /></section>}
    </div>
  );
}
