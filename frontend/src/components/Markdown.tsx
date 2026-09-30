import { marked } from "marked";
import { useMemo } from "react";

// Renders Git2Live's own docs (served by the backend from docs/*.md). Raw HTML in the
// markdown is escaped so the page never executes markup from a document.
const renderer = new marked.Renderer();
renderer.html = ({ text }) => text.replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function Markdown({ source }: { source: string }) {
  const html = useMemo(() => marked.parse(source, { renderer, async: false }) as string, [source]);
  return <article className="md" dangerouslySetInnerHTML={{ __html: html }} />;
}
