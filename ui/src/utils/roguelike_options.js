import { i18n } from '@/i18n'
import { itemDisplayName } from '@/i18n/gameNames'
const { t } = i18n.global
// Roguelike 主题与模式枚举。MAA 集成协议的主题/模式值列表，界面与测试共用；
// 主题补 BlackFlow；模式弃用 2（已移除）与 3（未开放），新增 6/7/30001/30003 及主题限定模式
// 10001/20001。主题限定模式用 theme 字段标注，界面按当前主题过滤。
export const rogue_themes = [
  {
    get label() {
      return t('tasks.rogueThemePhantom')
    },
    value: 'Phantom'
  },
  {
    get label() {
      return t('tasks.rogueThemeMizuki')
    },
    value: 'Mizuki'
  },
  {
    get label() {
      return t('tasks.rogueThemeSami')
    },
    value: 'Sami'
  },
  {
    get label() {
      return t('tasks.rogueThemeSarkaz')
    },
    value: 'Sarkaz'
  },
  {
    get label() {
      return t('tasks.rogueThemeJieGarden')
    },
    value: 'JieGarden'
  },
  {
    get label() {
      return t('tasks.rogueThemeBlackFlow')
    },
    value: 'BlackFlow'
  }
]

export const mode_list = [
  {
    get label() {
      return t('tasks.farmLevels')
    },
    value: 0
  },
  {
    get label() {
      return t('tasks.farmIngots')
    },
    value: 1
  },
  {
    get label() {
      return t('tasks.farmStarts')
    },
    value: 4
  },
  {
    get label() {
      return t('tasks.farmParadigms')
    },
    value: 5,
    theme: 'Sami'
  },
  {
    get label() {
      return t('tasks.farmMonthlySquads')
    },
    value: 6
  },
  {
    get label() {
      return t('tasks.farmDeepInvestigations')
    },
    value: 7
  },
  {
    get label() {
      return t('tasks.quickFirstFloor')
    },
    value: 10001,
    theme: 'Sarkaz'
  },
  {
    get label() {
      return t('tasks.farmPlaytime')
    },
    value: 20001,
    theme: 'JieGarden'
  },
  {
    get label() {
      return t('maaActivities.blackflowOpeningMode')
    },
    value: 30003,
    theme: 'BlackFlow'
  },
  {
    get label() {
      return t('tasks.farmSwaddled')
    },
    value: 30001,
    theme: 'BlackFlow'
  }
]

// 黑流树海使用独立策略列表，包含刷等级、投资、培养襁褓动物和刷开局；
// 不用通用策略列表；其余主题共用通用策略并按主题追加限定策略。
const blackflow_modes = [
  {
    get label() {
      return t('maaActivities.blackflowLevelMode')
    },
    value: 0
  },
  {
    get label() {
      return t('tasks.farmIngots')
    },
    value: 1
  },
  {
    get label() {
      return t('tasks.farmSwaddled')
    },
    value: 30001
  },
  {
    get label() {
      return t('maaActivities.blackflowOpeningMode')
    },
    value: 30003
  }
]

// 当前主题可选的策略列表：黑流树海走专属列表，其余按 theme 过滤主题限定策略，
// 未标注 theme 的通用策略始终可选。
export function modes_for_theme(theme) {
  if (theme === 'BlackFlow') {
    return blackflow_modes
  }
  return mode_list.filter((m) => !m.theme || m.theme === theme)
}

