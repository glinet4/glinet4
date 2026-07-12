# Security Policy

## Supported versions

`glinet4` is pre-1.0; only the latest `0.x` release on PyPI is supported.

## Reporting a vulnerability

Report security issues privately via
[GitHub Security Advisories](https://github.com/glinet4/glinet4/security/advisories/new),
not a public issue.

## Scope note

By design, `glinet4` talks to GL.iNet routers over plain HTTP on the LAN — the
router's JSON-RPC API has no TLS option. The `sid` session token `login()`
returns is therefore LAN-visible to anything that can observe traffic to the
router; treat it as a LAN-local secret, not a durable credential.
