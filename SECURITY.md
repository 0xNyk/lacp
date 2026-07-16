# Security Policy

## Supported scope

Security fixes target the current `main` branch. Published releases may lag `main`; check
the affected commit or tag before reporting. Issues in scope include:

- command execution routing and guardrail bypasses
- unsafe handling of secrets or credentials
- policy parsing/routing flaws that can downgrade execution safety
- remote runner behavior that can leak data or execute outside intended boundaries
- installer, hook, plugin, provenance, or release-path behavior that crosses an intended
  trust boundary

## Report a vulnerability

Please do not open public issues for vulnerabilities.

Use [GitHub's private vulnerability report](https://github.com/0xNyk/lacp/security/advisories/new)
when the repository offers that form. If the form is unavailable, email
`nyk@builderz.dev` with the subject `LACP security report`.

Include:

- affected file(s) and commit hash
- reproduction steps
- expected vs actual behavior
- impact assessment
- whether the report contains secrets or personal data

Do not attach production credentials or data. Use a minimal local reproduction and redact
tokens, paths, hostnames, and user content. The maintainer will coordinate disclosure after
the affected scope and fix are understood; no fixed response-time promise is made.

## Secrets and credentials

- Never commit API keys, tokens, or credentials.
- Use environment variables and local `.env` only.
- `.env` files are local operator state and must stay out of git history.

## Hardening rules

- Prefer `--dry-run` for new remote setup changes.
- Keep remote execution provider explicit (`daytona` or `e2b`) and auditable.
- Treat untrusted code paths as `local_sandbox` or `remote_sandbox`.