// 协议字段随所选主题/策略展示的条件：只在协议明确注明「仅某主题/某模式」的
// 字段上做条件展示，其余字段始终展示。谓词返回 false 则界面隐藏且后端不下发该字段。
export const field_conditions = {
  // 协议注明 stop_at_final_boss 仅适用于除 Phantom 以外的主题，且仅在其策略为 0（刷等级）时下发
  stop_at_final_boss: (theme, mode) => theme !== 'Phantom' && mode === 0,
  // 仅在策略为 0（刷等级）时下发 stop_at_max_level
  stop_at_max_level: (theme, mode) => mode === 0,
  // 协议注明 expected_collapsal_paradigms 仅在主题为 Sami 且策略为 5 时有效
  expected_collapsal_paradigms: (theme, mode) => theme === 'Sami' && mode === 5,
  // 协议注明 stop_when_investment_full 仅在投资源石锭且策略为 1（刷源石锭）时生效；
  // 策略 1 在模式切换时强制开启投资（对照 RoguelikeMode 设置器），此处只判模式
  stop_when_investment_full: (theme, mode) => mode === 1,
  // 普通刷开局显示购物与分队设置；黑流树海刷开局另用准备局分队。
  collectible_mode_shopping: (theme, mode) => mode === 4,
  collectible_mode_squad: (theme, mode) => mode === 4 || (theme === 'BlackFlow' && mode === 30003),
  // 协议注明 collectible_mode_start_list 仅在策略为 4（刷开局）时有效
  collectible_mode_start_list: (theme, mode) => mode === 4,
  // 协议注明 start_with_elite_two 仅适用于模式 4，MAA 在策略为 4 的主题均下发，
  // 值内联主题 Mizuki/Sami 限制（见 elite_two_visible 的分队判断）
  start_with_elite_two: (theme, mode) => mode === 4 && (theme === 'Mizuki' || theme === 'Sami'),
  // 协议注明 only_start_with_elite_two 仅在模式为 4 且 start_with_elite_two 为 true 时有效，
  // 主题同样仅限 Mizuki/Sami
  only_start_with_elite_two: (theme, mode) =>
    mode === 4 && (theme === 'Mizuki' || theme === 'Sami'),
  // 协议注明 refresh_trader_with_dice（指路鳞）仅支持主题 Mizuki
  refresh_trader_with_dice: (theme) => theme === 'Mizuki',
  // 协议注明 investment_with_more_score 仅在策略为 1（刷源石锭）且非黑流树海主题时生效
  investment_with_more_score: (theme, mode) => mode === 1 && theme !== 'BlackFlow',
  // 协议注明 monthly_squad_auto_iterate 与 monthly_squad_check_comms 仅模式 6（月度小队）下发
  monthly_squad_auto_iterate: (theme, mode) => mode === 6,
  monthly_squad_check_comms: (theme, mode) => mode === 6,
  // 协议注明 deep_exploration_auto_iterate 仅模式 7（深入调查）下发
  deep_exploration_auto_iterate: (theme, mode) => mode === 7,
  // 核心仅在萨米刷开局模式读取第一层密文板设置。
  first_floor_foldartal: (theme, mode) => theme === 'Sami' && mode === 4,
  // 协议注明 start_foldartal_list 仅萨米刷开局模式有效（模型另限生活至上分队）
  start_foldartal_list: (theme, mode) => theme === 'Sami' && mode === 4,
  // 协议注明 blackflow_cultivation_target 仅黑流树海刷襁褓动物模式使用
  blackflow_cultivation_target: (theme, mode) => theme === 'BlackFlow' && mode === 30001,
  // 协议注明 find_playTime_target 仅界园刷常乐节点模式下发
  find_playtime_target: (theme, mode) => theme === 'JieGarden' && mode === 20001
}

// 当前主题/策略下某协议字段是否应展示（且应下发）。
export function is_field_enabled(name, theme, mode) {
  const cond = field_conditions[name]
  return cond ? cond(theme, mode) : true
}

// 战术分队类（对照 RoguelikeSquadIsProfessional），凹开局直升精二仅对这类分队生效。
export const professional_squads = ['突击战术分队', '堡垒战术分队', '远程战术分队', '破坏战术分队']

// 凹开局干员直升精二：主题/策略门限由 is_field_enabled 判过，此处再查分队是否战术分队类。
export function elite_two_visible(theme, mode, squad) {
  return (
    is_field_enabled('start_with_elite_two', theme, mode) && professional_squads.includes(squad)
  )
}

// 只凹开局干员直升精二需先勾选直升（对照 RoguelikeOnlyStartWithEliteTwoRaw 的可见条件）。
export function only_elite_two_visible(theme, mode, squad, start) {
  return is_field_enabled('only_start_with_elite_two', theme, mode) && start
}

