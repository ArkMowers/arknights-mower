export const groupRestingMessages = {
  'zh-CN': {
    title: '各组心情阈值',
    helpTitle: '各组心情阈值说明',
    productSwitchingHelp: '对于需要切换产物的大组，建议单独调低心情阈值，以减少产物频繁切换。',
    inheritanceHelp:
      '未设置的组和未绑组干员沿用上方心情阈值。主表、副表按相同组名应用，移除后恢复全局值。',
    shiftOffHelp: '普通下班线和急救线均按组阈值换算，多绑组干员独立休息时沿用全局值。',
    maintenanceHelp: '大版本维护前的准备时段，所有组统一使用维护阈值。',
    maintenanceRuntimeHelp: '维护前的准备时段，所有组统一使用此阈值，结束后恢复日常及各组设置',
    thresholdLabel: '{group}心情阈值',
    chooseGroup: '选择单独设置的绑组',
    groupSelectionLabel: '单独设置心情阈值的绑组'
  },
  'en-US': {
    title: 'Group morale thresholds',
    helpTitle: 'About group morale thresholds',
    productSwitchingHelp:
      'For large groups that switch products, a lower group threshold is recommended to reduce frequent product changes.',
    inheritanceHelp:
      'Groups without an override and ungrouped operators use the morale threshold above. The same group name shares its setting across the main and backup plans. Removing an override restores the global value.',
    shiftOffHelp:
      'Normal shift-off and rescue thresholds are calculated from the group threshold. Operators with multiple group bindings use the global value when resting independently.',
    maintenanceHelp:
      'During preparation for major maintenance, all groups use the maintenance threshold.',
    maintenanceRuntimeHelp:
      'During the preparation window, all groups use this threshold. The normal global and group settings resume when the window ends.',
    thresholdLabel: '{group} morale threshold',
    chooseGroup: 'Select a group to set separately',
    groupSelectionLabel: 'Group with a separate morale threshold'
  },
  'ja-JP': {
    title: 'グループ別の体力閾値',
    helpTitle: 'グループ別の体力閾値について',
    productSwitchingHelp:
      '生産品を切り替える大きなグループでは、頻繁な切り替えを減らすため、そのグループの体力閾値を低めに設定することをおすすめします。',
    inheritanceHelp:
      '個別設定のないグループと未所属のオペレーターには、上の体力閾値を適用します。主表・補助表で同じグループ名には同じ設定を使います。個別設定を削除すると全体設定に戻ります。',
    shiftOffHelp:
      '通常の退勤閾値と救急閾値は、グループの閾値から計算します。複数のグループに所属するオペレーターが単独で休息する場合は全体設定を使います。',
    maintenanceHelp:
      '大型メンテナンス前の準備期間は、全グループにメンテナンス用の閾値を適用します。',
    maintenanceRuntimeHelp:
      'メンテナンス前の準備期間は全グループにこの閾値を適用し、期間終了後は通常の全体設定とグループ別設定に戻します',
    thresholdLabel: '{group}の体力閾値',
    chooseGroup: '個別に設定するグループを選択',
    groupSelectionLabel: '体力閾値を個別に設定するグループ'
  },
  'zh-TW': {
    title: '各組心情閾值',
    helpTitle: '各組心情閾值說明',
    productSwitchingHelp: '對於需要切換產物的大組，建議單獨調低心情閾值，以減少產物頻繁切換。',
    inheritanceHelp:
      '未設定的組和未綁組幹員沿用上方心情閾值。主表、副表按相同組名套用，移除後恢復全域值。',
    shiftOffHelp: '一般下班線和急救線均按組閾值換算，多綁組幹員獨立休息時沿用全域值。',
    maintenanceHelp: '大型版本維護前的準備時段，所有組統一使用維護閾值。',
    maintenanceRuntimeHelp: '維護前的準備時段，所有組統一使用此閾值，結束後恢復日常及各組設定',
    thresholdLabel: '{group}心情閾值',
    chooseGroup: '選擇單獨設定的綁組',
    groupSelectionLabel: '單獨設定心情閾值的綁組'
  }
}
