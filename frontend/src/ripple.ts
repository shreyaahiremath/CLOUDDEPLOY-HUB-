// Material ripple: one delegated listener for every pressable surface.
const TARGETS = ".btn, .fab, .nav-link, .tab, .chip, .list-item, .bnav-item .pill, .scheme-dot";

export function installRipple(): void {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  document.addEventListener("pointerdown", (event) => {
    const host = (event.target as Element | null)?.closest<HTMLElement>(TARGETS);
    if (!host || host.matches(":disabled, [aria-disabled='true']")) return;
    const rect = host.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2.2;
    const dot = document.createElement("span");
    dot.className = "ripple";
    dot.style.width = dot.style.height = `${size}px`;
    dot.style.left = `${event.clientX - rect.left - size / 2}px`;
    dot.style.top = `${event.clientY - rect.top - size / 2}px`;
    dot.addEventListener("animationend", () => dot.remove());
    host.appendChild(dot);
  }, { passive: true });
}