// 勾选「只凹开局干员直升精二」时奖励选择隐藏（非 Phantom 主题 + 战术分队类，
// 与后端撤销 collectible_mode_start_list 的条件一致）。
export function collectible_start_visible(theme, mode, squad, only, start) {
  return (
    is_field_enabled('collectible_mode_start_list', theme, mode) &&
    !(only && start && theme !== 'Phantom' && professional_squads.includes(squad))
  )
}

// 「只凹需先勾直升」的联动清理规则：直升取消勾选或直升不再可见（主题/策略/分队变化）时，
// 只凹必须一并清除，否则会下发 start_with_elite_two=false 与
// only_start_with_elite_two=true 的组合，被 MAA 核心判定非法。
export function only_elite_two_needs_reset(theme, mode, squad, start, only) {
  return only && (!start || !elite_two_visible(theme, mode, squad))
}

// 通信作为切换依据需先勾选月度小队自动切换（对照 XAML 的可视条件）。
export function monthly_squad_check_comms_visible(theme, mode, auto) {
  return is_field_enabled('monthly_squad_check_comms', theme, mode) && auto
}

// 凹开局板子仅生活至上分队可获得（对照 RoguelikeSquadIsFoldartal）。
export function start_foldartal_visible(theme, mode, squad) {
  return is_field_enabled('start_foldartal_list', theme, mode) && squad === '生活至上分队'
}

// 各主题肉鸽难度范围（对照：萨卡兹/水月/界园 0-18，其余 0-15）。
const difficulty_max = {
  Phantom: 15,
  Mizuki: 18,
  Sami: 15,
  Sarkaz: 18,
  JieGarden: 18,
  BlackFlow: 15
}

// 难度下拉：不切换(-1)、最高难度(MAX)、N0..当前主题最高难度（如 N15/N18）。
// MAX 与 MAA 一致下发 int.MaxValue，由 MAA 核心按主题最大难度处理。
export function difficulty_options(theme) {
  const max = difficulty_max[theme] ?? 15
  const options = [
    {
      get label() {
        return t('tasks.keepDifficulty')
      },
      value: -1
    },
    { label: `MAX (${max})`, value: 2147483647 }
  ]
  for (let value = 0; value <= max; value++) {
    options.push({ label: `N${value}`, value })
  }
  return options
}

