---
title: 房间标题确认
status: implemented
category: simplification
date: 2026-10-12
---

# 房间标题确认

## 契约

[INV-REC-11] 设施标题优先：当前 Capture Frame 中匹配成功的设施标题优先于图标颜色，包括进入动画期间；未知标题保留图标识别和有界的房间进入恢复。

## 边界与简化

`BaseMixin.detect_room` 为进入确认、名单读回和训练导航提供房间身份。现有标题匹配先于颜色分类执行，并包含回收站标题。`detect_room_type` 继续为生产设施观察提供共享图标分类。改动调整现有识别顺序，不增加动画计时器、另一套分类器或恢复循环。调度机制、设备生命周期和配置结构保留现有契约，无需修改术语表。

## 验证

离线测试重放用户归档中的三张标题裁剪图，保留解码后的原始像素，并确认动画中及稳定后的回收站身份。合成的训练室颜色干扰不能覆盖已匹配的标题。空白标题保持未知，编号制造站和训练室图标保留识别能力，实际进入确认避免多余的首页恢复。现有地图重新定位测试继续检查有界失败和取消行为。

## 审查

### 规范检查

通过：识别使用同一 Capture Frame，不增加外部操作或重试循环，保留现有未知结果和配置，并通过治理与 Python 静态检查。简化审查保留共享的生产设施分类器，不删除公共接口。

### 功能检查

通过：全部 590 张归档截图完成离线回放。相对 alpha 基准 `798630d5`，原先的五次训练室识别改为回收站，其他身份结果均保持不变。颜色干扰最强的裁剪图在当前图标分类器上同样复现训练室结果，而标题识别与进入确认正确判定回收站。

迁移至 alpha 后的验证：`python -m pytest arknights_mower/tests/room_map_relocation_tests.py arknights_mower/tests/verify_governance_tests.py -q` 通过 84 项测试。`python scripts/verify_governance.py --base origin/alpha`、定向 Ruff 静态与格式检查、`git diff --check` 均通过。设备运行待实测。
