# Support

LACP is an experimental local control plane. Maintainers do not promise SLA,
paid support, or compatibility with every host version.

| Need | Where |
| --- | --- |
| Bug or feature | GitHub issues |
| Security | [SECURITY.md](SECURITY.md) — private advisory or `nyk@builderz.dev` |
| Usage questions | Issue with `bin/lacp doctor --json` attached (redact paths/secrets) |
| Production agent crons (Hermes, posting, cookies) | Out of scope. Do not wrap those binaries with `lacp adopt-local`. |

What this project does not do: managed cloud runtime, chat UI, or a substitute
for a coding-agent host's own sandbox.
