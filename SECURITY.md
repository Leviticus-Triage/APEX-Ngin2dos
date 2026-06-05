# Security Policy

## Authorized use only

APEX Ngin2dos is an **offensive security research tool**. It is designed to demonstrate HTTP/2 HPACK amplification and memory exhaustion against server implementations you are permitted to test.

**Do not** use this software against systems without explicit written authorization.

## Required controls

1. **Scope documentation** — Every attack run must include a ticket, contract reference, or scope description.
2. **Target allowlist** — Copy `allowed_targets.json.example` to `allowed_targets.json` and restrict hosts in production workflows.
3. **Profile limits** — Use `probe` / `safe` profiles first; reserve `apex*` modes for isolated labs.
4. **Monitoring** — Run destructive tests only with server metrics and a rollback plan.

## Reporting vulnerabilities in this tool

If you discover a security issue **in this repository** (not in nginx/httpd/etc.):

1. Do **not** open a public issue for exploit details.
2. Contact the maintainer via GitHub private advisory or the email on the GitHub profile.
3. Include steps to reproduce and impact assessment.

## Reporting upstream HTTP/2 bomb issues

Original disclosure track: [califio/publications](https://github.com/califio/publications/tree/main/MADBugs/http2-bomb).

## Disclaimer

Authors and contributors are not responsible for misuse. Users must comply with applicable laws and contractual obligations.
