const groups = [
  { id: 'base', label: '基建任务' },
  { id: 'daily', label: '日常任务' },
  { id: 'combat', label: '作战与空闲' },
  { id: 'support', label: '运行配置' },
  { id: 'mower', label: '界面与维护' }
]

const editorDefinitions = [
  ['mower-interface', '界面与窗口', '设置主题、界面缩放、版本显示与桌面窗口。'],
  ['mower-notifications', '通知与助手', '设置邮件通知和 Mower AI 助手。'],
  ['mower-profiles', '档案与运行', '导入档案时选择保留内容，导出当前档案，或重启续接任务。'],
  ['mower-updates', '网络与更新', '设置网络代理，检查和更新 Mower、MAA 本体与资源。'],
  ['mower-data', '数据与维护', '管理仓库历史、截图与报错归档、完整备份与恢复。'],
  ['intervals', '执行间隔', '设置日常任务、刷理智、仓库扫描与制造站补货的执行间隔。'],
  ['device', '连接与启动', '连接设备，设置截图、触控、游戏启动与任务空档时的动作。'],
  ['runtime', '运行参数', '设置截图间隔、选人采样和页面等待时间。'],
  ['accounts', '账号与数据来源', '管理森空岛账号、同步设置和收益统计口径。'],
  ['maa', 'MAA 核心', '设置 MAA 安装目录、连接方式和游戏主题恢复。'],
  ['base', '自动救急', '设置自动救急，驻员、跑单和菲亚梅塔充能由排班表管理。'],
  ['runorder', '跑单', '设置跑单提前量、葛朗台跑单和返回主界面选项。'],
  [
    'drone',
    '无人机加速',
    '选择加速房间和无人机使用阈值；未指定房间时仍按排班加速符合条件的贸易站。'
  ],
  ['clue', '线索搜集与交流', '设置线索收集、交流与多余线索赠送。'],
  ['workshop', '加工站合成', '管理加工干员、材料与成品库存条件，每条加工配置分别启用。'],
  ['training', '技能专精', '前往养成规划管理专精计划与全自动专精设置。'],
  ['trust', '自动切换信赖', '设置基建副手与活动室的信赖检查和替换条件。'],
  ['credit', '访友与信用', '分别选择访友和购物的执行方式，设置信用作战与购买偏好。'],
  ['visit', '访问好友', '选择由 Mower 或 MAA 访问好友并收取信用。'],
  ['credit-fight', '信用作战', '设置由 MAA 完成的信用作战及所用队伍。'],
  ['shop', '信用商店购物', '选择购物的执行方式，设置优先购买名单与购买策略。'],
  ['report', '读取基报', '设置是否每天读取基建报告。'],
  ['skland', '森空岛签到', '选择需要签到的账号、游戏和区服。'],
  ['mail', '领取邮件', '设置是否由 Mower 每天领取游戏邮件。'],
  ['event-sign-in', '活动签到', '领取游戏内七日签到活动中已满足登录天数的奖励。'],
  ['recruit', '公开招募', '设置三星招募阈值、五星招募策略和支援机械标签处理。'],
  ['depot', '仓库物品混合读取', '设置仓库读取，扫描结果用于材料库存与养成计划。'],
  ['stage-plan', '刷理智', '选择执行方式、每日关卡、理智药和库存规则。'],
  ['rewards', 'MAA 领取奖励', '任务奖励随 MAA 日常领取，邮件、免费单抽与活动奖励分别勾选。'],
  [
    'long',
    '空闲长任务',
    '选择集成战略、保全派驻、生息演算或隐秘战线，并设置参数与每天可启动的时段。'
  ],
  ['idle', '空闲动作', '设置等待下一项任务时如何处理游戏与模拟器。']
]

