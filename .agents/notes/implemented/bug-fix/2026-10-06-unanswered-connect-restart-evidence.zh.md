---
title: 未应答连接的重启证据
status: implemented
category: bug-fix
date: 2026-10-06
---

# 未应答连接的重启证据

## 现象

共享 ADB 服务停止应答主机握手后无法恢复。每个恢复周期都记录 `设备恢复暂停，30 秒后重新检查所选目标：共享 ADB 握手无法验证，保留现有监听`，所选模拟器在外部工具重启该服务之前始终不可用。实测故障中该警告持续二十八分钟，服务始终无响应。

恢复也无法重新启动协调器已经停止的服务。服务持续缺席，而每次观察都重复主机握手超时、不给出缺席结论；`_start` 拒绝这种未确认的观察，所选模拟器在外部工具启动该服务之前始终不可用。

## 根因

`probe_adb_server` 区分两个超时阶段。接收主机应答超时抛出 `SharedADBHandshakeTimeout`；TCP 连接阶段超时抛出的是普通 `SharedADBError`。

`SharedADBRecovery._require_host_timeout` 只接受 `SharedADBHandshakeTimeout` 作为主机故障证据，其他探测错误一律抛出 `共享 ADB 握手无法验证，保留现有监听`。因此连接阶段超时在首次观察时即中止恢复，早于 `_failed_probes` 与 `_failed_since` 的更新，既未进入持续故障窗口，也未到达重启判定，协调器始终不会停止已卡死的服务。

该分类与观察所证明的事实不符。TCP 连接完成但无应答，与连接始终未完成，都表示主机握手未得到应答。超时本身无法区分卡住的监听者与连接拒绝在探测预算之后才到达的缺席服务。

把两个阶段都归为重启证据修复了过早中止，但仍留下另一种恢复失败。协调器的一秒观察可能早于本地连接拒绝结果结束。停止成功后，`_wait_absent` 仍持续观察到超时而不是服务缺席，最终耗尽重连恢复上限。`_start` 也在启动之前拒绝这种未确认的观察。

## 契约

[INV-DEV-19] Shared ADB Recovery 与 [INV-05] Shared ADB Guard 保留现有保证。[设备控制契约](../../../../docs/subsystems/device-control.md#3-subsystem-invariants) 定义完整的观察、协调重启与启动规则。[INV-SCHED-39] 按[调度恢复契约](../../../../docs/subsystems/base-scheduler.md#3-subsystem-invariants)保留待执行任务。

未应答的连接在独立监听查询确认缺席之前仍未得到确认。这区分了本地连接拒绝延迟与提供重启证据的现有监听者。仅延长 socket 超时无法解决服务持续缺席、连接观察却持续超时的情况。

畸形响应、响应提前关闭或应答阶段超时均不使用原生查询确认缺席。这保留了连接已到达存活进程的证据。连接被拒绝仍是原始 socket 探测的唯一缺席结果；协调器还接受成功的 Windows 监听查询确认的缺席。

[端口占用进程核验后停止的决策](2026-10-07-verified-adb-listener-stop.zh.md) 扩展协议停止边界。停止请求超时允许使用其 Windows 进程核验兜底；未通过核验或停止失败仍保留尝试记录、冷却，并拒绝启动服务。

[INV-05] Shared ADB Guard 保持不变：隐式 `kill-server` 仍被禁止，显式主机恢复边界仍是停止共享服务的唯一途径。

## 实现

`probe_adb_server` 通过单一处理分支把两个阶段的超时上报为 `SharedADBHandshakeTimeout`，并把 `phase` 记录为 `connect` 或 `response`。畸形响应、响应提前关闭、无效协议版本与非超时的连接失败仍为 `SharedADBError`。没有阶段信息的异常保留现有恢复行为。

`server_process.adb_listener_absent` 读取有容量限制的 IPv4 与 IPv6 进程归属表，不打开或终止进程。IPv6 记录布局使用 `ctypes` 原生对齐。查询错误不确认缺席，共享端口上的任何 IPv6 监听都保留可能存在双栈占用的判定。

`SharedADBRecovery._observe` 只对连接阶段超时补充该查询。它通过 `remaining` 传入当前截止时间和取消检查；预算耗尽与取消在任何修改之前清除主机失败证据。`_wait_absent` 与 `_start` 共享此分类并重新获取证据，不信任停止确认或先前的缺席观察。

`SharedADBRecovery` 保留持续故障窗口、主机共享锁、持久化冷却、持锁复探和尝试 generation。确认缺席走现有启动路径，不发送停止请求；未确认的观察保留协调重启的全部条件。

## 概念影响

[INV-06] 评估保留 ADB 服务共享管理、重连恢复上限与模拟器实例绑定的名称、含义和边界。原生监听观察只扩展现有恢复协调器内的实现证据，不增加持久化选择或领域概念。词汇表无需变更。

## 验证

`adb_server_tests.py` 验证统一超时分类和阶段信息，同时保留连接拒绝、畸形响应与非超时失败的行为。

`adb_shared_server_tests.py` 重现超过一秒探测预算才返回的本地连接拒绝，验证冷启动、收到停止确认后和核验进程停止后的启动成功，以及启动前证据改变、原生查询失败、应答超时隔离、取消和预算耗尽。两个应用会话使用生产协调器、原生查询边界和会话 ADB 适配器，验证服务丢失后的同目标注册与截图、触控资源重建。既有持续故障、冷却、未核验停止和跨进程锁回归仍保留在该套件中。

`adb_server_process_tests.py` 替代两种原生表和进程 API，验证空表、IPv4 与 IPv6 监听、无关记录、查询失败、截断的 IPv6 记录以及当前预算下的取消，且不打开进程句柄。既有核验终止回归保持有效。

定向验证还包含 `adb_shared_transport_tests.py`、`device_adb_recovery_tests.py` 与 `scheduler_recovery_preservation_tests.py`，分别覆盖共享路由、应用恢复和待执行任务保留。

上述六个离线套件通过，共 397 个测试和 22 个子测试。全仓库 Ruff 规则检查与格式检查以及 `git diff --check` 均通过。`python scripts/verify_governance.py` 通过，仅有两条既存归档测试引用兼容性警告。在未占用端口上对真实 Windows 表执行的一次只读人工检查确认了查询判定：空表、IPv4 回环与通配监听、IPv6 回环与双栈监听、无关端口，以及由运行中的 ADB 服务占用的共享端口。规范轴与需求轴审查未发现未解决缺陷。套件证据仍以原生 API、socket 与辅助适配器的替代实现为界；未验证真实设备行为。
