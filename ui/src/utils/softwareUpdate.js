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
