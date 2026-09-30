import { useEffect, useState, type ComponentType } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth";
import {
  IconBook, IconCloud, IconFolder, IconGit, IconHelp, IconHistory, IconHome, IconLogout, IconMap, IconMenu, IconMoon,
  IconPlus, IconSettings,
} from "./icons";

type Item = { to: string; label: string; icon: ComponentType<{ size?: number }>; end?: boolean };
const GROUPS: { label: string; items: Item[] }[] = [
  { label: "Deploy", items: [
    { to: "/", label: "Dashboard", icon: IconHome, end: true },
    { to: "/projects", label: "Projects", icon: IconFolder, end: true },
    { to: "/projects/new", label: "Add Project", icon: IconPlus },
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

export function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--primary)" />
      <circle cx="9" cy="16" r="3" fill="#fff" /><circle cx="23" cy="9" r="2.5" fill="#fff" /><circle cx="23" cy="23" r="2.5" fill="#f2a93b" />
      <path d="M11.5 15 20.6 10M11.5 17l9.1 5" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function cycleTheme() {
  const root = document.documentElement;
  const next = root.dataset.theme === "dark" ? "light" : root.dataset.theme === "light" ? "" : "dark";
  if (next) root.dataset.theme = next; else delete root.dataset.theme;
  try { next ? localStorage.setItem("cdh_theme", next) : localStorage.removeItem("cdh_theme"); } catch { /* ignore */ }
  return next || "system";
}

export function Layout() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState<string>(() => document.documentElement.dataset.theme || "system");
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
        <Link to="/" className="brand"><Logo />CloudDeploy Hub</Link>
        <button className="btn ghost" onClick={() => setOpen(true)} aria-label="Open navigation" aria-expanded={open}><IconMenu /></button>
      </div>
      {open && <div className="scrim" onClick={() => setOpen(false)} aria-hidden="true" />}
      <aside className={`sidebar ${open ? "open" : ""}`} aria-label="Main navigation">
        <Link to="/" className="brand"><Logo />CloudDeploy Hub</Link>
        {GROUPS.map((g) => (
          <nav key={g.label} className="nav-group" aria-label={g.label}>
            <div className="nav-label">{g.label}</div>
            {g.items.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                <Icon size={18} />{label}
              </NavLink>
            ))}
          </nav>
        ))}
        <div className="sidebar-foot">
          <button className="btn ghost sm" style={{ justifyContent: "flex-start" }} onClick={() => setTheme(cycleTheme())} aria-label={`Theme: ${theme}. Change theme`}>
            <IconMoon size={16} />Theme: {theme}
          </button>
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
      <main className="main" id="main"><Outlet /></main>
    </div>
  );
}
