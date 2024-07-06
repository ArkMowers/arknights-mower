---
sort: 2
---

# 版本与分支

Mower 同时维护两个分支：测试版与稳定版。新功能的开发以及 bug 修复都测试分支上进行。然而，对代码的改动可能引入新的 bug，功能的变动也需要用户不断地学习和适应，使用测试版可能不时遇到新的 bug。对于没有精力跟踪 mower 开发进度，或希望获得稳定体验的用户，稳定版也是必不可少的。

## 版本号

版本号由 `arknights_mower/__init__.py` 文件中的 `__version__` 变量表示。

```python
from arknights_mower import __version__
print(__version__)
```

Mower 使用 GitHub Actions 自动为 Windows 平台打包。打包过程中，修改版本号的步骤如下：

```yaml
- name: change version number
  if: github.event.head_commit.message != '发版'
  shell: bash
  run: |
    sed -i 's/__version__ = "\(.*\)"/__version__ = "\1+${GITHUB_SHA::7}"/g' ./arknights_mower/__init__.py
```

当提交信息是“发版”时，CI 不会修改版本号；反之，CI 会把 commit id 的前 7 位附加到版本号后面，使用加号分隔。

- 测试版使用滚动更新，版本号格式为 `YYYY.MM+<commit id>`，其中 `YYYY` 为四位年份，`MM` 为两位月份，`<commit id>` 为 commit id 的前 7 位。测试版代码的 `__version__` 中只写 `YYYY.MM` 的部分，靠 CI 自动添加 commit id。
- 稳定版使用定点更新，版本号格式为 `YYYY.MM.X`，其中 `X` 为小版本号。创建分支时 `X` 为 1，以后每次发版时，需手动增加 `X`，并将提交信息设为“发版”。

## 日志页背景

Mower 每年发布 4 个大版本，以新版发布前 3 个月内对基建影响最大的干员立绘作为日志页背景。

- 2024.02：在版本发布前，mower 实装了新的肥鸭充能策略，所以选择菲亚梅塔。
- 2024.05：从春节活动开始到周年活动前，对基建影响最大的干员是阿罗玛。
- 2024.08：预计为乌尔比安。

## 如何开发测试版

测试版的开发一直在 dev_shawn 分支进行。在发布新版本时，只需要对版本号做出修改。例如 2024 年夏活更新后，将 dev_shawn 分支的版本号从 `2024.05` 改为 `2024.08` 即可。

## 如何维护稳定版

为保证稳定版的特性相对稳定，稳定版只接受添加新干员和 bug 修复。除非修复 bug 需要，否则不要添加新的功能。

稳定版的代码与测试版有所不同，所以在发布新版本时，需要基于当前的测试版新建稳定版分支，然后修改测试分支的版本号。例如 2024 年夏活更新时，稳定分支 2024.02 停止维护，基于 dev_shawn 分支新建 2024.05 分支，并把 2024.05 分支的版本号从 `2024.05` 改为 `2024.05.1`，作为新的稳定版发版。后续在稳定分支上进行若干改动后，将版本号由 `2024.05.1` 改为 `2024.05.2` 并发版，以此类推。

虽然稳定版的代码在单独的分支，但除修改版本号外，出于以下原因，应尽量避免直接向稳定分支提交代码：

1. 直接向稳定分支提交的代码，没有经过测试，可能引入新的 bug；
2. Mower 的开发力量有限，同时维护两个分支耗费的精力太多，在当前阶段是不现实的；
3. 稳定分支是基于测试分支创建的，在绝大部分情况下，对于同一个 bug，两个分支可以使用相同的方式进行修复。

因此，更恰当的做法是，将提交推送到测试分支，经过用户的充分测试后，以 cherry-pick 的方式，将修改反向移植到稳定分支。

```mermaid
%%{init: {'gitGraph': {'mainBranchName': 'dev_shawn'}}}%%
gitGraph

commit

branch 2024.02
commit id: "2024.02.1" tag: "2024.02.1"

checkout dev_shawn
commit id: "2024.05"
commit
commit id: "bug fix"

checkout 2024.02
cherry-pick id: "bug fix"

checkout dev_shawn
commit

checkout 2024.02
commit id: "2024.02.2" tag: "2024.02.2"

checkout dev_shawn
commit
```

为避免打扰用户，若无特殊情况，稳定版每星期最多发版一次。
