"""Supabase as the durable database, through its HTTPS API (no Postgres password/connection string).

The app keeps working data in a local SQLite file (fast, and what SQLAlchemy talks to). When
SUPABASE_URL + SUPABASE_SECRET_KEY are set:

  * startup:  every table is loaded from Supabase into SQLite (Supabase is the source of truth)
  * commit:   every inserted / changed / deleted row is written back to Supabase (ordered queue)
  * uploads:  project source zips live in a private Supabase Storage bucket

So a Render restart or spin-down loses nothing. Requires a single backend instance (Render free = 1).
"""
from __future__ import annotations

import base64
import json
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import DateTime, LargeBinary, Table, event, inspect
from sqlalchemy.orm import Session

log = logging.getLogger("clouddeploy.supabase")

BUCKET = "project-sources"
# Large blobs go to Storage instead of a table row.
UNSYNCED_TABLES = {"project_sources"}
PAGE = 1000


def _jwt_role(key: str) -> str | None:
    """Role claim of a legacy Supabase JWT key (anon / service_role), without verifying it."""
    parts = key.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("role")
    except (ValueError, json.JSONDecodeError):
        return None


def as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


class SupabaseStore:
    def __init__(self) -> None:
        self.enabled = False   # credentials present
        self.ready = False     # tables reachable; sync active
        self.error: str | None = None
        self.last_sync_error: str | None = None
        self._rest: httpx.Client | None = None
        self._storage: httpx.Client | None = None
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._tables: list[Table] = []

    # ----- setup ---------------------------------------------------------------------------
    def configure(self, url: str, key: str) -> None:
        self.enabled = bool(url and key)
        self.ready = False
        self.error = None
        if not self.enabled:
            return
        if key.startswith("sb_publishable_") or _jwt_role(key) == "anon":
            self.error = ("SUPABASE_SECRET_KEY is a public key (publishable / anon). Use the secret key (sb_secret_... or "
                          "service_role) from Supabase > Project Settings > API Keys. Public keys cannot protect user data.")
            return
        base = url.rstrip("/")
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        self._rest = httpx.Client(base_url=f"{base}/rest/v1", headers=headers, timeout=30)
        self._storage = httpx.Client(base_url=f"{base}/storage/v1", headers=headers, timeout=120)

    def status(self) -> dict:
        if not self.enabled:
            return {"database": "SQLite (local only)", "ok": True, "detail": None}
        if not self.ready:
            return {"database": "Supabase (NOT connected)", "ok": False, "detail": self.error}
        return {"database": "Supabase", "ok": self.last_sync_error is None, "detail": self.last_sync_error}

    # ----- (de)serialisation -----------------------------------------------------------------
    @staticmethod
    def _out(table: Table, row: dict) -> dict:
        out = {}
        for col in table.columns:
            value = row.get(col.name)
            if isinstance(value, datetime):
                value = as_utc(value).isoformat()
            elif isinstance(value, (bytes, bytearray)):
                value = "\\x" + bytes(value).hex()
            out[col.name] = value
        return out

    @staticmethod
    def _in(table: Table, row: dict) -> dict:
        out = {}
        for col in table.columns:
            value = row.get(col.name)
            if value is not None and isinstance(col.type, DateTime):
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            elif value is not None and isinstance(col.type, LargeBinary):
                value = bytes.fromhex(value[2:]) if isinstance(value, str) and value.startswith("\\x") else value
            out[col.name] = value
        return out

    # ----- startup load ------------------------------------------------------------------------
    def bootstrap(self, engine, metadata) -> None:
        """Replace the local SQLite contents with what Supabase holds."""
        if not self.enabled or self.error or self._rest is None:
            if self.error:
                log.error("Supabase disabled: %s", self.error)
            return
        self._tables = [t for t in metadata.sorted_tables if t.name not in UNSYNCED_TABLES]
        try:
            loaded: dict[str, list[dict]] = {t.name: self._fetch_all(t) for t in self._tables}
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300]
            if exc.response.status_code == 404 or "PGRST205" in body:
                self.error = "Tables are missing. Run supabase/schema.sql once in the Supabase SQL Editor, then restart."
            elif exc.response.status_code in (401, 403):
                self.error = "Supabase rejected the key. Check SUPABASE_URL and SUPABASE_SECRET_KEY (secret key, not publishable)."
            else:
                self.error = f"Supabase returned HTTP {exc.response.status_code}: {body}"
            log.error("Supabase not connected: %s", self.error)
            return
        except httpx.HTTPError as exc:
            self.error = f"Could not reach Supabase: {exc.__class__.__name__}"
            log.error("Supabase not connected: %s", self.error)
            return

        with engine.begin() as conn:
            for table in reversed(metadata.sorted_tables):
                conn.execute(table.delete())
            for table in self._tables:
                rows = loaded[table.name]
                if rows:
                    conn.execute(table.insert(), [self._in(table, r) for r in rows])
        self._ensure_bucket()
        self.ready = True
        self._thread = threading.Thread(target=self._worker, name="supabase-sync", daemon=True)
        self._thread.start()
        log.info("Supabase connected: loaded %s rows", sum(len(v) for v in loaded.values()))

    def _fetch_all(self, table: Table) -> list[dict]:
        assert self._rest is not None
        pk = ",".join(c.name for c in table.primary_key.columns)
        rows: list[dict] = []
        offset = 0
        while True:
            resp = self._rest.get(f"/{table.name}", params={"select": "*", "order": pk, "limit": PAGE, "offset": offset})
            resp.raise_for_status()
            batch = resp.json()
            rows.extend(batch)
            if len(batch) < PAGE:
                return rows
            offset += PAGE

    # ----- write-behind queue --------------------------------------------------------------------
    def enqueue(self, ops: list[tuple[str, Table, dict]]) -> None:
        if self.ready and ops:
            self._queue.put(ops)

    def flush(self) -> None:
        """Block until every queued write has been sent (tests, shutdown)."""
        self._queue.join()

    def _worker(self) -> None:
        while True:
            ops = self._queue.get()
            try:
                for kind, table, data in ops:
                    self._send(kind, table, data)
                self.last_sync_error = None
            except Exception as exc:  # noqa: BLE001 - never kill the sync thread
                self.last_sync_error = f"{exc.__class__.__name__}: {str(exc)[:200]}"
                log.error("Supabase sync failed: %s", self.last_sync_error)
            finally:
                self._queue.task_done()

    def _send(self, kind: str, table: Table, data: dict) -> None:
        assert self._rest is not None
        pk_cols = [c.name for c in table.primary_key.columns]
        for attempt in range(4):
            try:
                if kind == "upsert":
                    resp = self._rest.post(
                        f"/{table.name}", params={"on_conflict": ",".join(pk_cols)}, json=[self._out(table, data)],
                        headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
                    )
                else:
                    resp = self._rest.delete(f"/{table.name}", params={k: f"eq.{data[k]}" for k in pk_cols})
                if resp.status_code < 500:
                    resp.raise_for_status()
                    return
                error: Exception = httpx.HTTPStatusError("server error", request=resp.request, response=resp)
            except httpx.TransportError as exc:
                error = exc
            if attempt == 3:
                raise error
            time.sleep(1.5 * (attempt + 1))

    # ----- Storage (uploaded project zips) -------------------------------------------------------
    def _ensure_bucket(self) -> None:
        assert self._storage is not None
        try:
            resp = self._storage.post("/bucket", json={"id": BUCKET, "name": BUCKET, "public": False})
            if resp.status_code not in (200, 201, 400, 409):  # 400/409 = already exists
                log.warning("Could not create storage bucket: HTTP %s %s", resp.status_code, resp.text[:200])
        except httpx.HTTPError as exc:
            log.warning("Could not create storage bucket: %s", exc)

    def put_source(self, project_id: int, archive: bytes) -> None:
        if not self.ready or self._storage is None:
            return
        resp = self._storage.post(
            f"/object/{BUCKET}/{project_id}.zip", content=archive,
            headers={"Content-Type": "application/zip", "x-upsert": "true"},
        )
        resp.raise_for_status()

    def get_source(self, project_id: int) -> bytes | None:
        if not self.ready or self._storage is None:
            return None
        resp = self._storage.get(f"/object/{BUCKET}/{project_id}.zip")
        if resp.status_code in (400, 404):
            return None
        resp.raise_for_status()
        return resp.content

    def delete_source(self, project_id: int) -> None:
        if not self.ready or self._storage is None:
            return
        try:
            self._storage.request("DELETE", f"/object/{BUCKET}", json={"prefixes": [f"{project_id}.zip"]})
        except httpx.HTTPError as exc:
            log.warning("Could not delete stored source for project %s: %s", project_id, exc)


