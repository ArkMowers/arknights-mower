const valueEditors = {
  run_order: 'runorder',
  switch_product: 'base',
  菲亚梅塔: 'base',
  shifit_off: 'base',
  shifit_on: 'base',
  exhaust_on: 'base',
  self_correction: 'base',
  Impart: 'clue',
  clue: 'clue',
  maa_Mall: 'credit',
  recruit: 'recruit',
  skland: 'skland',
  宿舍排序: 'base',
  释放宿舍空位: 'base',
  宿舍补位: 'base',
  技能专精: 'training',
  换协助位: 'training',
  仓库扫描: 'depot',
  加工材料: 'workshop'
}

const nameValues = {
  RUN_ORDER: 'run_order',
  SWITCH_PRODUCT: 'switch_product',
  FIAMMETTA: '菲亚梅塔',
  SHIFT_OFF: 'shifit_off',
  SHIFT_ON: 'shifit_on',
  EXHAUST_OFF: 'exhaust_on',
  SELF_CORRECTION: 'self_correction',
  CLUE_PARTY: 'Impart',
  CLUE: 'clue',
  MAA_MALL: 'maa_Mall',
  NOT_SPECIFIC: '',
  RECRUIT: 'recruit',
  SKLAND: 'skland',
  RE_ORDER: '宿舍排序',
  RELEASE_DORM: '释放宿舍空位',
  FILL_DORM: '宿舍补位',
  REFRESH_TIME: '强制刷新任务时间',
  SKILL_UPGRADE: '技能专精',
  SWAP_SUPPORT: '换协助位',
  DEPOT: '仓库扫描',
  WORKSHOP: '加工材料'
}

const displayEditors = {
  跑单: 'runorder',
  '切换产物/订单': 'base',
  肥鸭: 'base',
  下班: 'base',
  上班: 'base',
  用尽下班: 'base',
  纠错: 'base',
  趴体: 'clue',
  线索任务: 'clue',
  MAA信用购物: 'credit',
  公招: 'recruit',
  森空岛签到: 'skland',
  宿舍排序: 'base',
  释放宿舍空位: 'base',
  宿舍补位: 'base',
  技能专精: 'training',
  换协助位: 'training',
  仓库扫描: 'depot',
  加工材料: 'workshop',
  基建换班: 'base',
  收取订单: 'base',
  无人机加速: 'drone'
}

export function getTaskEditor(task) {
  const type = task?.type
  const value =
    typeof type === 'string'
      ? type
      : (type?._value_ ?? type?.value ?? nameValues[type?._name_ ?? type?.name])
  if (value === '强制刷新任务时间') {
    return task.recovery_observation_rooms?.length ? 'base' : 'runorder'
  }
  if (value !== undefined && value !== '') {
    return Object.hasOwn(valueEditors, value) ? valueEditors[value] : null
  }
  const display = typeof type === 'object' ? type?.display_value : undefined
  if (display === '强制刷新任务时间') {
    return task.recovery_observation_rooms?.length ? 'base' : 'runorder'
  }
  if (Object.hasOwn(displayEditors, display)) return displayEditors[display]
  if ((!value && !display) || display === '空任务') {
    return Object.keys(task?.plan ?? {}).length ? 'base' : null
  }
  return null
}

export function getEditorQueue(queue, editorId) {
  return queue.filter((task) => getTaskEditor(task) === editorId)
}
