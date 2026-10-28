export default {
  overview: 'オペレーター稼働時間一覧',
  overviewScroll: 'オペレーター稼働時間一覧を横にスクロール',
  sampling:
    '集計期間の {hours} 時間のみを対象とし、ウォームアップは含みません。勤務、休息、待機、体力切れでの勤務を別々に集計します。主担当と交代要員の勤務時間には体力切れでの勤務を含めません。',
  ratioHelp:
    '勤務割合＝勤務時間÷集計時間。勤務・休息比＝勤務時間÷休息時間。休息時間がない場合は — を表示します。',
  operator: 'オペレーター',
  workFraction: '勤務割合',
  workRest: '勤務・休息比',
  work: '勤務（時間）',
  primary: '主担当（時間）',
  substitute: '交代要員（時間）',
  rest: '休息（時間）',
  idle: '待機（時間）',
  exhausted: '体力切れ（時間）',
  finalMorale: '終了時の体力',
  currentTask: '現在のタスク',
  taskLabel: '{kind}：{label}',
  pendingTask: '次の実行待ちタスク',
  due: '予定時刻 T+{hours} 時間',
  morale: '体力 {value} / {limit}',
  noStaff: '未配属',
  noGroup: 'グループ未設定',
  recent: '最近の動作：{events}',
  occurrences: '{label} {count} 回',
  noDetails: 'この観測には具体的なオペレーターやタスクの情報がありません。',
  observedOnly:
    '表示内容は観測記録です。動作の頻度だけでは原因を特定できません。過去の検証記録は、現在も問題が未解決であることを意味しません。',
  dayRange: '{period}日数は {min}～{max} の整数で指定してください',
  warmup: 'ウォームアップ',
  sample: '集計',
  seedRange: '乱数シードは 0～4294967295 の整数で指定してください',
  missingDrone: 'ドローンの対象施設が今回の勤務表にありません',
  noOperatorCache:
    '利用可能な Skland の育成データキャッシュがありません。同期するか、別の育成データを選択してください',
  emptyOperatorCache: 'Skland のキャッシュに所持オペレーターがありません',
  enterOperators: 'オペレーターと育成状況を入力してください',
  invalidOperatorMode: '育成データの選択が無効です',
  noWeights: 'Mower の収益計算設定が未読込です。再試行するか、今回のみの重みを指定してください',
  invalidWeights: '産出の重みの取得元が無効です',
  experience: '経験値',
  goldEquivalent: '純金の龍門幣換算額',
  tradeLmd: '貿易による龍門幣',
  lmdCost: '龍門幣消費',
  netLmd: '龍門幣純増',
  fragments: '源石の欠片',
  orundum: '合成玉',
  recycle: '回収施設の産出',
  recruitment: '公開求人の更新',
  clues: '応接室の手がかり',
  expUnit: '経験値',
  lmdUnit: '龍門幣',
  itemUnit: '個',
  countUnit: '回',
  dorm: '宿舎{number}',
  baseSkills: '基地スキル',
  owned: '所持済み',
  unowned: '未所持',
  active: '解放済み',
  locked: '未解放',
  replaced: '置き換え済み',
  initialMorale: '初期体力 24（個人の上限に従う）',
  initialFiammettaMorale:
    'フィアメッタの初期体力は {value}、他のオペレーターは個人の上限から開始（未設定なら 24）',
  sourceImage:
    '元画像：{label}。QR コードには主表・補助表全体と詳細設定を含み、Mower の「勤務表をインポート」で読み込めます。',
  sampleSummary:
    'ウォームアップ {warmup} 日（収益に含まない）、集計 {sample} 日、合計 {total} 日、乱数シード {seed}。',
  droneInventorySummary: 'ドローン：{target}。{inventory}',
  finiteInventorySummary: '有限在庫：外部からの収入はなく、収支を連続して記録します。{shortage}',
  potentialInventorySummary:
    '潜在生産量：初期在庫の制約を受けず、納品可能な収入を表すものではありません。',
  initialInventorySummary: '初期在庫（{source}）：{inventory}。初期数量は収益に含みません。',
  cachedInventorySource: 'Skland のキャッシュ（手動変更可）',
  allZero: 'すべて 0',
  goldBalanceSummary:
    '純金の残量：初期 {initial}、集計開始 {opening}、終了 {closing}。負の値は不足量であり、実際の在庫ではありません。',
  cacheDateSummary:
    '在庫キャッシュの同期日時：{date}。現在のゲーム内状態を表すものではありません。',
  noCacheDate: 'キャッシュ日時なし',
  operatorAssumptions: 'オペレーター：{source}。{initialMorale}。ジェイを昇進0として扱う：{jaye}。',
  cachedOperatorsSource: 'Skland のキャッシュにある実際の所持状況と育成状態',
  manualOperatorsSource: '今回入力した所持状況と育成状態',
  maximumOperatorsSource: '全オペレーターを最大育成と仮定',
  enabled: '有効',
  disabled: '無効',
  noTrainingAssumption:
    '今回は未完了の訓練計画も実行中の訓練もない状態に固定し、訓練進捗や完了時刻は演算しません。',
  historicalTrainingAssumption:
    '過去の演算で未完了の訓練計画：{present}。全期間この条件を維持し、訓練完了は演算しません。',
  goldEquivalentAssumption:
    '純金の龍門幣換算値は製造した純金×500＋特殊注文の追加価値で、納品で消費した純金は差し引きません。実際の龍門幣収入ではありません。',
  weightAssumptions:
    '生産物の重み（{source}）：{weights}。加重生産量は龍門幣の決済額ではありません。',
  modelAssumptions:
    'モデルの仮定：理想的な注文完了処理、一部の入室確認・配置にかかる時間を再現し、その他のクリック・認識時間は省略します。宿舎の雰囲気はレベル上限とします。',
  thresholdStrategyAssumption:
    '交代方式 {version}、リアルタイム体力計算：{enabled}。両モードとも体力変化を演算し、通常の退勤閾値で交代します。交代要員の不足を避けるための早期退勤は行いません。通常の緊急呼び戻しでは、対応する主担当が全回復するまで勤務できる必要があります。',
  strategyAssumption:
    '交代方式 {version}、リアルタイム体力計算：{enabled}。両モードとも体力変化を演算します。',
  noStrategyAssumption:
    'この記録には交代方式のバージョンがありません。再演算すると現在の方式と比較できます。',
  facilityLevelsAssumption:
    '今回の施設レベル（勤務表の保存値を優先し、未設定なら推定）：{levels}。',
  provenanceAssumption:
    '計算器の基準 {base}、選択的な同期 {sync}（ローカル適応を含む）。配置の基準は Mower alpha {mowerBase}、今回の照合先 {mowerChecked}。本体の後続変更は自動同期しません。',
  legacyProvenanceAssumption:
    '計算器 {calculator}（完了時刻の精度、純金の不足許可、製造費用、求人・手がかり観測のローカル適応を含む）。配置の参照先は Mower alpha {mower}。本体の後続変更は自動同期しません。',
  recruitmentAssumption:
    '求人の更新回数は事務室の配置・体力・解放済みスキルから計算します。初期進捗は 0、ウォームアップの進捗は引き継ぎますが完了回数は含みません。更新回数は即時使用すると仮定し、3 回の上限による停止は再現しません。加重収益には含みません。',
  noClueAssumption: 'この記録には応接室の手がかり集計がありません。再演算すると確認できます。',
  clueAssumption:
    '応接室の手がかりは配置員による捜索完了数だけを集計します。初期進捗は 0、ウォームアップの進捗は引き継ぎますが完了数は含みません。即時受取・在庫整理を仮定し、満杯による停止、毎日の贈り物、戦友からの贈り物は再現しません。FP や加重収益は計算しません。',
  clueExchangeAssumption:
    '手がかりの生産量は全期間で情報共有を有効とし、体力切れでない配置員の解放済み加速スキルを含めます。全手がかりの収集や情報共有の切替は再現せず、配置側の Party Time は空のままです。',
  legacyClueExchangeAssumption:
    'この記録は情報共有を無効として計算しています。再演算では全期間有効として手がかり生産量を計算します。',
  recyclingAssumption:
    '回収施設は生産回数だけを集計し、ランダム素材の推定、素材在庫の追加、素材の収益価値は計算しません。',
  offlineAssumption:
    'オフラインモデルによる推定であり、実測収益や勤務表の実行可能性を証明するものではありません。画像のインポートでは今回の計算パラメーターと結果は復元しません。',
  sampleAnnotation: '{algorithm} · 集計 {days} 日',
  dailyWeightedIncome: '日平均加重収益',
  orderDistribution: '注文分布・元の区分',
  totalOrders: '合計 {count} 件',
  noStatistics: '集計なし',
  orderGold: '純金 {count} 個',
  otherOrders: 'その他 {count} 件 · {percent}%',
  noSavedOrders: '注文統計の保存なし',
  imageFailed: '収益画像を作成できませんでした',
  imageAuthor: '作成者：{author}',
  imageRemarks: '備考：{remarks}',
  custom: 'カスタム',
  imageWeights: '経験値 {experience} · 純金 {gold} · 注文 {orders}',
  imageFragmentWeights: '源石の欠片 {fragments} · 合成玉 {orundum}',
  imageFilename: '{name}_日平均収益{score}_{days}日.jpg',
  display: {
    progress: '{period} {elapsed} / {total} 時間',
    preparing: '勤務表データを準備中',
    preparingCalculation: '計算を準備中…',
    workerFailed: 'バックグラウンド演算に失敗しました',
    transferFailed: '演算結果を転送できませんでした',
    stopped: '演算を停止しました。パラメーターを変更して再試行できます。',
    archiveTimeout: '収益記録ストレージの待機がタイムアウトしました',
    archiveBlocked: '収益記録ストレージを別のウィンドウが使用しています',
    archiveAborted: '収益記録の保存処理を中止しました',
    archiveIncompatible: '保存済み収益記録の形式に互換性がありません',
    inventorySource: '在庫の取得元が無効です',
    noInventoryCache: 'Skland の在庫キャッシュがありません。同期するか手動設定を選択してください',
    unknownOperator: '行 {line}：不明なオペレーター',
    duplicateInventoryOperator: '行 {line}：{operator} が重複しています',
    invalidRow: '行 {line}：「ID または元の中国語名,昇進段階,レベル」を入力してください',
    invalidStage: '行 {line}：{operator}：昇進段階またはレベルが無効です',
    missingSkills: '行 {line}：{operator}：完全なスキル枠データがありません',
    invalidInventory: 'オペレーター一覧は配列で指定してください',
    unsupportedOfficeSkill: '未対応の事務室スキル：{skill}（{id}）',
    unsupportedReceptionSkill: '未対応の応接室スキル：{skill}（{id}）',
    missingReceptionDevelopment: '応接室オペレーターの育成情報がありません：{operator}',
    duplicatePrimary:
      '{operator} が {room1} と {room2} の両方に配置されています。主担当は重複配置できません。',
    powerDeficit:
      '基地の総消費電力 ({consumption}) が総発電量 ({generation}) を超えており、電力が不足しています。',
    unbuiltFacility: '{room} は未建設のため、オペレーター・休息ベッド・交代要員を設定できません。',
    outputFacilityType:
      '{room} は生産施設のため、製造所・貿易所・発電所のいずれかが必要です。現在の種類：{type}。',
    outputFacilityLevel: '{room} のレベルは 1～3 が必要です。現在：{level}。',
    invalidFactoryProduct:
      '製造所 {room} の生産品 {product} は無効です。純金・作戦記録・源石の欠片から選択してください。',
    invalidTradeProduct:
      '貿易所 {room} の生産品 {product} は無効です。龍門幣または源石の注文を選択してください。',
    controlLevel: '制御中枢のレベルは 1～5 が必要です。現在のレベル：{level}、種類：{type}。',
    dormLevel: '宿舎 {room} のレベルは 1～5 が必要です。現在のレベル：{level}、種類：{type}。',
    functionalLevel: '補助施設 {room} のレベルは 1～3 が必要です。現在：{level}。',
    activityRoomUnsupported:
      '活動室 ({room}) は収益・電力演算に未対応のため、電力合計から除外しています。',
    capacity: '{room} の配置人数 ({count}) が施設レベルの定員 ({capacity}) を超えています。',
    placeholder: '{room} の枠は {kind} のプレースホルダーであり、収益演算では空席として扱います。',
    noReplacement: '{room} の配置員 ({operator}) に交代要員が設定されていません。',
    freeDormOnly: 'Free は宿舎にのみ配置できます。',
    freeNoGroup: 'Free に所属グループは設定できません。',
    fiammettaNoGroup: 'フィアメッタはグループ交代に参加できません。',
    uniqueBindings: '複数所属のグループ名は重複できず、名前なしの列は 1 列までです。',
    dormNoPersonalBinding:
      '宿舎の複数所属に個人用の名前なし列は設定できません。個別休息は宿舎以外の主担当のみが対象です。',
    replacementEachBinding: '複数所属のすべての列に交代要員が必要です。',
    duplicateReplacement: '交代リスト内でオペレーターが重複しています：{operator}。',
    freeReplacement: 'Free の交代要員は、フィアメッタ以外のグループ所属宿舎枠にのみ設定できます。',
    replacementConflict:
      '交代要員 {operator} は同じ名前付きグループの別の主担当、または勤務していない交代要員である必要があります。',
    groupAnchor:
      '{group} に出退勤を決める主担当がいません。宿舎以外で、体力 0 勤務・複数所属・待機候補に該当しない主担当が必要です。',
    groupReplacements: 'グループ {group} を配置できません。交代リストで全メンバーを補えません。',
    groupBeds: 'グループ {group} を配置できません。有効な宿舎ベッドが不足しています。',
    backupIssue: '補助表 {label}：{message}',
    backupOnlyIssue:
      '補助表 {label} の単独適用時：{message} 実際の組み合わせは切替前に検証します。',
    activityRunning: '演算が進行しています。',
    activitySlow:
      '演算の進行に時間がかかっています。以下は調査用の最近のオペレーター・タスクの観測であり、原因を特定するものではありません。',
    shiftOff: '退勤',
    shiftOn: '出勤',
    fiammetta: 'フィアメッタの体力回復',
    backupSwitch: '補助表切替',
    backupTask: '補助表の配置',
    releaseDorm: '宿舎から退去',
    bedTakeover: 'ベッドの引継ぎ',
    exhaustSupport: '使い切り支援',
    runOrder: '注文完了処理',
    switchProduct: '生産品・注文切替',
    exhaustOff: '使い切り退勤',
    correction: '配置を修正',
    clueExchange: '情報共有',
    dormOrder: '宿舎の並べ替え',
    releaseDormSlot: '宿舎の枠を開放',
    reported: '演算の過去の報告：{message}',
    shortSlow: '演算の進行に時間がかかっています。',
    droneCapacity: 'ドローン上限は 0 以上の安全な整数で指定してください',
    finiteModel:
      '設定した初期在庫を使用し、ウォームアップ開始から消費・回収・納品を連続して記録します。集計開始時にリセットしません。外部収入や自動補充はなく、不足時は対象の製造・納品を停止します。回収施設のランダム素材は在庫に含みません。',
    goldDebtModel:
      '{message} 今回は純金の不足を許可し、不足しても納品を妨げません。他の素材には在庫制約が適用されます。',
    compatibilityModel:
      'Mower 標準の互換交代方式を使用します。補助表を 6 段階で評価し、タスク保護をすべて維持します',
    alphaModel:
      'Mower alpha 勤務モデル（80c97ee60 の差分適応）を使用します。補助表の収束、共有グループ、宿舎の分離に対応します',
    unsupportedStage:
      '動的演算は照合済みの最大基地スキルを使用します。低い昇進段階はまだコンパイルされていません',
    operationDuration: '現在の演算は、配置操作にかかる時間を省略する場合にのみ対応しています',
    orderLifecycle:
      '注文完了処理の設定は維持します。このレポートは通常班の効率を集計し、注文ごとの配置・回収・資源決済は再現しません。',
    integration:
      '{mode}のウォームアップ、最大ステップ {step} h を使用します。複製の丸めなどの非線形効率は区間中点で数値積分します。ステップを小さくして感度を確認できます。',
    wholeHours: '1 時間単位',
    continuous: '連続',
    singleRecovery:
      '単体回復は自身とフィアメッタを常に除外します。単体回復スキル所持者は回復候補がその 1 名だけのときに適格となり、自ら対象を固定しません。後の入居で資格を失う場合があり、確認や明示指定でも資格を無視できません。通常の適格な対象は全回復・退去・宿舎担当変更まで維持し、再選択は体力の低い順、同値なら枠順です。',
    ioClock:
      '各部屋から戻る 0.5 秒と、近い予定タスクがない場合の通知確認 1 秒を時間軸に含めます。認識と他のクリック時間は 0 とします。run 完了後も同時刻のタスクがある場合、外側の単調時計を 1 マイクロ秒進めますが、タスク時刻は変更しません。',
    continuousMorale:
      '体力と読み取り値は連続数値で扱い、ゲームの体力バーの画素や認識誤差は再現しません。フィアメッタの回復保護が無効な場合、満タン付近の微小な不足で回復が密集することがあります。この方式を維持し、追加クールダウンは設けません。',
    tradeQuality:
      '裁縫系の注文確率は線形近似です。α/β は同じ枠で連続 3/5 時間勤務すると最大となり、枠の移動や退勤で時間をリセットします。同種効果は重複せず、現在の純金 4 個の確率が最も高いものを使います。中間曲線と重複の仕組みは実測で未検証です。',
    passiveOccupancy:
      '{room} / {operator}：今回は待機配置のみを演算します。加工・訓練タスクは行わず、体力消費は 0/h です',
    unmodeledTaskMorale:
      '{room} / {operator}：この施設のタスク体力消費は未対応です。タスク未実行として 0/h で扱います',
    backupCycle: '補助表の同時刻タスク連鎖が循環しています',
    clueModel:
      '手がかり生産量は情報共有を常時有効として計算します。配置側の Party Time は空のままで、手がかりの待機項目や情報共有タスクは実行しません。',
    legacyClueModel:
      '情報共有は常に無効、Party Time は空で、手がかりの待機項目や情報共有タスクは実行しません。',
    orderModel:
      '理想的な注文完了処理では、開始時にペペ・クロージャのモードを固定し、通常注文完了時にプロヴァイゾ・テキーラの収益を換算します。Mower の注文読み取り・タスク順序・起動時刻を維持し、一時交代は行いません。通常の交代・回収・ドローンタスクは Mower の時間軸に従います。',
    eventLimit: '積分区間が {count} 件に達しました。結果は未完了です',
    sameTimeAction: '同時刻の配置処理が収束しません。結果は未完了です',
    stalled: '次の正の長さの区間を決定できません',
    pendingFailure:
      '集計終了時も {task} タスク（{rooms}）の失敗が未解決でした：{message}。元のタスクと時刻を保持し、今回の収益演算は未完了です。',
    recoveredDelay:
      '{message}。{count} 回の延期は、その後の完全なグループ退勤イベントで回復を確認しました',
    blockingPlan: '勤務表に実行を妨げるエラーがあるため、収益を計算できません',
    incompleteReport: '完全な生産レポートを取得できませんでした',
    missingInventoryOperator:
      '{operator}：勤務表または連携に参加していますが、オペレーター一覧に登録されていません',
    fillDorm: '宿舎の枠を補充',
    refreshTaskTimes: 'タスク時刻を再取得',
    swapSupport: '訓練の協力者を交代',
    potentialModel:
      '潜在生産モードは素材不足を無視し、施設の保管容量と回収は Mower の配置に従い、完成時に生産量を加算します。帳簿は推定用で実際の入金ではありません。ドローンは選択した方式と実際の生成数に従って使用します。',
    idealRunOrders:
      '理想的な注文完了処理は、解放済みのペペ・クロージャ候補から新規注文モードを選び、通常注文完了時に U-Official・プロヴァイゾ・テキーラの効果を適用します。Mower のタスク読み取り・順序・起動時刻は維持します。一時交代や待機はせず、注文完了担当の体力や専用ドローンを消費しません。通常の配置とドローン対象方式は適用します。',
    dronePolicy:
      'ドローンは Mower のタスク段階で使用し、{hours} 時間ごとの待機項目確認と {count} 機の判定閾値を使います。選択した施設を加速し、注文完了用の追加ドローンは消費しません。',
    incomplete: '演算は未完了です',
    finding: '過去の報告（{finding}）：{message}。現在も未解決であることを示す記録ではありません。',
    groupBlocked: '使用可能な交代要員またはベッド不足、元の配置を維持',
    forcedBedWait: '強制宿舎タスクが有効な回復ベッドを待機',
    backupPreviewCycle: '補助表の事前演算の循環',
    backupDeferred: '補助表切替の延期',
    taskException: 'タスクの異常',
    planException: '勤務表計画の異常',
    planningException: '配置計画の異常',
    groupOperators: '所属グループ {group}、現在の関連オペレーター：{operators}',
    slotOperators: '枠 {slot}、現在の関連オペレーター：{operators}',
    groupDetail: '所属グループ {group}',
    slotDetail: '枠 {slot}',
    activitySpan: '、演算時間の幅 {minutes} 分',
    repeatedShifts:
      '最近の記録：{operator} の出勤 {on} 回、退勤 {off} 回{span}。活動の記述のみで、原因は未特定です。',
    repeatedBackups:
      '最近の記録：{label} の切替 {count} 回{span}。活動の記述のみで、原因は未特定です。',
    repeatedRecharges:
      '最近の記録：フィアメッタの回復 {count} 回{span}。活動の記述のみで、原因は未特定です。',
    smallRecharge:
      '最近のフィアメッタの回復 {count} 回では、対象の体力増加が 1 以下でした。直近は {operator}：{before} → {after}、増加 {gain}。回復の無効や演算遅延の原因を示す値ではありません。',
    orderCompleted: '注文完了',
    orderDelivered: '注文を納品',
    productSwitch: '生産品切替',
    productSwitchDrone: '生産品切替にドローンを使用',
    tradeDrone: '貿易を加速',
    manufactureDrone: '製造を加速',
    recycleCollected: '回収施設の生産物を回収'
  },
  present: 'あり',
  absent: 'なし',
  dailyOutput: '日平均生産量'
}
