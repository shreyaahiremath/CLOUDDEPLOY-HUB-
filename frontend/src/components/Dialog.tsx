// Material dialog for confirmations (replaces window.confirm). Uses the native <dialog> element
// so focus trapping, Esc to close and the backdrop come from the browser.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { IconAlert } from "./icons";

interface Options { title: string; body?: ReactNode; confirmLabel?: string; cancelLabel?: string; danger?: boolean }
type Pending = Options & { resolve: (ok: boolean) => void };

let open: ((p: Pending) => void) | null = null;

export function confirmDialog(options: Options): Promise<boolean> {
  return new Promise((resolve) => {
    if (open) open({ ...options, resolve });
    else resolve(window.confirm(options.title));
  });
}

export function DialogHost() {
  const [pending, setPending] = useState<Pending | null>(null);
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => { open = setPending; return () => { open = null; }; }, []);
  useEffect(() => { if (pending && ref.current && !ref.current.open) ref.current.showModal(); }, [pending]);

  const finish = (ok: boolean) => {
    pending?.resolve(ok);
    ref.current?.close();
    setPending(null);
  };

  if (!pending) return null;
  return (
    <dialog ref={ref} className="dialog" aria-labelledby="dialog-title" onCancel={(e) => { e.preventDefault(); finish(false); }}
      onClick={(e) => { if (e.target === ref.current) finish(false); }}>
      <div className="dialog-icon" aria-hidden="true"><IconAlert size={22} /></div>
      <h2 id="dialog-title">{pending.title}</h2>
      {pending.body && <div className="muted">{pending.body}</div>}
      <div className="actions">
        <button className="btn ghost" style={{ color: "var(--md-primary)" }} onClick={() => finish(false)} autoFocus>{pending.cancelLabel ?? "Cancel"}</button>
        <button className={`btn ${pending.danger ? "danger filled" : "primary"}`} onClick={() => finish(true)}>{pending.confirmLabel ?? "Confirm"}</button>
      </div>
    </dialog>
  );
}
