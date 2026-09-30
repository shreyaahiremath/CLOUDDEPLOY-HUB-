import type { ReactNode } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Layout } from "./components/Layout";
import { AddProject } from "./pages/AddProject";
import { Architecture } from "./pages/Architecture";
import { AuthCallback, Login } from "./pages/Auth";
import { ChoosePlatform } from "./pages/ChoosePlatform";
import { Dashboard } from "./pages/Dashboard";
import { DeployConfig } from "./pages/DeployConfig";
import { DeploymentDetail } from "./pages/DeploymentDetail";
import { DocPage } from "./pages/Docs";
import { GitHubPage } from "./pages/GitHub";
import { History } from "./pages/History";
import { ProjectDetail } from "./pages/ProjectDetail";
import { Projects } from "./pages/Projects";
import { Providers } from "./pages/Providers";
import { Settings } from "./pages/Settings";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div style={{ display: "grid", placeItems: "center", height: "100vh" }}><span className="spinner lg" role="status" aria-label="Loading your workspace" /></div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

function NotFound() {
  return (
    <div className="page">
      <div className="card empty">
        <h3>Page not found</h3>
        <p>That address doesn't match any page in Git2Live.</p>
        <Link className="btn primary" to="/">Go to Dashboard</Link>
      </div>
    </div>
  );
}

export function App() {
  return (
    <ErrorBoundary>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route element={<RequireAuth><Layout /></RequireAuth>}>
            <Route index element={<Dashboard />} />
            <Route path="projects" element={<Projects />} />
            <Route path="projects/new" element={<AddProject />} />
            <Route path="projects/:id" element={<ProjectDetail />} />
            <Route path="projects/:id/deploy" element={<ChoosePlatform />} />
            <Route path="projects/:id/deploy/:provider" element={<DeployConfig />} />
            <Route path="deployments" element={<History />} />
            <Route path="deployments/:id" element={<DeploymentDetail />} />
            <Route path="github" element={<GitHubPage />} />
            <Route path="providers" element={<Providers />} />
            <Route path="architecture" element={<Architecture />} />
            <Route path="docs" element={<DocPage />} />
            <Route path="docs/:name" element={<DocPage />} />
            <Route path="faqs" element={<DocPage fixed="faqs" />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
    </ErrorBoundary>
  );
}
