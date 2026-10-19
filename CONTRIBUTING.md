# Contributing to EcoTrace

Thank you for contributing. This guide describes how work flows from an idea to a merged change, and why we work this way. The conventions apply to the core team and to outside contributors alike.

## Why these conventions exist

- **Traceable history.** Every change follows the same chain: issue → branch → commit → pull request. Anyone can start from a line of code and find the commit that introduced it, the pull request where it was reviewed and the issue that explains why it was needed. The same idea of lineage is at the heart of the product, so we apply it to our own work.
- **Automatic changelog.** Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), so `CHANGELOG.md` and release notes are generated from the history instead of being written by hand.
- **Easier review.** Small pull requests tied to one issue, with a predictable title and a "How to test" section, are faster and safer to review.
- **Easier outside contribution.** A newcomer can read this file, pick an issue and open a pull request that fits in, without having to ask how things are done.

CI checks these conventions automatically on every pull request (see [Automated checks](#automated-checks)).

## Workflow at a glance

1. Open an issue (or pick an existing one) using a template.
2. Create a branch from `main` named after the issue.
3. Commit using Conventional Commits.
4. Open a pull request that closes the issue.
5. Get at least one approval from a teammate.
6. Squash merge. Never push directly to `main`.

## Issues

- **Title:** `[<Area>] <Imperative summary>`, for example `[Core] Add RLS policies for tenant isolation`.
- **Areas:** `Core`, `Gateway`, `Identity`, `Data`, `Storage`, `Workflow`, `Events`, `Ledger`, `Intake`, `Carbon`, `Purchase`, `Portal`, `Dashboard`, `Dxctl`, `Infra`, `Docs`. They mirror the commit scopes below.
- **Body:** use a template from `.github/ISSUE_TEMPLATE/`. Every issue has the sections **Context**, **Scope** and **Acceptance criteria**.
- One issue describes one deliverable. If it needs more than a few days of work, split it.

## Branches

Format: `<type>/<issue-number>-<short-kebab-desc>`

```text
feat/12-tenant-onboarding-cli
fix/31-hasura-tenant-claim
docs/7-adr-0001-tech-choices
```

- `<type>` is one of the commit types below.
- `<issue-number>` is the GitHub issue the branch resolves.
- `<short-kebab-desc>` uses lowercase letters, digits and hyphens only.

## Commits

Format: `<type>(<scope>): <imperative summary>`

```text
feat(intake): add electricity bill extractor
fix(gateway): reject tokens without tenant claim
docs(docs): record ADR for object storage
```

| Type | Use for |
|---|---|
| `feat` | A new feature |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `refactor` | A code change that neither fixes a bug nor adds a feature |
| `test` | Adding or correcting tests |
| `chore` | Maintenance that does not change runtime behaviour |
| `ci` | CI configuration and workflows |
| `build` | Build system, container images, dependencies |
| `perf` | A performance improvement |

**Scopes:** `core`, `gateway`, `identity`, `data`, `storage`, `workflow`, `events`, `ledger`, `intake`, `carbon`, `purchase`, `portal`, `dashboard`, `dxctl`, `infra`, `docs`.

Rules:

- The scope is required.
- The summary is in the imperative mood ("add", not "added" or "adds"), starts with a lowercase letter and has no trailing period.
- Use the body to explain *why* when the change is not obvious.
- Mark breaking changes with `!` after the scope (`feat(core)!: ...`) and a `BREAKING CHANGE:` footer.

## Pull requests

- **Title:** same format as a commit, because the title becomes the squash commit on `main`.
- **Body:** use the template. It has **Summary**, **How to test** and `Closes #<issue-number>`. The issue number must match the one in the branch name.
- Keep pull requests small and focused on one issue.
- **Review:** at least one approval from a teammate who did not write the change.
- **Merge:** squash merge only, then delete the branch.

## Versioning and changelog

- Releases are tagged with [Semantic Versioning](https://semver.org/) as `v0.x.y` until `v1.0.0`.
- `CHANGELOG.md` is generated from commit messages with [git-cliff](https://git-cliff.org) (`make changelog` or `npm run changelog`). Do not edit it by hand.

## Project rules

These rules come from the [project brief](docs/project-brief.md) and are checked during review.

- **English only** for code, identifiers, branch names, commits, issues, pull requests and documentation. User-facing UI text is localised (for example to Vietnamese) through i18n files and is never hard-coded.
- **No business logic in the core.** `core/` and `capabilities/` never reference a specific company or tenant. Company-specific behaviour belongs in `apps/` or in a tenant config pack under `tenants/`.
- **Licenses.** Only use components with an [OSI-approved license](https://opensource.org/licenses). Before adding a dependency or container image, check its current license and record it in [docs/licenses.md](docs/licenses.md). If a license is unclear, flag it in the pull request instead of guessing.
- **Pinned versions.** Every container image and package uses an exact version that has been verified to exist. No `latest` tags and no version ranges.
- **Architecture decisions.** Significant choices are recorded as an ADR in `docs/adr/NNNN-title.md`, using [the template](docs/adr/0000-template.md).
- **No secrets in Git.** Only `.env.example` with placeholder values is committed. Real secrets live in OpenBao.
- **Laptop-friendly.** The `core` Compose profile must run on a 16 GB laptop. Heavy services go in the `full` profile.

## Local setup

Requirements: Git, Node.js 24 or later, Python 3.12 or later, and GNU Make (optional; every target has an `npm run` equivalent).

```sh
make setup   # npm ci + pip install -r requirements-dev.txt
make lint    # Markdown and YAML checks
```

To check your commits before pushing:

```sh
npm run lint:commits
```

## Automated checks

The `lint` workflow runs on every pull request and on `main`:

| Check | What it enforces |
|---|---|
| PR title | Conventional Commits format with an allowed type and scope |
| Commits | Every commit in the pull request follows the same format |
| Branch name | `<type>/<issue-number>-<short-kebab-desc>` |
| Linked issue | The body contains `Closes #N`, where `N` matches the branch |
| Markdown | `markdownlint-cli2` |
| YAML | `yamllint` |

Line endings are normalised to LF by `.gitattributes`, and `.editorconfig` configures editors to match.

A pull request cannot be merged until all checks pass.
