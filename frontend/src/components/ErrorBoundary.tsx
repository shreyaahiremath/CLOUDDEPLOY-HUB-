import { Component, type ErrorInfo, type ReactNode } from "react";

/** Catches render crashes so a broken page shows a message instead of a blank screen. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Page crashed:", error, info.componentStack);
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page" role="alert">
        <div className="card empty">
          <h3>This page hit a problem</h3>
          <p>Something on this screen failed to load. Your projects and deployments are safe.</p>
          <code style={{ maxWidth: "100%", overflowWrap: "anywhere" }}>{this.state.error.message}</code>
          <div className="row" style={{ justifyContent: "center" }}>
            <button className="btn primary" onClick={() => window.location.reload()}>Reload page</button>
            <a className="btn" href="/">Go to Dashboard</a>
          </div>
        </div>
      </div>
    );
  }
}
