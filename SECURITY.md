# Security Policy

## Supported Scope

This repository is a local control-plane framework. Security issues in scope include:
- command execution routing and guardrail bypasses
- unsafe handling of secrets or credentials
- policy parsing/routing flaws that can downgrade execution safety
- remote runner behavior that can leak data or execute outside intended boundaries

## Reporting a Vulnerability

Please do not open public issues for vulnerabilities.

Report privately via GitHub Security Advisories for this repository:
- Security tab -> Report a vulnerability

Include:
- affected file(s) and commit hash
- reproduction steps
- expected vs actual behavior
- impact assessment

## Secrets and Credentials

- Never commit API keys, tokens, or credentials.
- Use environment variables and local `.env` only.
- `.env` files are local operator state and must stay out of git history.

## Hardening Rules

- Prefer `--dry-run` for new remote setup changes.
- Keep remote execution provider explicit (`daytona` or `e2b`) and auditable.
- Treat untrusted code paths as `local_sandbox` or `remote_sandbox`.
