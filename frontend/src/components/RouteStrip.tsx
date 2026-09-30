// Signature element: the deployment's route from source to live URL, lit by real status only.
import type { Deployment, Status } from "../api";
import { IconCheck, IconX } from "./icons";

const STOPS = ["Source", "Validate", "Build", "Deploy", "Health", "Live"] as const;
const INDEX: Partial<Record<Status, number>> = {
  QUEUED: 1, VALIDATING: 1, BUILDING: 2, DEPLOYING: 3, HEALTH_CHECKING: 4, SUCCESS: 5,
};

function failedAt(d: Deployment): number {
  if (d.health_status === "unreachable") return 4;
  if (!d.provider_resource_id && !d.deployment_id) return 1;
  const raw = (d.provider_status ?? "").toLowerCase();
  if (raw.includes("build")) return 2;
  return raw ? 3 : 2;
}

export function RouteStrip({ d }: { d: Deployment }) {
  const failed = d.status === "FAILED";
  const destroyed = d.status === "DESTROYED" || d.status === "DESTROYING";
  const current = failed ? failedAt(d) : destroyed ? -1 : INDEX[d.status] ?? 0;

  return (
    <ol className="route" aria-label="Deployment progress">
      {STOPS.map((label, i) => {
        let state = "";
        if (destroyed) state = "";
        else if (failed && i === current) state = "failed";
        else if (i < current || (i === 0)) state = "done";
        else if (i === current) state = d.status === "SUCCESS" ? "live" : "active";
        if (d.status === "SUCCESS" && i < 5) state = "done";
        const text = state === "failed" ? `${label}: failed` : state === "active" ? `${label}: in progress` : state ? `${label}: complete` : `${label}: pending`;
        return (
          <li key={label} className={`route-stop ${state}`} aria-label={text} aria-current={state === "active" ? "step" : undefined}>
            <span className="route-node">
              {state === "failed" ? <IconX size={14} /> : state === "done" || state === "live" ? <IconCheck size={14} /> : <small>{i + 1}</small>}
            </span>
            <span>{label}</span>
          </li>
        );
      })}
    </ol>
  );
}
