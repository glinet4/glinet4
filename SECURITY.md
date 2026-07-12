# Security Policy

## Supported versions

`glinet4` is pre-1.0; only the latest `0.x` release on PyPI is supported.

## Reporting a vulnerability

Report security issues privately via
[GitHub Security Advisories](https://github.com/glinet4/glinet4/security/advisories/new),
not a public issue.

## Scope note

`glinet4` typically talks to GL.iNet routers over plain HTTP on the LAN. If
your setup exposes the API over HTTPS with a self-signed certificate, see the
transport's `ssl` parameter. Over plain HTTP, the `sid` session token
`login()` returns is LAN-visible to anything that can observe traffic to the
router; treat it as a LAN-local secret, not a durable credential.
