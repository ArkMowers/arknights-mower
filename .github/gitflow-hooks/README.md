# git-flow hooks

## Install

```bash
git config gitflow.path.hooks `git rev-parse --show-toplevel`/.github/gitflow-hooks
```

## git-flow config

- Branch name for production releases: `main`
- Branch name for "next release" development: `dev`
- Feature branch prefix: `feature/`
- Bugfix branch prefix: `bugfix/`
- Release branch prefix: `release/`
- Hotfix branch prefix: `hotfix/`
- Support branch prefix: `support/`
- Version tag prefix: `v`
