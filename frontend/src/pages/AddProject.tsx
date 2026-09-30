import { useRef, useState, type DragEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api, type GitHubStatus, type Project } from "../api";
import { IconGit, IconUpload } from "../components/icons";
import { Alert, PageHead, Spinner } from "../components/ui";
import { formatBytes, useApi } from "../hooks";
import { RepoPicker } from "./GitHub";

type Picked = { file: File; path: string };

// Folder drag & drop: walk FileSystemEntry trees so nested files keep their relative paths.
async function readEntry(entry: FileSystemEntry, prefix = ""): Promise<Picked[]> {
  if (entry.isFile) {
    const file = await new Promise<File>((res, rej) => (entry as FileSystemFileEntry).file(res, rej));
    return [{ file, path: prefix + entry.name }];
  }
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  const all: FileSystemEntry[] = [];
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((res, rej) => reader.readEntries(res, rej));
    if (!batch.length) break;
    all.push(...batch);
  }
  const nested = await Promise.all(
    all.filter((e) => !["node_modules", ".git", "__pycache__", ".venv", "venv"].includes(e.name))
      .map((e) => readEntry(e, `${prefix}${entry.name}/`)),
  );
  return nested.flat();
}

export function AddProject() {
  const navigate = useNavigate();
  const gh = useApi<GitHubStatus>("/api/github/status");
  const [tab, setTab] = useState<"upload" | "github">("upload");
  const [files, setFiles] = useState<Picked[]>([]);
  const [name, setName] = useState("");
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; rejected?: { path: string; reason: string }[] } | null>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const zipInput = useRef<HTMLInputElement>(null);

  const accept = (picked: Picked[]) => {
    const kept = picked.filter((p) => !/(^|\/)(node_modules|\.git|__pycache__|\.venv|venv)\//.test(p.path));
    setFiles(kept);
    setError(null);
    const top = kept[0]?.path.includes("/") ? kept[0].path.split("/")[0] : kept[0]?.file.name.replace(/\.zip$/i, "");
    if (!name && top) setName(top);
  };

  const onDrop = async (e: DragEvent) => {
    e.preventDefault(); setOver(false);
    const entries = Array.from(e.dataTransfer.items).map((i) => i.webkitGetAsEntry()).filter(Boolean) as FileSystemEntry[];
    accept((await Promise.all(entries.map((en) => readEntry(en)))).flat());
  };

  const upload = async () => {
    setBusy(true); setError(null);
    const form = new FormData();
    form.append("name", name.trim());
    for (const f of files) { form.append("files", f.file, f.file.name); form.append("paths", f.path); }
    try {
      const project = await api<Project>("/api/projects/upload", { method: "POST", body: form });
      navigate(`/projects/${project.id}`, { state: { justAdded: true } });
    } catch (e) {
      const data = (e as ApiError).data as { detail?: { report?: { rejected: { path: string; reason: string }[] } } } | undefined;
      setError({ message: (e as Error).message, rejected: data?.detail?.report?.rejected });
      setBusy(false);
    }
  };

  const total = files.reduce((n, f) => n + f.file.size, 0);

  return (
    <div className="page">
      <PageHead title="Add Project" sub="Bring your own application. It is never mixed with sample code or CloudDeploy Hub itself." />
      <div className="tabs" role="tablist">
        <button className="tab" role="tab" aria-selected={tab === "upload"} onClick={() => setTab("upload")}>Upload Project Folder</button>
        <button className="tab" role="tab" aria-selected={tab === "github"} onClick={() => setTab("github")}>Connect GitHub Repository</button>
      </div>

      {tab === "upload" ? (
        <div className="stack lg">
          <div
            className={`dropzone ${over ? "over" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={onDrop}
          >
            <div className="empty-icon"><IconUpload /></div>
            <h3>Drag &amp; drop your project folder</h3>
            <p className="muted">or pick it from your computer. <code>.env</code> files, keys, secrets and executables are removed before anything is stored.</p>
            <div className="row" style={{ justifyContent: "center" }}>
              <button className="btn primary" onClick={() => folderInput.current?.click()}>Browse folder</button>
              <button className="btn" onClick={() => zipInput.current?.click()}>Upload .zip</button>
            </div>
            <input ref={folderInput} type="file" hidden multiple
              {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
              onChange={(e) => accept(Array.from(e.target.files ?? []).map((f) => ({ file: f, path: f.webkitRelativePath || f.name })))} />
            <input ref={zipInput} type="file" hidden accept=".zip,application/zip"
              onChange={(e) => accept(Array.from(e.target.files ?? []).map((f) => ({ file: f, path: f.name })))} />
          </div>

          {files.length > 0 && (
            <div className="card stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <b>{files.length} file{files.length === 1 ? "" : "s"} selected · {formatBytes(total)}</b>
                <button className="btn sm ghost" onClick={() => setFiles([])}>Clear</button>
              </div>
              <div className="field">
                <label htmlFor="pname">Project name</label>
                <input id="pname" className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="weather-api" />
              </div>
              <button className="btn primary" onClick={upload} disabled={busy || !name.trim()}>
                {busy ? <Spinner label="Validating and analyzing" /> : "Upload and analyze"}
              </button>
            </div>
          )}
          {error && (
            <Alert tone="danger" title="Upload rejected">
              {error.message}
              {error.rejected && error.rejected.length > 0 && (
                <ul>{error.rejected.slice(0, 8).map((r) => <li key={r.path}><code>{r.path}</code>: {r.reason}</li>)}</ul>
              )}
            </Alert>
          )}
        </div>
      ) : gh.loading ? <Spinner label="Checking GitHub connection" /> : gh.data?.connected ? (
        <RepoPicker onPicked={(p) => navigate(`/projects/${p.id}`, { state: { justAdded: true } })} />
      ) : (
        <div className="card empty">
          <div className="empty-icon"><IconGit /></div>
          <h3>Connect GitHub first</h3>
          <p>Authorize CloudDeploy Hub with GitHub to list your repositories. Your password is never requested or stored.</p>
          <Link className="btn primary" to="/github">Go to GitHub Integration</Link>
        </div>
      )}
    </div>
  );
}
