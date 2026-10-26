// 离线预览的养成规划示例，使用公开干员资料和虚构练度，不代表真实账号。
// 技能、模组按逐级材料种子生成详情；库存、配方和统计只定义一次。
// 这些计算只服务界面预览，不用于真实账号的材料核算或自动合成。

const MATERIALS = {
  3211: { name: '先锋芯片', owned: 90, rarity: 3 },
  3212: { name: '先锋芯片组', owned: 55, rarity: 4 },
  3213: { name: '先锋双芯片', owned: 9, rarity: 5 },
  3221: { name: '近卫芯片', owned: 0, rarity: 3 },
  3223: { name: '近卫双芯片', owned: 9, rarity: 5 },
  3231: { name: '重装芯片', owned: 90, rarity: 3 },
  3232: { name: '重装芯片组', owned: 55, rarity: 4 },
  3233: { name: '重装双芯片', owned: 0, rarity: 5 },
  3241: { name: '狙击芯片', owned: 0, rarity: 3 },
  3243: { name: '狙击双芯片', owned: 0, rarity: 5 },
  3251: { name: '术师芯片', owned: 0, rarity: 3 },
  3253: { name: '术师双芯片', owned: 0, rarity: 5 },
  3261: { name: '医疗芯片', owned: 0, rarity: 3 },
  3263: { name: '医疗双芯片', owned: 9, rarity: 5 },
  3271: { name: '辅助芯片', owned: 0, rarity: 3 },
  3273: { name: '辅助双芯片', owned: 0, rarity: 5 },
  3281: { name: '特种芯片', owned: 0, rarity: 3 },
  3283: { name: '特种双芯片', owned: 9, rarity: 5 },
  3301: { name: '技巧概要·卷1', owned: 460, rarity: 2 },
  3302: { name: '技巧概要·卷2', owned: 230, rarity: 3 },
  3303: { name: '技巧概要·卷3', owned: 72, rarity: 4 },
  4001: { name: '龙门币', owned: 4800000, rarity: 1 },
  30011: { name: '源岩', owned: 2400, rarity: 1 },
  30012: { name: '固源岩', owned: 900, rarity: 2 },
  30013: { name: '固源岩组', owned: 260, rarity: 3 },
  30014: { name: '提纯源岩', owned: 9, rarity: 4 },
  30021: { name: '代糖', owned: 0, rarity: 1 },
  30022: { name: '糖', owned: 900, rarity: 2 },
  30023: { name: '糖组', owned: 260, rarity: 3 },
  30024: { name: '糖聚块', owned: 12, rarity: 4 },
  30031: { name: '酯原料', owned: 0, rarity: 1 },
  30032: { name: '聚酸酯', owned: 900, rarity: 2 },
  30033: { name: '聚酸酯组', owned: 260, rarity: 3 },
  30034: { name: '聚酸酯块', owned: 70, rarity: 4 },
  30041: { name: '异铁碎片', owned: 0, rarity: 1 },
  30042: { name: '异铁', owned: 900, rarity: 2 },
  30043: { name: '异铁组', owned: 260, rarity: 3 },
  30044: { name: '异铁块', owned: 15, rarity: 4 },
  30051: { name: '双酮', owned: 2400, rarity: 1 },
  30052: { name: '酮凝集', owned: 900, rarity: 2 },
  30053: { name: '酮凝集组', owned: 260, rarity: 3 },
  30054: { name: '酮阵列', owned: 5, rarity: 4 },
  30061: { name: '破损装置', owned: 2400, rarity: 1 },
  30062: { name: '装置', owned: 900, rarity: 2 },
  30063: { name: '全新装置', owned: 260, rarity: 3 },
  30064: { name: '改量装置', owned: 8, rarity: 4 },
  30073: { name: '扭转醇', owned: 260, rarity: 3 },
  30074: { name: '白马醇', owned: 9, rarity: 4 },
  30083: { name: '轻锰矿', owned: 260, rarity: 3 },
  30084: { name: '三水锰矿', owned: 12, rarity: 4 },
  30093: { name: '研磨石', owned: 260, rarity: 3 },
  30094: { name: '五水研磨石', owned: 10, rarity: 4 },
  30103: { name: 'RMA70-12', owned: 260, rarity: 3 },
  30104: { name: 'RMA70-24', owned: 7, rarity: 4 },
  30115: { name: '聚合剂', owned: 8, rarity: 5 },
  30125: { name: '双极纳米片', owned: 0, rarity: 5 },
  30135: { name: 'D32钢', owned: 2, rarity: 5 },
  30145: { name: '晶体电子单元', owned: 1, rarity: 5 },
  30155: { name: '烧结核凝晶', owned: 0, rarity: 5 },
  30165: { name: '重相位对映体', owned: 1, rarity: 5 },
  31013: { name: '凝胶', owned: 260, rarity: 3 },
  31014: { name: '聚合凝胶', owned: 70, rarity: 4 },
  31023: { name: '炽合金', owned: 260, rarity: 3 },
  31024: { name: '炽合金块', owned: 70, rarity: 4 },
  31033: { name: '晶体元件', owned: 260, rarity: 3 },
  31034: { name: '晶体电路', owned: 70, rarity: 4 },
  31043: { name: '半自然溶剂', owned: 260, rarity: 3 },
  31044: { name: '精炼溶剂', owned: 70, rarity: 4 },
  31053: { name: '化合切削液', owned: 260, rarity: 3 },
  31054: { name: '切削原液', owned: 70, rarity: 4 },
  31063: { name: '转质盐组', owned: 0, rarity: 3 },
  31064: { name: '转质盐聚块', owned: 70, rarity: 4 },
  31073: { name: '褐素纤维', owned: 0, rarity: 3 },
  31074: { name: '固化纤维板', owned: 5, rarity: 4 },
  31083: { name: '环烃聚质', owned: 260, rarity: 3 },
  31084: { name: '环烃预制体', owned: 4, rarity: 4 },
  31093: { name: '类凝结核', owned: 260, rarity: 3 },
  31094: { name: '手性屈光体', owned: 2, rarity: 4 },
  mod_unlock_token: { name: '模组数据块', owned: 20, rarity: 5 },
  growth_exp: { name: '作战记录经验', owned: 2820000, rarity: 1 },
  mod_update_token_1: { name: '数据增补条', owned: 80, rarity: 4 },
  mod_update_token_2: { name: '数据增补仪', owned: 20, rarity: 5 }
}

const RECIPES = {
  30014: [['30013', 4]],
  30024: [
    ['30023', 2],
    ['30043', 1],
    ['30083', 1]
  ],
  30034: [
    ['30033', 2],
    ['30053', 1],
    ['30073', 1]
  ],
  30044: [
    ['30043', 2],
    ['30063', 1],
    ['30033', 1]
  ],
  30054: [
    ['30053', 2],
    ['30023', 1],
    ['30083', 1]
  ],
  30064: [
    ['30013', 2],
    ['30063', 1],
    ['30093', 1]
  ],
  30074: [
    ['30023', 1],
    ['30073', 1],
    ['30103', 1]
  ],
  30084: [
    ['30083', 2],
    ['30073', 1],
    ['30033', 1]
  ],
  30094: [
    ['30093', 1],
    ['30043', 1],
    ['30063', 1]
  ],
  30104: [
    ['30013', 2],
    ['30103', 1],
    ['30053', 1]
  ],
  30115: [
    ['30014', 1],
    ['30044', 1],
    ['30054', 1]
  ],
  30125: [
    ['30074', 2],
    ['30064', 1]
  ],
  30135: [
    ['30084', 1],
    ['30094', 1],
    ['30104', 1]
  ],
  30145: [
    ['31014', 2],
    ['31024', 1],
    ['31034', 1]
  ],
  30155: [
    ['31064', 1],
    ['31054', 1],
    ['31044', 2]
  ],
  30165: [
    ['31094', 2],
    ['31084', 1],
    ['31074', 1]
  ],
  31014: [
    ['30043', 1],
    ['31013', 1],
    ['31023', 1]
  ],
  31024: [
    ['31023', 1],
    ['30063', 1],
    ['30093', 1]
  ],
  31034: [
    ['31033', 2],
    ['31013', 1],
    ['31023', 1]
  ],
  31044: [
    ['31043', 1],
    ['31053', 1],
    ['31013', 1]
  ],
  31054: [
    ['31053', 1],
    ['31033', 1],
    ['30103', 1]
  ],
  31064: [
    ['31063', 1],
    ['31043', 1],
    ['30023', 1]
  ],
  31074: [
    ['31073', 1],
    ['30033', 2],
    ['30013', 1]
  ],
  31084: [
    ['31083', 1],
    ['31073', 1],
    ['31063', 1]
  ],
  31094: [
    ['31093', 1],
    ['31083', 1],
    ['30023', 1]
  ]
}

