# Points of Fail (PoF) self-assessment

Part I of the OLP PMNM 2026 rules (50 points) scores the repository with the "Points of Fail" from Tom Callaway's [How you know your Free or Open Source Software Project is doomed to FAIL](http://spot.livejournal.com/308370.html). Each criterion starts at its maximum and loses points for each fail. This page lists the evidence for every fail.

**Self-score: 50 / 50**, checked on 2026-11-17. The risks are listed at the end.

| # | Criterion | Max | Self-score |
|---|---|---|---|
| 1 | Source control on the Internet | 5 | 5 |
| 2 | OSI-approved license | 10 | 10 |
| 3 | At least one release | 5 | 5 |
| 4 | Building from source | 10 | 10 |
| 5 | Libraries and bundling | 10 | 10 |
| 6 | Documentation and communication | 10 | 10 |
| | **Total** | **50** | **50** |

## 1. Source control on the Internet (5)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| No web viewer | −3 | Pass | <https://github.com/CMC-GreenDX/greendx> |
| Not open to everyone | −3 | Pass | Public repository; no account needed to clone |
| Not actually used | −5 | Pass | Every change goes through an [issue](https://github.com/CMC-GreenDX/greendx/issues?q=is%3Aissue), a branch and a [pull request](https://github.com/CMC-GreenDX/greendx/pulls?q=is%3Apr) checked by [CI](../.github/workflows) |

## 2. OSI-approved license (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| License not stated in each source file | −5 | Pass | SPDX header in every source file, checked by `make license-check` and CI ([tools/license-headers.py](../tools/license-headers.py)) |
| Incompatible licenses | −5 | Pass | Apache-2.0; every third-party component is OSI-approved ([docs/licenses.md](licenses.md)); GPL ClamAV runs as a separate, unmodified container |
| No statement of the license's intent | −5 | Pass | [README](../README.md#license) and [NOTICE](../NOTICE) |
| No full copy of the license | −5 | Pass | [LICENSE](../LICENSE) |

The project answers the competition topic (DX-OS Open-Core): see the [project brief](project-brief.md).

## 3. At least one release (5)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| No release | −5 | Pass | [v0.1.0, v0.1.1 and v0.2.0](https://github.com/CMC-GreenDX/greendx/releases) |
| Releases not versioned | −3 | Pass | Semantic Versioning ([CONTRIBUTING.md](../CONTRIBUTING.md#versioning-and-changelog)) |
| Non-open release format (zip, rar, …) | −3 | Pass, at risk | `greendx-X.Y.Z.tar.gz` and `SHA256SUMS`, built by the [release workflow](../.github/workflows/release.yml) |

## 4. Building from source (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| No build instructions | −5 | Pass | [docs/install.md](install.md), tested from a fresh clone |
| Configured by editing header files | −5 | Pass | `.env` from [.env.example](../.env.example) and config packs in [tenants/](../tenants) |
| Cannot be configured before building | −5 | Pass | Both are read at start-up and validated by the JSON Schemas in [core/schemas/](../core/schemas) |
| Built with closed or home-made tools | −5 | Pass | Docker Compose, GNU Make, Python, Go, Node.js |
| Does not work outside the source tree | −5 | Pass, at risk | Services run as containers; the Compose commands run from the repository root ([install.md](install.md#without-make)) |

## 5. Libraries and bundling (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| Does not use available libraries | −5 | Pass | Dependencies from PyPI, Go modules, npm and official images, at pinned versions |
| Ships copies of other projects | −5 | Pass | Nothing is vendored; Trillian's schema is downloaded at its pinned tag and checked by SHA-256 ([fetch-schema.sh](../deploy/compose/trillian/fetch-schema.sh)) |
| Bundled code has been modified | −5 | Pass | Nothing is bundled ([docs/licenses.md](licenses.md)) |

## 6. Documentation and communication (10)

| Fail | Points | Status | Evidence |
|---|---|---|---|
| No bug tracker | −5 | Pass | [GitHub Issues](https://github.com/CMC-GreenDX/greendx/issues) with bug and task templates |
| No changelog | −5 | Pass | [CHANGELOG.md](../CHANGELOG.md), generated from the commit history |
| No README or instructions | −5 | Pass | [README](../README.md), [install guide](install.md), [CONTRIBUTING.md](../CONTRIBUTING.md), [ADRs](adr), [API guide](api/README.md) |

## Risks

- **Criterion 3 (−3):** GitHub adds a zip of the source to every release and it cannot be removed. The release notes name the `.tar.gz` as the supported format.
- **Criterion 4 (−5):** the Compose commands must run from the repository root, because they mount configuration from it.
- **Criterion 2 (−5):** the header checker excludes JSON and XML data files; JSON does not support comments, while XML does. The current source-header check does not establish license coverage for these excluded files.
- **Criterion 1:** most pull requests merged before 2026-11-15 had no review. Every pull request now needs an approval from another team member.
