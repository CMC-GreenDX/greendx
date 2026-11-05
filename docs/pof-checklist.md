# Points of Fail (PoF) self-assessment

Part I of the OLP PMNM 2026 rules (50 of 100 points) is scored on this repository before the final, using the "Points of Fail" from Tom Callaway's [How you know your Free or Open Source Software Project is doomed to FAIL](http://spot.livejournal.com/308370.html). A criterion starts at its maximum and loses points for each fail.

This page maps every criterion to the evidence in this repository, gives an honest self-score and links each remaining gap to the issue that closes it. It is updated whenever a gap is closed.

- **Last checked:** 2026-11-04, on `main` at commit `2f4e396`
- **Self-score today:** 35 / 50
- **Target before submission (2026-12-06):** 50 / 50

## Summary

| # | Criterion | Max | Self-score | Status | Open gaps |
|---|---|---|---|---|---|
| 1 | Source control on the Internet | 5 | 5 | Met | — |
| 2 | OSI-approved license | 10 | 5 | Partly met | [#52](https://github.com/CMC-GreenDX/greendx/issues/52) |
| 3 | At least one release | 5 | 0 | Not met | [#54](https://github.com/CMC-GreenDX/greendx/issues/54) |
| 4 | Building from source | 10 | 10 | Met, at risk | [#55](https://github.com/CMC-GreenDX/greendx/issues/55) |
| 5 | Libraries and bundling | 10 | 10 | Met | — |
| 6 | Documentation and communication | 10 | 5 | Partly met | [#53](https://github.com/CMC-GreenDX/greendx/issues/53) |
| | **Total** | **50** | **35** | | |

## 1. Source control on the Internet (5)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| Public source control but no web viewer | −3 | Pass | The repository is browsable on GitHub: <https://github.com/CMC-GreenDX/greendx> |
| Source control exists but is not open to everyone | −3 | Pass | The repository is public; no account is needed to read or clone it |
| Source control exists but is not actually used | −5 | Pass | Every change goes through an issue and a reviewed pull request: [issues](https://github.com/CMC-GreenDX/greendx/issues?q=is%3Aissue), [pull requests](https://github.com/CMC-GreenDX/greendx/pulls?q=is%3Apr), [commit history](https://github.com/CMC-GreenDX/greendx/commits/main), CI on every pull request ([.github/workflows](../.github/workflows)) |

## 2. OSI-approved license (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| The license is not stated in each source file | −5 | **Fail** | No source file has an SPDX header yet. Fixed by [#52](https://github.com/CMC-GreenDX/greendx/issues/52): an `SPDX-License-Identifier: Apache-2.0` header in every source file, a `NOTICE` file and a CI check |
| The code contains incompatible licenses | −5 | Pass | Our code is Apache-2.0. Every third-party component is under an OSI-approved license and recorded in [docs/licenses.md](licenses.md); GPL and AGPL components (ClamAV, Grafana) run only as separate, unmodified containers. Components that moved to non-OSI licenses (Vault, Redpanda, immudb, n8n, MinIO) were rejected, see [ADR-0001](adr/0001-core-technology-choices.md) |
| No statement of the license's intent | −5 | Pass | The [README](../README.md#license) states the license and how third-party licenses are handled |
| No full copy of the license text | −5 | Pass | Full Apache License 2.0 text in [LICENSE](../LICENSE); GitHub detects it as Apache-2.0 |

The project also solves the problem set by the competition (DX-OS Open-Core): a headless core plus capability spaces, described in the [README](../README.md#architecture) and the [project brief](project-brief.md).

## 3. At least one release (5)

The first release must exist before the submission deadline (2026-12-06).

| Fail | Points | Status | Evidence |
|---|---|---|---|
| No release | −5 | **Fail** | No tag or release yet: [Releases](https://github.com/CMC-GreenDX/greendx/releases). Fixed by [#54](https://github.com/CMC-GreenDX/greendx/issues/54) |
| Releases are not versioned | −3 | Planned | Releases follow Semantic Versioning (`v0.1.0`, then up to `v1.0.0`), as set in [CONTRIBUTING.md](../CONTRIBUTING.md#versioning-and-changelog) |
| Releases use non-open formats (zip, rar, …) | −3 | Planned | Each release attaches a `.tar.gz` source archive |

## 4. Building from source (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| No instructions to build from source | −5 | Pass, at risk | [Getting started](../README.md#getting-started) and [docs/demo-script.md](demo-script.md) give the commands, but the README still says the full guide comes later. Completed by [#55](https://github.com/CMC-GreenDX/greendx/issues/55) |
| Configured by editing header files by hand | −5 | Pass | Configuration comes from environment variables in `.env`, created from [.env.example](../.env.example) by `make up`, and from tenant config packs in [tenants/](../tenants) validated by JSON Schemas in [core/schemas/](../core/schemas) |
| Cannot be configured before building | −5 | Pass | `.env` and the config packs are read at start-up; no source edit is needed |
| Built with closed-source or home-made tools | −5 | Pass | Docker Compose, GNU Make, Python, Go and Node.js, all open source; see the [Makefile](../Makefile) and [deploy/compose/](../deploy/compose) |
| Does not work outside the source tree | −5 | Pass | Services run as containers built from the source, started with `make up` from the repository root; the project page and API reference are static and also served from GitHub Pages: <https://cmc-greendx.github.io/greendx/> |

## 5. Libraries and bundling (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| Does not try to use libraries already available | −5 | Pass | Dependencies come from their standard registries (PyPI, Go modules, npm, container registries) at pinned versions: `requirements.txt` per service, [apps/ledger-sealer/go.mod](../apps/ledger-sealer/go.mod), [package-lock.json](../package-lock.json) |
| Ships copies of the projects it depends on | −5 | Pass | No third-party source is committed. Swagger UI is downloaded at build time by the [Pages workflow](../.github/workflows/pages.yml) |
| Bundled code has been modified | −5 | Pass | Nothing is bundled, so nothing is modified. Every library, its version, license and use is listed in [docs/licenses.md](licenses.md) |

## 6. Documentation and communication (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| No bug tracker | −5 | Pass | [GitHub Issues](https://github.com/CMC-GreenDX/greendx/issues) with [bug](../.github/ISSUE_TEMPLATE/bug.md) and [task](../.github/ISSUE_TEMPLATE/task.md) templates |
| No changelog | −5 | **Fail** | [CHANGELOG.md](../CHANGELOG.md) exists but is still empty. Generated from the commit history by [#53](https://github.com/CMC-GreenDX/greendx/issues/53) |
| No README or instructions | −5 | Pass | [README.md](../README.md), [CONTRIBUTING.md](../CONTRIBUTING.md), [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md), [architecture decisions](adr), [API guide](api/README.md), the published [API reference](https://cmc-greendx.github.io/greendx/api/) and the [project page](https://cmc-greendx.github.io/greendx/) |

## How to keep this page true

- When an issue linked above is closed, update its row, the summary table, the self-score and the "Last checked" line in the same pull request.
- Before submission, check every link on this page from a browser that is not logged in to GitHub.
