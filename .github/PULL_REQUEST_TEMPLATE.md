## Summary

<!-- What changed and why (authorized research context) -->

## Component

- [ ] benchmark / APEX engine
- [ ] MCP / CLI
- [ ] tunnel
- [ ] lab-replay
- [ ] docs / hardening
- [ ] CI

## Safety checklist

- [ ] Authorization gates unchanged (or intentionally documented)
- [ ] No secrets or production hostnames committed
- [ ] Lab-only defaults for destructive modes preserved
- [ ] Docs updated if user-facing behavior changed

## Test plan

- [ ] `python3 -m py_compile` on touched modules
- [ ] `./bin/http2-bomb --help` (if CLI touched)
- [ ] Lab command run (paste sanitized output):

```bash
# paste here
```
