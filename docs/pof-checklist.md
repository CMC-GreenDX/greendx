# Points of Fail (PoF) self-assessment

Part I of the OLP PMNM 2026 rules (50 of 100 points) is scored on this repository before the final, using the "Points of Fail" from Tom Callaway's [How you know your Free or Open Source Software Project is doomed to FAIL](http://spot.livejournal.com/308370.html). A criterion starts at its maximum and loses points for each fail.

This page maps every criterion to the evidence in this repository and gives an honest self-score. It is updated whenever the state of the repository changes.

- **Last checked:** 2026-11-09, on `main` after [#65](https://github.com/CMC-GreenDX/greendx/pull/65)
- **Self-score:** 50 / 50 (100 / 100 on the competition's scale), with the risks listed below
- **History:** 30 / 50 on 2026-11-08 at commit `5ce5360`. Each gap got its own pull request (#60–#65), merged on 2026-11-09.
- **Deadline:** the first release must exist before submission (2026-12-06); the repository is scored on 7–9 December

## Summary

| # | Criterion | Max | Self-score | Closed by |
|---|---|---|---|---|
| 1 | Source control on the Internet | 5 | 5 | — |
| 2 | OSI-approved license | 10 | 10 | [#60](https://github.com/CMC-GreenDX/greendx/pull/60) |
| 3 | At least one release | 5 | 5 | [#62](https://github.com/CMC-GreenDX/greendx/pull/62), [v0.1.0](https://github.com/CMC-GreenDX/greendx/releases/tag/v0.1.0) |
| 4 | Building from source | 10 | 10 | [#64](https://github.com/CMC-GreenDX/greendx/pull/64) |
| 5 | Libraries and bundling | 10 | 10 | [#61](https://github.com/CMC-GreenDX/greendx/pull/61) |
| 6 | Documentation and communication | 10 | 10 | [#63](https://github.com/CMC-GreenDX/greendx/pull/63) |
| | **Total** | **50** | **50** | |

## 1. Source control on the Internet (5)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| Public source control but no web viewer | −3 | Pass | The repository is browsable on GitHub: <https://github.com/CMC-GreenDX/greendx> |
| Source control exists but is not open to everyone | −3 | Pass | The repository is public; no account is needed to read or clone it |
| Source control exists but is not actually used | −5 | Pass | Every change goes through an issue, a branch and a pull request with CI: [issues](https://github.com/CMC-GreenDX/greendx/issues?q=is%3Aissue), [pull requests](https://github.com/CMC-GreenDX/greendx/pulls?q=is%3Apr), [commit history](https://github.com/CMC-GreenDX/greendx/commits/main), [.github/workflows](../.github/workflows) |

**Weak point.** Only 1 of 22 pull requests merged before November had an approving review, and the fixes #60–#65 were also merged without one because of the deadline. After the 2026-11-09 review, every pull request needs an approval from another team member before it is merged, and every member opens pull requests under their own account.

## 2. OSI-approved license (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| The license is not stated in each source file | −5 | Pass | Every source file starts with `SPDX-FileCopyrightText` and `SPDX-License-Identifier: Apache-2.0` lines, and [NOTICE](../NOTICE) states the copyright. CI fails when a header is missing: [tools/license-headers.py](../tools/license-headers.py), `make license-check`. |
| The code contains incompatible licenses | −5 | Pass | Our code is Apache-2.0. Every third-party component has an OSI-approved license and is recorded in [docs/licenses.md](licenses.md). The GPL-licensed ClamAV runs as a separate, unmodified container. Components that moved to non-OSI licenses (Vault, Redpanda, immudb, n8n, MinIO) were rejected: see [ADR-0001](adr/0001-core-technology-choices.md). |
| No statement of the license's intent | −5 | Pass | The [README](../README.md#license) states the license, what it allows, and how third-party licenses are kept |
| No full copy of the license text | −5 | Pass | Full Apache License 2.0 text in [LICENSE](../LICENSE); GitHub detects it as Apache-2.0 |

The project also solves the problem set by the competition (DX-OS Open-Core): a headless core plus capability spaces, described in the [README](../README.md#architecture) and the [project brief](project-brief.md).

## 3. At least one release (5)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| No release | −5 | Pass | [Releases](https://github.com/CMC-GreenDX/greendx/releases): v0.1.0 (2026-11-09), then v0.1.1 with the fixes below |
| Releases are not versioned | −3 | Pass | Semantic Versioning (`v0.1.0`, `v0.1.1`, then up to `v1.0.0`), as set in [CONTRIBUTING.md](../CONTRIBUTING.md#versioning-and-changelog) |
| Releases use non-open formats (zip, rar, …) | −3 | Pass, at risk | Each release attaches `greendx-X.Y.Z.tar.gz` and `SHA256SUMS`, built by the [release workflow](../.github/workflows/release.yml) from the tag, and the notes name the `.tar.gz` as the supported format. GitHub always adds its own "Source code (zip)", which cannot be removed. |

## 4. Building from source (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| No instructions to build from source | −5 | Pass | [docs/install.md](install.md): requirements, tools from Ubuntu packages, configuration, build, checks, running without `make`, troubleshooting. Tested with a fresh clone: all 7 check suites pass. |
| Configured by editing header files by hand | −5 | Pass | Configuration comes from environment variables in `.env`, created from [.env.example](../.env.example), and from tenant config packs in [tenants/](../tenants), validated by JSON Schemas in [core/schemas/](../core/schemas) |
| Cannot be configured before building | −5 | Pass | `.env` and the config packs are read at start-up; no source edit is needed |
| Built with closed-source or home-made tools | −5 | Pass | Docker Engine and Compose, GNU Make, Python, Go and Node.js, all open source; see the [Makefile](../Makefile) and [deploy/compose/](../deploy/compose). GitHub Codespaces is only an optional place to run them. |
| Does not work outside the source tree | −5 | Pass, at risk | Services run as containers built from the source, so nothing is installed into the source tree. The Compose commands run from the repository root because they mount configuration from it; [install.md](install.md#without-make) explains this. |

## 5. Libraries and bundling (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| Does not try to use libraries already available | −5 | Pass | Dependencies come from their standard registries (PyPI, Go modules, npm, container registries) at pinned versions: `requirements.txt` per service, [apps/ledger-sealer/go.mod](../apps/ledger-sealer/go.mod), [package-lock.json](../package-lock.json) |
| Ships copies of the projects it depends on | −5 | Pass | The copy of Trillian's schema was removed. `make up` downloads it from the pinned v1.8.0 tag and checks its SHA-256: [deploy/compose/trillian/fetch-schema.sh](../deploy/compose/trillian/fetch-schema.sh). Swagger UI is downloaded at build time by the [Pages workflow](../.github/workflows/pages.yml). |
| Bundled code has been modified | −5 | Pass | Nothing is bundled. Every library, its version, license and use is listed in [docs/licenses.md](licenses.md). |

## 6. Documentation and communication (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| No bug tracker | −5 | Pass | [GitHub Issues](https://github.com/CMC-GreenDX/greendx/issues) with [bug](../.github/ISSUE_TEMPLATE/bug.md) and [task](../.github/ISSUE_TEMPLATE/task.md) templates |
| No changelog | −5 | Pass | [CHANGELOG.md](../CHANGELOG.md), generated from the Conventional Commits history with git-cliff, one section per release |
| No README or instructions | −5 | Pass | [README.md](../README.md), [docs/install.md](install.md), [CONTRIBUTING.md](../CONTRIBUTING.md), [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md), [architecture decisions](adr), [API guide](api/README.md), the published [API reference](https://cmc-greendx.github.io/greendx/api/) and the [project page](https://cmc-greendx.github.io/greendx/) |

## Risks

- **Criterion 3, up to −3:** GitHub's automatic zip archive could be counted as a non-open format. The notes of every release say the `.tar.gz` is the supported format.
- **Criterion 4, up to −5:** commands run from the repository root. This is how Docker Compose mounts configuration; install.md explains it.
- **Criterion 1:** the review history is weak (see above).

## Next steps

1. Before submission, release `v1.0.0` from the final `main` and update this page.
2. Keep every new pull request reviewed by another team member.

## How to keep this page true

- When the state of the repository changes, update the affected row, the summary table, the self-score and the "Last checked" line in the same pull request.
- Before submission, check every link on this page from a browser that is not logged in to GitHub.
