export const baseSkillMessages = {
  'zh-CN': {
    snapshotLoaded: '已读取 {count} 名干员的森空岛练度。',
    title: '基建技能',
    groups: '基建组合',
    sync: '同步森空岛练度',
    filters: '技能筛选',
    operator: '干员',
    skill: '技能',
    operatorSearch: '干员名称 / 拼音',
    operatorSearchLabel: '搜索干员',
    skillSearch: '技能名称或描述 / 拼音',
    skillSearchLabel: '搜索技能',
    collapseFilters: '收起设施与状态筛选',
    expandFilters: '展开设施与状态筛选',
    filtered: ' · 已筛选',
    allFacilities: '全部设施',
    facilityFilter: '设施筛选',
    allOwnership: '全部持有状态',
    ownershipFilter: '持有状态筛选',
    allUnlock: '全部解锁状态',
    unlockFilter: '技能解锁筛选',
    resetFilters: '重置筛选',
    clearFilters: '清除筛选',
    counts: '{operators} 名干员 / {skills} 个技能版本',
    replacedHelp: '“已替换”表示该技能的升级版本已解锁',
    empty: '没有符合筛选条件的基建技能',
    skillNumber: '技能序号',
    unlockCondition: '解锁条件',
    status: '当前状态',
    skillName: '技能名称',
    facility: '进驻场所',
    description: '描述',
    loading: '正在读取本地森空岛练度…',
    syncHelp: '同步森空岛练度后可显示持有和技能解锁状态。',
    loadFailed: '读取森空岛练度失败：{message}',
    syncFailed: '同步森空岛练度失败',
    syncError: '同步森空岛练度失败：{message}',
    operatorSkills: '{operator}的基建技能',
    numberedSkill: '技能 {number}',
    active: '已解锁',
    locked: '未解锁',
    replaced: '已替换',
    owned: '已拥有',
    unowned: '未拥有',
    progression: '精{phase} {level}级',
    specialEffects: '特殊效果',
    maxLevel: '按满练度计算',
    searchGroups: '搜索组合 / 干员 / 拼音',
    searchGroupsLabel: '搜索组合',
    allCategories: '全部分类',
    groupCategory: '组合分类',
    groupOwnership: '组合持有状态',
    groupList: '基建组合列表',
    noGroups: '没有符合条件的组合，请调整筛选条件',
    core: '核心干员',
    support: '备选干员',
    accessory: '挂件',
    coreOwned: '核心均已拥有',
    missing: '含未拥有成员',
    unknown: '持有状态未知',
    ownershipSummary: '已拥有 {owned} / {total}',
    unknownCount: ' · {count} 人未知',
    selected: '已选中',
    unselected: '未选中',
    estimate: '效率估算',
    emptySelection: '勾选核心或备选干员计算',
    noDirectBonus: '该选择无直接效率加成，详见明细',
    estimateDetails: '计算条件与明细',
    estimateHelp: '仅计所选干员技能，不含设施基础效率；不同设施分别显示，中枢同类加成取最高',
    dormCount: '宿舍人数',
    recruits: '额外招募位',
    tradeCount: '贸易站数',
    powerCount: '发电站数',
    suiCount: '工作设施内岁人数',
    factoryCount: '制造站数',
    dormLevel: '爱丽丝/车尔尼宿舍等级',
    roomResidents: '塑心所在宿舍人数',
    catRoom: '调查团进驻',
    droneCap: '无人机上限',
    eunectesRoom: '森蚺进驻',
    platforms: '其他发电站有作业平台',
    hunters: '每个制造站猎人数',
    average: '按照平均效率计算',
    goldLines: '实际赤金生产线',
    receptionLevel: '会客室等级',
    jayeStage: '孑的精英阶段',
    orderCap: '设施基础订单上限',
    followSkland: '跟随森空岛',
    unpromoted: '未精英化',
    eliteOne: '精一及以上',
    none: '无',
    yes: '有',
    general: '通用',
    experience: '经验',
    originium: '源石',
    tradeMetric: '贸易订单效率',
    factoryMetric: '{product}制造生产力',
    capacityError: '{room}已选{count}人，最多{limit}人，请取消部分干员',
    unownedError: '{name}未拥有，无法按实际练度计算',
    missingJaye: '孑缺少森空岛练度，请同步或手选精英阶段',
    missingGrowth: '{name}缺少森空岛练度，请同步后计算',
    groupsById: {
      'builtin-run-order': {
        title: '跑单干员',
        note: ''
      },
      'builtin-smoke': {
        title: '人间烟火',
        note: '同时有5名岁干员在工作设施，如在意公招效率，不推荐使用'
      },
      'builtin-perception': {
        title: '感知信息',
        note: '如在意公招效率，不推荐使用'
      },
      'builtin-lgd': {
        title: '龙门近卫局',
        note: ''
      },
      'builtin-monster-hunter': {
        title: '怪物猎人小队',
        note: ''
      },
      'builtin-automation': {
        title: '自动化',
        note: ''
      },
      'builtin-abyss': {
        title: '深海猎人',
        note: ''
      },
      'builtin-redpine': {
        title: '红松林',
        note: ''
      },
      'builtin-tianmao': {
        title: '精英干员',
        note: '至少5名精英干员位于不同设施'
      },
      'builtin-nasti': {
        title: '莱茵科技',
        note: '需要5名莱茵生命干员（不含缪尔赛思）'
      },
      'builtin-makoto': {
        title: '结城理·S.E.E.S.',
        note: ''
      },
      'builtin-pozy': {
        title: '鸿雪杜林组',
        note: ''
      },
      'builtin-siracusa': {
        title: '叙拉古',
        note: ''
      },
      'builtin-exusiai': {
        title: '能天使',
        note: ''
      },
      'builtin-glasgow': {
        title: '格拉斯哥帮',
        note: ''
      },
      'builtin-karlan': {
        title: '喀兰贸易',
        note: ''
      },
      'builtin-gold': {
        title: '金属工艺',
        note: ''
      },
      'builtin-bubble': {
        title: '泡泡仓库',
        note: ''
      },
      'builtin-cloud': {
        title: '红云经验',
        note: ''
      },
      'builtin-standardization': {
        title: '黑钢标准化',
        note: ''
      }
    },
    tradeCategory: '贸易',
    metalCategory: '金属',
    sameFactory: '同一制造站',
    sameTrading: '同一贸易站',
    non153: '非153',
    threePower: '3电',
    zeroMorale: '0心情',
    positiveMorale: '不可0心情',
    fourGold: '4赤使用',
    fiveEliteTrade: '目前5精干35%贸易',
    points: '点',
    rooms: '间',
    people: '人',
    lines: '条',
    orders: '笔',
    slots: '格',
    perHour: '/小时'
  },
  'en-US': {
    snapshotLoaded: 'Loaded SKLand progression for {count} operators.',
    title: 'Base Skills',
    groups: 'Base combinations',
    sync: 'Sync SKLand progression',
    filters: 'Skill filters',
    operator: 'Operator',
    skill: 'Skill',
    operatorSearch: 'Operator name / Pinyin',
    operatorSearchLabel: 'Search operators',
    skillSearch: 'Skill name or description / Pinyin',
    skillSearchLabel: 'Search skills',
    collapseFilters: 'Hide facility and status filters',
    expandFilters: 'Show facility and status filters',
    filtered: ' · Filtered',
    allFacilities: 'All facilities',
    facilityFilter: 'Filter by facility',
    allOwnership: 'All ownership states',
    ownershipFilter: 'Filter by ownership',
    allUnlock: 'All unlock states',
    unlockFilter: 'Filter by skill unlock state',
    resetFilters: 'Reset filters',
    clearFilters: 'Clear filters',
    counts: '{operators} operators / {skills} skill versions',
    replacedHelp: '“Replaced” means an upgraded version of this skill has been unlocked.',
    empty: 'No Base Skills match these filters',
    skillNumber: 'Skill number',
    unlockCondition: 'Unlock condition',
    status: 'Current status',
    skillName: 'Skill name',
    facility: 'Facility',
    description: 'Description',
    loading: 'Reading local SKLand progression…',
    syncHelp: 'Sync SKLand progression to show ownership and skill unlock status.',
    loadFailed: 'Could not read SKLand progression: {message}',
    syncFailed: 'Could not sync SKLand progression',
    syncError: 'Could not sync SKLand progression: {message}',
    operatorSkills: 'Base Skills for {operator}',
    numberedSkill: 'Skill {number}',
    active: 'Unlocked',
    locked: 'Locked',
    replaced: 'Replaced',
    owned: 'Owned',
    unowned: 'Not owned',
    progression: 'Elite {phase} Lv. {level}',
    specialEffects: 'Special effects',
    maxLevel: 'Calculate at maximum progression',
    searchGroups: 'Search combinations / operators / Pinyin',
    searchGroupsLabel: 'Search combinations',
    allCategories: 'All categories',
    groupCategory: 'Combination category',
    groupOwnership: 'Combination ownership',
    groupList: 'Base combinations',
    noGroups: 'No combinations match. Adjust the filters.',
    core: 'Core operators',
    support: 'Alternatives',
    accessory: 'Supporting operators',
    coreOwned: 'All core operators owned',
    missing: 'Includes unowned members',
    unknown: 'Ownership unknown',
    ownershipSummary: 'Owned {owned} / {total}',
    unknownCount: ' · {count} unknown',
    selected: 'Selected',
    unselected: 'Not selected',
    estimate: 'Efficiency estimate',
    emptySelection: 'Select core or alternative operators to calculate',
    noDirectBonus: 'This selection has no direct efficiency bonus. See details.',
    estimateDetails: 'Conditions and calculation details',
    estimateHelp:
      'Only selected operators’ skills are counted, excluding base facility efficiency. Facilities are shown separately; only the highest Control Center bonus of each type applies.',
    dormCount: 'Operators in Dormitories',
    recruits: 'Extra recruitment slots',
    tradeCount: 'Trading Posts',
    powerCount: 'Power Plants',
    suiCount: 'Sui operators in work facilities',
    factoryCount: 'Factories',
    dormLevel: 'Iris / Czerny Dormitory level',
    roomResidents: 'Operators in Virtuosa’s Dormitory',
    catRoom: 'Terra Research Commission facility',
    droneCap: 'Drone capacity',
    eunectesRoom: 'Eunectes facility',
    platforms: 'Other Power Plants have Work Platforms',
    hunters: 'Hunters per Factory',
    average: 'Use average efficiency',
    goldLines: 'Actual Pure Gold production lines',
    receptionLevel: 'Reception Room level',
    jayeStage: 'Jaye’s Elite stage',
    orderCap: 'Base facility order limit',
    followSkland: 'Use SKLand progression',
    unpromoted: 'Not promoted',
    eliteOne: 'Elite 1 or higher',
    none: 'No',
    yes: 'Yes',
    general: 'General',
    experience: 'EXP',
    originium: 'Originium',
    tradeMetric: 'Trading Post order efficiency',
    factoryMetric: '{product} Factory productivity',
    capacityError: '{room}: {count} selected, maximum {limit}. Deselect some operators.',
    unownedError: '{name} is not owned; actual progression cannot be used.',
    missingJaye:
      'Jaye’s SKLand progression is missing. Sync it or choose his Elite stage manually.',
    missingGrowth: '{name} has no SKLand progression. Sync before calculating.',
    groupsById: {
      'builtin-run-order': {
        title: 'Run-order operators',
        note: ''
      },
      'builtin-smoke': {
        title: 'Worldly Plight',
        note: 'Requires five Sui operators in work facilities at once. Not recommended if recruitment efficiency is a priority.'
      },
      'builtin-perception': {
        title: 'Perception Information',
        note: 'Not recommended if recruitment efficiency is a priority.'
      },
      'builtin-lgd': {
        title: 'Lungmen Guard Department',
        note: ''
      },
      'builtin-monster-hunter': {
        title: 'Monster Hunter squad',
        note: ''
      },
      'builtin-automation': {
        title: 'Automation',
        note: ''
      },
      'builtin-abyss': {
        title: 'Abyssal Hunters',
        note: ''
      },
      'builtin-redpine': {
        title: 'Pinus Sylvestris',
        note: ''
      },
      'builtin-tianmao': {
        title: 'Elite operators',
        note: 'At least five Elite operators in separate facilities.'
      },
      'builtin-nasti': {
        title: 'Rhine Technology',
        note: 'Requires five Rhine Lab operators, excluding Muelsyse.'
      },
      'builtin-makoto': {
        title: 'Makoto Yuki · S.E.E.S.',
        note: ''
      },
      'builtin-pozy': {
        title: 'Pozëmka and Durins',
        note: ''
      },
      'builtin-siracusa': {
        title: 'Siracusa',
        note: ''
      },
      'builtin-exusiai': {
        title: 'Exusiai',
        note: ''
      },
      'builtin-glasgow': {
        title: 'Glasgow Gang',
        note: ''
      },
      'builtin-karlan': {
        title: 'Karlan Trade',
        note: ''
      },
      'builtin-gold': {
        title: 'Metalwork',
        note: ''
      },
      'builtin-bubble': {
        title: 'Bubble storage',
        note: ''
      },
      'builtin-cloud': {
        title: 'Vermeil EXP',
        note: ''
      },
      'builtin-standardization': {
        title: 'Blacksteel standardization',
        note: ''
      }
    },
    tradeCategory: 'Trade',
    metalCategory: 'Metal',
    sameFactory: 'Same Factory',
    sameTrading: 'Same Trading Post',
    non153: 'Not a 1/5/3 layout',
    threePower: '3 Power Plants',
    zeroMorale: '0 Morale',
    positiveMorale: 'Requires positive Morale',
    fourGold: 'Use with 4 Pure Gold lines',
    fiveEliteTrade: 'Currently +35% trading with 5 Elite operators',
    points: ' points',
    rooms: ' rooms',
    people: ' operators',
    lines: ' lines',
    orders: ' orders',
    slots: ' slots',
    perHour: '/h'
  },
  'ja-JP': {
    snapshotLoaded: '{count} 名の SKLand 育成状況を読み込みました。',
    title: '基地スキル',
    groups: '基地の組み合わせ',
    sync: 'SKLand の育成状況を同期',
    filters: 'スキル絞り込み',
    operator: 'オペレーター',
    skill: 'スキル',
    operatorSearch: 'オペレーター名 / ピンイン',
    operatorSearchLabel: 'オペレーターを検索',
    skillSearch: 'スキル名・説明 / ピンイン',
    skillSearchLabel: 'スキルを検索',
    collapseFilters: '施設・状態の絞り込みを折りたたむ',
    expandFilters: '施設・状態の絞り込みを開く',
    filtered: ' · 絞り込み中',
    allFacilities: 'すべての施設',
    facilityFilter: '施設で絞り込み',
    allOwnership: 'すべての所持状態',
    ownershipFilter: '所持状態で絞り込み',
    allUnlock: 'すべての解放状態',
    unlockFilter: 'スキルの解放状態で絞り込み',
    resetFilters: '絞り込みをリセット',
    clearFilters: '絞り込みを解除',
    counts: 'オペレーター {operators} 名 / スキル {skills} 種',
    replacedHelp: '「置き換え済み」は、上位のスキルが解放されていることを表します。',
    empty: '条件に一致する基地スキルがありません',
    skillNumber: 'スキル番号',
    unlockCondition: '解放条件',
    status: '現在の状態',
    skillName: 'スキル名',
    facility: '配属施設',
    description: '説明',
    loading: 'ローカルの SKLand 育成状況を読み込み中…',
    syncHelp: 'SKLand の育成状況を同期すると、所持・スキル解放状態が表示されます。',
    loadFailed: 'SKLand の育成状況を読み込めませんでした：{message}',
    syncFailed: 'SKLand の育成状況を同期できませんでした',
    syncError: 'SKLand の育成状況を同期できませんでした：{message}',
    operatorSkills: '{operator} の基地スキル',
    numberedSkill: 'スキル {number}',
    active: '解放済み',
    locked: '未解放',
    replaced: '置き換え済み',
    owned: '所持',
    unowned: '未所持',
    progression: '昇進{phase} Lv.{level}',
    specialEffects: '特殊効果',
    maxLevel: '最大育成時として計算',
    searchGroups: '組み合わせ・オペレーター / ピンインで検索',
    searchGroupsLabel: '組み合わせを検索',
    allCategories: 'すべての分類',
    groupCategory: '組み合わせの分類',
    groupOwnership: '組み合わせの所持状態',
    groupList: '基地の組み合わせ一覧',
    noGroups: '一致する組み合わせがありません。絞り込み条件を変更してください。',
    core: '主力オペレーター',
    support: '代替オペレーター',
    accessory: '補助オペレーター',
    coreOwned: '主力を全員所持',
    missing: '未所持メンバーを含む',
    unknown: '所持状態不明',
    ownershipSummary: '所持 {owned} / {total}',
    unknownCount: ' · 不明 {count} 名',
    selected: '選択済み',
    unselected: '未選択',
    estimate: '効率の試算',
    emptySelection: '主力・代替オペレーターを選択すると計算します',
    noDirectBonus: '選択した構成に直接的な効率加算はありません。明細をご確認ください。',
    estimateDetails: '計算条件と明細',
    estimateHelp:
      '選択したオペレーターのスキルのみを計算し、施設の基本効率は含みません。施設ごとに表示し、制御中枢の同種の効果は最大値のみ適用します。',
    dormCount: '宿舎の人数',
    recruits: '追加の求人枠',
    tradeCount: '貿易所の数',
    powerCount: '発電所の数',
    suiCount: '作業施設内の「歳」人数',
    factoryCount: '製造所の数',
    dormLevel: 'アイリス／ツェルニーの宿舎レベル',
    roomResidents: 'ヴィルトゥオーサがいる宿舎の人数',
    catRoom: 'テラ大陸調査団の配属先',
    droneCap: 'ドローンの上限',
    eunectesRoom: 'ユーネクテスの配属先',
    platforms: '他の発電所に作業用プラットフォームがある',
    hunters: '製造所ごとのアビサルハンター人数',
    average: '平均効率で計算',
    goldLines: '実際の純金の生産ライン数',
    receptionLevel: '応接室レベル',
    jayeStage: 'ジェイの昇進段階',
    orderCap: '施設の基本注文上限',
    followSkland: 'SKLand の育成状況に従う',
    unpromoted: '未昇進',
    eliteOne: '昇進1以上',
    none: 'なし',
    yes: 'あり',
    general: '汎用',
    experience: '作戦記録',
    originium: '源石',
    tradeMetric: '貿易所の受注効率',
    factoryMetric: '{product}の製造効率',
    capacityError:
      '{room}に{count}名を選択しています（上限{limit}名）。一部の選択を解除してください。',
    unownedError: '{name}を所持していないため、実際の育成状況では計算できません。',
    missingJaye:
      'ジェイの SKLand 育成状況がありません。同期するか昇進段階を手動で選択してください。',
    missingGrowth: '{name}の SKLand 育成状況がありません。同期してから計算してください。',
    groupsById: {
      'builtin-run-order': {
        title: '受注調整オペレーター',
        note: ''
      },
      'builtin-smoke': {
        title: '俗世の憂',
        note: '同時に5名の「歳」を作業施設に配属します。公開求人の効率を重視する場合は推奨しません。'
      },
      'builtin-perception': {
        title: '知覚情報',
        note: '公開求人の効率を重視する場合は推奨しません。'
      },
      'builtin-lgd': {
        title: '龍門近衛局',
        note: ''
      },
      'builtin-monster-hunter': {
        title: 'モンスターハンター隊',
        note: ''
      },
      'builtin-automation': {
        title: '自動化',
        note: ''
      },
      'builtin-abyss': {
        title: 'アビサル',
        note: ''
      },
      'builtin-redpine': {
        title: 'レッドパイン',
        note: ''
      },
      'builtin-tianmao': {
        title: 'エリートオペレーター',
        note: '5名以上のエリートオペレーターをそれぞれ別の施設に配属します。'
      },
      'builtin-nasti': {
        title: 'ラインテク',
        note: 'ミュルジス以外のライン生命オペレーター5名が必要です。'
      },
      'builtin-makoto': {
        title: '結城理 · S.E.E.S.',
        note: ''
      },
      'builtin-pozy': {
        title: 'パゼオンカ・ドゥリン組',
        note: ''
      },
      'builtin-siracusa': {
        title: 'シラクーザ',
        note: ''
      },
      'builtin-exusiai': {
        title: 'エクシア',
        note: ''
      },
      'builtin-glasgow': {
        title: 'グラスゴー',
        note: ''
      },
      'builtin-karlan': {
        title: 'カランド貿易',
        note: ''
      },
      'builtin-gold': {
        title: '金属工芸',
        note: ''
      },
      'builtin-bubble': {
        title: 'バブルの保管庫',
        note: ''
      },
      'builtin-cloud': {
        title: 'ヴァーミルの作戦記録',
        note: ''
      },
      'builtin-standardization': {
        title: 'BSW の標準化',
        note: ''
      }
    },
    tradeCategory: '貿易',
    metalCategory: '金属',
    sameFactory: '同じ製造所',
    sameTrading: '同じ貿易所',
    non153: '1/5/3 構成以外',
    threePower: '発電所3か所',
    zeroMorale: '体力0',
    positiveMorale: '体力が必要',
    fourGold: '純金4ラインで使用',
    fiveEliteTrade: '現在はエリート5名で受注効率+35%',
    points: '点',
    rooms: 'か所',
    people: '名',
    lines: 'ライン',
    orders: '件',
    slots: '枠',
    perHour: '/時'
  },
  'zh-TW': {
    snapshotLoaded: '已讀取 {count} 名幹員的森空島練度。',
    title: '基建技能',
    groups: '基建組合',
    sync: '同步森空島練度',
    filters: '技能篩選',
    operator: '幹員',
    skill: '技能',
    operatorSearch: '幹員名稱 / 拼音',
    operatorSearchLabel: '搜尋幹員',
    skillSearch: '技能名稱或描述 / 拼音',
    skillSearchLabel: '搜尋技能',
    collapseFilters: '收起設施與狀態篩選',
    expandFilters: '展開設施與狀態篩選',
    filtered: ' · 已篩選',
    allFacilities: '全部設施',
    facilityFilter: '設施篩選',
    allOwnership: '全部持有狀態',
    ownershipFilter: '持有狀態篩選',
    allUnlock: '全部解鎖狀態',
    unlockFilter: '技能解鎖篩選',
    resetFilters: '重置篩選',
    clearFilters: '清除篩選',
    counts: '{operators} 名幹員 / {skills} 個技能版本',
    replacedHelp: '“已替換”表示該技能的升級版本已解鎖',
    empty: '沒有符合篩選條件的基建技能',
    skillNumber: '技能序號',
    unlockCondition: '解鎖條件',
    status: '當前狀態',
    skillName: '技能名稱',
    facility: '進駐場所',
    description: '描述',
    loading: '正在讀取本地森空島練度…',
    syncHelp: '同步森空島練度後可顯示持有和技能解鎖狀態。',
    loadFailed: '讀取森空島練度失敗：{message}',
    syncFailed: '同步森空島練度失敗',
    syncError: '同步森空島練度失敗：{message}',
    operatorSkills: '{operator}的基建技能',
    numberedSkill: '技能 {number}',
    active: '已解鎖',
    locked: '未解鎖',
    replaced: '已替換',
    owned: '已擁有',
    unowned: '未擁有',
    progression: '精{phase} {level}級',
    specialEffects: '特殊效果',
    maxLevel: '按滿練度計算',
    searchGroups: '搜尋組合 / 幹員 / 拼音',
    searchGroupsLabel: '搜尋組合',
    allCategories: '全部分類',
    groupCategory: '組合分類',
    groupOwnership: '組合持有狀態',
    groupList: '基建組合列表',
    noGroups: '沒有符合條件的組合，請調整篩選條件',
    core: '核心幹員',
    support: '備選幹員',
    accessory: '掛件',
    coreOwned: '核心均已擁有',
    missing: '含未擁有成員',
    unknown: '持有狀態未知',
    ownershipSummary: '已擁有 {owned} / {total}',
    unknownCount: ' · {count} 人未知',
    selected: '已選中',
    unselected: '未選中',
    estimate: '效率估算',
    emptySelection: '勾選核心或備選幹員計算',
    noDirectBonus: '該選擇無直接效率加成，詳見明細',
    estimateDetails: '計算條件與明細',
    estimateHelp: '僅計所選幹員技能，不含設施基礎效率；不同設施分別顯示，中樞同類加成取最高',
    dormCount: '宿舍人數',
    recruits: '額外招募位',
    tradeCount: '貿易站數',
    powerCount: '發電站數',
    suiCount: '工作設施內歲人數',
    factoryCount: '製造站數',
    dormLevel: '愛麗絲/車爾尼宿舍等級',
    roomResidents: '塑心所在宿舍人數',
    catRoom: '調查團進駐',
    droneCap: '無人機上限',
    eunectesRoom: '森蚺進駐',
    platforms: '其他發電站有作業平臺',
    hunters: '每個製造站獵人數',
    average: '按照平均效率計算',
    goldLines: '實際赤金生產線',
    receptionLevel: '會客室等級',
    jayeStage: '孑的精英階段',
    orderCap: '設施基礎訂單上限',
    followSkland: '跟隨森空島',
    unpromoted: '未精英化',
    eliteOne: '精一及以上',
    none: '無',
    yes: '有',
    general: '通用',
    experience: '經驗',
    originium: '源石',
    tradeMetric: '貿易訂單效率',
    factoryMetric: '{product}製造生產力',
    capacityError: '{room}已選{count}人，最多{limit}人，請取消部分幹員',
    unownedError: '{name}未擁有，無法按實際練度計算',
    missingJaye: '孑缺少森空島練度，請同步或手選精英階段',
    missingGrowth: '{name}缺少森空島練度，請同步後計算',
    groupsById: {
      'builtin-run-order': {
        title: '跑單幹員',
        note: ''
      },
      'builtin-smoke': {
        title: '人間煙火',
        note: '同時有5名歲幹員在工作設施，如在意公招效率，不推薦使用'
      },
      'builtin-perception': {
        title: '感知資訊',
        note: '如在意公招效率，不推薦使用'
      },
      'builtin-lgd': {
        title: '龍門近衛局',
        note: ''
      },
      'builtin-monster-hunter': {
        title: '怪物獵人小隊',
        note: ''
      },
      'builtin-automation': {
        title: '自動化',
        note: ''
      },
      'builtin-abyss': {
        title: '深海獵人',
        note: ''
      },
      'builtin-redpine': {
        title: '紅松林',
        note: ''
      },
      'builtin-tianmao': {
        title: '精英幹員',
        note: '至少5名精英幹員位於不同設施'
      },
      'builtin-nasti': {
        title: '萊茵科技',
        note: '需要5名萊茵生命幹員（不含繆爾賽思）'
      },
      'builtin-makoto': {
        title: '結城理·S.E.E.S.',
        note: ''
      },
      'builtin-pozy': {
        title: '鴻雪杜林組',
        note: ''
      },
      'builtin-siracusa': {
        title: '敘拉古',
        note: ''
      },
      'builtin-exusiai': {
        title: '能天使',
        note: ''
      },
      'builtin-glasgow': {
        title: '格拉斯哥幫',
        note: ''
      },
      'builtin-karlan': {
        title: '喀蘭貿易',
        note: ''
      },
      'builtin-gold': {
        title: '金屬工藝',
        note: ''
      },
      'builtin-bubble': {
        title: '泡泡倉庫',
        note: ''
      },
      'builtin-cloud': {
        title: '紅雲經驗',
        note: ''
      },
      'builtin-standardization': {
        title: '黑鋼標準化',
        note: ''
      }
    },
    tradeCategory: '貿易',
    metalCategory: '金屬',
    sameFactory: '同一製造站',
    sameTrading: '同一貿易站',
    non153: '非153',
    threePower: '3電',
    zeroMorale: '0心情',
    positiveMorale: '不可0心情',
    fourGold: '4赤使用',
    fiveEliteTrade: '目前5精幹35%貿易',
    points: '點',
    rooms: '間',
    people: '人',
    lines: '條',
    orders: '筆',
    slots: '格',
    perHour: '/小時'
  }
}