store = SupabaseStore()


def _row(obj: Any) -> tuple[Table, dict]:
    mapper = inspect(obj).mapper
    table = mapper.local_table
    return table, {col.name: getattr(obj, mapper.get_property_by_column(col).key) for col in table.columns}


def install(session_factory, metadata) -> None:
    """Mirror every committed ORM change to Supabase."""
    order = {t.name: i for i, t in enumerate(metadata.sorted_tables)}

    @event.listens_for(session_factory, "after_flush")
    def _collect(session: Session, _ctx) -> None:
        if not store.ready:
            return
        upserts = [_row(o) for o in list(session.new) + list(session.dirty)]
        deletes = [_row(o) for o in session.deleted]
        ops = [("upsert", t, d) for t, d in sorted(upserts, key=lambda x: order[x[0].name]) if t.name not in UNSYNCED_TABLES]
        ops += [("delete", t, d) for t, d in sorted(deletes, key=lambda x: -order[x[0].name]) if t.name not in UNSYNCED_TABLES]
        session.info.setdefault("supabase_ops", []).extend(ops)

    @event.listens_for(session_factory, "after_commit")
    def _push(session: Session) -> None:
        store.enqueue(session.info.pop("supabase_ops", []))

    @event.listens_for(session_factory, "after_rollback")
    def _discard(session: Session) -> None:
        session.info.pop("supabase_ops", None)
