# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| **Provider Not Configured** | Token env var missing on the backend | Add it on Render (or `backend/.env`) and restart |
| "Google sign-in isn't configured" | `GOOGLE_CLIENT_ID/SECRET` missing | Create a Google OAuth client; redirect URI `{BACKEND_URL}/api/auth/google/callback` |
| Google says `redirect_uri_mismatch` | `BACKEND_URL` differs from the URI registered in Google | Make them identical, including `https://` and no trailing slash |
| Login loops back to the sign-in page | `FRONTEND_URL` wrong, or `VITE_API_URL` points to the wrong backend | Fix both, then redeploy the frontend |
| Browser console shows a CORS error | Frontend origin not allowed | Set `FRONTEND_URL` exactly; for preview URLs set `CORS_ORIGIN_REGEX` |
| First request is very slow | Render free instance was asleep | Expected on the free plan |
| GitHub "The sign-in link expired" | OAuth `state` older than 15 minutes or reused | Select Connect GitHub again |
| Username mismatch warning | Signed in to GitHub as a different account | Disconnect, sign out of github.com, connect again |
| Render: "could not access the repository" | Private repo without Render's GitHub connection | Connect GitHub inside Render and grant repo access, or make it public |
| Render deploy `build_failed` | Build command failed | Open **View Logs**; check `requirements.txt` / `package.json` |
| "Deployment exists but application is unreachable" | App crashed or doesn't listen on `$PORT` | Start command must bind `0.0.0.0:$PORT`; add a `/` or `/health` route |
| Vercel URL returns 401 | Vercel Deployment Protection | Project Settings → Deployment Protection → disable for production |
| Vercel "framework" error | Detected framework differs | Set build command / output directory in the configuration |
| Netlify build error | Build command or publish dir wrong | Check the generated `netlify.toml` in the preview; override settings |
| GitHub Pages: "private repository" | Pages on GitHub Free needs a public repo | Make the repo public, or choose Vercel/Netlify |
| GitHub Pages: blank page, 404 assets | Wrong base path | Vite/CRA are handled automatically; other tools need a `/<repo>/` base |
| Cloudflare: 403 from API | Token lacks Pages permission / wrong account ID | Create a token with *Cloudflare Pages: Edit* |
| Actions run not found | Workflow registered slowly after commit | Select Try Again; CloudDeploy Hub retries dispatch automatically |
| "The uploaded files are no longer available" | Project uploaded before DB-backed sources existed | Upload the project again |
| Upload rejected: "Possible GitHub token on line N" | A secret is committed in your code | Remove it, use an environment variable, and rotate the secret |
