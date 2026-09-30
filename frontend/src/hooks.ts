import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

export interface Resource<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
  setData: (d: T) => void;
}

/** Fetch a JSON resource. With `pollMs`, refreshes in the background while `shouldPoll(data)` holds. */
export function useApi<T>(path: string | null, opts: { pollMs?: number; shouldPoll?: (d: T) => boolean } = {}): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(path));
  const shouldPoll = useRef(opts.shouldPoll);
  shouldPoll.current = opts.shouldPoll;

  const reload = useCallback(async () => {
    if (!path) return;
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    setLoading(Boolean(path));
    void reload();
  }, [reload, path]);

  useEffect(() => {
    if (!opts.pollMs || !data) return;
    if (shouldPoll.current && !shouldPoll.current(data)) return;
    const id = window.setTimeout(() => void reload(), opts.pollMs);
    return () => window.clearTimeout(id);
  }, [data, opts.pollMs, reload]);

  return { data, error, loading, reload, setData };
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const secs = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 45) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return days < 30 ? `${days} d ago` : new Date(iso).toLocaleDateString();
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
