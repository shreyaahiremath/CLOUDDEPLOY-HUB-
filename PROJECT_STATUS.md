# Project Status

STATUS: CloudDeploy Hub 1.0.0 | DONE: backend, frontend, 5 provider integrations, Google + GitHub OAuth, Supabase support, tests, docs, deploy configs | IN PROGRESS: none | BLOCKED: real provider acceptance runs need provider accounts/tokens | NEXT: deploy the hub (Supabase → Render → Vercel), then run scripts/acceptance_test.py per provider and record the results in docs/project-report-content.md §22–23

| Provider | Code | Contract tests | Real end-to-end verified |
|---|---|---|---|
| Render | ✓ | ✓ | Not yet (needs RENDER_API_KEY) |
| Vercel | ✓ | ✓ | Not yet (needs VERCEL_TOKEN) |
| Netlify | ✓ | ✓ | Not yet (needs NETLIFY_AUTH_TOKEN) |
| GitHub Pages | ✓ | ✓ | Not yet (needs GitHub OAuth app) |
| Cloudflare Pages | ✓ | ✓ | Not yet (needs Cloudflare token + account) |
