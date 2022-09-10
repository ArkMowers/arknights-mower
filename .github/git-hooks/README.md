# git hooks

## Install

```bash
git config core.hooksPath `git rev-parse --show-toplevel`/.github/git-hooks
```

## git commit 提交规范

参考：https://www.conventionalcommits.org/zh-hans/v1.0.0-beta.4/

- build: Changes that affect the build system or external dependencies.
- chore: Others.
- ci: Changes to our CI configuration files and scripts.
- docs: Documentation only changes.
- feat: A new feature.
- fix: A bug fix.
- hotfix: Publish a hotfix.
- perf: A code change that improves performance.
- refactor: A code change that neither fixes a bug or adds a feature.
- release: Publish a new release.
- revert: Revert the last commit.
- style: Changes that do not affect the meaning of the code.
- test: Adding missing tests or correcting existing tests.
- typo: Typographical error.
- update: Data updates.
- workflow: Changes to our workflow configuration files and scripts.