const taskDefinitions = [
  ['base', 'base'],
  ['runorder', 'base'],
  ['drone', 'base'],
  ['clue', 'base'],
  ['workshop', 'base'],
  ['training', 'base'],
  ['trust', 'daily'],
  ['skland', 'daily'],
  ['mail', 'daily'],
  ['event-sign-in', 'daily'],
  ['report', 'daily'],
  ['recruit', 'daily'],
  ['depot', 'daily'],
  ['visit', 'daily'],
  ['credit-fight', 'daily'],
  ['shop', 'daily'],
  ['rewards', 'daily'],
  ['stage-plan', 'combat'],
  ['long', 'combat'],
  ['intervals', 'support'],
  ['runtime', 'support'],
  ['accounts', 'support'],
  ['maa', 'support'],
  ['mower-interface', 'mower'],
  ['mower-notifications', 'mower'],
  ['mower-profiles', 'mower'],
  ['mower-updates', 'mower'],
  ['mower-data', 'mower']
]

// 目录的补充词来自对应编辑器中的字段和常用名称，条件字段也可用于定位所属配置。
const editorKeywords = {
  'mower-interface':
    '主题 暗色 亮色 跟随系统 界面缩放 软件版本 版本类型 语言 版本水印 显示水印 隐藏水印 关闭窗口 托盘 启动时窗口状态',
  'mower-notifications': '邮件 SMTP QQ 通知 发件人 收件人 Mower AI 助手 自定义模型 API 密钥',
  'mower-profiles': '档案 选择保留内容 导入 导出 重启续接 重启 Mower 进程 结束 退出',
  'mower-updates': 'Mower MAA 本体 资源 网络 更新 Mirror酱 CDK 代理 下载源 更新源 自动更新',
  'mower-data': '仓库历史 截图 保存 报错归档 容量 空间 完整备份 恢复 数据库',
  device:
    '设备 模拟器 ADB 截图 触控 MuMu 性能适配 恢复 超时 重试 选择实例 旋转截图 截图命令 启动游戏 点击坐标 启动命令 自定义命令启动 空闲动作 关闭MuMu模拟器12时断开该实例的adb连接 启动后自动开始任务',
  intervals: '日常任务间隔 MAA 日常 制造站补货',
  runtime: '截图最短间隔 选人采样间隔 操作反馈超时 等待时间 截图间隔 等待次数',
  accounts: '森空岛账号 一图流干员同步 OAuth token 收益统计',
  maa: 'MAA目录 连接配置 触控模式 恢复主题 目标主题',
  base: '换班 排班 轮班 自动救急 救急排班',
  runorder: '跑单前置延时 葛朗台跑单 葛朗台缓冲时间 跑单前返回主界面',
  drone: '无人机使用房间 无人机使用阈值 无人机加速间隔 制造站 贸易站',
  clue: '线索 收集 交流 赠送 雷锋模式',
  workshop: '加工 合成 材料 成品 无缝合成',
  training: '全自动专精 养成规划 训练室',
  trust: '信赖 副手 活动室 优先信赖阈值',
  skland: '森空岛 签到 终末地 官服 Bilibili',
  mail: '邮件 领取 游戏内邮件',
  'event-sign-in': '活动 签到 登录 七日 奖励 补领',
  report: '日报 报告 基建报告',
  recruit:
    '招募 招聘 公招券 三星招募阈值 五星招募策略 手动选择 五星词条组合唯一时自动选择 保留支援机械标签',
  depot: '仓库 扫描 库存 混合读取',
  visit: '访友 好友 处理方式 访友执行方式 Mower MAA',
  'credit-fight': '信用作战 编队 队伍',
  shop: '购物 采购 商店 处理方式 购物执行方式 按需领取信用 按性价比购物 购物性价比阈值 理智/信用 只购买折扣物品 保留最大信用点（低于 300 停止购买） 停止购买 无视黑名单继续购买，直至不再溢出 优先购买 黑名单 信用溢出 Mower MAA',
  'stage-plan':
    '刷图 关卡 战斗 周计划 理智药 临期 药 有效期 库存 上报至企鹅物流 上报至一图流 关卡体力默认值 每次吃药 MAA Mower',
  rewards: '邮件奖励 免费单抽 幸运墙 合成玉 限时开采许可 赠送月卡 五周年月卡',
  long: [
    '集成战略 保全派驻 生息演算 隐秘战线 肉鸽主题 开局分队 开局职业组 开局干员 难度 策略 开始时间 停止时间',
    '凹开局干员直升精二 只凹开局干员直升精二，不进行作战 开局干员使用助战 开局干员使用非好友助战 月度小队自动切换 将月度小队通信也作为切换依据 深入调查自动切换 刷新商店（指路鳞） 坍缩范式',
    '到达险路恶敌前停止 肉鸽等级刷满后停止 投资源石锭 源石锭投资满时停止 投资模式启用购物、招募、进2层 烧水时启用购物 烧水分队 第一层远见板子 凹开局板子 刷开局期望奖励 目标襁褓动物 目标常乐节点',
    '关卡 导能单元 导入作业 作业信息',
    '沙洲遗闻 重启锚点 支援道具名称 增加方式 单次最大组装轮数',
    '超时时长 选择路线'
  ].join(' ')
}

