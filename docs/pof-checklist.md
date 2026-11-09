# Points of Fail (PoF) self-assessment

Part I of the OLP PMNM 2026 rules (50 of 100 points) is scored on this repository before the final, using the "Points of Fail" from Tom Callaway's [How you know your Free or Open Source Software Project is doomed to FAIL](http://spot.livejournal.com/308370.html). A criterion starts at its maximum and loses points for each fail.

This page maps every criterion to the evidence in this repository. It gives an honest self-score and links each remaining gap to the pull request that closes it. It is updated whenever a gap is closed.

- **Last checked:** 2026-11-08, on `main` at commit `5ce5360`
- **Self-score on `main` today:** 30 / 50
- **Self-score once the open pull requests are merged and v0.1.0 is published:** 50 / 50, with the risks listed below
- **Deadline:** the first release must exist before submission (2026-12-06); the repository is scored on 7–9 December

## Summary

| # | Criterion | Max | On `main` today | After the open pull requests | Closed by |
|---|---|---|---|---|---|
| 1 | Source control on the Internet | 5 | 5 | 5 | — |
| 2 | OSI-approved license | 10 | 5 | 10 | [#60](https://github.com/CMC-GreenDX/greendx/pull/60) |
| 3 | At least one release | 5 | 0 | 5 | [#62](https://github.com/CMC-GreenDX/greendx/pull/62), then the v0.1.0 release |
| 4 | Building from source | 10 | 10, at risk | 10 | [#64](https://github.com/CMC-GreenDX/greendx/pull/64) |
| 5 | Libraries and bundling | 10 | 5 | 10 | [#61](https://github.com/CMC-GreenDX/greendx/pull/61) |
| 6 | Documentation and communication | 10 | 5 | 10 | [#63](https://github.com/CMC-GreenDX/greendx/pull/63) |
| | **Total** | **50** | **30** | **50** | |

## 1. Source control on the Internet (5)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| Public source control but no web viewer | −3 | Pass | The repository is browsable on GitHub: <https://github.com/CMC-GreenDX/greendx> |
| Source control exists but is not open to everyone | −3 | Pass | The repository is public; no account is needed to read or clone it |
| Source control exists but is not actually used | −5 | Pass | Every change goes through an issue, a branch and a pull request with CI: [issues](https://github.com/CMC-GreenDX/greendx/issues?q=is%3Aissue), [pull requests](https://github.com/CMC-GreenDX/greendx/pulls?q=is%3Apr), [commit history](https://github.com/CMC-GreenDX/greendx/commits/main), [.github/workflows](../.github/workflows) |

**Weak point, being fixed.** Until early November, only 1 of 22 merged pull requests had an approving review, and almost every commit came from one account. From now on, a pull request is merged only after another team member approves it, and every member opens pull requests under their own account.

## 2. OSI-approved license (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| The license is not stated in each source file | −5 | **Fail today**, fixed by [#60](https://github.com/CMC-GreenDX/greendx/pull/60) | #60 adds an `SPDX-License-Identifier: Apache-2.0` header to every source file (98 files) and a `NOTICE` file. CI fails when a header is missing (`tools/license-headers.py`, `make license-check`). |
| The code contains incompatible licenses | −5 | Pass | Our code is Apache-2.0. Every third-party component has an OSI-approved license and is recorded in [docs/licenses.md](licenses.md). The GPL-licensed ClamAV runs as a separate, unmodified container. Components that moved to non-OSI licenses (Vault, Redpanda, immudb, n8n, MinIO) were rejected: see [ADR-0001](adr/0001-core-technology-choices.md). |
| No statement of the license's intent | −5 | Pass | The [README](../README.md#license) states the license; #60 adds what it allows and how third-party licenses are kept |
| No full copy of the license text | −5 | Pass | Full Apache License 2.0 text in [LICENSE](../LICENSE); GitHub detects it as Apache-2.0 |

The project also solves the problem set by the competition (DX-OS Open-Core): a headless core plus capability spaces, described in the [README](../README.md#architecture) and the [project brief](project-brief.md).

## 3. At least one release (5)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| No release | −5 | **Fail today** | No tag or release yet: [Releases](https://github.com/CMC-GreenDX/greendx/releases). The v0.1.0 archive, checksum and notes for `5ce5360` are prepared. A maintainer publishes them by pushing the `v0.1.0` tag once [#62](https://github.com/CMC-GreenDX/greendx/pull/62) is merged. |
| Releases are not versioned | −3 | Pass once published | Semantic Versioning (`v0.1.0`, then up to `v1.0.0`), as set in [CONTRIBUTING.md](../CONTRIBUTING.md#versioning-and-changelog) |
| Releases use non-open formats (zip, rar, …) | −3 | Pass once published, at risk | The release workflow attaches `greendx-X.Y.Z.tar.gz` and `SHA256SUMS`, and the notes name the `.tar.gz` as the supported format. GitHub always adds its own "Source code (zip)", which cannot be removed. |

## 4. Building from source (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| No instructions to build from source | −5 | Pass, completed by [#64](https://github.com/CMC-GreenDX/greendx/pull/64) | Today: [Getting started](../README.md#getting-started), which still says the full guide comes later. #64 adds [docs/install.md](install.md): requirements, tools from Ubuntu packages, configuration, build, checks, running without `make`, troubleshooting. It was tested with a fresh clone. |
| Configured by editing header files by hand | −5 | Pass | Configuration comes from environment variables in `.env`, created from [.env.example](../.env.example), and from tenant config packs in [tenants/](../tenants), validated by JSON Schemas in [core/schemas/](../core/schemas) |
| Cannot be configured before building | −5 | Pass | `.env` and the config packs are read at start-up; no source edit is needed |
| Built with closed-source or home-made tools | −5 | Pass | Docker Engine and Compose, GNU Make, Python, Go and Node.js, all open source; see the [Makefile](../Makefile) and [deploy/compose/](../deploy/compose). GitHub Codespaces is only an optional place to run them. |
| Does not work outside the source tree | −5 | Pass, at risk | Services run as containers built from the source, so nothing is installed into the source tree. The Compose commands run from the repository root because they mount configuration from it; [install.md](install.md#without-make) explains this. |

## 5. Libraries and bundling (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| Does not try to use libraries already available | −5 | Pass | Dependencies come from their standard registries (PyPI, Go modules, npm, container registries) at pinned versions: `requirements.txt` per service, [apps/ledger-sealer/go.mod](../apps/ledger-sealer/go.mod), [package-lock.json](../package-lock.json) |
| Ships copies of the projects it depends on | −5 | **Fail today**, fixed by [#61](https://github.com/CMC-GreenDX/greendx/pull/61) | `deploy/compose/trillian/storage.sql` is an unchanged copy of Trillian v1.8.0's schema. #61 removes it: `make up` downloads it from the pinned tag and checks its SHA-256. Swagger UI is already downloaded at build time by the [Pages workflow](../.github/workflows/pages.yml). |
| Bundled code has been modified | −5 | Pass | The one copied file was not modified (it matches upstream byte for byte apart from three attribution lines). Every library, its version, license and use is listed in [docs/licenses.md](licenses.md). |

## 6. Documentation and communication (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| No bug tracker | −5 | Pass | [GitHub Issues](https://github.com/CMC-GreenDX/greendx/issues) with [bug](../.github/ISSUE_TEMPLATE/bug.md) and [task](../.github/ISSUE_TEMPLATE/task.md) templates |
| No changelog | −5 | **Fail today**, fixed by [#63](https://github.com/CMC-GreenDX/greendx/pull/63) | [CHANGELOG.md](../CHANGELOG.md) is still only a header. #63 generates it from the commit history with git-cliff, with a section for v0.1.0. |
| No README or instructions | −5 | Pass | [README.md](../README.md), [CONTRIBUTING.md](../CONTRIBUTING.md), [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md), [architecture decisions](adr), [API guide](api/README.md), the published [API reference](https://cmc-greendx.github.io/greendx/api/) and the [project page](https://cmc-greendx.github.io/greendx/) |

## Order of work

1. Review and merge #60, #61, #63 and #64 (any order), then #62.
2. Push the `v0.1.0` tag on `5ce5360`. The release workflow creates the release with `greendx-0.1.0.tar.gz` and `SHA256SUMS`.
3. Before submission, release again (`v0.2.0` or `v1.0.0`) from the final `main`, and update this page.

## How to keep this page true

- When a gap is closed, update its row, the summary table, the self-scores and the "Last checked" line in the same pull request.
- Before submission, check every link on this page from a browser that is not logged in to GitHub.
