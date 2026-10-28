export const baseEstimateMessages = {
  'zh-CN': {
    sameFactory: '同一制造站',
    sameTradingPost: '同一贸易站',
    smokeSui: '{name}：{count}名岁 × 5 = {value}烟火',
    smokeRecruit: '{name}：{count}个额外招募位 × 10 = {value}烟火',
    smokeDorm: '{name}：{count}名宿舍干员提供{count}烟火',
    smokeConversion: '{first} {firstValue}% + {second} {secondValue}%，每5/3点烟火按完整组折算',
    perceptionDorm: '{name}：{count}名宿舍干员提供{count}感知',
    perceptionRecruit: '{name}：{value}感知，心情耗尽后清空',
    perceptionLevel: '{name}：{level}级宿舍提供{level}感知',
    automationParts:
      '{first} {firstValue}% + {second} {secondValue}% + {third} {thirdValue}% + {fourth} {fourthValue}%',
    numberedFactory: '制造站{number}·通用制造生产力',
    hunterDistribution: '{name}在中枢，{count}名猎人分配到{stations}个制造站{distribution}',
    distributionPrefix: '，',
    hunterStation: '第{number}站{count}人',
    listSeparator: '、',
    redpineParts: '制造干员基础 {base}% + 骑士/红松林加成 {bonus}%',
    rhineParts: '{first} {firstValue}% + {second} {secondValue}%；{third}在发电站',
    goldLinesParts:
      '实际{actual}条 + {first}杜林{bonus}条 + {second}{extra}条，{second}仅按实际赤金生产线计算',
    pozyParts: '{first} {firstValue}% + {second} {secondValue}% + {third} {thirdValue}%',
    siracusaParts: '{first} {firstValue}% + {second} {secondValue}% + {third}中枢加成 {bonus}%',
    jayeStage: '{name}{stage}，使用{source}',
    sklandProgression: '森空岛练度',
    manualSelection: '手动选择',
    jayeParts: '其他干员 {peers}% + {name} {value}%，按空单状态估算',
    orderCapParts:
      '订单上限增加{positive}，{first}减少{negative}，{second}减少{reduction}，上限至少1',
    orderConversion:
      '{first} {firstValue}% + {second} {secondValue}%，仅转换干员净增加的订单上限，不含设施基础值',
    metalParts: '基础金属技能 {base}% + {first}/{second}加成 {bonus}%',
    storageParts: '基础 {base}% + 每名干员各自仓库折算 {bonus}%',
    cloudParts: '{method}：基础 {base}% + {name}仓库折算 {bonus}%',
    averageMethod: '按右满30小时工作周期取平均',
    maximumMethod: '按时间技能的最高效率计算',
    standardizationParts: '标准化 {base}% + {first}/{second}加成 {bonus}%',
    tradeMetric: '贸易订单效率',
    recipeHelp: '各配方效率已包含通用制造加成，选择对应配方的结果，不重复叠加',
    smokeMetric: '人间烟火',
    lingSmoke: '{operator0}：烟火模式，心情大于12，提供15烟火',
    duskSmoke: '{operator0}：烟火模式，心情不高于12，提供15烟火',
    recruitMetric: '公招联络速度',
    allTradeMetric: '所有贸易站订单效率',
    allFactoryMetric: '所有制造站·通用制造生产力',
    perceptionMetric: '感知信息',
    resonanceMetric: '无声共鸣',
    lingPerception: '{operator0}：感知模式，心情不高于12，提供10感知',
    duskPerception: '{operator0}：感知模式，心情大于12，提供10感知',
    saileachRule: '{operator0}按办公室基础联络速度5%判断；比例转换按完整组折算',
    bothCenter: '两人均进驻中枢',
    matatabiMetric: '木天蓼',
    hunterCenter: '{operator1}和{operator0}进驻中枢，调查团按所选设施计算',
    virtualPowerMetric: '计入技能的发电站',
    suppressedRule: '仅保留按设施数量提供的生产加成，其他普通生产力归零',
    greyyMetric: '{operator0}·无人机充能',
    lumenMetric: '{operator0}·宿舍全员心情恢复',
    lancetRule: '{operator0}按发电站在岗条件计数，不计算自身充能技能',
    redpineRule:
      '{operator0}、{operator1}在中枢；{operator1}增加经验生产、降低赤金生产；{operator2}仅增加赤金生产',
    eliteMetric: '精英干员设施',
    droneMetric: '无人机充能速度',
    elitePlacement:
      '{operator0}在办公室、{operator1}在制造站、{operator2}在发电站、{operator3}在贸易站',
    eliteRoomRule:
      '精干设施数按已选精英干员人数计算，分别进驻不同设施；{operator0}最多计5间，{operator1}最多计10间',
    mechanistAverage: '{operator0}按右满30小时工作周期取平均，挂件不叠加自身技能',
    mechanistMaximum: '{operator0}按工作满12小时后的最高效率计算，挂件不叠加自身技能',
    rhineMetric: '其他莱茵生命干员',
    seesMetric: 'S.E.E.S.在岗人数',
    seesRule: '{operator1}在制造站，{operator0}在发电站，挂件仅提供S.E.E.S.人数',
    goldMetric: '赤金生产线',
    chestnutRule: '{operator1}在另一个制造站，源石结果包含通用加成；{operator0}族须有心情',
    exusiaiRule: '{operator0}与{operator1}进驻同一贸易站',
    delphineRule: '{operator0}进驻中枢，其余勾选成员进驻同一贸易站',
    siegeRule: '{operator0}在贸易站仅提供阵营人数，不计宿舍技能',
    orderMetric: '订单上限',
    gnosisRule:
      '{operator1}在中枢；先结算{operator3}的订单转效率，再计{operator2}的扣减，最后结算{operator0}的订单转效率',
    storageMetric: '仓库容量加成',
    standardizationRule: '{operator3}、{operator1}、{operator2}在同一制造站，{operator0}进驻中枢'
  },
  'en-US': {
    sameFactory: 'Same Factory',
    sameTradingPost: 'Same Trading Post',
    smokeSui: '{name}: {count} Sui operators × 5 = {value} Worldly Plight',
    smokeRecruit: '{name}: {count} extra recruitment slots × 10 = {value} Worldly Plight',
    smokeDorm: '{name}: {count} Dormitory operators provide {count} Worldly Plight',
    smokeConversion:
      '{first} {firstValue}% + {second} {secondValue}%; convert complete groups of 5/3 Worldly Plight respectively',
    perceptionDorm: '{name}: {count} Dormitory operators provide {count} Perception Information',
    perceptionRecruit: '{name}: {value} Perception Information, cleared when morale is depleted',
    perceptionLevel: '{name}: a level {level} Dormitory provides {level} Perception Information',
    automationParts:
      '{first} {firstValue}% + {second} {secondValue}% + {third} {thirdValue}% + {fourth} {fourthValue}%',
    numberedFactory: 'Factory {number} · General productivity',
    hunterDistribution:
      '{name} in the Control Center; {count} Hunters assigned to {stations} Factories{distribution}',
    distributionPrefix: ': ',
    hunterStation: 'Factory {number}: {count} operators',
    listSeparator: '; ',
    redpineParts: 'Factory operators’ base {base}% + Knight/Pinus Sylvestris bonus {bonus}%',
    rhineParts: '{first} {firstValue}% + {second} {secondValue}%; {third} in a Power Plant',
    goldLinesParts:
      '{actual} actual lines + {bonus} from {first}’s Durin bonus + {extra} from {second}; {second} counts only actual Pure Gold production lines',
    pozyParts: '{first} {firstValue}% + {second} {secondValue}% + {third} {thirdValue}%',
    siracusaParts:
      '{first} {firstValue}% + {second} {secondValue}% + {third} Control Center bonus {bonus}%',
    jayeStage: '{name}: {stage}, using {source}',
    sklandProgression: 'SKLand progression',
    manualSelection: 'manual selection',
    jayeParts: 'Other operators {peers}% + {name} {value}%; estimated with no pending orders',
    orderCapParts:
      'Order limit +{positive}, −{negative} from {first}, −{reduction} from {second}; minimum limit 1',
    orderConversion:
      '{first} {firstValue}% + {second} {secondValue}%; convert only the net order-limit increase from operators, excluding facility base capacity',
    metalParts: 'Base Metalwork skills {base}% + {first}/{second} bonus {bonus}%',
    storageParts:
      'Base {base}% + storage conversion calculated separately for each operator {bonus}%',
    cloudParts: '{method}: base {base}% + {name} storage conversion {bonus}%',
    averageMethod:
      'Average over a 30-hour work cycle with the right-side operators fully rested at the start',
    maximumMethod: 'Use the maximum efficiency of time-dependent skills',
    standardizationParts: 'Standardization {base}% + {first}/{second} bonus {bonus}%',
    tradeMetric: 'Trading Post order efficiency',
    recipeHelp:
      'Each recipe’s result includes general Factory bonuses. Use the matching recipe result without adding the bonus again.',
    smokeMetric: 'Worldly Plight',
    lingSmoke: '{operator0}: Worldly Plight mode; morale above 12 provides 15 Worldly Plight',
    duskSmoke: '{operator0}: Worldly Plight mode; morale at most 12 provides 15 Worldly Plight',
    recruitMetric: 'Recruitment contact speed',
    allTradeMetric: 'Order efficiency in all Trading Posts',
    allFactoryMetric: 'All Factories · General productivity',
    perceptionMetric: 'Perception Information',
    resonanceMetric: 'Soundless Resonance',
    lingPerception:
      '{operator0}: Perception mode; morale at most 12 provides 10 Perception Information',
    duskPerception:
      '{operator0}: Perception mode; morale above 12 provides 10 Perception Information',
    saileachRule:
      '{operator0} uses the Office’s base contact speed of 5%; conversions count complete groups',
    bothCenter: 'Both operators are in the Control Center',
    matatabiMetric: 'Matatabi',
    hunterCenter:
      '{operator1} and {operator0} are in the Control Center; Terra Research Commission uses the selected facility',
    virtualPowerMetric: 'Power Plants counted by skills',
    suppressedRule:
      'Keep only productivity bonuses based on facility counts; other ordinary productivity becomes zero',
    greyyMetric: '{operator0} · Drone recovery',
    lumenMetric: '{operator0} · Morale recovery for all Dormitory occupants',
    lancetRule:
      '{operator0} counts as a staffed Power Plant condition; its own drone recovery skill is excluded',
    redpineRule:
      '{operator0} and {operator1} are in the Control Center. {operator1} increases EXP and reduces Pure Gold productivity; {operator2} only increases Pure Gold productivity.',
    eliteMetric: 'Facilities with Elite Operators',
    droneMetric: 'Drone recovery speed',
    elitePlacement:
      '{operator0} in the Office, {operator1} in a Factory, {operator2} in a Power Plant and {operator3} in a Trading Post',
    eliteRoomRule:
      'Count selected Elite Operators, each in a different facility. {operator0} counts up to 5 facilities; {operator1} up to 10.',
    mechanistAverage:
      '{operator0} uses the average over a 30-hour work cycle with the right-side operators fully rested at the start. Accessories do not add their own skill bonuses.',
    mechanistMaximum:
      '{operator0} uses maximum efficiency after 12 hours of work. Accessories do not add their own skill bonuses.',
    rhineMetric: 'Other Rhine Lab operators',
    seesMetric: 'Staffed S.E.E.S. operators',
    seesRule:
      '{operator1} in a Factory, {operator0} in a Power Plant; accessories only contribute to the S.E.E.S. count',
    goldMetric: 'Pure Gold production lines',
    chestnutRule:
      '{operator1} is in another Factory. Originium results include general bonuses; {operator0}s must have positive morale.',
    exusiaiRule: '{operator0} and {operator1} are in the same Trading Post',
    delphineRule:
      '{operator0} is in the Control Center; other selected members are in the same Trading Post',
    siegeRule:
      '{operator0} only contributes to the faction count in a Trading Post; her Dormitory skills are excluded',
    orderMetric: 'Order limit',
    gnosisRule:
      '{operator1} is in the Control Center. Resolve {operator3}’s order-to-efficiency conversion first, then {operator2}’s reduction, then {operator0}’s conversion.',
    storageMetric: 'Storage capacity bonus',
    standardizationRule:
      '{operator3}, {operator1} and {operator2} are in the same Factory; {operator0} is in the Control Center'
  },
  'ja-JP': {
    sameFactory: '同じ製造所',
    sameTradingPost: '同じ貿易所',
    smokeSui: '{name}：歳のオペレーター{count}人 × 5 = 俗世の憂{value}',
    smokeRecruit: '{name}：追加求人枠{count}個 × 10 = 俗世の憂{value}',
    smokeDorm: '{name}：宿舎の{count}人から俗世の憂{count}を獲得',
    smokeConversion:
      '{first} {firstValue}% + {second} {secondValue}%。俗世の憂をそれぞれ5・3の整数単位で換算',
    perceptionDorm: '{name}：宿舎の{count}人から知覚情報{count}を獲得',
    perceptionRecruit: '{name}：知覚情報{value}。体力がなくなると消去',
    perceptionLevel: '{name}：レベル{level}の宿舎から知覚情報{level}を獲得',
    automationParts:
      '{first} {firstValue}% + {second} {secondValue}% + {third} {thirdValue}% + {fourth} {fourthValue}%',
    numberedFactory: '製造所{number}・汎用製造効率',
    hunterDistribution:
      '{name}を制御中枢に配置。ハンター{count}人を製造所{stations}か所に配置{distribution}',
    distributionPrefix: '：',
    hunterStation: '製造所{number}：{count}人',
    listSeparator: '、',
    redpineParts: '製造担当の基本{base}% + 騎士・レッドパイン補正{bonus}%',
    rhineParts: '{first} {firstValue}% + {second} {secondValue}%。{third}は発電所に配置',
    goldLinesParts:
      '実際の{actual}ライン + {first}のドゥリン補正{bonus}ライン + {second}の{extra}ライン。{second}は実際の純金ラインのみ参照',
    pozyParts: '{first} {firstValue}% + {second} {secondValue}% + {third} {thirdValue}%',
    siracusaParts:
      '{first} {firstValue}% + {second} {secondValue}% + {third}の制御中枢補正{bonus}%',
    jayeStage: '{name}：{stage}、{source}を使用',
    sklandProgression: 'SKLand の育成状況',
    manualSelection: '手動の選択',
    jayeParts: '他のオペレーター{peers}% + {name} {value}%。未処理オーダーなしで推計',
    orderCapParts:
      '注文上限+{positive}、{first}で−{negative}、{second}で−{reduction}。上限の最小値は1',
    orderConversion:
      '{first} {firstValue}% + {second} {secondValue}%。施設の基礎値を除き、オペレーターによる上限の純増分のみ換算',
    metalParts: '基本の金属加工スキル{base}% + {first}・{second}の補正{bonus}%',
    storageParts: '基本{base}% + 各オペレーターの保管上限を個別換算した補正{bonus}%',
    cloudParts: '{method}：基本{base}% + {name}の保管上限換算{bonus}%',
    averageMethod: '右側の担当が体力全快の状態から30時間勤務した平均',
    maximumMethod: '時間経過スキルの最高効率で計算',
    standardizationParts: '標準化{base}% + {first}・{second}の補正{bonus}%',
    tradeMetric: '貿易オーダー効率',
    recipeHelp:
      '各レシピの結果に汎用製造補正を含みます。該当するレシピを選び、補正を重ねて加算しないでください。',
    smokeMetric: '俗世の憂',
    lingSmoke: '{operator0}：俗世の憂モード。体力12超で俗世の憂15を付与',
    duskSmoke: '{operator0}：俗世の憂モード。体力12以下で俗世の憂15を付与',
    recruitMetric: '事務連絡速度',
    allTradeMetric: '全貿易所のオーダー効率',
    allFactoryMetric: '全製造所・汎用製造効率',
    perceptionMetric: '知覚情報',
    resonanceMetric: '静かなる共鳴',
    lingPerception: '{operator0}：知覚モード。体力12以下で知覚情報10を付与',
    duskPerception: '{operator0}：知覚モード。体力12超で知覚情報10を付与',
    saileachRule: '{operator0}の判定には事務室の基本連絡速度5%を使用。割合の換算は整数単位',
    bothCenter: '2人とも制御中枢に配置',
    matatabiMetric: 'マタタビ',
    hunterCenter: '{operator1}と{operator0}を制御中枢に配置。調査団は選択した施設で計算',
    virtualPowerMetric: 'スキル計算に含む発電所',
    suppressedRule: '施設数に応じた製造補正のみ残し、その他の通常製造効率は0になります',
    greyyMetric: '{operator0}・ドローン回復',
    lumenMetric: '{operator0}・宿舎全員の体力回復',
    lancetRule: '{operator0} は発電所在勤の条件として数え、自身のドローン回復スキルは含めません',
    redpineRule:
      '{operator0}と{operator1}を制御中枢に配置。{operator1}は作戦記録の製造を増やし、純金の製造を減らします。{operator2}は純金のみ増加。',
    eliteMetric: 'エリートオペレーターの配置施設',
    droneMetric: 'ドローン回復速度',
    elitePlacement:
      '{operator0}は事務室、{operator1}は製造所、{operator2}は発電所、{operator3}は貿易所に配置',
    eliteRoomRule:
      '選択したエリートオペレーターをそれぞれ別の施設に配置して計算。{operator0}は最大5施設、{operator1}は最大10施設を計上。',
    mechanistAverage:
      '{operator0}は右側の担当が体力全快の状態から30時間勤務した平均で計算。補助要員自身のスキルは加算しません。',
    mechanistMaximum:
      '{operator0}は12時間勤務後の最高効率で計算。補助要員自身のスキルは加算しません。',
    rhineMetric: 'その他のライン生命オペレーター',
    seesMetric: '勤務中の S.E.E.S. 人数',
    seesRule:
      '{operator1}は製造所、{operator0}は発電所に配置。補助要員は S.E.E.S. の人数にのみ算入。',
    goldMetric: '純金の製造ライン',
    chestnutRule:
      '{operator1}は別の製造所に配置。源石の結果に汎用補正を含みます。{operator0}族は体力が必要です。',
    exusiaiRule: '{operator0}と{operator1}を同じ貿易所に配置',
    delphineRule: '{operator0}は制御中枢、他の選択メンバーは同じ貿易所に配置',
    siegeRule: '{operator0}は貿易所で陣営人数にのみ算入し、宿舎スキルは含めません',
    orderMetric: '注文上限',
    gnosisRule:
      '{operator1}は制御中枢に配置。{operator3}のオーダー効率換算、{operator2}の減少、{operator0}の換算の順に計算。',
    storageMetric: '保管上限補正',
    standardizationRule:
      '{operator3}、{operator1}、{operator2}は同じ製造所、{operator0}は制御中枢に配置'
  },
  'zh-TW': {
    sameFactory: '同一製造站',
    sameTradingPost: '同一貿易站',
    smokeSui: '{name}：{count}名歲 × 5 = {value}煙火',
    smokeRecruit: '{name}：{count}個額外招募位 × 10 = {value}煙火',
    smokeDorm: '{name}：{count}名宿舍幹員提供{count}煙火',
    smokeConversion: '{first} {firstValue}% + {second} {secondValue}%，每5/3點煙火按完整組折算',
    perceptionDorm: '{name}：{count}名宿舍幹員提供{count}感知',
    perceptionRecruit: '{name}：{value}感知，心情耗盡後清空',
    perceptionLevel: '{name}：{level}級宿舍提供{level}感知',
    automationParts:
      '{first} {firstValue}% + {second} {secondValue}% + {third} {thirdValue}% + {fourth} {fourthValue}%',
    numberedFactory: '製造站{number}·通用製造生產力',
    hunterDistribution: '{name}在中樞，{count}名獵人分配到{stations}個製造站{distribution}',
    distributionPrefix: '，',
    hunterStation: '第{number}站{count}人',
    listSeparator: '、',
    redpineParts: '製造幹員基礎 {base}% + 騎士/紅松林加成 {bonus}%',
    rhineParts: '{first} {firstValue}% + {second} {secondValue}%；{third}在發電站',
    goldLinesParts:
      '實際{actual}條 + {first}杜林{bonus}條 + {second}{extra}條，{second}僅按實際赤金生產線計算',
    pozyParts: '{first} {firstValue}% + {second} {secondValue}% + {third} {thirdValue}%',
    siracusaParts: '{first} {firstValue}% + {second} {secondValue}% + {third}中樞加成 {bonus}%',
    jayeStage: '{name}{stage}，使用{source}',
    sklandProgression: '森空島練度',
    manualSelection: '手動選擇',
    jayeParts: '其他幹員 {peers}% + {name} {value}%，按空單狀態估算',
    orderCapParts:
      '訂單上限增加{positive}，{first}減少{negative}，{second}減少{reduction}，上限至少1',
    orderConversion:
      '{first} {firstValue}% + {second} {secondValue}%，僅轉換幹員淨增加的訂單上限，不含設施基礎值',
    metalParts: '基礎金屬技能 {base}% + {first}/{second}加成 {bonus}%',
    storageParts: '基礎 {base}% + 每名幹員各自倉庫折算 {bonus}%',
    cloudParts: '{method}：基礎 {base}% + {name}倉庫折算 {bonus}%',
    averageMethod: '按右滿30小時工作週期取平均',
    maximumMethod: '按時間技能的最高效率計算',
    standardizationParts: '標準化 {base}% + {first}/{second}加成 {bonus}%',
    tradeMetric: '貿易訂單效率',
    recipeHelp: '各配方效率已包含通用製造加成，選擇對應配方的結果，不重複疊加',
    smokeMetric: '人間煙火',
    lingSmoke: '{operator0}：煙火模式，心情大於12，提供15煙火',
    duskSmoke: '{operator0}：煙火模式，心情不高於12，提供15煙火',
    recruitMetric: '公招聯絡速度',
    allTradeMetric: '所有貿易站訂單效率',
    allFactoryMetric: '所有製造站·通用製造生產力',
    perceptionMetric: '感知資訊',
    resonanceMetric: '無聲共鳴',
    lingPerception: '{operator0}：感知模式，心情不高於12，提供10感知',
    duskPerception: '{operator0}：感知模式，心情大於12，提供10感知',
    saileachRule: '{operator0}按辦公室基礎聯絡速度5%判斷；比例轉換按完整組折算',
    bothCenter: '兩人均進駐中樞',
    matatabiMetric: '木天蓼',
    hunterCenter: '{operator1}和{operator0}進駐中樞，調查團按所選設施計算',
    virtualPowerMetric: '計入技能的發電站',
    suppressedRule: '僅保留按設施數量提供的生產加成，其他普通生產力歸零',
    greyyMetric: '{operator0}·無人機充能',
    lumenMetric: '{operator0}·宿舍全員心情恢復',
    lancetRule: '{operator0}按發電站在崗條件計數，不計算自身充能技能',
    redpineRule:
      '{operator0}、{operator1}在中樞；{operator1}增加經驗生產、降低赤金生產；{operator2}僅增加赤金生產',
    eliteMetric: '精英幹員設施',
    droneMetric: '無人機充能速度',
    elitePlacement:
      '{operator0}在辦公室、{operator1}在製造站、{operator2}在發電站、{operator3}在貿易站',
    eliteRoomRule:
      '精幹設施數按已選精英幹員人數計算，分別進駐不同設施；{operator0}最多計5間，{operator1}最多計10間',
    mechanistAverage: '{operator0}按右滿30小時工作週期取平均，掛件不疊加自身技能',
    mechanistMaximum: '{operator0}按工作滿12小時後的最高效率計算，掛件不疊加自身技能',
    rhineMetric: '其他萊茵生命幹員',
    seesMetric: 'S.E.E.S.在崗人數',
    seesRule: '{operator1}在製造站，{operator0}在發電站，掛件僅提供S.E.E.S.人數',
    goldMetric: '赤金生產線',
    chestnutRule: '{operator1}在另一個製造站，源石結果包含通用加成；{operator0}族須有心情',
    exusiaiRule: '{operator0}與{operator1}進駐同一貿易站',
    delphineRule: '{operator0}進駐中樞，其餘勾選成員進駐同一貿易站',
    siegeRule: '{operator0}在貿易站僅提供陣營人數，不計宿舍技能',
    orderMetric: '訂單上限',
    gnosisRule:
      '{operator1}在中樞；先結算{operator3}的訂單轉效率，再計{operator2}的扣減，最後結算{operator0}的訂單轉效率',
    storageMetric: '倉庫容量加成',
    standardizationRule: '{operator3}、{operator1}、{operator2}在同一製造站，{operator0}進駐中樞'
  }
}
