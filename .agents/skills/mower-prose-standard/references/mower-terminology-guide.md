# Arknights Mower Controlled Terminology Quick Reference

Quick reference mapping canonical domain terms against prohibited synonyms from `CONTEXT.md` and `CONTEXT.zh.md`.

## 1. Device & Transport Domain

| Authoritative Term (En / Zh) | Prohibited Synonyms (_Avoid_) | Rationale |
| :--- | :--- | :--- |
| **Device Profile** / 设备配置 | `Runtime state`, `Discovery candidate`, `Active connection` | Prevents conflating persistent user selections with transient memory state. |
| **Instance Binding** / 模拟器实例绑定 | `Dynamic device selection`, `Floating target`, `Auto fallback` | Prevents silent drifting to unintended devices on the host. |
| **Readiness Verdict** / 设备连接检查结果 | `Raw exception`, `Unformatted error string` | Enforces structured classification (`absent`, `offline`, `booting`, `ready`). |
| **Recovery Budget** / 重连恢复上限 | `Infinite retry`, `Unconstrained loop`, `Background sleep` | Enforces finite monotonic timeout deadlines. |
| **Topology Fingerprint** / 多开实例特征码 | `Vague identifier`, `Simulator metadata`, `Transient serial` | Enforces deterministic hash identity verification across port shifts. |
| **Temporary Preparation** / 实体设备临时分辨率适配 | `Permanent configuration`, `Unmanaged resolution change` | Enforces guaranteed restoration compensation on physical devices. |
| **Capture Frame** / 标准画面帧 | `Scaled preview`, `Raw stream byte` | Enforces strictly uncropped 1920×1080 canvas RGB matrix contract. |
| **Shared ADB Guard** / ADB 服务共享管理 | `Direct kill-server`, `Unguarded CLI call` | Prohibits disruptive `adb kill-server` invocations. |

## 2. Facility & Scheduling Domain

| Authoritative Term (En / Zh) | Prohibited Synonyms (_Avoid_) | Rationale |
| :--- | :--- | :--- |
| **Scheduling Plan** / 排班表 | `Task script`, `Macro`, `Work plan` | Distinct from ad-hoc automation scripts. |
| **Operator Mood** / 干员心情 | `Physical energy`, `Fatigue level` | Authoritative in-game stamina metric (0-24). |
| **Base Facility** / 基建设施 | `Building slot`, `Isolated room` | Standard operational room entity. |
| **Dormitory Recovery** / 宿舍心情恢复 | `Sleep queue`, `Rest list` | Governed by priority tiers and dorm manager entry order. |
| **Depletion Rate** / 心情消耗速率 | `Drain speed`, `Depletion cost` | Empirically calculated consumption metric. |
| **Dynamic Shift Transition** / 动态换班 | `Fixed timetable swap`, `Static worker cycle` | Event- and condition-driven rotation mechanism. |
| **Clue Collection & Exchange** / 线索搜集与交流 | `Party mode`, `Clue trade` | Automated Reception Room workflow and 24h party tracking. |
| **Drone Acceleration** / 无人机加速 | `Speed up`, `Drone boost` | Power Plant drone deduction mechanics. |
