// 国服游戏数据，核对日期：2026-09-09。
// 来源：display_meta_table.json → homeBackgroundData.themeList[].tmName，按 sortId 排序。
// https://github.com/Kengxxiao/ArknightsGameData/blob/master/zh_CN/gamedata/excel/display_meta_table.json
// MAA 的 UiTheme 资源只有识别任务和模板，不能用模板目录名作为 SwitchTheme 的中文参数。
const themeNames = [
  '日间',
  '夜间',
  '银凇',
  '迷城',
  '围攻',
  '词祭',
  '滋味',
  '大荒',
  '视相',
  '梦乡',
  '悬想',
  '命运',
  '齐聚',
  '天想',
  '重构',
  '出猎',
  '幽脉',
  '月满'
]

export function getMaaThemeOptions(savedTheme = '') {
  const options = themeNames.map((name) => ({ label: name, value: name }))
  // 保留旧版手动填写的值，避免打开设置页时丢失配置。
  if (savedTheme && !themeNames.includes(savedTheme)) {
    options.push({ label: `${savedTheme}（已保存）`, value: savedTheme })
  }
  return options
}
