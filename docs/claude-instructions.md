# Claude Instructions

*ReposRAG*

## Branches

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

## Professional / Production-Grade Conventions

Even though ReposRAG is a learning project and portfolio piece,
default to the same conventions a real production codebase would use in
every aspect — code, git, tooling, process — unless a specific doc says
otherwise. This section is the running list of what that means concretely
here.

### Commit messages

Already in use (see `git log`): `[Type]: description`. Keep using it,
with the full type list, matching the branch prefixes above: `feature`,
`fix`, `docs`, `chore`, `test`, `refactor`, `perf`, `ci`. This is this
repo's own bracketed variant of
[Conventional Commits](https://www.conventionalcommits.org/).
