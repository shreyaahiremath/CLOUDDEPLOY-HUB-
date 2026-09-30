# GitHub Integration

## Username vs. authentication

The **GitHub Username** field records who you *say* you are. CloudDeploy Hub checks that the user
exists (`GET /users/{username}`), but a username alone grants no access. Anyone can type anyone's
username. Access requires **Connect GitHub** (OAuth).

After OAuth, CloudDeploy Hub compares the entered username with the authenticated login. If they
differ it shows a warning and uses the authenticated account. It never silently associates
repositories with the wrong user.

## OAuth flow

```text
CloudDeploy Hub → Connect GitHub → github.com/login/oauth/authorize (state bound to your session)
→ you approve → /api/github/oauth/callback → code exchanged server-side → token encrypted in DB
→ back to the GitHub page: ✓ GitHub account verified
```

Requested scopes:

| Scope | Why |
|---|---|
| `repo` | List private repositories, create a repository, push an uploaded project, set Actions secrets |
| `workflow` | Commit the GitHub Pages / Cloudflare Pages workflow file |
| `read:user` | Read your login and avatar |

- CloudDeploy Hub never asks for or stores a GitHub password.
- The token is never sent to the browser. **Disconnect** deletes it and revokes the grant on GitHub.
- `state` values are single-use and expire after 15 minutes.

## Repository browser

`GET /user/repos` (paginated, owner + collaborator + org repos) with search, then
`GET /repos/{owner}/{repo}/branches` for the branch picker. Selecting **Use This Repository** reads the
repository tree through the API and runs the Project Analyzer. Nothing is cloned.

## Publishing an uploaded project

1. **Prepare publish** shows every file that will be uploaded. Excluded files (`.env`, keys,
   detected secrets, executables) are listed separately.
2. A `.gitignore` is added if the project has none.
3. **Publish Project to GitHub** creates the repository (`auto_init`) and pushes a single commit with
   the Git Data API (blobs → tree → commit → ref update).

## Changes CloudDeploy Hub may make to your repository

Only when you deploy, and always listed in the Deployment Preview first:

| Platform | Change |
|---|---|
| Render (Docker mode, no Dockerfile) | Commits the generated `Dockerfile` |
| GitHub Pages | Commits `.github/workflows/clouddeploy-pages.yml`; sets Pages source to GitHub Actions |
| Cloudflare Pages | Commits `.github/workflows/clouddeploy-cloudflare.yml`; adds encrypted Actions secrets `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` |
