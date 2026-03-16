<!-- Describe the change and motivation in a few sentences -->

## Description

**Related Issue**: Closes #XXX

## Suggested PR Title

<!-- Example: chore: org/domain foundation with pages + label/project automation -->

## Suggested Squash Commit Message

<!--
chore: establish org/domain foundation (pages, labels, project automation)

- migrate platform/docs references to thedataenginex.org
- add GitHub Pages docs deployment workflow
- add label sync and org project intake automation
- align issue templates/support/security/workflow docs
-->

## Keep / Change / Remove

- **Keep**:
- **Change**:
- **Remove**:

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Documentation update
- [ ] Infrastructure/DevOps change

## Changes Made

- Change 1
- Change 2
- Change 3

## Testing

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Tests pass locally (`uv run poe test`)
- [ ] Coverage maintained/improved (target: 80%+)

## Architecture Impact

- [ ] Cloud-neutral by default (no hard dependency on a single provider)
- [ ] Cost-aware default path (works locally or free/open-source tier)
- [ ] Extension points documented for future adapters/plugins

## Deprecation / Migration

- [ ] No deprecation impact
- [ ] If behavior changed, deprecation/migration notes were added to docs/release notes

## Checklist

- [ ] Linting passes (`uv run poe lint` ✓)
- [ ] Type checking passes (`uv run poe typecheck` ✓)
- [ ] Documentation updated (if applicable)
- [ ] Pre-commit hooks pass

## External Setup (if applicable)

- [ ] GitHub Pages source set to **GitHub Actions**
- [ ] Org/Repo variable set: `ORG_PROJECT_URL`
- [ ] Org/Repo secret set: `ORG_PROJECT_TOKEN`
- [ ] Cloudflare DNS updated for docs/api/apex domains
- [ ] Post-cutover checks completed (see `docs/DEPLOY_RUNBOOK.md` → Org + Domain Rollout)

## Notes for Reviewers