// 显示名称按游戏表同 ID 核对；未上线选项使用普通译文，界面语言不改变协议值。
// https://github.com/ArknightsAssets/ArknightsGamedata/tree/a6d4731c10edc58a70ee71b0b77b9f687af13d59
const optionKeys = {
  rogueSquads: {
    集群分队: 'rogue_1_band_2',
    矛头分队: 'rogue_1_band_4',
    研究分队: 'rogue_1_band_9',
    指挥分队: 'rogue_1_band_1',
    后勤分队: 'rogue_1_band_3',
    突击战术分队: 'rogue_1_band_5',
    堡垒战术分队: 'rogue_1_band_6',
    远程战术分队: 'rogue_1_band_7',
    破坏战术分队: 'rogue_1_band_8',
    高规格分队: 'rogue_1_band_10',
    心胜于物分队: 'rogue_2_band_11',
    物尽其用分队: 'rogue_2_band_15',
    以人为本分队: 'rogue_2_band_19',
    永恒狩猎分队: 'rogue_3_band_11',
    生活至上分队: 'rogue_3_band_12',
    科学主义分队: 'rogue_3_band_13',
    特训分队: 'rogue_3_band_9',
    魂灵护送分队: 'rogue_4_band_14',
    博闻广记分队: 'rogue_4_band_16',
    蓝图测绘分队: 'rogue_4_band_18',
    因地制宜分队: 'rogue_4_band_13',
    异想天开分队: 'rogue_4_band_22',
    点刺成锭分队: 'rogue_4_band_20',
    拟态学者分队: 'rogue_4_band_21',
    专业人士分队: 'rogue_4_band_30',
    特勤分队: 'rogue_5_band_3',
    高台突破分队: 'rogue_5_band_11',
    地面突破分队: 'rogue_5_band_12',
    游客分队: 'rogue_5_band_15',
    司岁台分队: 'rogue_5_band_17',
    天师府分队: 'rogue_5_band_19',
    花团锦簇分队: 'rogue_5_band_21',
    棋行险着分队: 'rogue_5_band_22',
    岁影回音分队: 'rogue_5_band_23',
    代理人分队: 'rogue_5_band_24',
    知学分队: 'rogue_5_band_25',
    商贾分队: 'rogue_5_band_26',
    本源研修分队: 'rogue_6_band_14',
    文明开化分队: 'rogue_6_band_15',
    开拓者分队: 'rogue_6_band_17',
    多边贸易分队: 'rogue_6_band_19',
    地质调查分队: 'rogue_6_band_21'
  },
  rogueParadigms: {
    去量化: 'rogue_3_chaos_1',
    去量深化: 'rogue_3_chaos_1_a',
    实质性坍缩: 'rogue_3_chaos_2',
    蔓延性坍缩: 'rogue_3_chaos_2_a',
    非线性移动: 'rogue_3_chaos_3',
    非线性行动: 'rogue_3_chaos_3_a',
    情绪实体: 'rogue_3_chaos_4',
    恐怖实体: 'rogue_3_chaos_4_a',
    泛社会悖论: 'rogue_3_chaos_5',
    泛文明悖论: 'rogue_3_chaos_5_a',
    气压异常: 'rogue_3_chaos_6',
    气压失序: 'rogue_3_chaos_6_a',
    触发性损伤: 'rogue_3_chaos_7',
    触发性危殆: 'rogue_3_chaos_7_a',
    趋同性消耗: 'rogue_3_chaos_8',
    趋同性缺失: 'rogue_3_chaos_8_a',
    目空一些: 'rogue_3_chaos_9',
    睁眼瞎: 'rogue_3_chaos_9_a',
    图像损坏: 'rogue_3_chaos_10',
    一抹黑: 'rogue_3_chaos_10_a'
  },
  rogueAnimals: {
    襁褓中的猫: 'rogue_6_legacy_01',
    襁褓羽蛇: 'rogue_6_legacy_04',
    襁褓中的狗: 'rogue_6_legacy_02',
    襁褓三头犬: 'rogue_6_legacy_03'
  },
  roguePlaytime: {
    掷地有声: 'scene_ro5_ent3_enter',
    种因得果: 'scene_ro5_ent2_enter',
    三缺一: 'scene_ro5_ent1_enter'
  },
  rogueRewards: {
    热水壶: 'rogue_1_relic_r01'
  }
}

export function rogueOptionLabel(category, value) {
  const key = optionKeys[category]?.[value]
  return key ? t(`tasks.${category}.${key}`) : value
}
export const blackflow_animals = [
  {
    get label() {
      return rogueOptionLabel('rogueAnimals', '襁褓中的猫')
    },
    value: 'swaddled_cat'
  },
  {
    get label() {
      return rogueOptionLabel('rogueAnimals', '襁褓中的狗')
    },
    value: 'swaddled_dog'
  },
  {
    get label() {
      return rogueOptionLabel('rogueAnimals', '襁褓三头犬')
    },
    value: 'swaddled_cerberus'
  },
  {
    get label() {
      return rogueOptionLabel('rogueAnimals', '襁褓羽蛇')
    },
    value: 'swaddled_feathered_serpent'
  }
]
// 已有物品译名只用于显示；尚无核实译名的奖励保留原名。
export const blackflow_rewards = [
  ['未编号物', 'unnumbered_item'],
  ['调查预付款', 'survey_advance'],
  ['空间租赁', 'space_lease'],
  ['退行补偿', 'regression_compensation'],
  ['林间代步', 'forest_ride'],
  ['巢寄生', 'nest_parasitism'],
  ['襁褓天马', 'pegasus'],
  ['襁褓骏鹰', 'hippogriff'],
  ['襁褓巨龙', 'dragon'],
  ['襁褓九头蛇', 'hydra'],
  ['襁褓白泽', 'bai_ze'],
  ['襁褓金乌', 'golden_crow']
].map(([label, value], index) => ({
  get label() {
    return itemDisplayName(label)
  },
  value,
  mask: 1 << index
}))
