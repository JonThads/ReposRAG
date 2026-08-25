# Claude Instructions

*ReposRAG*

### Output

When giving output, AI should give the format of:

1. Summary - gives an overall summary of all changes and things done
2. List of items - a list/bullet of all changes and things done
3. Detailed List - actual breakdown of each item from the Summary and List of Items

### Flow

Development always happens on one of the prefixed branches above, never
directly on `qa` or `main`.

1. Branch `<prefix>/<purpose>` off `qa`.
2. Open a pull request into `qa` — the QA pipeline (see "Actions" below)
   runs the full Postman + Playwright suite against it before it can
   merge.
3. Once `qa` is verified stable, open a pull request from `qa` into
   `main` for production — the Main pipeline additionally runs k6, a
   Docker image build check, and a secrets scan.

The GitHub Actions pipelines below are implemented and gate every merge
into `qa` and `main` via required status checks — merges are no longer
manual and PRs are no longer skipped.

## GitHub

### Repo

- Repo "ReposRAG"

### Actions

Three pipelines: GitHub Actions should have a check and testing for every
code merge. All three are implemented (`.github/workflows/`).

- Development — lint/build/boot-check, fires on pushes to the prefixed
  branches above (not `qa`/`main`)
- QA — full testing suite, gates PRs/pushes into `qa`
- Main — QA's suite plus, a Docker image build check, and a secrets
  scan, gates PRs/pushes into `main`; optional manual
  `workflow_dispatch` tags a release

## Environment

- The application should be in Docker.
- During local development, actual development should be visible, so
  Docker must not be headless.

## Tech Stack

- Python
- DeepEval
- Docker
- Git and GitHub
- Prometheus and Grafana

## Professional / Production-Grade Conventions

Even though ReposRAG is a learning project and portfolio piece,
default to the same conventions a real production codebase would use in
every aspect — code, git, tooling, process — unless a specific doc says
otherwise. This section is the running list of what that means concretely
here.

### Conventional Branch

Use the standards established in [conventionalbranch.org](https://conventionalbranch.org/)

Note:

- Branch "main" for Production
- Branch "qa" for QA and Testing
- Local development branches, all cut from `qa`, prefixed by purpose
  (mirrors the commit-type prefixes in "Professional / Production-Grade
  Conventions" below):
  - `feature/<purpose>` — new functionality
  - `fix/<purpose>` — bug fixes
  - `test/<purpose>` — test infrastructure/tooling (Postman, k6,
    Playwright) — this is process/tooling work, not a shipped product
    feature, so it gets its own prefix rather than living under `feature/`
  - `chore/<purpose>` — dependency, config, or tooling work with no
    behavior change
  - `docs/<purpose>` — documentation-only changes
  - `refactor/<purpose>` — internal restructuring, no behavior change
  - `ci/<purpose>` — GitHub Actions / pipeline changes

### Conventional Commits

Disregard already used previous Commit Messaging Standard primarily,

"Already in use (see `git log`): `[Type]: description`. Keep using it,
with the full type list, matching the branch prefixes above: `feature`,
`fix`, `docs`, `chore`, `test`, `refactor`, `perf`, `ci`."

Instead, use the standards established in [Conventional Commits](https://www.conventionalcommits.org/).

### Conventional Comments

Use the standards established in [conventionalcomments.org](https://conventionalcomments.org/)

Plus a Reference Work Item or Ticket Number.

For example, "[Comment] as per Jira Work Item RAG-14"

### Common Changelog

Use the standards established in [common-changelog.org](https://common-changelog.org/)
