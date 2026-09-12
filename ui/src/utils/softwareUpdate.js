export function confirmSoftwareInstall(
  dialogs,
  currentVersion,
  selection,
  instanceCount,
  install,
  cancel = () => {}
) {
  const target = { ...selection }
  return dialogs.warning({
    title: target.confirm_title || (target.downgrade ? '确认回退版本？' : '确认安装并重启？'),
    content:
      target.confirm_message ||
      `${target.source_repo ? `将使用仓库 ${target.source_repo}。` : ''}${target.downgrade ? `将从 ${currentVersion} 回退到 ${target.version}。旧版可能无法兼容当前配置或恢复任务。` : `将安装 ${target.version}。`}重启同一安装目录下的 ${instanceCount} 个实例，重置运行缓存；安装失败时尝试恢复原版本。${target.force ? '将覆盖本地源码改动，不备份本地修改；即使安装失败，本地修改也不会恢复。' : ''}`,
    positiveText: target.downgrade ? '确认回退' : '确认安装',
    negativeText: '取消',
    autoFocus: false,
    onNegativeClick: cancel,
    onClose: cancel,
    onMaskClick: cancel,
    onPositiveClick: () => install({ ...target, confirm_downgrade: target.downgrade === true })
  })
}

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
    content: `${target.source_repo ? `将使用仓库 ${target.source_repo}${target.source_pr ? ` 的 PR #${target.source_pr}` : ''}。` : ''}${target.base_commit ? `包含目标分支 ${target.source_branch} 的 ${target.base_commit} 与所选 PR 的 GitHub 合并结果。` : ''}将切换到提交 ${target.sha}，重启同一安装目录下的 ${instanceCount} 个实例，重置运行缓存并关闭软件自动更新。配置、专精计划和数据库记录保留；较旧版本可能无法兼容当前配置或恢复任务。${target.force ? '将覆盖本地源码改动，不备份本地修改；即使安装失败，本地修改也不会恢复。' : '安装失败时尝试恢复原版本。'}`,
    positiveText: target.force ? '确认强制切换' : '确认切换',
    negativeText: '取消',
    autoFocus: false,
    onPositiveClick: install
  })
}
