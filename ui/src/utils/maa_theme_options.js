import { i18n } from '@/i18n'
const { t } = i18n.global

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
  const options = themeNames.map((name) => ({
    get label() {
      return t(`tasks.maaThemes.${themeKeys[name]}`)
    },
    value: name
  }))
  // 保留旧版手动填写的值，避免打开设置页时丢失配置。
  if (savedTheme && !themeNames.includes(savedTheme)) {
    options.push({ label: t('tasks.savedTheme', { theme: savedTheme }), value: savedTheme })
  }
  return options
}

// 各语言按 display_meta_table 的同一主题 ID 取显示名；尚未上线的主题保留选项并提供译文。
// https://github.com/ArknightsAssets/ArknightsGamedata/tree/a6d4731c10edc58a70ee71b0b77b9f687af13d59
const themeKeys = {
  日间: 'tm_rhodes_day',
  夜间: 'tm_rhodes_night',
  银凇: 'tm_rogue_3',
  迷城: 'tm_mainline_1',
  围攻: 'tm_rainbowsix_1',
  词祭: 'tm_rogue_4',
  滋味: 'tm_dungeon_1',
  大荒: 'tm_sui_1',
  视相: 'tm_arcade_1',
  梦乡: 'tm_volcano_1',
  悬想: 'tm_rogue_5',
  命运: 'tm_avemujica_1',
  齐聚: 'tm_sanrio_1',
  天想: 'tm_lonetrail_1',
  重构: 'tm_kaltsit_1',
  出猎: 'tm_hunter_1',
  幽脉: 'tm_rogue_6',
  月满: 'tm_p3r_1'
}