const OPERATORS = [
  {
    char_id: 'char_2023_ling',
    name: '令',
    rarity: 6,
    profession: 'SUPPORT',
    sub_profession: 'summoner',
    elite: 2,
    level: 40,
    main_skill_level: 6,
    skill_levels: [0, 0, 0],
    mastery_error:
      '基础技能仅 6 级，可加入养成计划；升至 7 级后，请前往「养成规划」页面手动点击「刷新」后再执行专精',
    material_error: null,
    potential: 2,
    promotion_target: 2,
    max_phase: 2,
    max_level: 90,
    module_level: 60,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·重进酒',
        skill_icon_id: 'skchr_ling_1',
        current_level: 0,
        costs: [
          { 3303: 8, 30103: 5, 31024: 4 },
          { 3303: 12, 30064: 6, 31054: 4 },
          { 3303: 15, 30115: 6, 31024: 6 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·笑鸣瑟',
        skill_icon_id: 'skchr_ling_2',
        current_level: 0,
        costs: [
          { 3303: 8, 30044: 4, 31043: 3 },
          { 3303: 12, 31014: 9, 31044: 4 },
          { 3303: 15, 30014: 4, 30145: 6 }
        ]
      },
      {
        skill_index: 2,
        skill_name: '三技能·宁作吾',
        skill_icon_id: 'skchr_ling_3',
        current_level: 0,
        costs: [
          { 3303: 8, 30054: 4, 31013: 4 },
          { 3303: 12, 30014: 4, 30094: 9 },
          { 3303: 15, 30135: 6, 31014: 6 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_ling',
        name: '诗短梦长',
        type: 'SUM-Y',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30145: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30135: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30115: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', costs: null },
      {
        id: 'elite2_module',
        elite: 2,
        level: 60,
        label: '精二 60 级',
        costs: { 4001: 113303, growth_exp: 134150 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 90,
        label: '精二 90 级',
        costs: { 4001: 686690, growth_exp: 657264 }
      }
    ],
    basic_costs: { 3303: 8, 30013: 5, 30063: 4 }
  },
  {
    char_id: 'char_4087_ines',
    name: '伊内丝',
    rarity: 6,
    profession: 'PIONEER',
    sub_profession: 'agent',
    elite: 2,
    level: 55,
    main_skill_level: 7,
    skill_levels: [1, 0, 0],
    mastery_error: null,
    material_error: null,
    potential: 3,
    promotion_target: 2,
    max_phase: 2,
    max_level: 90,
    module_level: 60,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·淬影突袭',
        skill_icon_id: 'skchr_ines_1',
        current_level: 1,
        costs: [
          { 3303: 12, 30084: 8, 30094: 4 },
          { 3303: 15, 30115: 6, 31064: 6 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·暗夜无明',
        skill_icon_id: 'skchr_ines_2',
        current_level: 0,
        costs: [
          { 3303: 8, 30094: 4, 31033: 7 },
          { 3303: 12, 31014: 9, 31024: 4 },
          { 3303: 15, 30054: 5, 30125: 6 }
        ]
      },
      {
        skill_index: 2,
        skill_name: '三技能·独影归途',
        skill_icon_id: 'skchr_ines_3',
        current_level: 0,
        costs: [
          { 3303: 8, 30023: 8, 31054: 4 },
          { 3303: 12, 30044: 5, 30064: 4 },
          { 3303: 15, 30135: 6, 31044: 6 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_ines',
        name: '角部“护理”套组',
        type: 'AGE-Y',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30145: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30165: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30115: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', costs: null },
      {
        id: 'elite2_module',
        elite: 2,
        level: 60,
        label: '精二 60 级',
        costs: { 4001: 36721, growth_exp: 40600 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 90,
        label: '精二 90 级',
        costs: { 4001: 610108, growth_exp: 563714 }
      }
    ],
    basic_costs: null
  },
  {
    char_id: 'char_350_surtr',
    name: '史尔特尔',
    rarity: 6,
    profession: 'WARRIOR',
    sub_profession: 'artsfghter',
    elite: 2,
    level: 30,
    main_skill_level: 7,
    skill_levels: [1, 0, 0],
    mastery_error: null,
    material_error: null,
    potential: 4,
    promotion_target: 2,
    max_phase: 2,
    max_level: 90,
    module_level: 60,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·烈焰魔剑',
        skill_icon_id: 'skchr_surtr_1',
        current_level: 1,
        costs: [
          { 3303: 12, 30054: 4, 31014: 9 },
          { 3303: 15, 30064: 4, 30135: 6 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·熔核巨影',
        skill_icon_id: 'skchr_surtr_2',
        current_level: 0,
        costs: [
          { 3303: 8, 30083: 5, 30104: 4 },
          { 3303: 12, 30054: 8, 30074: 4 },
          { 3303: 15, 30104: 5, 30125: 6 }
        ]
      },
      {
        skill_index: 2,
        skill_name: '三技能·黄昏',
        skill_icon_id: 'skchr_surtr_3',
        current_level: 0,
        costs: [
          { 3303: 8, 30014: 4, 30093: 7 },
          { 3303: 12, 30074: 9, 30094: 4 },
          { 3303: 15, 30135: 6, 31014: 6 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_surtr',
        name: '萨米的不灭心脏碎片',
        type: 'AFT-X',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30135: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30155: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30145: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      },
      {
        id: 'uniequip_003_surtr',
        name: '旅游必需品',
        type: 'AFT-Y',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30115: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30155: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30145: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', costs: null },
      {
        id: 'elite2_module',
        elite: 2,
        level: 60,
        label: '精二 60 级',
        costs: { 4001: 142692, growth_exp: 175875 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 90,
        label: '精二 90 级',
        costs: { 4001: 716079, growth_exp: 698989 }
      }
    ],
    basic_costs: null
  },
  {
    char_id: 'char_179_cgbird',
    name: '夜莺',
    rarity: 6,
    profession: 'MEDIC',
    sub_profession: 'ringhealer',
    elite: 2,
    level: 70,
    main_skill_level: 7,
    skill_levels: [1, 0, 0],
    mastery_error: null,
    material_error: null,
    potential: 4,
    promotion_target: 2,
    max_phase: 2,
    max_level: 90,
    module_level: 60,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·治疗强化·γ型',
        skill_icon_id: 'skcom_heal_up[3]',
        current_level: 1,
        costs: [
          { 3303: 12, 30024: 7, 30044: 4 },
          { 3303: 15, 30054: 5, 30135: 6 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·法术护盾',
        skill_icon_id: 'skchr_cgbird_2',
        current_level: 0,
        costs: [
          { 3303: 6, 30024: 4, 30103: 5 },
          { 3303: 12, 30034: 7, 30054: 4 },
          { 3303: 15, 30064: 4, 30135: 6 }
        ]
      },
      {
        skill_index: 2,
        skill_name: '三技能·圣域',
        skill_icon_id: 'skchr_cgbird_3',
        current_level: 0,
        costs: [
          { 3303: 6, 30013: 8, 30034: 4 },
          { 3303: 12, 30044: 6, 30064: 3 },
          { 3303: 15, 30084: 5, 30125: 6 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_cgbird',
        name: '“封闭的希望”',
        type: 'RIN-X',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30145: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30115: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30125: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      },
      {
        id: 'uniequip_003_cgbird',
        name: '“莺歌”',
        type: 'RIN-Y',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30145: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30115: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30135: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', costs: null },
      { id: 'elite2_module', elite: 2, level: 60, label: '精二 60 级', costs: null },
      {
        id: 'elite2_max',
        elite: 2,
        level: 90,
        label: '精二 90 级',
        costs: { 4001: 469193, growth_exp: 416200 }
      }
    ],
    basic_costs: null
  },
  {
    char_id: 'char_264_f12yin',
    name: '山',
    rarity: 6,
    profession: 'WARRIOR',
    sub_profession: 'fighter',
    elite: 2,
    level: 45,
    main_skill_level: 7,
    skill_levels: [2, 1, 0],
    mastery_error: null,
    material_error: null,
    potential: 3,
    promotion_target: 2,
    max_phase: 2,
    max_level: 90,
    module_level: 60,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·左勾扫拳',
        skill_icon_id: 'skchr_f12yin_1',
        current_level: 2,
        costs: [{ 3303: 15, 30084: 5, 30135: 6 }]
      },
      {
        skill_index: 1,
        skill_name: '二技能·横扫架势',
        skill_icon_id: 'skchr_f12yin_2',
        current_level: 1,
        costs: [
          { 3303: 12, 30064: 5, 30084: 4 },
          { 3303: 15, 30094: 4, 30145: 6 }
        ]
      },
      {
        skill_index: 2,
        skill_name: '三技能·震地碎岩击',
        skill_icon_id: 'skchr_f12yin_3',
        current_level: 0,
        costs: [
          { 3303: 8, 30054: 4, 31013: 4 },
          { 3303: 12, 30074: 9, 30094: 4 },
          { 3303: 15, 30054: 5, 30125: 6 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_f12yin',
        name: '“自由的代价”',
        type: 'FGT-Y',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30135: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30115: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30125: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      },
      {
        id: 'uniequip_003_f12yin',
        name: '“夜深人静”',
        type: 'FGT-X',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30115: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30135: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30155: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', costs: null },
      {
        id: 'elite2_module',
        elite: 2,
        level: 60,
        label: '精二 60 级',
        costs: { 4001: 92545, growth_exp: 107175 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 90,
        label: '精二 90 级',
        costs: { 4001: 665932, growth_exp: 630289 }
      }
    ],
    basic_costs: null
  },
  {
    char_id: 'char_293_thorns',
    name: '棘刺',
    rarity: 6,
    profession: 'WARRIOR',
    sub_profession: 'lord',
    elite: 2,
    level: 60,
    main_skill_level: 7,
    skill_levels: [3, 0, 0],
    mastery_error: null,
    material_error: null,
    potential: 2,
    promotion_target: 2,
    max_phase: 2,
    max_level: 90,
    module_level: 60,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 1,
        skill_name: '二技能·护身尖刺',
        skill_icon_id: 'skchr_thorns_2',
        current_level: 0,
        costs: [
          { 3303: 8, 30053: 8, 30074: 4 },
          { 3303: 12, 30044: 6, 30064: 3 },
          { 3303: 15, 30054: 5, 30125: 6 }
        ]
      },
      {
        skill_index: 2,
        skill_name: '三技能·至高之术',
        skill_icon_id: 'skchr_thorns_3',
        current_level: 0,
        costs: [
          { 3303: 8, 30073: 7, 30094: 4 },
          { 3303: 12, 30054: 8, 30074: 4 },
          { 3303: 15, 30104: 5, 30125: 6 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_thorns',
        name: '“盐与沙”',
        type: 'LOR-X',
        elite: 2,
        level: 60,
        current_level: 1,
        max_level: 3,
        costs: [
          { 4001: 80000, 30155: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30135: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30145: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      },
      {
        id: 'uniequip_003_thorns',
        name: '沙蚀',
        type: 'LOR-D',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30155: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30145: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30165: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', costs: null },
      { id: 'elite2_module', elite: 2, level: 60, label: '精二 60 级', costs: null },
      {
        id: 'elite2_max',
        elite: 2,
        level: 90,
        label: '精二 90 级',
        costs: { 4001: 573387, growth_exp: 523114 }
      }
    ],
    basic_costs: null
  },
  {
    char_id: 'char_311_mudrok',
    name: '泥岩',
    rarity: 6,
    profession: 'TANK',
    sub_profession: 'unyield',
    elite: 2,
    level: 70,
    main_skill_level: 7,
    skill_levels: [2, 0, 0],
    mastery_error: null,
    material_error: null,
    potential: 5,
    promotion_target: 2,
    max_phase: 2,
    max_level: 90,
    module_level: 60,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·防御力强化·γ型',
        skill_icon_id: 'skcom_def_up[3]',
        current_level: 2,
        costs: [{ 3303: 15, 30125: 6, 31034: 4 }]
      },
      {
        skill_index: 1,
        skill_name: '二技能·岩崩锤',
        skill_icon_id: 'skchr_mudrok_2',
        current_level: 0,
        costs: [
          { 3303: 8, 31013: 3, 31034: 4 },
          { 3303: 12, 30014: 10, 31014: 4 },
          { 3303: 15, 30115: 6, 31024: 6 }
        ]
      },
      {
        skill_index: 2,
        skill_name: '三技能·秽壤的血脉',
        skill_icon_id: 'skchr_mudrok_3',
        current_level: 0,
        costs: [
          { 3303: 8, 30083: 5, 30104: 4 },
          { 3303: 12, 30044: 4, 31024: 7 },
          { 3303: 15, 30135: 6, 31014: 6 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_mudrok',
        name: '土石的根系',
        type: 'UNY-X',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30125: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30135: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30145: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      },
      {
        id: 'uniequip_003_mudrok',
        name: '沃土的愿景',
        type: 'UNY-Y',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30165: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30115: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30135: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', costs: null },
      { id: 'elite2_module', elite: 2, level: 60, label: '精二 60 级', costs: null },
      {
        id: 'elite2_max',
        elite: 2,
        level: 90,
        label: '精二 90 级',
        costs: { 4001: 469193, growth_exp: 416200 }
      }
    ],
    basic_costs: null
  },
  {
    char_id: 'char_377_gdglow',
    name: '澄闪',
    rarity: 6,
    profession: 'CASTER',
    sub_profession: 'funnel',
    elite: 2,
    level: 20,
    main_skill_level: 6,
    skill_levels: [0, 0, 0],
    mastery_error:
      '基础技能仅 6 级，可加入养成计划；升至 7 级后，请前往「养成规划」页面手动点击「刷新」后再执行专精',
    material_error: null,
    potential: 1,
    promotion_target: 2,
    max_phase: 2,
    max_level: 90,
    module_level: 60,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·火花四溅',
        skill_icon_id: 'skchr_gdglow_1',
        current_level: 0,
        costs: [
          { 3303: 8, 30043: 4, 30064: 3 },
          { 3303: 12, 30014: 10, 31014: 4 },
          { 3303: 15, 30064: 4, 30125: 6 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·电流翻涌',
        skill_icon_id: 'skchr_gdglow_2',
        current_level: 0,
        costs: [
          { 3303: 8, 30053: 8, 30074: 4 },
          { 3303: 12, 30104: 8, 31024: 4 },
          { 3303: 15, 30044: 5, 30115: 6 }
        ]
      },
      {
        skill_index: 2,
        skill_name: '三技能·澄净闪耀',
        skill_icon_id: 'skchr_gdglow_3',
        current_level: 0,
        costs: [
          { 3303: 8, 30084: 4, 31053: 5 },
          { 3303: 12, 30044: 4, 31024: 7 },
          { 3303: 15, 30054: 5, 30135: 6 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_gdglow',
        name: '“辛劳之翼”',
        type: 'FUN-X',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30135: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30125: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30145: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      },
      {
        id: 'uniequip_003_gdglow',
        name: '梦想终将实现',
        type: 'FUN-Y',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30155: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30145: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30165: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', costs: null },
      {
        id: 'elite2_module',
        elite: 2,
        level: 60,
        label: '精二 60 级',
        costs: { 4001: 160037, growth_exp: 204105 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 90,
        label: '精二 90 级',
        costs: { 4001: 733424, growth_exp: 727219 }
      }
    ],
    basic_costs: { 3303: 8, 30043: 4, 31013: 4 }
  },
  {
    char_id: 'char_479_sleach',
    name: '琴柳',
    rarity: 6,
    profession: 'PIONEER',
    sub_profession: 'bearer',
    elite: 2,
    level: 25,
    main_skill_level: 6,
    skill_levels: [0, 0, 0],
    mastery_error:
      '基础技能仅 6 级，可加入养成计划；升至 7 级后，请前往「养成规划」页面手动点击「刷新」后再执行专精',
    material_error: null,
    potential: 1,
    promotion_target: 2,
    max_phase: 2,
    max_level: 90,
    module_level: 60,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·支援号令·γ型',
        skill_icon_id: 'skcom_assist_cost[3]',
        current_level: 0,
        costs: [
          { 3303: 8, 30014: 4, 30093: 7 },
          { 3303: 12, 30084: 7, 30104: 4 },
          { 3303: 15, 30145: 6, 31044: 4 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·信仰传承',
        skill_icon_id: 'skchr_sleach_2',
        current_level: 0,
        costs: [
          { 3303: 8, 30013: 11, 31014: 4 },
          { 3303: 12, 31034: 4, 31054: 8 },
          { 3303: 15, 30115: 6, 31014: 6 }
        ]
      },
      {
        skill_index: 2,
        skill_name: '三技能·光辉旗帜',
        skill_icon_id: 'skchr_sleach_3',
        current_level: 0,
        costs: [
          { 3303: 8, 30103: 5, 31024: 4 },
          { 3303: 12, 30064: 6, 31054: 4 },
          { 3303: 15, 30125: 6, 31034: 4 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_sleach',
        name: '牧人的歌',
        type: 'BEA-X',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30145: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30125: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30135: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      },
      {
        id: 'uniequip_003_sleach',
        name: '“友谊万岁”',
        type: 'BEA-Y',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30135: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30155: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30145: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', costs: null },
      {
        id: 'elite2_module',
        elite: 2,
        level: 60,
        label: '精二 60 级',
        costs: { 4001: 152537, growth_exp: 191390 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 90,
        label: '精二 90 级',
        costs: { 4001: 725924, growth_exp: 714504 }
      }
    ],
    basic_costs: { 3303: 8, 30083: 3, 31043: 5 }
  },
  {
    char_id: 'char_103_angel',
    name: '能天使',
    rarity: 6,
    profession: 'SNIPER',
    sub_profession: 'fastshot',
    elite: 2,
    level: 90,
    main_skill_level: 7,
    skill_levels: [3, 3, 2],
    mastery_error: null,
    material_error: null,
    potential: 3,
    promotion_target: 2,
    max_phase: 2,
    max_level: 90,
    module_level: 60,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 2,
        skill_name: '三技能·过载模式',
        skill_icon_id: 'skchr_angel_3',
        current_level: 2,
        costs: [{ 3303: 15, 30034: 6, 30135: 6 }]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_angel',
        name: '能天使的杰作',
        type: 'MAR-X',
        elite: 2,
        level: 60,
        current_level: 2,
        max_level: 3,
        costs: [
          { 4001: 80000, 30135: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30145: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30115: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      },
      {
        id: 'uniequip_003_angel',
        name: '欢迎光临，企鹅物流',
        type: 'MAR-Y',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30155: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30145: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30115: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', costs: null },
      { id: 'elite2_module', elite: 2, level: 60, label: '精二 60 级', costs: null },
      { id: 'elite2_max', elite: 2, level: 90, label: '精二 90 级', costs: null }
    ],
    basic_costs: null
  },
  {
    char_id: 'char_180_amgoat',
    name: '艾雅法拉',
    rarity: 6,
    profession: 'CASTER',
    sub_profession: 'corecaster',
    elite: 2,
    level: 80,
    main_skill_level: 7,
    skill_levels: [3, 3, 1],
    mastery_error: null,
    material_error: null,
    potential: 1,
    promotion_target: 2,
    max_phase: 2,
    max_level: 90,
    module_level: 60,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 2,
        skill_name: '三技能·火山',
        skill_icon_id: 'skchr_amgoat_3',
        current_level: 1,
        costs: [
          { 3303: 12, 30024: 7, 30044: 4 },
          { 3303: 15, 30054: 5, 30135: 6 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_amgoat',
        name: '“错过的声音”',
        type: 'CCR-X',
        elite: 2,
        level: 60,
        current_level: 1,
        max_level: 3,
        costs: [
          { 4001: 80000, 30115: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30145: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30125: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      },
      {
        id: 'uniequip_003_amgoat',
        name: '宠物大赛第一名',
        type: 'CCR-Y',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30145: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30165: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30115: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', costs: null },
      { id: 'elite2_module', elite: 2, level: 60, label: '精二 60 级', costs: null },
      {
        id: 'elite2_max',
        elite: 2,
        level: 90,
        label: '精二 90 级',
        costs: { 4001: 297577, growth_exp: 255000 }
      }
    ],
    basic_costs: null
  },
  {
    char_id: 'char_4133_logos',
    name: '逻各斯',
    rarity: 6,
    profession: 'CASTER',
    sub_profession: 'corecaster',
    elite: 2,
    level: 60,
    main_skill_level: 7,
    skill_levels: [3, 0, 0],
    mastery_error: null,
    material_error: null,
    potential: 3,
    promotion_target: 2,
    max_phase: 2,
    max_level: 90,
    module_level: 60,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 1,
        skill_name: '二技能·提喻',
        skill_icon_id: 'skchr_logos_2',
        current_level: 0,
        costs: [
          { 3303: 8, 30014: 4, 31043: 8 },
          { 3303: 12, 30064: 4, 30074: 7 },
          { 3303: 15, 30084: 6, 30115: 6 }
        ]
      },
      {
        skill_index: 2,
        skill_name: '三技能·延异视阈',
        skill_icon_id: 'skchr_logos_3',
        current_level: 0,
        costs: [
          { 3303: 8, 30023: 5, 30064: 3 },
          { 3303: 12, 30044: 7, 30104: 4 },
          { 3303: 15, 30074: 4, 30145: 6 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_logos',
        name: '来自河谷的笔盒',
        type: 'CCR-D',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30115: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30155: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30135: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      },
      {
        id: 'uniequip_003_logos',
        name: '《语义范式百科》',
        type: 'CCR-Y',
        elite: 2,
        level: 60,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 80000, 30135: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30155: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30145: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', costs: null },
      { id: 'elite2_module', elite: 2, level: 60, label: '精二 60 级', costs: null },
      {
        id: 'elite2_max',
        elite: 2,
        level: 90,
        label: '精二 90 级',
        costs: { 4001: 573387, growth_exp: 523114 }
      }
    ],
    basic_costs: null
  },
  {
    char_id: 'char_172_svrash',
    name: '银灰',
    rarity: 6,
    profession: 'WARRIOR',
    sub_profession: 'lord',
    elite: 2,
    level: 90,
    main_skill_level: 7,
    skill_levels: [3, 1, 0],
    mastery_error: null,
    material_error: null,
    potential: 2,
    promotion_target: 2,
    max_phase: 2,
    max_level: 90,
    module_level: 60,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 1,
        skill_name: '二技能·雪境生存法则',
        skill_icon_id: 'skchr_svrash_2',
        current_level: 1,
        costs: [
          { 3303: 12, 30064: 5, 30084: 4 },
          { 3303: 15, 30024: 6, 30135: 6 }
        ]
      },
      {
        skill_index: 2,
        skill_name: '三技能·真银斩',
        skill_icon_id: 'skchr_svrash_3',
        current_level: 0,
        costs: [
          { 3303: 6, 30043: 4, 30064: 3 },
          { 3303: 12, 30074: 9, 30094: 4 },
          { 3303: 15, 30024: 5, 30125: 6 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_svrash',
        name: '雪境羽兽护理套组',
        type: 'LOR-X',
        elite: 2,
        level: 60,
        current_level: 3,
        max_level: 3,
        costs: [
          { 4001: 80000, 30115: 2, mod_unlock_token: 4 },
          { 4001: 100000, 30145: 3, mod_unlock_token: 4, mod_update_token_1: 60 },
          { 4001: 120000, 30155: 4, mod_unlock_token: 4, mod_update_token_2: 20 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级', costs: null },
      { id: 'elite2_module', elite: 2, level: 60, label: '精二 60 级', costs: null },
      { id: 'elite2_max', elite: 2, level: 90, label: '精二 90 级', costs: null }
    ],
    basic_costs: null
  },
  {
    char_id: 'char_173_slchan',
    name: '崖心',
    rarity: 5,
    profession: 'SPECIAL',
    sub_profession: 'hookmaster',
    elite: 1,
    level: 20,
    main_skill_level: 3,
    skill_levels: [0, 0],
    mastery_error:
      '尚未精二，可规划养成材料；精二且基础技能升至 7 级后，请前往「养成规划」页面手动点击「刷新」后再执行专精',
    material_error: null,
    potential: 1,
    promotion_target: 2,
    max_phase: 2,
    max_level: 80,
    module_level: 50,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·锁链勾爪',
        skill_icon_id: 'skchr_slchan_1',
        current_level: 0,
        costs: [
          { 3303: 5, 30083: 2, 30104: 3 },
          { 3303: 6, 30024: 3, 30104: 5 },
          { 3303: 10, 30034: 4, 30135: 4 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·束缚链',
        skill_icon_id: 'skchr_slchan_2',
        current_level: 0,
        costs: [
          { 3303: 5, 30014: 3, 30093: 4 },
          { 3303: 6, 30014: 6, 30034: 3 },
          { 3303: 10, 30064: 3, 30115: 4 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_slchan',
        name: '“凌绝顶”',
        type: 'HOK-X',
        elite: 2,
        level: 50,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 40000, 31044: 3, mod_unlock_token: 2 },
          { 4001: 50000, 30104: 4, mod_unlock_token: 2, mod_update_token_1: 20 },
          { 4001: 60000, 30024: 5, mod_unlock_token: 2, mod_update_token_2: 8 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      {
        id: 'elite2',
        elite: 2,
        level: 1,
        label: '精二 1 级',
        costs: { 3283: 3, 4001: 319327, 30044: 6, 30083: 13, growth_exp: 203828 }
      },
      {
        id: 'elite2_module',
        elite: 2,
        level: 50,
        label: '精二 50 级',
        costs: { 3283: 3, 4001: 423640, 30044: 6, 30083: 13, growth_exp: 354589 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 80,
        label: '精二 80 级',
        costs: { 3283: 3, 4001: 766705, 30044: 6, 30083: 13, growth_exp: 698828 }
      }
    ],
    basic_costs: { 3302: 18, 3303: 6, 30013: 4, 30022: 3, 30032: 5, 30083: 4, 30093: 2 }
  },
  {
    char_id: 'char_143_ghost',
    name: '幽灵鲨',
    rarity: 5,
    profession: 'WARRIOR',
    sub_profession: 'centurion',
    elite: 1,
    level: 30,
    main_skill_level: 4,
    skill_levels: [0, 0],
    mastery_error:
      '尚未精二，可规划养成材料；精二且基础技能升至 7 级后，请前往「养成规划」页面手动点击「刷新」后再执行专精',
    material_error: null,
    potential: 4,
    promotion_target: 2,
    max_phase: 2,
    max_level: 80,
    module_level: 50,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·攻击力强化·γ型',
        skill_icon_id: 'skcom_atk_up[3]',
        current_level: 0,
        costs: [
          { 3303: 5, 30024: 3, 30103: 3 },
          { 3303: 6, 30024: 5, 30044: 3 },
          { 3303: 10, 30094: 4, 30115: 4 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·肉斩骨断',
        skill_icon_id: 'skchr_ghost_2',
        current_level: 0,
        costs: [
          { 3303: 5, 30013: 4, 30034: 3 },
          { 3303: 6, 30034: 5, 30054: 3 },
          { 3303: 10, 30084: 3, 30125: 4 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_ghost',
        name: '幽明烛光',
        type: 'CEN-X',
        elite: 2,
        level: 50,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 40000, 31044: 3, mod_unlock_token: 2 },
          { 4001: 50000, 31024: 4, mod_unlock_token: 2, mod_update_token_1: 20 },
          { 4001: 60000, 30074: 5, mod_unlock_token: 2, mod_update_token_2: 8 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      {
        id: 'elite2',
        elite: 2,
        level: 1,
        label: '精二 1 级',
        costs: { 3223: 3, 4001: 310444, 30053: 15, 30074: 8, growth_exp: 190408 }
      },
      {
        id: 'elite2_module',
        elite: 2,
        level: 50,
        label: '精二 50 级',
        costs: { 3223: 3, 4001: 414757, 30053: 15, 30074: 8, growth_exp: 341169 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 80,
        label: '精二 80 级',
        costs: { 3223: 3, 4001: 757822, 30053: 15, 30074: 8, growth_exp: 685408 }
      }
    ],
    basic_costs: { 3302: 12, 3303: 6, 30013: 4, 30032: 5, 30063: 2, 30103: 3 }
  },
  {
    char_id: 'char_102_texas',
    name: '德克萨斯',
    rarity: 5,
    profession: 'PIONEER',
    sub_profession: 'pioneer',
    elite: 1,
    level: 55,
    main_skill_level: 6,
    skill_levels: [0, 0],
    mastery_error:
      '尚未精二，可规划养成材料；精二且基础技能升至 7 级后，请前往「养成规划」页面手动点击「刷新」后再执行专精',
    material_error: null,
    potential: 5,
    promotion_target: 2,
    max_phase: 2,
    max_level: 80,
    module_level: 50,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·冲锋号令·γ型',
        skill_icon_id: 'skcom_charge_cost[3]',
        current_level: 0,
        costs: [
          { 3303: 5, 30063: 2, 30084: 3 },
          { 3303: 6, 30084: 5, 30104: 3 },
          { 3303: 10, 30034: 4, 30135: 4 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·剑雨',
        skill_icon_id: 'skchr_texas_2',
        current_level: 0,
        costs: [
          { 3303: 5, 30073: 4, 30094: 3 },
          { 3303: 6, 30014: 3, 30094: 6 },
          { 3303: 10, 30064: 3, 30115: 4 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_texas',
        name: '外勤私人补给包',
        type: 'SOL-Y',
        elite: 2,
        level: 50,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 40000, 30104: 3, mod_unlock_token: 2 },
          { 4001: 50000, 30094: 4, mod_unlock_token: 2, mod_update_token_1: 20 },
          { 4001: 60000, 30084: 5, mod_unlock_token: 2, mod_update_token_2: 8 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      {
        id: 'elite2',
        elite: 2,
        level: 1,
        label: '精二 1 级',
        costs: { 3213: 3, 4001: 245135, 30013: 16, 30034: 8, growth_exp: 116000 }
      },
      {
        id: 'elite2_module',
        elite: 2,
        level: 50,
        label: '精二 50 级',
        costs: { 3213: 3, 4001: 349448, 30013: 16, 30034: 8, growth_exp: 266761 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 80,
        label: '精二 80 级',
        costs: { 3213: 3, 4001: 692513, 30013: 16, 30034: 8, growth_exp: 611000 }
      }
    ],
    basic_costs: { 3303: 6, 30053: 3, 30073: 3 }
  },
  {
    char_id: 'char_140_whitew',
    name: '拉普兰德',
    rarity: 5,
    profession: 'WARRIOR',
    sub_profession: 'lord',
    elite: 1,
    level: 50,
    main_skill_level: 5,
    skill_levels: [0, 0],
    mastery_error:
      '尚未精二，可规划养成材料；精二且基础技能升至 7 级后，请前往「养成规划」页面手动点击「刷新」后再执行专精',
    material_error: null,
    potential: 2,
    promotion_target: 2,
    max_phase: 2,
    max_level: 80,
    module_level: 50,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·日晷',
        skill_icon_id: 'skchr_whitew_1',
        current_level: 0,
        costs: [
          { 3303: 5, 30014: 3, 30093: 4 },
          { 3303: 6, 30014: 6, 30034: 3 },
          { 3303: 10, 30054: 4, 30135: 4 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·狼魂',
        skill_icon_id: 'skchr_whitew_2',
        current_level: 0,
        costs: [
          { 3303: 5, 30024: 3, 30103: 3 },
          { 3303: 6, 30024: 5, 30044: 3 },
          { 3303: 10, 30094: 4, 30115: 4 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_whitew',
        name: '“幼狼的牙齿”',
        type: 'LOR-X',
        elite: 2,
        level: 50,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 40000, 30024: 3, mod_unlock_token: 2 },
          { 4001: 50000, 30084: 4, mod_unlock_token: 2, mod_update_token_1: 20 },
          { 4001: 60000, 30014: 5, mod_unlock_token: 2, mod_update_token_2: 8 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      {
        id: 'elite2',
        elite: 2,
        level: 1,
        label: '精二 1 级',
        costs: { 3223: 3, 4001: 266892, 30043: 10, 30064: 6, growth_exp: 138618 }
      },
      {
        id: 'elite2_module',
        elite: 2,
        level: 50,
        label: '精二 50 级',
        costs: { 3223: 3, 4001: 371205, 30043: 10, 30064: 6, growth_exp: 289379 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 80,
        label: '精二 80 级',
        costs: { 3223: 3, 4001: 714270, 30043: 10, 30064: 6, growth_exp: 633618 }
      }
    ],
    basic_costs: { 3302: 6, 3303: 6, 30033: 3, 30093: 3, 30103: 2 }
  },
  {
    char_id: 'char_128_plosis',
    name: '白面鸮',
    rarity: 5,
    profession: 'MEDIC',
    sub_profession: 'ringhealer',
    elite: 1,
    level: 45,
    main_skill_level: 5,
    skill_levels: [0, 0],
    mastery_error:
      '尚未精二，可规划养成材料；精二且基础技能升至 7 级后，请前往「养成规划」页面手动点击「刷新」后再执行专精',
    material_error: null,
    potential: 3,
    promotion_target: 2,
    max_phase: 2,
    max_level: 80,
    module_level: 50,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·治疗强化·γ型',
        skill_icon_id: 'skcom_heal_up[3]',
        current_level: 0,
        costs: [
          { 3303: 5, 30043: 3, 30064: 2 },
          { 3303: 6, 30064: 4, 30084: 3 },
          { 3303: 10, 30024: 4, 30115: 4 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·脑啡肽',
        skill_icon_id: 'skchr_plosis_2',
        current_level: 0,
        costs: [
          { 3303: 5, 30053: 5, 30074: 3 },
          { 3303: 6, 30074: 6, 30094: 3 },
          { 3303: 10, 30014: 4, 30125: 4 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_plosis',
        name: '医疗环境分析装置',
        type: 'RIN-X',
        elite: 2,
        level: 50,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 40000, 30074: 3, mod_unlock_token: 2 },
          { 4001: 50000, 30044: 4, mod_unlock_token: 2, mod_update_token_1: 20 },
          { 4001: 60000, 30104: 5, mod_unlock_token: 2, mod_update_token_2: 8 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      {
        id: 'elite2',
        elite: 2,
        level: 1,
        label: '精二 1 级',
        costs: { 3263: 3, 4001: 283401, 30014: 9, 30093: 10, growth_exp: 156818 }
      },
      {
        id: 'elite2_module',
        elite: 2,
        level: 50,
        label: '精二 50 级',
        costs: { 3263: 3, 4001: 387714, 30014: 9, 30093: 10, growth_exp: 307579 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 80,
        label: '精二 80 级',
        costs: { 3263: 3, 4001: 730779, 30014: 9, 30093: 10, growth_exp: 651818 }
      }
    ],
    basic_costs: { 3302: 6, 3303: 6, 30043: 4, 30053: 2, 30073: 4 }
  },
  {
    char_id: 'char_108_silent',
    name: '赫默',
    rarity: 5,
    profession: 'MEDIC',
    sub_profession: 'physician',
    elite: 1,
    level: 40,
    main_skill_level: 4,
    skill_levels: [0, 0],
    mastery_error:
      '尚未精二，可规划养成材料；精二且基础技能升至 7 级后，请前往「养成规划」页面手动点击「刷新」后再执行专精',
    material_error: null,
    potential: 1,
    promotion_target: 2,
    max_phase: 2,
    max_level: 80,
    module_level: 50,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·治疗强化·γ型',
        skill_icon_id: 'skcom_heal_up[3]',
        current_level: 0,
        costs: [
          { 3303: 5, 30014: 3, 30093: 4 },
          { 3303: 6, 30014: 6, 30034: 3 },
          { 3303: 10, 30084: 4, 30115: 4 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·医疗无人机',
        skill_icon_id: 'skchr_silent_2',
        current_level: 0,
        costs: [
          { 3303: 5, 30024: 3, 30103: 3 },
          { 3303: 6, 30024: 5, 30044: 3 },
          { 3303: 10, 30094: 4, 30125: 4 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_silent',
        name: '紧急防卫程序',
        type: 'PHY-Y',
        elite: 2,
        level: 50,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 40000, 30094: 3, mod_unlock_token: 2 },
          { 4001: 50000, 30014: 4, mod_unlock_token: 2, mod_update_token_1: 20 },
          { 4001: 60000, 30064: 5, mod_unlock_token: 2, mod_update_token_2: 8 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      {
        id: 'elite2',
        elite: 2,
        level: 1,
        label: '精二 1 级',
        costs: { 3263: 3, 4001: 295765, 30013: 18, 30054: 7, growth_exp: 170618 }
      },
      {
        id: 'elite2_module',
        elite: 2,
        level: 50,
        label: '精二 50 级',
        costs: { 3263: 3, 4001: 400078, 30013: 18, 30054: 7, growth_exp: 321379 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 80,
        label: '精二 80 级',
        costs: { 3263: 3, 4001: 743143, 30013: 18, 30054: 7, growth_exp: 665618 }
      }
    ],
    basic_costs: { 3302: 12, 3303: 6, 30033: 3, 30062: 3, 30093: 3, 30103: 2 }
  },
  {
    char_id: 'char_196_sunbr',
    name: '古米',
    rarity: 4,
    profession: 'TANK',
    sub_profession: 'guardian',
    elite: 0,
    level: 40,
    main_skill_level: 3,
    skill_levels: [0, 0],
    mastery_error:
      '尚未精二，可规划养成材料；精二且基础技能升至 7 级后，请前往「养成规划」页面手动点击「刷新」后再执行专精',
    material_error: null,
    potential: 2,
    promotion_target: 2,
    max_phase: 2,
    max_level: 70,
    module_level: 40,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·备用军粮',
        skill_icon_id: 'skchr_sunbr_1',
        current_level: 0,
        costs: [
          { 3303: 2, 30033: 4, 30054: 1 },
          { 3303: 4, 30054: 2, 30074: 2 },
          { 3303: 6, 30054: 2, 30125: 2 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·食粮烹制',
        skill_icon_id: 'skchr_sunbr_2',
        current_level: 0,
        costs: [
          { 3303: 2, 30043: 2, 30064: 1 },
          { 3303: 4, 30064: 2, 30084: 2 },
          { 3303: 6, 30024: 2, 30135: 2 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_sunbr',
        name: '蜜糖馅饼礼包',
        type: 'GUA-X',
        elite: 2,
        level: 40,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 20000, 30053: 4, mod_unlock_token: 1 },
          { 4001: 25000, 30073: 5, mod_unlock_token: 1, mod_update_token_1: 15 },
          { 4001: 30000, 30043: 6, mod_unlock_token: 1, mod_update_token_2: 5 }
        ]
      }
    ],
    level_goals: [
      {
        id: 'elite1',
        elite: 1,
        level: 1,
        label: '精一 1 级',
        costs: { 3231: 3, 4001: 20666, 30022: 1, 30052: 1, growth_exp: 3800 }
      },
      {
        id: 'elite2',
        elite: 2,
        level: 1,
        label: '精二 1 级',
        costs: {
          3231: 3,
          3232: 5,
          4001: 192294,
          30022: 1,
          30052: 1,
          30083: 7,
          30103: 13,
          growth_exp: 133800
        }
      },
      {
        id: 'elite2_module',
        elite: 2,
        level: 40,
        label: '精二 40 级',
        costs: {
          3231: 3,
          3232: 5,
          4001: 250559,
          30022: 1,
          30052: 1,
          30083: 7,
          30103: 13,
          growth_exp: 226536
        }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 70,
        label: '精二 70 级',
        costs: {
          3231: 3,
          3232: 5,
          4001: 468056,
          30022: 1,
          30052: 1,
          30083: 7,
          30103: 13,
          growth_exp: 467600
        }
      }
    ],
    basic_costs: { 3302: 9, 3303: 4, 30032: 2, 30033: 3, 30042: 2, 30043: 3 }
  },
  {
    char_id: 'char_151_myrtle',
    name: '桃金娘',
    rarity: 4,
    profession: 'PIONEER',
    sub_profession: 'bearer',
    elite: 1,
    level: 30,
    main_skill_level: 4,
    skill_levels: [0, 0],
    mastery_error:
      '尚未精二，可规划养成材料；精二且基础技能升至 7 级后，请前往「养成规划」页面手动点击「刷新」后再执行专精',
    material_error: null,
    potential: 3,
    promotion_target: 2,
    max_phase: 2,
    max_level: 70,
    module_level: 40,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·支援号令·β型',
        skill_icon_id: 'skcom_assist_cost[2]',
        current_level: 0,
        costs: [
          { 3303: 2, 30023: 4, 30044: 1 },
          { 3303: 4, 30044: 2, 30064: 1 },
          { 3303: 6, 30094: 2, 30115: 2 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·治愈之翼',
        skill_icon_id: 'skchr_myrtle_2',
        current_level: 0,
        costs: [
          { 3303: 2, 30033: 4, 30054: 1 },
          { 3303: 4, 30054: 2, 30074: 2 },
          { 3303: 6, 30084: 2, 30125: 2 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_myrtle',
        name: '“私人收藏”',
        type: 'BEA-X',
        elite: 2,
        level: 40,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 20000, 30103: 4, mod_unlock_token: 1 },
          { 4001: 25000, 30033: 5, mod_unlock_token: 1, mod_update_token_1: 15 },
          { 4001: 30000, 31053: 6, mod_unlock_token: 1, mod_update_token_2: 5 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      {
        id: 'elite2',
        elite: 2,
        level: 1,
        label: '精二 1 级',
        costs: { 3212: 5, 4001: 156844, 30063: 8, 30093: 12, growth_exp: 105408 }
      },
      {
        id: 'elite2_module',
        elite: 2,
        level: 40,
        label: '精二 40 级',
        costs: { 3212: 5, 4001: 215109, 30063: 8, 30093: 12, growth_exp: 198144 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 70,
        label: '精二 70 级',
        costs: { 3212: 5, 4001: 432606, 30063: 8, 30093: 12, growth_exp: 439208 }
      }
    ],
    basic_costs: { 3302: 6, 3303: 4, 30012: 4, 30023: 3, 30033: 3 }
  },
  {
    char_id: 'char_149_scave',
    name: '清道夫',
    rarity: 4,
    profession: 'PIONEER',
    sub_profession: 'pioneer',
    elite: 0,
    level: 25,
    main_skill_level: 2,
    skill_levels: [0, 0],
    mastery_error:
      '尚未精二，可规划养成材料；精二且基础技能升至 7 级后，请前往「养成规划」页面手动点击「刷新」后再执行专精',
    material_error: null,
    potential: 2,
    promotion_target: 2,
    max_phase: 2,
    max_level: 70,
    module_level: 40,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·冲锋号令·β型',
        skill_icon_id: 'skcom_charge_cost[2]',
        current_level: 0,
        costs: [
          { 3303: 2, 30024: 1, 30103: 3 },
          { 3303: 4, 30024: 2, 30044: 2 },
          { 3303: 6, 30094: 2, 30115: 2 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·冲锋号令·攻击',
        skill_icon_id: 'skchr_scave_2',
        current_level: 0,
        costs: [
          { 3303: 2, 30013: 5, 30034: 1 },
          { 3303: 4, 30034: 2, 30054: 2 },
          { 3303: 6, 30084: 2, 30125: 2 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_scave',
        name: '“专属餐具”',
        type: 'SOL-X',
        elite: 2,
        level: 40,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 20000, 30043: 4, mod_unlock_token: 1 },
          { 4001: 25000, 31023: 5, mod_unlock_token: 1, mod_update_token_1: 15 },
          { 4001: 30000, 30033: 6, mod_unlock_token: 1, mod_update_token_2: 5 }
        ]
      }
    ],
    level_goals: [
      {
        id: 'elite1',
        elite: 1,
        level: 1,
        label: '精一 1 级',
        costs: { 3211: 3, 4001: 30986, 30012: 1, 30022: 1, growth_exp: 13108 }
      },
      {
        id: 'elite2',
        elite: 2,
        level: 1,
        label: '精二 1 级',
        costs: {
          3211: 3,
          3212: 5,
          4001: 202614,
          30012: 1,
          30022: 1,
          30063: 6,
          30073: 20,
          growth_exp: 143108
        }
      },
      {
        id: 'elite2_module',
        elite: 2,
        level: 40,
        label: '精二 40 级',
        costs: {
          3211: 3,
          3212: 5,
          4001: 260879,
          30012: 1,
          30022: 1,
          30063: 6,
          30073: 20,
          growth_exp: 235844
        }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 70,
        label: '精二 70 级',
        costs: {
          3211: 3,
          3212: 5,
          4001: 478376,
          30012: 1,
          30022: 1,
          30063: 6,
          30073: 20,
          growth_exp: 476908
        }
      }
    ],
    basic_costs: { 3301: 2, 3302: 9, 3303: 4, 30011: 5, 30013: 3, 30022: 2, 30032: 3, 30103: 2 }
  },
  {
    char_id: 'char_198_blackd',
    name: '讯使',
    rarity: 4,
    profession: 'PIONEER',
    sub_profession: 'pioneer',
    elite: 1,
    level: 10,
    main_skill_level: 2,
    skill_levels: [0, 0],
    mastery_error:
      '尚未精二，可规划养成材料；精二且基础技能升至 7 级后，请前往「养成规划」页面手动点击「刷新」后再执行专精',
    material_error: null,
    potential: 1,
    promotion_target: 2,
    max_phase: 2,
    max_level: 70,
    module_level: 40,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [
      {
        skill_index: 0,
        skill_name: '一技能·冲锋号令·β型',
        skill_icon_id: 'skcom_charge_cost[2]',
        current_level: 0,
        costs: [
          { 3303: 2, 30014: 1, 30093: 4 },
          { 3303: 4, 30014: 3, 30034: 2 },
          { 3303: 6, 30054: 2, 30135: 2 }
        ]
      },
      {
        skill_index: 1,
        skill_name: '二技能·冲锋号令·防御',
        skill_icon_id: 'skchr_blackd_2',
        current_level: 0,
        costs: [
          { 3303: 2, 30024: 1, 30103: 3 },
          { 3303: 4, 30024: 2, 30044: 2 },
          { 3303: 6, 30094: 2, 30115: 2 }
        ]
      }
    ],
    modules: [
      {
        id: 'uniequip_002_blackd',
        name: '耐低温通讯设备',
        type: 'SOL-X',
        elite: 2,
        level: 40,
        current_level: 0,
        max_level: 3,
        costs: [
          { 4001: 20000, 30033: 4, mod_unlock_token: 1 },
          { 4001: 25000, 31033: 5, mod_unlock_token: 1, mod_update_token_1: 15 },
          { 4001: 30000, 31053: 6, mod_unlock_token: 1, mod_update_token_2: 5 }
        ]
      }
    ],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      {
        id: 'elite2',
        elite: 2,
        level: 1,
        label: '精二 1 级',
        costs: { 3212: 5, 4001: 170281, 30053: 10, 30063: 11, growth_exp: 127048 }
      },
      {
        id: 'elite2_module',
        elite: 2,
        level: 40,
        label: '精二 40 级',
        costs: { 3212: 5, 4001: 228546, 30053: 10, 30063: 11, growth_exp: 219784 }
      },
      {
        id: 'elite2_max',
        elite: 2,
        level: 70,
        label: '精二 70 级',
        costs: { 3212: 5, 4001: 446043, 30053: 10, 30063: 11, growth_exp: 460848 }
      }
    ],
    basic_costs: { 3301: 2, 3302: 9, 3303: 4, 30012: 2, 30022: 3, 30061: 2, 30093: 2, 30103: 2 }
  },
  {
    char_id: 'char_124_kroos',
    name: '克洛丝',
    rarity: 3,
    profession: 'SNIPER',
    sub_profession: 'fastshot',
    elite: 0,
    level: 30,
    main_skill_level: 2,
    skill_levels: [],
    mastery_error: null,
    material_error: null,
    potential: 1,
    promotion_target: 1,
    max_phase: 1,
    max_level: 55,
    module_level: 0,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [],
    modules: [],
    level_goals: [
      {
        id: 'elite1',
        elite: 1,
        level: 1,
        label: '精一 1 级',
        costs: { 4001: 17904, growth_exp: 6600 }
      },
      {
        id: 'level_max',
        elite: 1,
        level: 55,
        label: '精一 55 级',
        costs: { 4001: 97997, growth_exp: 105600 }
      }
    ],
    basic_costs: { 3301: 2, 3302: 3, 3303: 2, 30012: 2, 30022: 2, 30061: 1, 30093: 1, 30103: 1 }
  },
  {
    char_id: 'char_122_beagle',
    name: '米格鲁',
    rarity: 3,
    profession: 'TANK',
    sub_profession: 'protector',
    elite: 0,
    level: 20,
    main_skill_level: 2,
    skill_levels: [],
    mastery_error: null,
    material_error: null,
    potential: 2,
    promotion_target: 1,
    max_phase: 1,
    max_level: 55,
    module_level: 0,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [],
    modules: [],
    level_goals: [
      {
        id: 'elite1',
        elite: 1,
        level: 1,
        label: '精一 1 级',
        costs: { 4001: 21903, growth_exp: 11593 }
      },
      {
        id: 'level_max',
        elite: 1,
        level: 55,
        label: '精一 55 级',
        costs: { 4001: 101996, growth_exp: 110593 }
      }
    ],
    basic_costs: { 3301: 2, 3302: 3, 3303: 2, 30012: 3, 30051: 1, 30062: 1, 30083: 1, 30093: 1 }
  },
  {
    char_id: 'char_123_fang',
    name: '芬',
    rarity: 3,
    profession: 'PIONEER',
    sub_profession: 'pioneer',
    elite: 1,
    level: 40,
    main_skill_level: 4,
    skill_levels: [],
    mastery_error: null,
    material_error: null,
    potential: 3,
    promotion_target: 1,
    max_phase: 1,
    max_level: 55,
    module_level: 0,
    supports_basic_skill7: true,
    basic_skill_prerequisite: { elite: 1, level: 1 },
    skills: [],
    modules: [],
    level_goals: [
      { id: 'elite1', elite: 1, level: 1, label: '精一 1 级', costs: null },
      {
        id: 'level_max',
        elite: 1,
        level: 55,
        label: '精一 55 级',
        costs: { 4001: 50030, growth_exp: 54618 }
      }
    ],
    basic_costs: { 3302: 2, 3303: 2, 30032: 2, 30043: 1, 30053: 2 }
  }
]

const MASTERY = {
  has_data: true,
  error: null,
  goals: [
    { char_id: 'char_102_texas', module_id: 'elite2' },
    { char_id: 'char_140_whitew', module_id: 'skill7' },
    { char_id: 'char_143_ghost', module_id: 'elite2' },
    { char_id: 'char_173_slchan', module_id: 'elite2' },
    { char_id: 'char_377_gdglow', module_id: 'elite2_module' },
    { char_id: 'char_264_f12yin', module_id: 'elite2_max' },
    { char_id: 'char_151_myrtle', module_id: 'elite2' },
    { char_id: 'char_180_amgoat', module_id: 'uniequip_002_amgoat', target_level: 3 }
  ],
  statistics: {
    1: {
      max_level: 0,
      module_level: 0,
      elite2: 0,
      modules: 0,
      masteries: 0,
      sanity_value: 0,
      module_blocks: 0,
      consumed_lmd: 0,
      consumed_exp: 0,
      skill_book_equivalent: 0,
      sanity_unpriced: [],
      sanity_incomplete: [],
      sanity_source: {
        source: '离线预览 · 一图流材料价值示例',
        algorithm_url: 'https://ark.yituliu.cn/survey/operators',
        values_url: 'https://ark.yituliu.cn/survey/operators',
        imported_at: 1792558842,
        pricing_mode: 'builtin'
      }
    },
    2: {
      max_level: 0,
      module_level: 0,
      elite2: 0,
      modules: 0,
      masteries: 0,
      sanity_value: 0,
      module_blocks: 0,
      consumed_lmd: 0,
      consumed_exp: 0,
      skill_book_equivalent: 0,
      sanity_unpriced: [],
      sanity_incomplete: [],
      sanity_source: {
        source: '离线预览 · 一图流材料价值示例',
        algorithm_url: 'https://ark.yituliu.cn/survey/operators',
        values_url: 'https://ark.yituliu.cn/survey/operators',
        imported_at: 1792558842,
        pricing_mode: 'builtin'
      }
    },
    3: {
      max_level: 0,
      module_level: 0,
      elite2: 0,
      modules: 0,
      masteries: 0,
      sanity_value: 509.55,
      module_blocks: 0,
      consumed_lmd: 62097,
      consumed_exp: 75389,
      skill_book_equivalent: 0.89,
      sanity_unpriced: [],
      sanity_incomplete: [],
      sanity_source: {
        source: '离线预览 · 一图流材料价值示例',
        algorithm_url: 'https://ark.yituliu.cn/survey/operators',
        values_url: 'https://ark.yituliu.cn/survey/operators',
        imported_at: 1792558842,
        pricing_mode: 'builtin'
      }
    },
    4: {
      max_level: 0,
      module_level: 0,
      elite2: 0,
      modules: 0,
      masteries: 0,
      sanity_value: 782.32,
      module_blocks: 0,
      consumed_lmd: 102931,
      consumed_exp: 91436,
      skill_book_equivalent: 2.33,
      sanity_unpriced: [],
      sanity_incomplete: [],
      sanity_source: {
        source: '离线预览 · 一图流材料价值示例',
        algorithm_url: 'https://ark.yituliu.cn/survey/operators',
        values_url: 'https://ark.yituliu.cn/survey/operators',
        imported_at: 1792558842,
        pricing_mode: 'builtin'
      }
    },
    5: {
      max_level: 0,
      module_level: 0,
      elite2: 0,
      modules: 0,
      masteries: 0,
      sanity_value: 4170.44,
      module_blocks: 0,
      consumed_lmd: 511318,
      consumed_exp: 460110,
      skill_book_equivalent: 23.33,
      sanity_unpriced: [],
      sanity_incomplete: [],
      sanity_source: {
        source: '离线预览 · 一图流材料价值示例',
        algorithm_url: 'https://ark.yituliu.cn/survey/operators',
        values_url: 'https://ark.yituliu.cn/survey/operators',
        imported_at: 1792558842,
        pricing_mode: 'builtin'
      }
    },
    6: {
      max_level: 2,
      module_level: 7,
      elite2: 13,
      modules: 4,
      masteries: 7,
      sanity_value: 89056.57,
      module_blocks: 28,
      consumed_lmd: 11471454,
      consumed_exp: 8322593,
      skill_book_equivalent: 533.44,
      sanity_unpriced: [],
      sanity_incomplete: [],
      sanity_source: {
        source: '离线预览 · 一图流材料价值示例',
        algorithm_url: 'https://ark.yituliu.cn/survey/operators',
        values_url: 'https://ark.yituliu.cn/survey/operators',
        imported_at: 1792558842,
        pricing_mode: 'builtin'
      }
    }
  },
  personal_statistics: {
    rarities: {
      1: {
        owned: 0,
        available: 12,
        elite2: 0,
        max_level: 0,
        module_level: 0,
        supports_mastery: false,
        supports_modules: false,
        max_phase: 0,
        max_level_limit: 30,
        skills: { 1: 0, 2: 0, 3: 0 },
        modules: { 1: 0, 2: 0, 3: 0 },
        sanity: 0,
        consumed_lmd: 0,
        consumed_exp: 0,
        module_blocks: 0,
        skill_book_equivalent: 0,
        materials: [],
        ranking: [],
        incomplete: [],
        unpriced: []
      },
      2: {
        owned: 0,
        available: 5,
        elite2: 0,
        max_level: 0,
        module_level: 0,
        supports_mastery: false,
        supports_modules: false,
        max_phase: 0,
        max_level_limit: 30,
        skills: { 1: 0, 2: 0, 3: 0 },
        modules: { 1: 0, 2: 0, 3: 0 },
        sanity: 0,
        consumed_lmd: 0,
        consumed_exp: 0,
        module_blocks: 0,
        skill_book_equivalent: 0,
        materials: [],
        ranking: [],
        incomplete: [],
        unpriced: []
      },
      3: {
        owned: 3,
        available: 17,
        elite2: 0,
        max_level: 0,
        module_level: 0,
        supports_mastery: false,
        supports_modules: false,
        max_phase: 1,
        max_level_limit: 55,
        skills: { 1: 0, 2: 0, 3: 0 },
        modules: { 1: 0, 2: 0, 3: 0 },
        sanity: 509.55,
        consumed_lmd: 62097,
        consumed_exp: 75389,
        module_blocks: 0,
        skill_book_equivalent: 0.89,
        materials: [
          { id: 'growth_exp', name: '作战记录经验', count: 75389, value: 0.0036, sanity: 271.4 },
          { id: '4001', name: '龙门币', count: 62097, value: 0.0036, sanity: 223.55 },
          { id: '3301', name: '技巧概要·卷1', count: 5, value: 1.2, sanity: 6 },
          { id: '3302', name: '技巧概要·卷2', count: 1, value: 3.6, sanity: 3.6 },
          { id: '30022', name: '糖', count: 1, value: 2.6, sanity: 2.6 },
          { id: '30011', name: '源岩', count: 2, value: 1.2, sanity: 2.4 }
        ],
        ranking: [
          {
            char_id: 'char_123_fang',
            name: '芬',
            rarity: 3,
            sanity: 425.45,
            unpriced: [],
            incomplete: false,
            forms: ['char_123_fang']
          },
          {
            char_id: 'char_124_kroos',
            name: '克洛丝',
            rarity: 3,
            sanity: 58.23,
            unpriced: [],
            incomplete: false,
            forms: ['char_124_kroos']
          },
          {
            char_id: 'char_122_beagle',
            name: '米格鲁',
            rarity: 3,
            sanity: 25.86,
            unpriced: [],
            incomplete: false,
            forms: ['char_122_beagle']
          }
        ],
        incomplete: [],
        unpriced: []
      },
      4: {
        owned: 4,
        available: 61,
        elite2: 0,
        max_level: 0,
        module_level: 0,
        supports_mastery: true,
        supports_modules: true,
        max_phase: 2,
        max_level_limit: 70,
        skills: { 1: 0, 2: 0, 3: 0 },
        modules: { 1: 0, 2: 0, 3: 0 },
        sanity: 782.32,
        consumed_lmd: 102931,
        consumed_exp: 91436,
        module_blocks: 0,
        skill_book_equivalent: 2.33,
        materials: [
          { id: '4001', name: '龙门币', count: 102931, value: 0.0036, sanity: 370.55 },
          { id: 'growth_exp', name: '作战记录经验', count: 91436, value: 0.0036, sanity: 329.17 },
          { id: '3211', name: '先锋芯片', count: 6, value: 6, sanity: 36 },
          { id: '3301', name: '技巧概要·卷1', count: 12, value: 1.2, sanity: 14.4 },
          { id: '3302', name: '技巧概要·卷2', count: 3, value: 3.6, sanity: 10.8 },
          { id: '30062', name: '装置', count: 2, value: 2.6, sanity: 5.2 },
          { id: '30021', name: '代糖', count: 4, value: 1.2, sanity: 4.8 },
          { id: '30051', name: '双酮', count: 3, value: 1.2, sanity: 3.6 },
          { id: '30022', name: '糖', count: 1, value: 2.6, sanity: 2.6 },
          { id: '30042', name: '异铁', count: 1, value: 2.6, sanity: 2.6 },
          { id: '30052', name: '酮凝集', count: 1, value: 2.6, sanity: 2.6 }
        ],
        ranking: [
          {
            char_id: 'char_151_myrtle',
            name: '桃金娘',
            rarity: 4,
            sanity: 384.08,
            unpriced: [],
            incomplete: false,
            forms: ['char_151_myrtle']
          },
          {
            char_id: 'char_198_blackd',
            name: '讯使',
            rarity: 4,
            sanity: 238.4,
            unpriced: [],
            incomplete: false,
            forms: ['char_198_blackd']
          },
          {
            char_id: 'char_196_sunbr',
            name: '古米',
            rarity: 4,
            sanity: 118.85,
            unpriced: [],
            incomplete: false,
            forms: ['char_196_sunbr']
          },
          {
            char_id: 'char_149_scave',
            name: '清道夫',
            rarity: 4,
            sanity: 40.99,
            unpriced: [],
            incomplete: false,
            forms: ['char_149_scave']
          }
        ],
        incomplete: [],
        unpriced: []
      },
      5: {
        owned: 6,
        available: 199,
        elite2: 0,
        max_level: 0,
        module_level: 0,
        supports_mastery: true,
        supports_modules: true,
        max_phase: 2,
        max_level_limit: 80,
        skills: { 1: 0, 2: 0, 3: 0 },
        modules: { 1: 0, 2: 0, 3: 0 },
        sanity: 4170.44,
        consumed_lmd: 511318,
        consumed_exp: 460110,
        module_blocks: 0,
        skill_book_equivalent: 23.33,
        materials: [
          { id: '4001', name: '龙门币', count: 511318, value: 0.0036, sanity: 1840.74 },
          { id: 'growth_exp', name: '作战记录经验', count: 460110, value: 0.0036, sanity: 1656.4 },
          { id: '3302', name: '技巧概要·卷2', count: 54, value: 3.6, sanity: 194.4 },
          { id: '30012', name: '固源岩', count: 31, value: 2.6, sanity: 80.6 },
          { id: '3301', name: '技巧概要·卷1', count: 48, value: 1.2, sanity: 57.6 },
          { id: '3221', name: '近卫芯片', count: 8, value: 6, sanity: 48 },
          { id: '3261', name: '医疗芯片', count: 8, value: 6, sanity: 48 },
          { id: '30011', name: '源岩', count: 30, value: 1.2, sanity: 36 },
          { id: '30022', name: '糖', count: 13, value: 2.6, sanity: 33.8 },
          { id: '30032', name: '聚酸酯', count: 13, value: 2.6, sanity: 33.8 },
          { id: '30042', name: '异铁', count: 10, value: 2.6, sanity: 26 },
          { id: '30052', name: '酮凝集', count: 10, value: 2.6, sanity: 26 },
          { id: '3211', name: '先锋芯片', count: 4, value: 6, sanity: 24 },
          { id: '3281', name: '特种芯片', count: 4, value: 6, sanity: 24 },
          { id: '30063', name: '全新装置', count: 3, value: 4.7, sanity: 14.1 },
          { id: '30031', name: '酯原料', count: 7, value: 1.2, sanity: 8.4 },
          { id: '30062', name: '装置', count: 3, value: 2.6, sanity: 7.8 },
          { id: '30041', name: '异铁碎片', count: 5, value: 1.2, sanity: 6 },
          { id: '30061', name: '破损装置', count: 4, value: 1.2, sanity: 4.8 }
        ],
        ranking: [
          {
            char_id: 'char_102_texas',
            name: '德克萨斯',
            rarity: 5,
            sanity: 1060.66,
            unpriced: [],
            incomplete: false,
            forms: ['char_102_texas']
          },
          {
            char_id: 'char_140_whitew',
            name: '拉普兰德',
            rarity: 5,
            sanity: 864.21,
            unpriced: [],
            incomplete: false,
            forms: ['char_140_whitew']
          },
          {
            char_id: 'char_128_plosis',
            name: '白面鸮',
            rarity: 5,
            sanity: 751.66,
            unpriced: [],
            incomplete: false,
            forms: ['char_128_plosis']
          },
          {
            char_id: 'char_108_silent',
            name: '赫默',
            rarity: 5,
            sanity: 611.23,
            unpriced: [],
            incomplete: false,
            forms: ['char_108_silent']
          },
          {
            char_id: 'char_143_ghost',
            name: '幽灵鲨',
            rarity: 5,
            sanity: 496.18,
            unpriced: [],
            incomplete: false,
            forms: ['char_143_ghost']
          },
          {
            char_id: 'char_173_slchan',
            name: '崖心',
            rarity: 5,
            sanity: 386.49,
            unpriced: [],
            incomplete: false,
            forms: ['char_173_slchan']
          }
        ],
        incomplete: [],
        unpriced: []
      },
      6: {
        owned: 13,
        available: 138,
        elite2: 13,
        max_level: 2,
        module_level: 7,
        supports_mastery: true,
        supports_modules: true,
        max_phase: 2,
        max_level_limit: 90,
        skills: { 1: 6, 2: 3, 3: 7 },
        modules: { 1: 2, 2: 1, 3: 1 },
        sanity: 89056.57,
        consumed_lmd: 11471454,
        consumed_exp: 8322593,
        module_blocks: 28,
        skill_book_equivalent: 533.44,
        materials: [
          { id: '4001', name: '龙门币', count: 11471454, value: 0.0036, sanity: 41297.23 },
          {
            id: 'growth_exp',
            name: '作战记录经验',
            count: 8322593,
            value: 0.0036,
            sanity: 29961.33
          },
          { id: '3303', name: '技巧概要·卷3', count: 415, value: 10.8, sanity: 4482 },
          { id: 'mod_update_token_1', name: '数据增补条', count: 120, value: 10, sanity: 1200 },
          { id: '3302', name: '技巧概要·卷2', count: 312, value: 3.6, sanity: 1123.2 },
          { id: '30115', name: '聚合剂', count: 54, value: 17.5, sanity: 945 },
          { id: '3223', name: '近卫双芯片', count: 16, value: 54, sanity: 864 },
          { id: '3253', name: '术师双芯片', count: 12, value: 54, sanity: 648 },
          { id: '30135', name: 'D32钢', count: 26, value: 17.5, sanity: 455 },
          { id: '30074', name: '白马醇', count: 51, value: 8.9, sanity: 453.9 },
          { id: '3213', name: '先锋双芯片', count: 8, value: 54, sanity: 432 },
          { id: 'mod_unlock_token', name: '模组数据块', count: 28, value: 15, sanity: 420 },
          { id: 'mod_update_token_2', name: '数据增补仪', count: 20, value: 20, sanity: 400 },
          { id: '30054', name: '酮阵列', count: 43, value: 8.9, sanity: 382.7 },
          { id: '30084', name: '三水锰矿', count: 36, value: 8.9, sanity: 320.4 },
          { id: '30145', name: '晶体电子单元', count: 18, value: 17.5, sanity: 315 },
          { id: '30012', name: '固源岩', count: 107, value: 2.6, sanity: 278.2 },
          { id: '30014', name: '提纯源岩', count: 30, value: 8.9, sanity: 267 },
          { id: '30094', name: '五水研磨石', count: 26, value: 8.9, sanity: 231.4 },
          { id: '3233', name: '重装双芯片', count: 4, value: 54, sanity: 216 },
          { id: '3243', name: '狙击双芯片', count: 4, value: 54, sanity: 216 },
          { id: '3263', name: '医疗双芯片', count: 4, value: 54, sanity: 216 },
          { id: '3273', name: '辅助双芯片', count: 4, value: 54, sanity: 216 },
          { id: '30104', name: 'RMA70-24', count: 24, value: 8.9, sanity: 213.6 },
          { id: '30073', name: '扭转醇', count: 45, value: 4.7, sanity: 211.5 },
          { id: '30032', name: '聚酸酯', count: 68, value: 2.6, sanity: 176.8 },
          { id: '30155', name: '烧结核凝晶', count: 10, value: 17.5, sanity: 175 },
          { id: '3301', name: '技巧概要·卷1', count: 130, value: 1.2, sanity: 156 },
          { id: '30064', name: '改量装置', count: 16, value: 8.9, sanity: 142.4 },
          { id: '30052', name: '酮凝集', count: 53, value: 2.6, sanity: 137.8 },
          { id: '30024', name: '糖聚块', count: 15, value: 8.9, sanity: 133.5 },
          { id: '30013', name: '固源岩组', count: 27, value: 4.7, sanity: 126.9 },
          { id: '30044', name: '异铁块', count: 14, value: 8.9, sanity: 124.6 },
          { id: '3221', name: '近卫芯片', count: 20, value: 6, sanity: 120 },
          { id: '30042', name: '异铁', count: 45, value: 2.6, sanity: 117 },
          { id: '31024', name: '炽合金块', count: 13, value: 8.9, sanity: 115.7 },
          { id: '30053', name: '酮凝集组', count: 24, value: 4.7, sanity: 112.8 },
          { id: '30063', name: '全新装置', count: 20, value: 4.7, sanity: 94 },
          { id: '30062', name: '装置', count: 36, value: 2.6, sanity: 93.6 },
          { id: '3251', name: '术师芯片', count: 15, value: 6, sanity: 90 },
          { id: '30093', name: '研磨石', count: 19, value: 4.7, sanity: 89.3 },
          { id: '31044', name: '精炼溶剂', count: 10, value: 8.9, sanity: 89 },
          { id: '30033', name: '聚酸酯组', count: 18, value: 4.7, sanity: 84.6 },
          { id: '31034', name: '晶体电路', count: 9, value: 8.9, sanity: 80.1 },
          { id: '30043', name: '异铁组', count: 16, value: 4.7, sanity: 75.2 },
          { id: '30083', name: '轻锰矿', count: 16, value: 4.7, sanity: 75.2 },
          { id: '30103', name: 'RMA70-12', count: 16, value: 4.7, sanity: 75.2 },
          { id: '31014', name: '聚合凝胶', count: 8, value: 8.9, sanity: 71.2 },
          { id: '31023', name: '炽合金', count: 15, value: 4.7, sanity: 70.5 },
          { id: '30125', name: '双极纳米片', count: 4, value: 17.5, sanity: 70 },
          { id: '30022', name: '糖', count: 24, value: 2.6, sanity: 62.4 },
          { id: '31013', name: '凝胶', count: 13, value: 4.7, sanity: 61.1 },
          { id: '3211', name: '先锋芯片', count: 10, value: 6, sanity: 60 },
          { id: '30023', name: '糖组', count: 11, value: 4.7, sanity: 51.7 },
          { id: '31043', name: '半自然溶剂', count: 8, value: 4.7, sanity: 37.6 },
          { id: '30021', name: '代糖', count: 31, value: 1.2, sanity: 37.2 },
          { id: '30034', name: '聚酸酯块', count: 4, value: 8.9, sanity: 35.6 },
          { id: '3231', name: '重装芯片', count: 5, value: 6, sanity: 30 },
          { id: '3241', name: '狙击芯片', count: 5, value: 6, sanity: 30 },
          { id: '3261', name: '医疗芯片', count: 5, value: 6, sanity: 30 },
          { id: '3271', name: '辅助芯片', count: 5, value: 6, sanity: 30 },
          { id: '30041', name: '异铁碎片', count: 24, value: 1.2, sanity: 28.8 },
          { id: '30051', name: '双酮', count: 24, value: 1.2, sanity: 28.8 },
          { id: '31053', name: '化合切削液', count: 5, value: 4.7, sanity: 23.5 },
          { id: '30011', name: '源岩', count: 14, value: 1.2, sanity: 16.8 },
          { id: '30031', name: '酯原料', count: 14, value: 1.2, sanity: 16.8 },
          { id: '30061', name: '破损装置', count: 12, value: 1.2, sanity: 14.4 }
        ],
        ranking: [
          {
            char_id: 'char_172_svrash',
            name: '银灰',
            rarity: 6,
            sanity: 12741.11,
            unpriced: [],
            incomplete: false,
            forms: ['char_172_svrash']
          },
          {
            char_id: 'char_103_angel',
            name: '能天使',
            rarity: 6,
            sanity: 12700.31,
            unpriced: [],
            incomplete: false,
            forms: ['char_103_angel']
          },
          {
            char_id: 'char_180_amgoat',
            name: '艾雅法拉',
            rarity: 6,
            sanity: 9383.23,
            unpriced: [],
            incomplete: false,
            forms: ['char_180_amgoat']
          },
          {
            char_id: 'char_311_mudrok',
            name: '泥岩',
            rarity: 6,
            sanity: 6694.99,
            unpriced: [],
            incomplete: false,
            forms: ['char_311_mudrok']
          },
          {
            char_id: 'char_293_thorns',
            name: '棘刺',
            rarity: 6,
            sanity: 6639,
            unpriced: [],
            incomplete: false,
            forms: ['char_293_thorns']
          },
          {
            char_id: 'char_179_cgbird',
            name: '夜莺',
            rarity: 6,
            sanity: 6440.69,
            unpriced: [],
            incomplete: false,
            forms: ['char_179_cgbird']
          },
          {
            char_id: 'char_4133_logos',
            name: '逻各斯',
            rarity: 6,
            sanity: 6265.3,
            unpriced: [],
            incomplete: false,
            forms: ['char_4133_logos']
          },
          {
            char_id: 'char_4087_ines',
            name: '伊内丝',
            rarity: 6,
            sanity: 5409.25,
            unpriced: [],
            incomplete: false,
            forms: ['char_4087_ines']
          },
          {
            char_id: 'char_264_f12yin',
            name: '山',
            rarity: 6,
            sanity: 5378.81,
            unpriced: [],
            incomplete: false,
            forms: ['char_264_f12yin']
          },
          {
            char_id: 'char_350_surtr',
            name: '史尔特尔',
            rarity: 6,
            sanity: 4558.86,
            unpriced: [],
            incomplete: false,
            forms: ['char_350_surtr']
          },
          {
            char_id: 'char_2023_ling',
            name: '令',
            rarity: 6,
            sanity: 4524.87,
            unpriced: [],
            incomplete: false,
            forms: ['char_2023_ling']
          },
          {
            char_id: 'char_479_sleach',
            name: '琴柳',
            rarity: 6,
            sanity: 4190.66,
            unpriced: [],
            incomplete: false,
            forms: ['char_479_sleach']
          },
          {
            char_id: 'char_377_gdglow',
            name: '澄闪',
            rarity: 6,
            sanity: 4129.49,
            unpriced: [],
            incomplete: false,
            forms: ['char_377_gdglow']
          }
        ],
        incomplete: [],
        unpriced: []
      }
    },
    source: {
      source: '离线预览 · 一图流材料价值示例',
      algorithm_url: 'https://ark.yituliu.cn/survey/operators',
      values_url: 'https://ark.yituliu.cn/survey/operators',
      imported_at: 1792558842,
      pricing_mode: 'builtin'
    }
  }
}

const HISTORY = [
  [1782622842, 0.42],
  [1786510842, 0.58],
  [1789534842, 0.72],
  [1791781242, 0.86],
  [1792990842, 1]
]

const SCENARIOS = {
  plans: [
    {
      id: 1,
      char_id: 'char_103_angel',
      name: '能天使',
      skill_index: 2,
      skill_name: '三技能·过载模式',
      target_level: 3,
      status: 'training',
      priority: 0,
      expires_at: null,
      failed_reason: null,
      support_runtime: {
        operator: '艾丽妮',
        efficiency: 75,
        level: 3,
        swap_target: null,
        swap_efficiency: 0,
        central_bonus: 5,
        mastery_swap_buffer: 10,
        configured_swap_buffer: 10,
        half_inherited: false,
        hours: 12.3,
        switch_after: null,
        activate_with: null,
        next_carry: null,
        manual: false,
        working_operator: '艾丽妮',
        working_since: '2026-10-26T07:48:42.833884',
        working_halves: true,
        working_until: '2026-10-26T20:20:42.833884'
      },
      support_current: 2
    },
    {
      id: 2,
      char_id: 'char_172_svrash',
      name: '银灰',
      skill_index: 1,
      skill_name: '二技能·雪境生存法则',
      target_level: 3,
      status: 'waiting_collect',
      priority: 1,
      expires_at: null,
      failed_reason: null,
      support_runtime: {
        operator: '逻各斯',
        efficiency: 60,
        level: 3,
        swap_target: null,
        swap_efficiency: 0,
        central_bonus: 5,
        mastery_swap_buffer: 10,
        configured_swap_buffer: 10,
        half_inherited: false,
        hours: 15,
        switch_after: null,
        activate_with: null,
        next_carry: null,
        manual: false,
        working_operator: '逻各斯',
        working_since: '2026-10-25T16:00:42.833884',
        working_halves: false,
        working_until: '2026-10-26T16:00:42.833884'
      },
      support_current: 1
    },
    {
      id: 3,
      char_id: 'char_180_amgoat',
      name: '艾雅法拉',
      skill_index: 2,
      skill_name: '三技能·火山',
      target_level: 3,
      status: 'idle',
      priority: 2,
      expires_at: null,
      failed_reason: null,
      support_runtime: null,
      support_current: 1
    },
    {
      id: 4,
      char_id: 'char_311_mudrok',
      name: '泥岩',
      skill_index: 1,
      skill_name: '二技能·岩崩锤',
      target_level: 3,
      status: 'idle',
      priority: 3,
      expires_at: null,
      failed_reason: null,
      support_runtime: null,
      support_current: 0
    },
    {
      id: 5,
      char_id: 'char_377_gdglow',
      name: '澄闪',
      skill_index: 0,
      skill_name: '一技能·火花四溅',
      target_level: 2,
      status: 'failed',
      priority: 5,
      expires_at: null,
      failed_reason: '训练位被占用，等待下一轮重试',
      support_runtime: null,
      support_current: 0
    },
    {
      id: 6,
      char_id: 'char_4087_ines',
      name: '伊内丝',
      skill_index: 0,
      skill_name: '一技能·淬影突袭',
      target_level: 3,
      status: 'idle',
      priority: 4,
      expires_at: '2026-10-27T13:00:42.833884',
      failed_reason: '材料不足',
      support_runtime: null,
      support_current: 1
    }
  ],
  planHistory: [
    {
      char_id: 'char_103_angel',
      name: '能天使',
      skill_index: 0,
      skill_name: '一技能·冲锋模式',
      target_level: 3,
      status: 'completed',
      failed_reason: null,
      time: '2026-09-30 10:00'
    },
    {
      char_id: 'char_180_amgoat',
      name: '艾雅法拉',
      skill_index: 0,
      skill_name: '一技能·二重咏唱',
      target_level: 3,
      status: 'completed',
      failed_reason: null,
      time: '2026-10-08 04:00'
    },
    {
      char_id: 'char_264_f12yin',
      name: '山',
      skill_index: 0,
      skill_name: '一技能·裂天',
      target_level: 2,
      status: 'completed',
      failed_reason: null,
      time: '2026-10-15 08:00'
    },
    {
      char_id: 'char_293_thorns',
      name: '棘刺',
      skill_index: 1,
      skill_name: '二技能·护身尖刺',
      target_level: 1,
      status: 'completed',
      failed_reason: null,
      time: '2026-10-21 23:00'
    }
  ],
  craftingOrder: {
    items: [
      {
        key: 'skill:char_103_angel:2',
        char_id: 'char_103_angel',
        kind: 'skill',
        locked: true,
        status: 'active',
        reason: '',
        char_name: '能天使',
        label: '三技能·过载模式 · 专三',
        profession: 'SNIPER',
        plan_id: 1
      },
      {
        key: 'skill:char_172_svrash:1',
        char_id: 'char_172_svrash',
        kind: 'skill',
        locked: true,
        status: 'active',
        reason: '',
        char_name: '银灰',
        label: '二技能·雪境生存法则 · 专三',
        profession: 'WARRIOR',
        plan_id: 2
      },
      {
        key: 'skill:char_4087_ines:0',
        char_id: 'char_4087_ines',
        kind: 'skill',
        locked: true,
        status: 'active',
        reason: '',
        char_name: '伊内丝',
        label: '一技能·淬影突袭 · 专三',
        profession: 'PIONEER',
        plan_id: 6
      },
      {
        key: 'skill:char_180_amgoat:2',
        char_id: 'char_180_amgoat',
        kind: 'skill',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '艾雅法拉',
        label: '三技能·火山 · 专三',
        profession: 'CASTER',
        plan_id: 3
      },
      {
        key: 'skill:char_311_mudrok:1',
        char_id: 'char_311_mudrok',
        kind: 'skill',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '泥岩',
        label: '二技能·岩崩锤 · 专三',
        profession: 'TANK',
        plan_id: 4
      },
      {
        key: 'skill:char_377_gdglow:0',
        char_id: 'char_377_gdglow',
        kind: 'skill',
        locked: false,
        status: 'preparing',
        reason: '仅准备材料，前置未完成',
        char_name: '澄闪',
        label: '一技能·火花四溅 · 专二',
        profession: 'CASTER',
        plan_id: 5
      },
      {
        key: 'goal:char_102_texas:elite2',
        char_id: 'char_102_texas',
        kind: 'goal',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '德克萨斯',
        label: '精英化至精二 Lv.1',
        profession: 'PIONEER',
        module_id: 'elite2'
      },
      {
        key: 'goal:char_140_whitew:skill7',
        char_id: 'char_140_whitew',
        kind: 'goal',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '拉普兰德',
        label: '基础技能升至 7 级',
        profession: 'WARRIOR',
        module_id: 'skill7'
      },
      {
        key: 'goal:char_143_ghost:elite2',
        char_id: 'char_143_ghost',
        kind: 'goal',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '幽灵鲨',
        label: '精英化至精二 Lv.1',
        profession: 'WARRIOR',
        module_id: 'elite2'
      },
      {
        key: 'goal:char_173_slchan:elite2',
        char_id: 'char_173_slchan',
        kind: 'goal',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '崖心',
        label: '精英化至精二 Lv.1',
        profession: 'SPECIAL',
        module_id: 'elite2'
      },
      {
        key: 'goal:char_151_myrtle:elite2',
        char_id: 'char_151_myrtle',
        kind: 'goal',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '桃金娘',
        label: '精英化至精二 Lv.1',
        profession: 'PIONEER',
        module_id: 'elite2'
      },
      {
        key: 'goal:char_180_amgoat:uniequip_002_amgoat',
        char_id: 'char_180_amgoat',
        kind: 'goal',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '艾雅法拉',
        label: '“错过的声音” · 模组 3 级',
        profession: 'CASTER',
        module_id: 'uniequip_002_amgoat'
      }
    ],
    planning_items: [
      {
        key: 'skill:char_103_angel:2',
        char_id: 'char_103_angel',
        kind: 'skill',
        locked: true,
        status: 'active',
        reason: '',
        char_name: '能天使',
        label: '三技能·过载模式 · 专三',
        profession: 'SNIPER',
        plan_id: 1,
        crafting_required: true
      },
      {
        key: 'skill:char_172_svrash:1',
        char_id: 'char_172_svrash',
        kind: 'skill',
        locked: true,
        status: 'active',
        reason: '',
        char_name: '银灰',
        label: '二技能·雪境生存法则 · 专三',
        profession: 'WARRIOR',
        plan_id: 2,
        crafting_required: true
      },
      {
        key: 'skill:char_4087_ines:0',
        char_id: 'char_4087_ines',
        kind: 'skill',
        locked: true,
        status: 'active',
        reason: '',
        char_name: '伊内丝',
        label: '一技能·淬影突袭 · 专三',
        profession: 'PIONEER',
        plan_id: 6,
        crafting_required: true
      },
      {
        key: 'skill:char_180_amgoat:2',
        char_id: 'char_180_amgoat',
        kind: 'skill',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '艾雅法拉',
        label: '三技能·火山 · 专三',
        profession: 'CASTER',
        plan_id: 3,
        crafting_required: true
      },
      {
        key: 'skill:char_311_mudrok:1',
        char_id: 'char_311_mudrok',
        kind: 'skill',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '泥岩',
        label: '二技能·岩崩锤 · 专三',
        profession: 'TANK',
        plan_id: 4,
        crafting_required: true
      },
      {
        key: 'skill:char_377_gdglow:0',
        char_id: 'char_377_gdglow',
        kind: 'skill',
        locked: false,
        status: 'preparing',
        reason: '仅准备材料，前置未完成',
        char_name: '澄闪',
        label: '一技能·火花四溅 · 专二',
        profession: 'CASTER',
        plan_id: 5,
        crafting_required: true
      },
      {
        key: 'goal:char_102_texas:elite2',
        char_id: 'char_102_texas',
        kind: 'goal',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '德克萨斯',
        label: '精二 Lv.1',
        profession: 'PIONEER',
        module_id: 'elite2',
        crafting_required: true
      },
      {
        key: 'goal:char_140_whitew:skill7',
        char_id: 'char_140_whitew',
        kind: 'goal',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '拉普兰德',
        label: '基础技能升至 7 级',
        profession: 'WARRIOR',
        module_id: 'skill7',
        crafting_required: true
      },
      {
        key: 'goal:char_143_ghost:elite2',
        char_id: 'char_143_ghost',
        kind: 'goal',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '幽灵鲨',
        label: '精二 Lv.1',
        profession: 'WARRIOR',
        module_id: 'elite2',
        crafting_required: true
      },
      {
        key: 'goal:char_173_slchan:elite2',
        char_id: 'char_173_slchan',
        kind: 'goal',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '崖心',
        label: '精二 Lv.1',
        profession: 'SPECIAL',
        module_id: 'elite2',
        crafting_required: true
      },
      {
        key: 'goal:char_377_gdglow:elite2_module',
        char_id: 'char_377_gdglow',
        kind: 'goal',
        locked: false,
        status: 'manual',
        reason: '纯等级提升，不需要合成',
        char_name: '澄闪',
        label: '精二 Lv.60',
        profession: 'CASTER',
        module_id: 'elite2_module',
        crafting_required: false
      },
      {
        key: 'goal:char_264_f12yin:elite2_max',
        char_id: 'char_264_f12yin',
        kind: 'goal',
        locked: false,
        status: 'manual',
        reason: '纯等级提升，不需要合成',
        char_name: '山',
        label: '精二 Lv.90',
        profession: 'WARRIOR',
        module_id: 'elite2_max',
        crafting_required: false
      },
      {
        key: 'goal:char_151_myrtle:elite2',
        char_id: 'char_151_myrtle',
        kind: 'goal',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '桃金娘',
        label: '精二 Lv.1',
        profession: 'PIONEER',
        module_id: 'elite2',
        crafting_required: true
      },
      {
        key: 'goal:char_180_amgoat:uniequip_002_amgoat',
        char_id: 'char_180_amgoat',
        kind: 'goal',
        locked: false,
        status: 'ready',
        reason: '',
        char_name: '艾雅法拉',
        label: '“错过的声音” · 模组 3 级',
        profession: 'CASTER',
        module_id: 'uniequip_002_amgoat',
        crafting_required: true
      }
    ],
    prepared_items: [
      {
        key: 'skill:char_180_amgoat:2',
        char_id: 'char_180_amgoat',
        kind: 'skill',
        locked: false,
        status: 'ready',
        reason: '材料已备齐，待完成养成',
        char_name: '艾雅法拉',
        label: '三技能·火山 · 专三',
        profession: 'CASTER',
        plan_id: 3,
        crafting_required: true,
        materials_prepared: true
      },
      {
        key: 'skill:char_311_mudrok:1',
        char_id: 'char_311_mudrok',
        kind: 'skill',
        locked: false,
        status: 'ready',
        reason: '材料已备齐，待完成养成',
        char_name: '泥岩',
        label: '二技能·岩崩锤 · 专三',
        profession: 'TANK',
        plan_id: 4,
        crafting_required: true,
        materials_prepared: true
      }
    ],
    custom: true
  },
  survey: {
    operators: [
      {
        charId: 'char_2023_ling',
        own: 16800,
        sampleSize: 26880,
        elite: { 0: 521, 1: 2369, 2: 13910 },
        skill1: { 0: 0, 1: 0, 2: 4520, 3: 12280 },
        skill2: { 0: 0, 1: 0, 2: 6156, 3: 10644 },
        skill3: { 0: 0, 1: 0, 2: 5625, 3: 11175 },
        modY: { 0: 10920, 1: 2058, 2: 1764, 3: 2058 }
      },
      {
        charId: 'char_4087_ines',
        own: 21684,
        sampleSize: 37513,
        elite: { 0: 377, 1: 1714, 2: 19593 },
        skill1: { 0: 0, 1: 0, 2: 5274, 3: 16410 },
        skill2: { 0: 0, 1: 0, 2: 7477, 3: 14207 },
        skill3: { 0: 0, 1: 0, 2: 6785, 3: 14899 },
        modY: { 0: 9541, 1: 4251, 2: 3642, 3: 4250 }
      },
      {
        charId: 'char_350_surtr',
        own: 26568,
        sampleSize: 49416,
        elite: { 0: 616, 1: 2806, 2: 23146 },
        skill1: { 0: 0, 1: 0, 2: 5776, 3: 20792 },
        skill2: { 0: 0, 1: 0, 2: 8587, 3: 17981 },
        skill3: { 0: 0, 1: 0, 2: 7730, 3: 18838 },
        modX: { 0: 14082, 1: 4371, 2: 3745, 3: 4370 },
        modY: { 0: 14082, 1: 4371, 2: 3745, 3: 4370 }
      },
      {
        charId: 'char_179_cgbird',
        own: 18252,
        sampleSize: 36321,
        elite: { 0: 530, 1: 2413, 2: 15309 },
        skill1: { 0: 0, 1: 0, 2: 3498, 3: 14754 },
        skill2: { 0: 0, 1: 0, 2: 5505, 3: 12747 },
        skill3: { 0: 0, 1: 0, 2: 4910, 3: 13342 },
        modX: { 0: 11317, 1: 2428, 2: 2080, 3: 2427 },
        modY: { 0: 11317, 1: 2428, 2: 2080, 3: 2427 }
      },
      {
        charId: 'char_264_f12yin',
        own: 23136,
        sampleSize: 37480,
        elite: { 0: 357, 1: 1624, 2: 21155 },
        skill1: { 0: 0, 1: 0, 2: 3836, 3: 19300 },
        skill2: { 0: 0, 1: 0, 2: 6479, 3: 16657 },
        skill3: { 0: 0, 1: 0, 2: 5717, 3: 17419 },
        modY: { 0: 9486, 1: 4778, 2: 4095, 3: 4777 },
        modX: { 0: 9486, 1: 4778, 2: 4095, 3: 4777 }
      },
      {
        charId: 'char_293_thorns',
        own: 28020,
        sampleSize: 49035,
        elite: { 0: 596, 1: 2711, 2: 24713 },
        skill1: { 0: 0, 1: 0, 2: 3923, 3: 24097 },
        skill2: { 0: 0, 1: 0, 2: 7241, 3: 20779 },
        skill3: { 0: 0, 1: 0, 2: 6309, 3: 21711 },
        modX: { 0: 14010, 1: 4904, 2: 4203, 3: 4903 },
        modD: { 0: 14010, 1: 4904, 2: 4203, 3: 4903 }
      },
      {
        charId: 'char_311_mudrok',
        own: 19704,
        sampleSize: 37043,
        elite: { 0: 534, 1: 2430, 2: 16740 },
        skill1: { 0: 0, 1: 0, 2: 2251, 3: 17453 },
        skill2: { 0: 0, 1: 0, 2: 4666, 3: 15038 },
        skill3: { 0: 0, 1: 0, 2: 4005, 3: 15699 },
        modX: { 0: 11626, 1: 2828, 2: 2423, 3: 2827 },
        modY: { 0: 11626, 1: 2828, 2: 2423, 3: 2827 }
      },
      {
        charId: 'char_377_gdglow',
        own: 24588,
        sampleSize: 49421,
        elite: { 0: 332, 1: 1508, 2: 22748 },
        skill1: { 0: 0, 1: 0, 2: 2174, 3: 22414 },
        skill2: { 0: 0, 1: 0, 2: 5292, 3: 19296 },
        skill3: { 0: 0, 1: 0, 2: 4458, 3: 20130 },
        modX: { 0: 9344, 1: 5336, 2: 4573, 3: 5335 },
        modY: { 0: 9344, 1: 5336, 2: 4573, 3: 5335 }
      },
      {
        charId: 'char_479_sleach',
        own: 29472,
        sampleSize: 48334,
        elite: { 0: 569, 1: 2591, 2: 26312 },
        skill1: { 0: 0, 1: 0, 2: 1845, 3: 27627 },
        skill2: { 0: 0, 1: 0, 2: 5706, 3: 23766 },
        skill3: { 0: 0, 1: 0, 2: 11160, 3: 18312 },
        modX: { 0: 13852, 1: 5467, 2: 4686, 3: 5467 },
        modY: { 0: 13852, 1: 5467, 2: 4686, 3: 5467 }
      },
      {
        charId: 'char_103_angel',
        own: 21156,
        sampleSize: 37446,
        elite: { 0: 532, 1: 2422, 2: 18202 },
        skill1: { 0: 0, 1: 0, 2: 1058, 3: 20098 },
        skill2: { 0: 0, 1: 0, 2: 8209, 3: 12947 },
        skill3: { 0: 0, 1: 0, 2: 7547, 3: 13609 },
        modX: { 0: 11848, 1: 3259, 2: 2792, 3: 3257 },
        modY: { 0: 11848, 1: 3259, 2: 2792, 3: 3257 }
      },
      {
        charId: 'char_180_amgoat',
        own: 26040,
        sampleSize: 49476,
        elite: { 0: 807, 1: 3672, 2: 21561 },
        skill1: { 0: 0, 1: 0, 2: 7005, 3: 19035 },
        skill2: { 0: 0, 1: 0, 2: 9542, 3: 16498 },
        skill3: { 0: 0, 1: 0, 2: 8718, 3: 17322 },
        modX: { 0: 16926, 1: 3191, 2: 2734, 3: 3189 },
        modY: { 0: 16926, 1: 3191, 2: 2734, 3: 3189 }
      },
      {
        charId: 'char_4133_logos',
        own: 17724,
        sampleSize: 35979,
        elite: { 0: 308, 1: 1401, 2: 16015 },
        skill1: { 0: 0, 1: 0, 2: 4311, 3: 13413 },
        skill2: { 0: 0, 1: 0, 2: 6112, 3: 11612 },
        skill3: { 0: 0, 1: 0, 2: 5546, 3: 12178 },
        modD: { 0: 7799, 1: 3475, 2: 2977, 3: 3473 },
        modY: { 0: 7799, 1: 3475, 2: 2977, 3: 3473 }
      },
      {
        charId: 'char_172_svrash',
        own: 22608,
        sampleSize: 37529,
        elite: { 0: 525, 1: 2387, 2: 19696 },
        skill1: { 0: 0, 1: 0, 2: 4915, 3: 17693 },
        skill2: { 0: 0, 1: 0, 2: 7307, 3: 15301 },
        skill3: { 0: 0, 1: 0, 2: 6578, 3: 16030 },
        modX: { 0: 11983, 1: 3720, 2: 3187, 3: 3718 }
      },
      {
        charId: 'char_173_slchan',
        own: 12600,
        sampleSize: 22554,
        elite: { 0: 578, 1: 2628, 2: 9394 },
        skill1: { 0: 0, 1: 0, 2: 3836, 3: 8764 },
        skill2: { 0: 0, 1: 0, 2: 5756, 3: 6844 },
        modX: { 0: 7812, 1: 1677, 2: 1436, 3: 1675 }
      },
      {
        charId: 'char_143_ghost',
        own: 8789,
        sampleSize: 16874,
        elite: { 0: 297, 1: 1349, 2: 7143 },
        skill1: { 0: 0, 1: 0, 2: 2481, 3: 6308 },
        skill2: { 0: 0, 1: 0, 2: 3868, 3: 4921 },
        modX: { 0: 3604, 1: 1816, 2: 1555, 3: 1814 }
      },
      {
        charId: 'char_102_texas',
        own: 11027,
        sampleSize: 22605,
        elite: { 0: 429, 1: 1953, 2: 8645 },
        skill1: { 0: 0, 1: 0, 2: 2868, 3: 8159 },
        skill2: { 0: 0, 1: 0, 2: 4667, 3: 6360 },
        modY: { 0: 5514, 1: 1931, 2: 1653, 3: 1929 }
      },
      {
        charId: 'char_140_whitew',
        own: 13266,
        sampleSize: 22286,
        elite: { 0: 585, 1: 2663, 2: 10018 },
        skill1: { 0: 0, 1: 0, 2: 3155, 3: 10111 },
        skill2: { 0: 0, 1: 0, 2: 5392, 3: 7874 },
        modX: { 0: 7827, 1: 1905, 2: 1631, 3: 1903 }
      },
      {
        charId: 'char_128_plosis',
        own: 9454,
        sampleSize: 17111,
        elite: { 0: 303, 1: 1377, 2: 7774 },
        skill1: { 0: 0, 1: 0, 2: 2039, 3: 7415 },
        skill2: { 0: 0, 1: 0, 2: 3684, 3: 5770 },
        modX: { 0: 3593, 1: 2052, 2: 1758, 3: 2051 }
      },
      {
        charId: 'char_108_silent',
        own: 11693,
        sampleSize: 22684,
        elite: { 0: 435, 1: 1979, 2: 9279 },
        skill1: { 0: 0, 1: 0, 2: 2262, 3: 9431 },
        skill2: { 0: 0, 1: 0, 2: 4360, 3: 7333 },
        modY: { 0: 5496, 1: 2170, 2: 1859, 3: 2168 }
      },
      {
        charId: 'char_196_sunbr',
        own: 3009,
        sampleSize: 6228,
        elite: { 0: 200, 1: 911, 2: 1898 },
        skill1: { 0: 507, 1: 1251, 2: 847, 3: 404 },
        skill2: { 0: 0, 1: 468, 2: 1621, 3: 920 },
        modX: { 0: 1686, 1: 464, 2: 396, 3: 463 }
      },
      {
        charId: 'char_151_myrtle',
        own: 3863,
        sampleSize: 6567,
        elite: { 0: 274, 1: 1244, 2: 2345 },
        skill1: { 0: 1206, 1: 1363, 2: 900, 3: 394 },
        skill2: { 0: 0, 1: 496, 2: 2144, 3: 1223 },
        modX: { 0: 2511, 1: 474, 2: 405, 3: 473 }
      },
      {
        charId: 'char_149_scave',
        own: 4718,
        sampleSize: 8633,
        elite: { 0: 287, 1: 1305, 2: 3126 },
        skill1: { 0: 1398, 1: 1698, 2: 1124, 3: 498 },
        skill2: { 0: 0, 1: 478, 2: 2695, 3: 1545 },
        modX: { 0: 2076, 1: 926, 2: 792, 3: 924 }
      },
      {
        charId: 'char_198_blackd',
        own: 3263,
        sampleSize: 6395,
        elite: { 0: 213, 1: 966, 2: 2084 },
        skill1: { 0: 915, 1: 1197, 2: 795, 3: 356 },
        skill2: { 0: 0, 1: 242, 2: 1917, 3: 1104 },
        modX: { 0: 1730, 1: 538, 2: 459, 3: 536 }
      },
      {
        charId: 'char_124_kroos',
        own: 1568,
        sampleSize: 3277,
        elite: { 0: 151, 1: 687, 2: 730 },
        skill1: { 0: 875, 1: 385, 2: 235, 3: 73 },
        skill2: { 0: 0, 1: 683, 2: 581, 3: 304 },
        skill3: { 0: 0, 1: 0, 2: 910, 3: 658 }
      },
      {
        charId: 'char_122_beagle',
        own: 1894,
        sampleSize: 3257,
        elite: { 0: 168, 1: 764, 2: 962 },
        skill1: { 0: 1044, 1: 470, 2: 289, 3: 91 },
        skill2: { 0: 0, 1: 797, 2: 719, 3: 378 },
        skill3: { 0: 0, 1: 0, 2: 1075, 3: 819 }
      },
      {
        charId: 'char_123_fang',
        own: 1339,
        sampleSize: 2477,
        elite: { 0: 123, 1: 560, 2: 656 },
        skill1: { 0: 730, 1: 336, 2: 207, 3: 66 },
        skill2: { 0: 0, 1: 544, 2: 520, 3: 275 },
        skill3: { 0: 0, 1: 0, 2: 743, 3: 596 }
      }
    ],
    fetched_at: 1792985442,
    stale: false,
    error: null,
    source_url: 'https://auth.yituliu.cn/open/ak-operator-statistics/result'
  },
  route: {
    routes: [],
    defaults: {
      先锋: {
        supports: [
          {
            name: '夜半',
            skill_level: 1,
            efficiency: 75,
            swap: true,
            swap_name: '逻各斯',
            match: false
          },
          {
            name: '缄默德克萨斯',
            skill_level: 2,
            efficiency: 80,
            swap: true,
            swap_name: '逻各斯',
            match: false
          },
          {
            name: '凛御银灰',
            skill_level: 3,
            efficiency: 80,
            swap: false,
            swap_name: '',
            match: false
          }
        ],
        optimal: false,
        half_off: true
      },
      近卫: {
        supports: [
          {
            name: '赤冬',
            skill_level: 1,
            efficiency: 75,
            swap: true,
            swap_name: '艾丽妮',
            match: true
          },
          {
            name: '燧石',
            skill_level: 2,
            efficiency: 75,
            swap: true,
            swap_name: '艾丽妮',
            match: true
          },
          {
            name: '百炼嘉维尔',
            skill_level: 3,
            efficiency: 95,
            swap: false,
            swap_name: '',
            match: true
          }
        ],
        optimal: false,
        half_off: true
      },
      重装: {
        supports: [
          {
            name: '极光',
            skill_level: 1,
            efficiency: 75,
            swap: true,
            swap_name: '逻各斯',
            match: false
          },
          {
            name: '暴雨',
            skill_level: 2,
            efficiency: 75,
            swap: true,
            swap_name: '逻各斯',
            match: false
          },
          { name: '望', skill_level: 3, efficiency: 70, swap: false, swap_name: '', match: false }
        ],
        optimal: false,
        half_off: true
      },
      狙击: {
        supports: [
          {
            name: '假日威龙陈',
            skill_level: 1,
            efficiency: 95,
            swap: true,
            swap_name: '艾丽妮',
            match: true
          },
          {
            name: '埃拉托',
            skill_level: 2,
            efficiency: 75,
            swap: true,
            swap_name: '艾丽妮',
            match: true
          },
          { name: 'W', skill_level: 3, efficiency: 95, swap: false, swap_name: '', match: true }
        ],
        optimal: false,
        half_off: true
      },
      术师: {
        supports: [
          {
            name: '特米米',
            skill_level: 1,
            efficiency: 75,
            swap: true,
            swap_name: '逻各斯',
            match: true
          },
          {
            name: '薄绿',
            skill_level: 2,
            efficiency: 75,
            swap: true,
            swap_name: '逻各斯',
            match: true
          },
          { name: '死芒', skill_level: 3, efficiency: 95, swap: false, swap_name: '', match: true }
        ],
        optimal: false,
        half_off: true
      },
      医疗: {
        supports: [
          {
            name: '阿',
            skill_level: 1,
            efficiency: 60,
            swap: true,
            swap_name: '逻各斯',
            match: false
          },
          {
            name: '濯尘芙蓉',
            skill_level: 2,
            efficiency: 75,
            swap: true,
            swap_name: '逻各斯',
            match: false
          },
          { name: '望', skill_level: 3, efficiency: 70, swap: false, swap_name: '', match: false }
        ],
        optimal: false,
        half_off: true
      },
      辅助: {
        supports: [
          {
            name: '铃兰',
            skill_level: 1,
            efficiency: 60,
            swap: true,
            swap_name: '逻各斯',
            match: true
          },
          {
            name: '铃兰',
            skill_level: 2,
            efficiency: 60,
            swap: true,
            swap_name: '逻各斯',
            match: true
          },
          {
            name: '浊心斯卡蒂',
            skill_level: 3,
            efficiency: 95,
            swap: false,
            swap_name: '',
            match: true
          }
        ],
        optimal: false,
        half_off: true
      },
      特种: {
        supports: [
          {
            name: '罗宾',
            skill_level: 1,
            efficiency: 75,
            swap: true,
            swap_name: '逻各斯',
            match: false
          },
          {
            name: '缄默德克萨斯',
            skill_level: 2,
            efficiency: 80,
            swap: true,
            swap_name: '逻各斯',
            match: false
          },
          {
            name: '归溟幽灵鲨',
            skill_level: 3,
            efficiency: 95,
            swap: false,
            swap_name: '',
            match: false
          }
        ],
        optimal: false,
        half_off: true
      }
    },
    settings: {
      central_bonus: 5,
      mastery_swap_buffer: 10,
      mastery_swap_buffers: { no_central: 10, central: 10, central_unhalved_m2: 10 }
    },
    best_trainers: {
      先锋: {
        1: { name: '夜半', efficiency: 75, owned: false, unlocked: false },
        2: { name: '缄默德克萨斯', efficiency: 80, owned: false, unlocked: false },
        3: { name: '凛御银灰', efficiency: 80, owned: false, unlocked: false }
      },
      近卫: {
        1: { name: '赤冬', efficiency: 75, owned: false, unlocked: false },
        2: { name: '燧石', efficiency: 75, owned: false, unlocked: false },
        3: { name: '百炼嘉维尔', efficiency: 95, owned: false, unlocked: false }
      },
      重装: {
        1: { name: '极光', efficiency: 75, owned: false, unlocked: false },
        2: { name: '暴雨', efficiency: 75, owned: false, unlocked: false },
        3: { name: '望', efficiency: 70, owned: false, unlocked: false }
      },
      狙击: {
        1: { name: '假日威龙陈', efficiency: 95, owned: false, unlocked: false },
        2: { name: '埃拉托', efficiency: 75, owned: false, unlocked: false },
        3: { name: 'W', efficiency: 95, owned: false, unlocked: false }
      },
      术师: {
        1: { name: '特米米', efficiency: 75, owned: false, unlocked: false },
        2: { name: '薄绿', efficiency: 75, owned: false, unlocked: false },
        3: { name: '死芒', efficiency: 95, owned: false, unlocked: false }
      },
      医疗: {
        1: { name: '阿', efficiency: 60, owned: false, unlocked: false },
        2: { name: '濯尘芙蓉', efficiency: 75, owned: false, unlocked: false },
        3: { name: '望', efficiency: 70, owned: false, unlocked: false }
      },
      辅助: {
        1: { name: '铃兰', efficiency: 60, owned: false, unlocked: false },
        2: { name: '铃兰', efficiency: 60, owned: false, unlocked: false },
        3: { name: '浊心斯卡蒂', efficiency: 95, owned: false, unlocked: false }
      },
      特种: {
        1: { name: '罗宾', efficiency: 75, owned: false, unlocked: false },
        2: { name: '缄默德克萨斯', efficiency: 80, owned: false, unlocked: false },
        3: { name: '归溟幽灵鲨', efficiency: 95, owned: false, unlocked: false }
      }
    },
    defaults_error: null
  },
  workshop: {
    defaults: {
      fodder_operators: ['休谟斯', '蚀清'],
      t5_operators: ['年'],
      book_operators: ['司霆惊蛰']
    },
    recommendations: {
      fodder_operators: [
        { name: '九色鹿', materials: [], bonuses: {}, causality: true },
        { name: '蚀清', materials: ['异铁组'], bonuses: { 异铁组: 80 }, material_scope: 't4' },
        {
          name: '休谟斯',
          materials: ['聚酸酯组', '异铁组', '酮凝集组'],
          bonuses: { 聚酸酯组: 90, 异铁组: 90, 酮凝集组: 90 }
        },
        {
          name: '旅骨',
          materials: ['手性屈光体', '重相位对映体'],
          bonuses: { 手性屈光体: 90, 重相位对映体: 90 }
        },
        {
          name: '莱伊',
          materials: ['固源岩组', '异铁组', '酮凝集组'],
          bonuses: { 固源岩组: 80, 异铁组: 80, 酮凝集组: 80 }
        },
        { name: '号角', materials: ['炽合金块'], bonuses: { 炽合金块: 100 } }
      ],
      t5_operators: [
        {
          name: '年',
          materials: ['双极纳米片', '聚合剂', 'D32钢', '晶体电子单元', '烧结核凝晶'],
          bonuses: { 双极纳米片: 100, 聚合剂: 100, D32钢: 100, 晶体电子单元: 100, 烧结核凝晶: 100 }
        }
      ],
      book_operators: [
        {
          name: '司霆惊蛰',
          materials: ['技巧概要·卷1', '技巧概要·卷2', '技巧概要·卷3'],
          bonuses: { '技巧概要·卷3': 80 }
        },
        {
          name: '子月',
          materials: ['技巧概要·卷1', '技巧概要·卷2', '技巧概要·卷3'],
          bonuses: { '技巧概要·卷3': 80 }
        },
        {
          name: '弑君者',
          materials: ['技巧概要·卷1', '技巧概要·卷2', '技巧概要·卷3'],
          bonuses: { '技巧概要·卷3': 75 }
        }
      ]
    },
    owned_operators: [
      '能天使',
      '银灰',
      '艾雅法拉',
      '史尔特尔',
      '泥岩',
      '山',
      '棘刺',
      '澄闪',
      '伊内丝',
      '令',
      '琴柳',
      '夜莺',
      '逻各斯',
      '德克萨斯',
      '拉普兰德',
      '白面鸮',
      '赫默',
      '幽灵鲨',
      '崖心',
      '桃金娘',
      '古米',
      '讯使',
      '清道夫',
      '芬',
      '克洛丝',
      '米格鲁',
      '九色鹿',
      '蚀清',
      '休谟斯',
      '年',
      '司霆惊蛰',
      '菲亚梅塔',
      '推进之王'
    ],
    blocked_operators: [],
    nine_colored_deer: { name: '九色鹿', owned: true },
    min_bonus: 80
  },
  workshopReference: {
    recommendations: {
      fodder_operators: [
        { name: '九色鹿', materials: [], bonuses: {}, causality: true },
        { name: '蚀清', materials: ['异铁组'], bonuses: { 异铁组: 80 }, material_scope: 't4' },
        {
          name: '休谟斯',
          materials: ['聚酸酯组', '异铁组', '酮凝集组'],
          bonuses: { 聚酸酯组: 90, 异铁组: 90, 酮凝集组: 90 }
        },
        {
          name: '旅骨',
          materials: ['手性屈光体', '重相位对映体'],
          bonuses: { 手性屈光体: 90, 重相位对映体: 90 }
        },
        {
          name: '莱伊',
          materials: ['固源岩组', '异铁组', '酮凝集组'],
          bonuses: { 固源岩组: 80, 异铁组: 80, 酮凝集组: 80 }
        },
        { name: '号角', materials: ['炽合金块'], bonuses: { 炽合金块: 100 } }
      ],
      t5_operators: [
        {
          name: '年',
          materials: ['双极纳米片', '聚合剂', 'D32钢', '晶体电子单元', '烧结核凝晶'],
          bonuses: { 双极纳米片: 100, 聚合剂: 100, D32钢: 100, 晶体电子单元: 100, 烧结核凝晶: 100 }
        }
      ],
      book_operators: [
        {
          name: '司霆惊蛰',
          materials: ['技巧概要·卷1', '技巧概要·卷2', '技巧概要·卷3'],
          bonuses: { '技巧概要·卷3': 80 }
        },
        {
          name: '子月',
          materials: ['技巧概要·卷1', '技巧概要·卷2', '技巧概要·卷3'],
          bonuses: { '技巧概要·卷3': 80 }
        },
        {
          name: '弑君者',
          materials: ['技巧概要·卷1', '技巧概要·卷2', '技巧概要·卷3'],
          bonuses: { '技巧概要·卷3': 75 }
        }
      ]
    }
  },
  workshopStatus: {
    mode: 'automatic',
    execution: 'idle',
    project_key: null,
    project_name: null,
    recipe: null,
    generation: 4,
    pending_refresh: false,
    observed_at: '2026-10-26T13:00:42.846641',
    blockers: []
  },
  materialSummary: {
    material_summary: {
      materials: [
        { id: '3303', name: '技巧概要·卷3', required: 123, owned: 72, craftable: true },
        { id: '30044', name: '异铁块', required: 10, owned: 15, craftable: true },
        { id: '30024', name: '糖聚块', required: 7, owned: 12, craftable: true },
        { id: '30135', name: 'D32钢', required: 6, owned: 2, craftable: true },
        { id: '30054', name: '酮阵列', required: 5, owned: 5, craftable: true },
        { id: 'mod_unlock_token', name: '模组数据块', required: 8, owned: 20, craftable: true },
        { id: 'mod_update_token_1', name: '数据增补条', required: 60, owned: 80, craftable: true },
        { id: '30145', name: '晶体电子单元', required: 3, owned: 1, craftable: true },
        { id: '4001', name: '龙门币', required: 2091119, owned: 4800000, craftable: true },
        { id: 'mod_update_token_2', name: '数据增补仪', required: 20, owned: 20, craftable: true },
        { id: '30125', name: '双极纳米片', required: 4, owned: 0, craftable: true },
        { id: '31034', name: '晶体电路', required: 4, owned: 70, craftable: true },
        { id: '31013', name: '凝胶', required: 7, owned: 260, craftable: true },
        { id: '31014', name: '聚合凝胶', required: 8, owned: 70, craftable: true },
        { id: '30014', name: '提纯源岩', required: 20, owned: 9, craftable: true },
        { id: '30115', name: '聚合剂', required: 12, owned: 8, craftable: true },
        { id: '31024', name: '炽合金块', required: 6, owned: 70, craftable: true },
        { id: '30064', name: '改量装置', required: 3, owned: 8, craftable: true },
        { id: '30043', name: '异铁组', required: 8, owned: 260, craftable: true },
        { id: 'growth_exp', name: '作战记录经验', required: 1450038, owned: 0, craftable: false },
        { id: '30094', name: '五水研磨石', required: 4, owned: 10, craftable: true },
        { id: '30084', name: '三水锰矿', required: 8, owned: 12, craftable: true },
        { id: '31064', name: '转质盐聚块', required: 6, owned: 70, craftable: true },
        { id: '3213', name: '先锋双芯片', required: 3, owned: 9, craftable: true },
        { id: '30034', name: '聚酸酯块', required: 8, owned: 70, craftable: true },
        { id: '30013', name: '固源岩组', required: 16, owned: 260, craftable: true },
        { id: '3302', name: '技巧概要·卷2', required: 6, owned: 230, craftable: true },
        { id: '30093', name: '研磨石', required: 15, owned: 260, craftable: true },
        { id: '30103', name: 'RMA70-12', required: 2, owned: 260, craftable: true },
        { id: '30033', name: '聚酸酯组', required: 3, owned: 260, craftable: true },
        { id: '3223', name: '近卫双芯片', required: 3, owned: 9, craftable: true },
        { id: '30074', name: '白马醇', required: 8, owned: 9, craftable: true },
        { id: '30053', name: '酮凝集组', required: 15, owned: 260, craftable: true },
        { id: '3283', name: '特种双芯片', required: 3, owned: 9, craftable: true },
        { id: '30083', name: '轻锰矿', required: 13, owned: 260, craftable: true },
        { id: '3212', name: '先锋芯片组', required: 5, owned: 55, craftable: true },
        { id: '30063', name: '全新装置', required: 8, owned: 260, craftable: true }
      ],
      crafting: [
        {
          id: '31024',
          name: '炽合金块',
          rarity: 4,
          required: 8,
          owned: 70,
          used: 8,
          direct: 6,
          to_craft: 0,
          craftable: true
        },
        {
          id: '31014',
          name: '聚合凝胶',
          rarity: 4,
          required: 12,
          owned: 70,
          used: 12,
          direct: 8,
          to_craft: 0,
          craftable: true
        },
        {
          id: '30104',
          name: 'RMA70-24',
          rarity: 4,
          required: 4,
          owned: 7,
          used: 4,
          direct: 0,
          to_craft: 0,
          craftable: true
        },
        {
          id: '30094',
          name: '五水研磨石',
          rarity: 4,
          required: 8,
          owned: 10,
          used: 8,
          direct: 4,
          to_craft: 0,
          craftable: true
        },
        {
          id: '30084',
          name: '三水锰矿',
          rarity: 4,
          required: 12,
          owned: 12,
          used: 12,
          direct: 8,
          to_craft: 0,
          craftable: true
        },
        {
          id: '30074',
          name: '白马醇',
          rarity: 4,
          required: 16,
          owned: 9,
          used: 9,
          direct: 8,
          to_craft: 7,
          craftable: true
        },
        {
          id: '30064',
          name: '改量装置',
          rarity: 4,
          required: 7,
          owned: 8,
          used: 7,
          direct: 3,
          to_craft: 0,
          craftable: true
        },
        {
          id: '30054',
          name: '酮阵列',
          rarity: 4,
          required: 9,
          owned: 5,
          used: 5,
          direct: 5,
          to_craft: 4,
          craftable: true
        },
        {
          id: '30044',
          name: '异铁块',
          rarity: 4,
          required: 14,
          owned: 15,
          used: 14,
          direct: 10,
          to_craft: 0,
          craftable: true
        },
        {
          id: '30014',
          name: '提纯源岩',
          rarity: 4,
          required: 24,
          owned: 9,
          used: 9,
          direct: 20,
          to_craft: 15,
          craftable: true
        },
        {
          id: '30053',
          name: '酮凝集组',
          rarity: 3,
          required: 23,
          owned: 260,
          used: 23,
          direct: 15,
          to_craft: 0,
          craftable: true
        },
        {
          id: '30023',
          name: '糖组',
          rarity: 3,
          required: 11,
          owned: 260,
          used: 11,
          direct: 0,
          to_craft: 0,
          craftable: true
        },
        {
          id: '30013',
          name: '固源岩组',
          rarity: 3,
          required: 76,
          owned: 260,
          used: 76,
          direct: 16,
          to_craft: 0,
          craftable: true
        },
        {
          id: '3302',
          name: '技巧概要·卷2',
          rarity: 3,
          required: 159,
          owned: 230,
          used: 6,
          direct: 6,
          to_craft: 0,
          craftable: true
        },
        {
          id: '31034',
          name: '晶体电路',
          rarity: 4,
          required: 6,
          owned: 70,
          used: 6,
          direct: 4,
          to_craft: 0,
          craftable: true
        },
        {
          id: '30103',
          name: 'RMA70-12',
          rarity: 3,
          required: 9,
          owned: 260,
          used: 9,
          direct: 2,
          to_craft: 0,
          craftable: true
        },
        {
          id: '30083',
          name: '轻锰矿',
          rarity: 3,
          required: 17,
          owned: 260,
          used: 17,
          direct: 13,
          to_craft: 0,
          craftable: true
        },
        {
          id: '30073',
          name: '扭转醇',
          rarity: 3,
          required: 7,
          owned: 260,
          used: 7,
          direct: 0,
          to_craft: 0,
          craftable: true
        }
      ],
      missing: [
        {
          id: 'growth_exp',
          name: '作战记录经验',
          rarity: 1,
          required: 1450038,
          owned: 0,
          used: 0,
          direct: 1450038,
          to_craft: 1450038,
          craftable_count: 0,
          count: 1450038,
          blue: false
        }
      ],
      available: false,
      craftable: false,
      crafting_gold: 13400,
      manual_chips: true,
      missing_skills: ['char_377_gdglow_0'],
      missing_operators: [
        'char_264_f12yin',
        'char_143_ghost',
        'char_102_texas',
        'char_151_myrtle',
        'char_173_slchan',
        'char_377_gdglow'
      ]
    },
    t3_summary: [
      {
        id: 'growth_exp',
        name: '作战记录经验',
        rarity: 1,
        required: 1450038,
        owned: 0,
        used: 0,
        direct: 1450038,
        to_craft: 1450038,
        craftable_count: 0,
        count: 1450038,
        blue: false
      }
    ]
  },
  operatorNames: [
    '令',
    '伊内丝',
    '史尔特尔',
    '夜莺',
    '山',
    '棘刺',
    '泥岩',
    '澄闪',
    '琴柳',
    '能天使',
    '艾雅法拉',
    '逻各斯',
    '银灰',
    '崖心',
    '幽灵鲨',
    '德克萨斯',
    '拉普兰德',
    '白面鸮',
    '赫默',
    '古米',
    '桃金娘',
    '清道夫',
    '讯使',
    '克洛丝',
    '米格鲁',
    '芬',
    '九色鹿',
    '蚀清',
    '休谟斯',
    '年',
    '司霆惊蛰',
    '菲亚梅塔',
    '推进之王'
  ]
}

const clone = (value) => JSON.parse(JSON.stringify(value))

function namedCosts(costs) {
  return Object.entries(costs).map(([id, count]) => ({ id, count, name: MATERIALS[id].name }))
}

// 每次汇总独立消耗示例库存，避免切换目标或创建另一预览会话时互相影响。
function materialSummary(costs) {
  const stock = Object.fromEntries(Object.entries(MATERIALS).map(([id, item]) => [id, item.owned]))
  const rows = new Map()
  const crafting = []
  const missing = []
  function consume(id, count) {
    const definition = MATERIALS[id]
    const row = rows.get(id) || {
      id,
      name: definition.name,
      required: 0,
      owned: definition.owned,
      craftable: true
    }
    row.required += count
    rows.set(id, row)
    const used = Math.min(stock[id], count)
    stock[id] -= used
    const shortage = count - used
    if (!shortage) return true
    const recipe = RECIPES[id]
    if (!recipe) {
      row.craftable = false
      missing.push({ id, name: definition.name, count: shortage, blue: definition.rarity === 3 })
      return false
    }
    let craftable = true
    for (const [ingredient, amount] of recipe) {
      if (!consume(ingredient, amount * shortage)) craftable = false
    }
    row.craftable &&= craftable
    crafting.push({ ...row, rarity: definition.rarity, used, direct: count, to_craft: shortage })
    return craftable
  }
  for (const [id, count] of costs) consume(id, count)
  const materials = [...rows.values()]
  return {
    materials,
    crafting,
    missing,
    available: materials.every((item) => item.owned >= item.required),
    craftable: missing.length === 0,
    crafting_gold: 0,
    manual_chips: costs.some(([id]) => /^32[1-8]3$/.test(id))
  }
}

function createSkill(seed, prerequisiteCosts) {
  const { costs, ...skill } = seed
  const stages = costs.map((materials, index) => ({
    from_level: 7 + skill.current_level + index,
    to_level: 8 + skill.current_level + index,
    lvl_up_time: [28800, 57600, 86400][skill.current_level + index],
    needed_materials: namedCosts(materials)
  }))
  const targets = {}
  for (let target = skill.current_level + 1; target <= 3; target += 1) {
    const selected = stages.slice(0, target - skill.current_level)
    const skillCosts = costs.slice(0, target - skill.current_level).flatMap(Object.entries)
    const combined = materialSummary([...prerequisiteCosts, ...skillCosts])
    targets[target] = {
      target_level: target,
      remaining_levels: target - skill.current_level,
      total_time: selected.reduce((sum, stage) => sum + stage.lvl_up_time, 0),
      chain_needed_materials: selected.flatMap((stage) => stage.needed_materials),
      material_summary: combined,
      skill_material_summary: materialSummary(skillCosts),
      full_chain_achievable: combined.craftable
    }
  }
  return { ...skill, stages, targets, ...targets[3] }
}

function createModule(seed, prerequisiteCosts) {
  const { costs, ...module } = seed
  const targets = {}
  for (let target = module.current_level + 1; target <= module.max_level; target += 1) {
    const selected = costs.slice(module.current_level, target).flatMap(Object.entries)
    targets[target] = {
      opening_summary: materialSummary(selected),
      material_summary: materialSummary([...prerequisiteCosts, ...selected])
    }
  }
  return {
    ...module,
    levels: costs.map((items, index) => ({ level: index + 1, materials: namedCosts(items) })),
    targets,
    ...targets[module.max_level]
  }
}

function createOperator(seed) {
  const { skills, modules, level_goals, basic_costs, ...identity } = seed
  const goals = level_goals.map(({ costs, ...goal }) => ({
    ...goal,
    summary: costs === null ? null : materialSummary(Object.entries(costs))
  }))
  const goalCosts = (key) =>
    Object.entries(level_goals.find((goal) => goal.id === key)?.costs || {})
  const promotionCosts = seed.elite < 2 ? goalCosts('elite2') : []
  const basicCosts = seed.main_skill_level < 7 ? Object.entries(basic_costs || {}) : []
  const moduleCosts = goalCosts('elite2_module')
  return {
    ...identity,
    recommendations: skills.map((skill) => createSkill(skill, [...promotionCosts, ...basicCosts])),
    modules: modules.map((module) => createModule(module, moduleCosts)),
    level_goals: goals,
    promotion_summary: promotionCosts.length ? materialSummary(promotionCosts) : null,
    max_level_summary:
      goals.find((goal) => goal.id === 'elite2_max' || goal.id === 'level_max')?.summary || null,
    module_level_summary: moduleCosts.length ? materialSummary(moduleCosts) : null,
    basic_skill_summary: basic_costs === null ? null : materialSummary(Object.entries(basic_costs))
  }
}

function historyStatistics(statistics, factor) {
  return Object.fromEntries(
    Object.entries(statistics).map(([rarity, values]) => [
      rarity,
      Object.fromEntries(
        Object.entries(values).map(([key, value]) => [
          key,
          typeof value === 'number'
            ? ['sanity_value', 'skill_book_equivalent'].includes(key)
              ? Math.round(value * factor * 100) / 100
              : Math.round(value * factor)
            : clone(value)
        ])
      )
    ])
  )
}

function createSupportPlan(current, target, charName) {
  const stages = []
  for (let level = current + 1; level <= target; level += 1) {
    const operator = level === 3 ? '逻各斯' : '艾丽妮'
    const efficiency = level === 3 ? 60 : 75
    const swapTarget = level < target ? '逻各斯' : null
    stages.push({
      operator,
      efficiency,
      level,
      swap_target: swapTarget,
      swap_efficiency: swapTarget ? 60 : 0,
      central_bonus: 5,
      mastery_swap_buffer: 10,
      configured_swap_buffer: 10,
      half_inherited: false,
      hours: Math.round(([8, 16, 24][level - 1] / (1 + efficiency / 100)) * 100) / 100,
      switch_after: null,
      activate_with: null,
      next_carry: null,
      manual: false
    })
  }
  return {
    version: 1,
    stages,
    hours: Math.round(stages.reduce((sum, stage) => sum + stage.hours, 0) * 100) / 100,
    switches: 0,
    central_bonus: 5,
    current,
    target,
    char_name: charName
  }
}

export function createGrowthPreview() {
  const mastery = clone(MASTERY)
  return {
    ...clone(SCENARIOS),
    plans: SCENARIOS.plans.map((seed) => {
      const { support_current, ...plan } = clone(seed)
      return {
        ...plan,
        support_plan: createSupportPlan(support_current, plan.target_level, plan.name)
      }
    }),
    mastery: {
      ...mastery,
      operators: OPERATORS.map((seed) => createOperator(clone(seed))),
      history: HISTORY.map(([time, factor]) => ({
        time,
        rarities: historyStatistics(mastery.statistics, factor)
      }))
    }
  }
}
