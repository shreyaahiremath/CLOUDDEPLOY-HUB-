"""Provider capability catalog + compatibility engine.

Everything here describes what each provider's *free* offering can run. It deliberately avoids
promising limits: free plans are provider-controlled and can change.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

FREE_PLAN_NOTICE = "Free plan available subject to the provider's current limits and terms."
FREE_PLAN_CHANGE_NOTICE = (
    "Free-plan availability and limits are controlled by the selected provider and may change."
)


@dataclass(frozen=True)
class ProviderCapability:
    key: str
    name: str
    plan: str
    deployment_types: tuple[str, ...]
    best_for: tuple[str, ...]
    limitations: tuple[str, ...]
    url_pattern: str
    requires_github_repo: bool
    env_vars: tuple[str, ...]
    docs_url: str
    pricing_url: str
    build_strategy: str

    def to_dict(self) -> dict:
        return {**asdict(self), "free_plan_notice": FREE_PLAN_NOTICE}


CATALOG: dict[str, ProviderCapability] = {
    "render": ProviderCapability(
        key="render",
        name="Render",
        plan="Free",
        deployment_types=("Web Service", "Static Site"),
        best_for=("FastAPI / Flask / Django", "Node.js / Express", "Docker", "Static sites"),
        limitations=(
            "Free web services spin down when idle; the first request after idle is slow.",
            "Monthly free usage is capped by Render. See Render's pricing page for current numbers.",
            "Background workers and some features are not available on the free plan.",
        ),
        url_pattern="https://<service>.onrender.com",
        requires_github_repo=True,
        env_vars=("RENDER_API_KEY",),
        docs_url="https://render.com/docs/free",
        pricing_url="https://render.com/pricing",
        build_strategy="Render pulls the GitHub repository and builds it with a native runtime or your Dockerfile.",
    ),
    "vercel": ProviderCapability(
        key="vercel",
        name="Vercel",
        plan="Hobby (free)",
        deployment_types=("Frontend", "Next.js", "Serverless Functions"),
        best_for=("Next.js", "React / Vite", "Static sites", "Serverless functions"),
        limitations=(
            "Hobby plan is for personal, non-commercial use under Vercel's terms.",
            "Backends run as serverless functions with execution time limits, not as persistent servers.",
            "Usage limits are set by Vercel and may change.",
        ),
        url_pattern="https://<project>.vercel.app",
        requires_github_repo=False,
        env_vars=("VERCEL_TOKEN",),
        docs_url="https://vercel.com/docs/plans/hobby",
        pricing_url="https://vercel.com/pricing",
        build_strategy="CloudDeploy Hub uploads the source files to Vercel through its API and Vercel builds them.",
    ),
    "netlify": ProviderCapability(
        key="netlify",
        name="Netlify",
        plan="Free",
        deployment_types=("Static", "Frontend", "Functions"),
        best_for=("React / Vite", "Static sites", "Next.js", "Netlify Functions"),
        limitations=(
            "The free plan has monthly credit/usage limits set by Netlify.",
            "No persistent backend servers; server code must be Netlify Functions.",
        ),
        url_pattern="https://<site>.netlify.app",
        requires_github_repo=False,
        env_vars=("NETLIFY_AUTH_TOKEN",),
        docs_url="https://docs.netlify.com/api-and-cli-guides/api-guides/get-started-with-api/",
        pricing_url="https://www.netlify.com/pricing/",
        build_strategy="CloudDeploy Hub uploads a source zip to Netlify's Build API and Netlify builds it.",
    ),
    "github_pages": ProviderCapability(
        key="github_pages",
        name="GitHub Pages",
        plan="Free (public repositories)",
        deployment_types=("Static websites",),
        best_for=("HTML / CSS / JS", "React / Vite static builds", "Documentation sites"),
        limitations=(
            "Static files only. No server-side code.",
            "On GitHub Free, Pages is available for public repositories only.",
            "GitHub applies size and bandwidth soft limits.",
        ),
        url_pattern="https://<user>.github.io/<repository>/",
        requires_github_repo=True,
        env_vars=(),
        docs_url="https://docs.github.com/en/pages",
        pricing_url="https://github.com/pricing",
        build_strategy="CloudDeploy Hub adds a GitHub Actions workflow that builds the site and publishes it to Pages.",
    ),
    "cloudflare_pages": ProviderCapability(
        key="cloudflare_pages",
        name="Cloudflare Pages",
        plan="Free",
        deployment_types=("Static", "Frontend", "Pages Functions"),
        best_for=("React / Vite", "Static sites", "Edge functions (functions/ folder)"),
        limitations=(
            "Build and request limits on the free plan are set by Cloudflare.",
            "No long-running backend servers.",
        ),
        url_pattern="https://<project>.pages.dev",
        requires_github_repo=True,
        env_vars=("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"),
        docs_url="https://developers.cloudflare.com/pages/",
        pricing_url="https://www.cloudflare.com/plans/developer-platform/",
        build_strategy="A GitHub Actions workflow builds the site and deploys it with Cloudflare's official wrangler CLI.",
    ),
}

PROVIDER_ORDER = ["render", "vercel", "netlify", "github_pages", "cloudflare_pages"]

COMPATIBLE, CONDITIONAL, INCOMPATIBLE = "compatible", "conditional", "incompatible"


def _category(analysis: dict) -> str:
    app_type = analysis.get("app_type")
    key = analysis.get("framework_key")
    if app_type == "Static Frontend":
        return "static"
    if app_type == "Frontend":
        return "spa"
    if app_type == "Serverless":
        return "serverless"
    if app_type == "Full Stack" and key in ("nextjs", "nuxt", "sveltekit"):
        return "ssr"
    if app_type in ("Backend API", "Full Stack"):
        if key in ("fastapi", "flask", "django"):
            return "backend_python"
        if key in ("express", "fastify", "koa", "hono", "nestjs", "node"):
            return "backend_node"
        return "backend_other"
    if app_type == "Worker":
        return "worker"
    return "unknown"


def evaluate(analysis: dict | None, provider: str) -> dict:
    """Return {status, reasons[]} for one provider."""
    if not analysis:
        return {"status": INCOMPATIBLE, "reasons": ["Analyze the project first."]}
    cat = _category(analysis)
    key = analysis.get("framework_key")
    docker = analysis.get("has_dockerfile")
    fw = analysis.get("framework", "This project")

    def ok(*r: str) -> dict:
        return {"status": COMPATIBLE, "reasons": list(r)}

    def maybe(*r: str) -> dict:
        return {"status": CONDITIONAL, "reasons": list(r)}

    def no(*r: str) -> dict:
        return {"status": INCOMPATIBLE, "reasons": list(r)}

    if provider == "render":
        if cat in ("static", "spa"):
            return ok("Deploys as a free Render Static Site.")
        if cat == "ssr":
            return ok(f"{fw} runs as a Node web service (free instance type).")
        if cat in ("backend_python", "backend_node"):
            return ok(f"{fw} runs as a free Render Web Service" + (" using your Dockerfile." if docker else " with a native runtime."))
        if cat == "backend_other":
            if docker or key in ("go", "ruby", "rust"):
                return ok(f"{fw} runs as a free Render Web Service.")
            return no(f"{fw} needs a Dockerfile to run on Render.")
        if cat == "serverless":
            return maybe("Render has no serverless functions. Only the static part would be deployed.")
        if cat == "worker":
            return no("Background workers are not available on Render's free plan.")
        if docker:
            return ok("Deploys your Dockerfile as a free Render Web Service.")
        return no("Could not determine how to run this project.")

    if provider == "vercel":
        if cat in ("static", "spa", "ssr", "serverless"):
            return ok(f"Vercel builds {fw} natively.")
        if cat == "backend_python":
            return maybe(
                f"Vercel runs {fw} as a Python serverless function, not a long-running server.",
                "Background tasks, WebSockets and local file writes will not work.",
            )
        if cat == "backend_node" and key in ("express", "hono", "fastify", "nestjs"):
            return maybe(f"Vercel runs {fw} as a serverless function. Long-running connections will not work.")
        if cat == "worker":
            return no("Vercel does not run background workers.")
        return no(f"{fw} needs a persistent server, which Vercel does not provide.")

    if provider == "netlify":
        if cat in ("static", "spa"):
            return ok("Netlify builds and serves the static output.")
        if cat == "ssr":
            if key in ("nextjs", "nuxt"):
                return ok(f"Netlify's {fw} runtime handles server-rendered routes.")
            return maybe(f"{fw} needs a Netlify adapter for server-rendered routes.")
        if cat == "serverless":
            return ok("Static site plus Netlify Functions.")
        return no(f"{fw} needs a persistent server. Netlify serves static sites and functions only.")

    if provider == "github_pages":
        if cat == "static" and key == "nextjs":
            return maybe("Next.js static export under /<repo>/ needs basePath set in next.config.")
        if cat in ("static", "spa"):
            return ok("Builds with GitHub Actions and publishes static files.", "Free for public repositories.")
        return no("GitHub Pages only serves static files. It cannot run a backend or server-rendered app.")

    if provider == "cloudflare_pages":
        if cat in ("static", "spa"):
            return ok("Cloudflare Pages serves the static output from its edge network.")
        if cat == "serverless":
            return maybe("Only Pages Functions in a functions/ folder run on Cloudflare. Other serverless code will not.")
        if cat == "ssr":
            return no(f"{fw} server rendering needs a Cloudflare adapter (e.g. OpenNext), which is not automated here.")
        return no("Cloudflare Pages cannot run long-running backend servers.")

    return no("Unknown provider.")


def evaluate_all(analysis: dict | None, *, has_github_repo: bool) -> list[dict]:
    out = []
    for key in PROVIDER_ORDER:
        cap = CATALOG[key]
        verdict = evaluate(analysis, key)
        verdict["provider"] = key
        verdict["needs_github_publish"] = cap.requires_github_repo and not has_github_repo
        out.append(verdict)
    return out
