export function confirmForceUpdate(dialogs, version, instanceCount, install) {
  return dialogs.warning({
    title: '确认强制更新？',
    content: `将强制切换到 ${version}，覆盖本地源码改动，不备份本地修改，并重启同一安装目录下的 ${instanceCount} 个实例。即使安装失败，本地修改也不会恢复。`,
    positiveText: '确认强制更新',
    negativeText: '取消',
    autoFocus: false,
    onPositiveClick: install
  })
}

export function confirmSourceVersion(dialogs, target, instanceCount, install) {
  return dialogs.warning({
    title: target.force ? '确认强制切换源码版本？' : '确认切换源码版本？',
    content: `将切换到提交 ${target.sha}，重启同一安装目录下的 ${instanceCount} 个实例，重置运行缓存并关闭软件自动更新。配置、专精计划和数据库记录保留；较旧版本可能无法兼容当前配置或恢复任务。${target.force ? '将覆盖本地源码改动，不备份本地修改；即使安装失败，本地修改也不会恢复。' : '安装失败时尝试恢复原版本。'}`,
    positiveText: target.force ? '确认强制切换' : '确认切换',
    negativeText: '取消',
    autoFocus: false,
    onPositiveClick: install
  })
}