const taskSwitches = {
  clue: 'enable_party',
  training: 'enable_mastery',
  trust: 'trust_rotation_enable',
  skland: 'skland_enable',
  mail: 'check_mail_enable',
  'event-sign-in': 'event_sign_in_enable',
  report: 'report_enable',
  recruit: 'recruit_enable',
  depot: 'maa_depot_enable',
  visit: 'visit_friend_enable',
  'credit-fight': 'maa_credit_fight',
  shop: 'maa_mall_enable',
  'stage-plan': 'stage_plan_enable',
  long: 'maa_rg_enable'
}

const maaRewardFields = [
  'maa_mail',
  'maa_recruit',
  'maa_orundum',
  'maa_mining',
  'maa_specialaccess'
]

export function getMaaRewardSelection(config) {
  const checked = maaRewardFields.every((key) => Boolean(config[key]))
  return {
    checked,
    indeterminate: !checked && maaRewardFields.some((key) => Boolean(config[key]))
  }
}

export function createTaskWorkflow(config) {
  const hiddenEditors = new Set(
    config.manager_owned_device
      ? [
          'device',
          'idle',
          'runtime',
          ...(config.extra_settings_visible === true ? [] : ['mower-updates', 'mower-data'])
        ]
      : []
  )
  const editors = editorDefinitions
    .filter(([id]) => !hiddenEditors.has(id))
    .map(([id, title, description]) => ({
      id,
      title,
      description:
        config.manager_owned_device && id === 'maa' ? '设置 MAA 恢复主题与目标主题。' : description,
      searchKeywords:
        config.manager_owned_device && id === 'maa'
          ? 'MAA 恢复主题 目标主题'
          : editorKeywords[id] || ''
    }))
  const rewardSelection = getMaaRewardSelection(config)
  const tasks = taskDefinitions
    .filter(([id]) => !hiddenEditors.has(id))
    .map(([id, group]) => {
      const editor = editors.find((entry) => entry.id === id)
      return {
        id,
        editor: id,
        title: editor.title,
        description: editor.description,
        searchKeywords: editor.searchKeywords,
        group,
        mode:
          id === 'rewards' ? 'aggregate' : Object.hasOwn(taskSwitches, id) ? 'switch' : 'automatic',
        ...(id === 'rewards' ? { indeterminate: rewardSelection.indeterminate } : {})
      }
    })
  const workshopSettings = config.workshop_manual_settings ?? config.workshop_settings ?? []
  const statuses = Object.fromEntries(
    tasks.map((task) => {
      if (task.id === 'long')
        return [task.id, config.maa_rg_enable === true || config.maa_rg_enable === 1]
      if (Object.hasOwn(taskSwitches, task.id))
        return [task.id, Boolean(config[taskSwitches[task.id]])]
      if (task.id === 'workshop') return [task.id, workshopSettings.some((entry) => entry.enabled)]
      if (task.id === 'rewards') return [task.id, rewardSelection.checked]
      return [task.id, true]
    })
  )
  return { groups, tasks, editors, statuses }
}

export function setTaskEnabled(config, id, value) {
  if (id === 'rewards') {
    for (const key of maaRewardFields) config[key] = Boolean(value)
    return true
  }
  if (!Object.hasOwn(taskSwitches, id)) return false
  config[taskSwitches[id]] = id === 'long' ? (value ? 1 : 0) : Boolean(value)
  return true
}
