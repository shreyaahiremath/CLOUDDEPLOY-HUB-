# FAQs

### What is CloudDeploy Hub?
A web platform that takes your own application (from GitHub or an uploaded folder), analyzes it, and
deploys it to a free cloud platform you choose through that platform's real API. You get back the real
public URL only after it passes a health check.

### What is multi-cloud deployment?
Deploying the same application to more than one cloud provider, or being able to choose between
providers, without rewriting your deployment process for each one. CloudDeploy Hub gives five
providers one workflow: analyze → choose → preview → deploy → verify.

### Which platforms are supported?
Render, Vercel, Netlify, GitHub Pages and Cloudflare Pages. Paid or credit-based platforms (AWS,
Azure, GCP, Oracle Cloud) are intentionally not included in this version.

### Are these platforms free?
Each one currently offers a free option suitable for the deployment types listed on the Providers
page. You need your own account with each provider.

### Are free plans unlimited?
No. Free plans have usage limits, may sleep or spin down when idle, and can change at any time. The
provider's current terms always apply.

### How do I connect GitHub?
Open **GitHub**, enter your username and select **Connect GitHub**. You approve access on github.com
and are sent back to CloudDeploy Hub. Your password is never requested.

### Why is a GitHub username not authentication by itself?
Anyone can type any username. Only GitHub's OAuth flow proves you control the account. The username
field is used to catch mistakes: if you sign in as a different account, you get a warning.

### Can I upload a local project?
Yes. Drag and drop a folder or upload a `.zip`. Files are validated first: `.env` files, keys, detected
secrets and executables are removed, and path-traversal tricks are rejected.

### Can I deploy a FastAPI project?
Yes, on **Render** as a free web service (native Python runtime or Docker). Vercel is offered only as
"needs adaptation" because it runs Python as serverless functions.

### Can I deploy React?
Yes. React (Vite or Create React App) works on Vercel, Netlify, GitHub Pages, Cloudflare Pages and
Render static sites.

### Can I deploy Next.js?
Yes, on Vercel, Netlify and Render (Node web service). With `output: 'export'` it is static and can
also go to GitHub Pages or Cloudflare Pages.

### Can I deploy static HTML?
Yes, on all five platforms.

### Why can't GitHub Pages run my FastAPI backend?
GitHub Pages only serves static files. It has no server process to run Python, so CloudDeploy Hub
marks it as not compatible for backends.

### How does Render deployment work?
CloudDeploy Hub calls the Render API to create a free web service (or static site) from your GitHub
repository. Render builds and runs it, and the `onrender.com` URL comes from Render's response.

### How does Vercel deployment work?
Your source files are uploaded to Vercel's file API and a production deployment is created. Vercel
builds it and CloudDeploy Hub reads the production alias (`*.vercel.app`).

### How does Netlify deployment work?
A zip of your source (plus a generated `netlify.toml` if needed) is sent to Netlify's Build API.
Netlify builds and publishes it at the site's `netlify.app` URL.

### How does Cloudflare Pages deployment work?
CloudDeploy Hub creates a Pages project through the Cloudflare API, adds a GitHub Actions workflow to
your repository, and triggers it. The workflow builds your site and deploys it with Cloudflare's
official `wrangler` CLI to `*.pages.dev`.

### How does GitHub Pages deployment work?
CloudDeploy Hub enables Pages with GitHub Actions as the source, commits a workflow, and triggers it.
The workflow builds the site (with the correct base path) and publishes it with `actions/deploy-pages`.

### What happens if deployment fails?
You see **Deployment Failed** with the provider's actual error, the last log lines, and a suggested fix.
**Try Again** reuses the same provider resource where possible.

### Where are deployment logs obtained from?
From the provider: Render's logs API, Vercel deployment events, the Netlify deploy summary, and GitHub
Actions job logs for GitHub Pages and Cloudflare Pages. CloudDeploy Hub's own orchestration events are
shown in a separate tab and are labelled as such.

### How are credentials protected?
Provider tokens live only in backend environment variables. GitHub tokens and deployment environment
variables are encrypted in the database. Session tokens are stored as hashes. Nothing secret is sent
to the browser.

### Can I destroy a deployment?
Yes. **Destroy Deployment** deletes the provider resource (Render service, Vercel project, Netlify
site, Cloudflare Pages project, or unpublishes GitHub Pages).

### Can I add another provider later?
Yes. Implement the `DeploymentProvider` interface for the new platform, add its capability rules, and
verify it with a real end-to-end deployment. See the Provider Guide.
