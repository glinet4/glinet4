# Contributing

## Dev setup

1. Clone the repo.
2. Ensure you have Python 3.11 or greater (`python3 -V`) and install [uv](https://docs.astral.sh/uv/).
3. `uv sync` — creates the in-project `.venv` and installs the runtime + dev dependencies.
4. `uvx prek install` — installs the git pre-commit hooks defined in
   `.pre-commit-config.yaml` ([prek](https://github.com/j178/prek) is a drop-in
   replacement for the `pre-commit` tool). Run them on demand with
   `uvx prek run --all-files`.

## Running the tests

Most of the suite (`tests/test_enums.py`, `tests/test_error_handling.py`,
`tests/test_exports.py`, `tests/test_glinet_unit.py`, `tests/test_rpc_surface.py`,
`tests/test_transport.py`) is unit-level and needs no hardware. `uv run pytest -q`
runs it.

`tests/test_glinet.py` is different: it is a **live** suite that talks to a real
GL.iNet router over its JSON-RPC API. Copy `.env.example` to `.env` and set at
least `GLINET_PASSWORD` (and `GLINET_HOST` if your router isn't at
`192.168.8.1`); `.env` is git-ignored. Without `GLINET_PASSWORD` the whole live
module is skipped automatically — you don't need a router to contribute.

```bash
cp .env.example .env
$EDITOR .env               # set GLINET_PASSWORD, GLINET_HOST if needed
uv run pytest -q           # unit suite + live suite (if configured)
uv run pytest -s           # -s to see the raw router responses
```

A subset of the live suite is **disruptive** (reboot, VPN/WireGuard/Tailscale
toggles). It is skipped unless `GLINET_RUN_DISRUPTIVE` is truthy (`1`/`true`/`yes`).
Only set it against **hardware you own** — never against a router other people
or services currently depend on:

```bash
GLINET_RUN_DISRUPTIVE=1 uv run pytest -q tests/test_glinet.py
```

CI runs the unit suite only (it has no router to talk to) with a coverage gate:
`uv run pytest -v --cov=glinet4 --cov-fail-under=85` (see `.github/workflows/ci.yml`).

## Lint, types, formatting

`uvx prek run --all-files` runs ruff format, ruff check, mypy (strict, `glinet4/`
only — the test suite is exercised by pytest instead, not type-checked), pylint,
plus file-hygiene and GitHub Actions linters (`actionlint`, `zizmor`,
`check-github-workflows`). CI runs the same hooks. To type-check just the
library by hand: `uv run mypy glinet4`.

## Commits and PRs

Commit messages and squash-merge PR titles must follow
[Conventional Commits](https://www.conventionalcommits.org/) — `feat:`, `fix:`,
`docs:`, `chore:`, `ci:`, `build:`, `test:`, etc. [release-please](https://github.com/googleapis/release-please)
reads them to compute the next version and generate `CHANGELOG.md`: `feat:` bumps
the minor version, `fix:` bumps the patch version; `docs:`/`chore:`/`ci:`/`build:`/`test:`
do not trigger a release. The project is pre-1.0 (see "Versioning & stability" in
[README.md](README.md#versioning--stability)), so a breaking change can ship in
a `fix:` or `feat:` commit without a major bump — call it out clearly in the
commit body regardless.

Keep PRs small and focused; avoid unrelated formatting churn in a functional
change.

## Submitting a device capture

`glinet4`'s API coverage (see the table in [README.md](README.md#api-coverage))
is expanded from real, sanitised captures of routers' JSON-RPC surfaces, not
guesswork. If you have a GL.iNet router/firmware combination that isn't
represented yet:

1. Run `uvx glinet4-profiler` against your router. It captures the API surface
   read-only, sanitises MACs/IPs/SSIDs/hostnames/secrets locally on your
   machine, and shows you the result before anything leaves it.
2. Use the profiler's **Submit** action (or open one manually) to file the
   capture via [glinet4-registry](https://github.com/glinet4/glinet4-registry)'s
   profile-submission issue flow.
3. Only submit captures from a router you own; never run the profiler, and
   especially never run disruptive tests from this repo, against a router
   other people or services depend on.

## Releases

Releases are cut by [release-please](https://github.com/googleapis/release-please):
every push to `main` refreshes a release PR that accumulates changes; merging it
bumps the version in `pyproject.toml`, updates `CHANGELOG.md`, tags `vX.Y.Z`, and
publishes to PyPI via trusted publishing (OIDC, no stored token — see
`.github/workflows/publish.yml`). You don't need to do any of this by hand; just
follow the commit-message convention above.
