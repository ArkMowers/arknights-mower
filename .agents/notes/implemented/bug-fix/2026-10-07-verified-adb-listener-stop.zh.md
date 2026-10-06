---
title: Verified ADB Listener Stop
status: implemented
category: bug-fix
date: 2026-10-07
---

# Verified ADB Listener Stop

## 契约

既有持续无应答握手窗口、锁、冷却与持锁复探准许重启后，协议停止超时仅允许在 Windows 上终止共享端口的已确认占用者，且其可执行文件与所选 ADB 一致。保留进程句柄，防止进程 ID 复用改变终止目标。终止前重新核对端口归属与无应答状态；启动前在既有重连恢复上限内确认端口释放。

## 实现边界

协议拒绝与无效响应不授权强制终止。Windows 兜底使用本机进程和 TCP 表原生接口，不按进程名搜索、不终止进程树、不增加依赖。其他平台、权限不足、端口归属不唯一、可执行文件不一致及端口归属变化均保留有界失败恢复、持久化冷却，并且不启动服务。

[TerminateProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess) 异步终止进程，因此原生停止通过保留的句柄等待完成。[GetExtendedTcpTable](https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getextendedtcptable) 提供监听端口的进程归属。

## 验证

离线测试替换全部 Socket、进程、原生接口与时钟，覆盖卡死的协议停止、精确可执行文件核验、保留句柄清理、身份变化或复用、健康复探、停止信号、超时、终止失败及启动前的端口释放验证。
