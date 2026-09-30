import { useEffect, useState, type ComponentType, type CSSProperties } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth";
import { SCHEMES, applyScheme, currentScheme } from "../theme";
import { DialogHost } from "./Dialog";
import { ErrorBoundary } from "./ErrorBoundary";
import { Logo } from "./Logo";
import {
  IconBook, IconCloud, IconFolder, IconGit, IconHelp, IconHistory, IconHome, IconLogout, IconMap, IconMenu, IconPlus, IconSettings,
} from "./icons";

type Item = { to: string; label: string; icon: ComponentType<{ size?: number }>; end?: boolean };
const GROUPS: { label: string; items: Item[] }[] = [
  { label: "Deploy", items: [
    { to: "/", label: "Dashboard", icon: IconHome, end: true },
    { to: "/projects", label: "Projects", icon: IconFolder, end: true },
    { to: "/deployments", label: "Deployment History", icon: IconHistory },
  ] },
  { label: "Connect", items: [
    { to: "/github", label: "GitHub", icon: IconGit },
    { to: "/providers", label: "Providers", icon: IconCloud },
    { to: "/settings", label: "Settings", icon: IconSettings },
  ] },
  { label: "Learn", items: [
    { to: "/architecture", label: "Architecture", icon: IconMap },
    { to: "/docs", label: "Documentation", icon: IconBook },
    { to: "/faqs", label: "FAQs", icon: IconHelp },
  ] },
];
const BOTTOM: Item[] = [
  { to: "/", label: "Home", icon: IconHome, end: true },
  { to: "/projects", label: "Projects", icon: IconFolder, end: true },
  { to: "/projects/new", label: "Add", icon: IconPlus },
  { to: "/deployments", label: "History", icon: IconHistory },
];

/** Theme colour picker: the whole UI re-tints from the chosen seed (Material You dynamic colour). */
export function SchemePicker() {
  const [active, setActive] = useState(() => currentScheme().key);
  return (
    <div className="scheme-dots" role="radiogroup" aria-label="Theme colour">
      {SCHEMES.map((s) => (
        <button
          key={s.key} type="button" role="radio" aria-checked={active === s.key} aria-label={`${s.name} theme`} title={s.name}
          className="scheme-dot" style={{ "--h": s.hue, "--h3": s.hue3 } as CSSProperties}
          onClick={() => { applyScheme(s); setActive(s.key); }}
        />
      ))}
    </div>
  );
}

export function Layout() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="shell">
      <div className="topbar">
        <Link to="/" className="brand"><Logo size={32} />Git2Live</Link>
        <button className="btn ghost" onClick={() => setOpen(true)} aria-label="Open navigation" aria-expanded={open}><IconMenu /></button>
      </div>
      {open && <div className="scrim" onClick={() => setOpen(false)} aria-hidden="true" />}
      <aside className={`sidebar ${open ? "open" : ""}`} aria-label="Main navigation">
        <Link to="/" className="brand"><Logo />Git2Live</Link>
        <Link to="/projects/new" className="fab"><IconPlus size={22} />Add Project</Link>
        {GROUPS.map((g) => (
          <nav key={g.label} className="nav-group" aria-label={g.label}>
            <div className="nav-label">{g.label}</div>
            {g.items.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                <Icon size={20} />{label}
              </NavLink>
            ))}
          </nav>
        ))}
        <div className="sidebar-foot">
          <div>
            <div className="nav-label">Theme colour</div>
            <SchemePicker />
          </div>
          {user && (
            <div className="user-chip">
              {user.avatar_url ? <img src={user.avatar_url} alt="" referrerPolicy="no-referrer" /> : <span className="avatar" />}
              <span title={user.email}>{user.name || user.email}</span>
              <span className="spacer" />
              <button className="btn ghost sm" onClick={() => void signOut()} aria-label="Sign out"><IconLogout size={16} /></button>
            </div>
          )}
        </div>
      </aside>
      <main className="main" id="main"><ErrorBoundary resetKey={location.pathname}><Outlet /></ErrorBoundary></main>
      <nav className="bottom-nav" aria-label="Quick navigation">
        {BOTTOM.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => `bnav-item ${isActive ? "active" : ""}`}>
            <span className="pill"><Icon size={22} /></span>{label}
          </NavLink>
        ))}
        <button className="bnav-item" onClick={() => setOpen(true)} aria-label="More pages">
          <span className="pill"><IconMenu size={22} /></span>More
        </button>
      </nav>
      <DialogHost />
    </div>
  );
}
