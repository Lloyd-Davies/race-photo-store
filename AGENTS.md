# Collaboration guide

This repo owns the web application, API, database schema, Celery jobs, shared
server code, container images and production Compose definition. The sibling
`race-photo-preprocessor` repo owns the Windows desktop application.

## Start here

- Project decisions and operator documentation live in Notion; read the current task.
- Check `git status` before editing. Preserve existing uncommitted work and
  untracked files; do not reset, clean, stage everything or bundle unrelated work.
- New branches use `codex/`. Use a separate worktree for a clean task when needed;
  remember it does not contain the current uncommitted features.
- Always follow the existing Conventional Commit style: `feat(scope): ...`,
  `fix(scope): ...`, `test(scope): ...` or `chore(scope): ...`. Commit focused changes.
- This is a public repository. Keep deployment domains, personal branding and
  production values in private environment settings/Notion, never committed defaults,
  Compose fallbacks, frontend HTML or test fixtures. Use generic synthetic examples.
- Use `scripts/setup.ps1`, `scripts/check.ps1` and `scripts/local.ps1`.
- The local stack is standalone `compose.local.yml`, on port 18081. Do not start
  the production Compose stack or use production credentials for local tests.
- Preserve public upload compatibility and run the paired smoke test for changes
  to those interfaces.

## Review and release

- Make small PRs against `dev`; link the Notion card and any paired desktop PR.
- Record exact commits, tests and known limitations. Treat `latest`/`dev-latest`
  as mutable, not evidence of the version running live.
- Lloyd performs production Portainer updates using the Notion release checklist; never
  deploy, alter production data or assume schema rollback from an image change.
- Keep all tokens, customer data and Portainer secret values out of commits,
  command output, issue bodies and Notion.
- At task start read the linked Notion card; on completion update acceptance
  criteria, evidence and blockers. If Notion is unavailable, report pending updates.
- Architecture recommendation is to keep two repos pending Lloyd's review.
  Do not move repositories or code as part of the collaboration setup.
