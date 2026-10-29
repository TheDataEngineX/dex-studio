# Contributing

How work happens in this repo: main plus feature branches, everything
through a pull request, nothing merges without the founder's review
(decision 0002 in the dataenginex repo's docs/decisions/).

## Branching

- main is the only long-lived branch. It stays green and releasable.
- All work happens on short-lived feature branches named
  feature/<short-name> - one branch per milestone or task.
- No direct commits to main. GitHub branch protection enforces the
  pull-request requirement.

## Workflow (Mac, Zed editor)

1. Pull the latest main.
2. Create the feature branch: git checkout -b feature/<short-name>
3. Build in small commits, scoped to one milestone or task.
4. Run the tests before pushing: python -m pytest
5. Push the branch and open a pull request into main. Say what
   changed and how it was tested.
6. After review and merge, delete the feature branch.

## Rules

- One milestone at a time. Park new ideas in an issue instead of
  expanding a branch.
- Architecture and scope decisions are recorded in the dataenginex
  repo's decision log (docs/decisions/) and apply here too.
- This runtime uses only the public API of the dataenginex
  foundation package, installed from PyPI in shipped builds.
- Plain ASCII in code and docs.
