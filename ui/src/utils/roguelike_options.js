// Roguelike 主题与模式枚举（#264）。MAA 集成协议的主题/模式值列表，界面与测试共用；
// 主题补 BlackFlow；模式弃用 2（已移除）与 3（未开放），新增 6/7/30001 及主题限定模式
// 10001/20001。主题限定模式用 theme 字段标注，界面按当前主题过滤。
export const rogue_themes = [
  { label: '傀影与猩红孤钻', value: 'Phantom' },
  { label: '水月与深蓝之树', value: 'Mizuki' },
  { label: '探索者的银凇止境', value: 'Sami' },
  { label: '萨卡兹的无终奇语', value: 'Sarkaz' },
  { label: '界园志异', value: 'JieGarden' },
  { label: '沉沦者的黑流树海', value: 'BlackFlow' }
]

export const mode_list = [
  { label: '刷等级，尽可能稳定地打更多层数', value: 0 },
  { label: '刷源石锭，投资完成后自动退出', value: 1 },
  { label: '刷开局，刷取热水壶或精二干员开局', value: 4 },
  { label: '刷坍缩范式，遇到非稀有坍缩范式后直接重开', value: 5, theme: 'Sami' },
  { label: '刷月度小队，尽可能稳定地打更多层数', value: 6 },
  { label: '刷深入调查，尽可能稳定地打更多层数', value: 7 },
  { label: '快速通过第一层', value: 10001, theme: 'Sarkaz' },
  { label: '刷常乐节点，第一层进洞，找不到需要的节点就重开', value: 20001, theme: 'JieGarden' },
  { label: '刷襁褓动物', value: 30001, theme: 'BlackFlow' }
]

// 黑流树海用独立的三套策略（对照：刷等级快速飞三层 / 刷源石锭 / 刷襁褓动物），
// 不用通用策略列表；其余主题共用通用策略并按主题追加限定策略。
const blackflow_modes = [
  { label: '刷等级，快速飞三层', value: 0 },
  { label: '刷源石锭，投资完成后自动退出', value: 1 },
  { label: '刷襁褓动物', value: 30001 }
]

// 当前主题可选的策略列表：黑流树海走专属列表，其余按 theme 过滤主题限定策略，
// 未标注 theme 的通用策略始终可选。
export function modes_for_theme(theme) {
  if (theme === 'BlackFlow') {
    return blackflow_modes
  }
  return mode_list.filter((m) => !m.theme || m.theme === theme)
}

// 协议字段随所选主题/策略展示的条件（#264）：只在协议明确注明「仅某主题/某模式」的
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
  // 协议注明 collectible_mode_shopping 与 collectible_mode_squad 仅用于策略 4（刷开局）
  collectible_mode_shopping: (theme, mode) => mode === 4,
  collectible_mode_squad: (theme, mode) => mode === 4,
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
  // 协议注明 first_floor_foldartal 仅萨米刷开局模式有效（模型另限模式 4）
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
    { label: '不切换难度', value: -1 },
    { label: `MAX (${max})`, value: 2147483647 }
  ]
  for (let value = 0; value <= max; value++) {
    options.push({ label: `N${value}`, value })
  }
  return options
}
