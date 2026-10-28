export default {
  general: {
    appearanceWindow: '外観とウィンドウ',
    notificationsAssistant: '通知とアシスタント',
    profilesRuntime: 'プロファイルと実行',
    networkUpdates: 'ネットワークと更新',
    dataMaintenance: 'データと保守',
    light: 'ライト',
    dark: 'ダーク',
    followSystem: 'システム設定に従う',
    askEveryTime: '毎回確認',
    minimizeToTray: 'トレイに最小化',
    exitCompletely: '完全に終了',
    restoreLastState: '前回の状態を復元',
    normalWindow: '通常のウィンドウ',
    maximizedWindow: '最大化したウィンドウ',
    couldNotLoadWindowPreferences: 'ウィンドウ設定を読み込めませんでした',
    couldNotSaveTheCloseAction: '閉じる操作の設定を保存できませんでした',
    failedToSaveTheCloseAction: '閉じる操作の設定の保存に失敗しました',
    couldNotSaveTheStartupWindowState: '起動時のウィンドウ状態を保存できませんでした',
    failedToSaveTheStartupWindowState: '起動時のウィンドウ状態の保存に失敗しました',
    general: '一般',
    interfaceScale: '表示倍率',
    adjustTextAndControlSizesThenClick:
      '文字と操作部品の大きさを調整し、「適用」を押してください。',
    applyInterfaceScale: '表示倍率を適用',
    currentInterfaceScale: '現在の表示倍率',
    pendingInterfaceScale: '適用前の表示倍率',
    current: '現在',
    pending: '適用前',
    apply: '適用',
    theme: 'テーマ',
    window: 'ウィンドウ',
    hideMenuBarIcon: 'メニューバーのアイコンを隠す',
    useTrayIcon: 'トレイアイコンを使用',
    takesEffectAfterRestartingAStandaloneLaunch:
      '再起動後に有効になります。単独起動ではトレイプロセスを作成せず、ウィンドウを閉じた後も動作します。インスタンスマネージャーの共通トレイは、非表示での再起動後も利用できます。',
    takesEffectAfterRestartingInstancesLaunchedBy:
      '再起動後に有効になります。インスタンスマネージャーから起動したインスタンスは、共通のトレイを使います。',
    closeWindow: 'ウィンドウを閉じる操作',
    chooseWhatHappensWhenYouClickThe: '閉じるボタンを押したときの動作を選択します。',
    startupWindowState: '起動時のウィンドウ状態',
    appliesTheNextTimeTheMowerDesktop:
      '次回 Mower のデスクトップウィンドウを開くときに適用します。「前回の状態を復元」は、前回の通常表示または最大化状態を引き継ぎます。',
    screenshotsErrorArchives: 'スクリーンショットとエラー記録',
    screenshotRetention: 'スクリーンショットの保持期間',
    howLongOrdinaryScreenshotsAreKeptSet:
      '通常のスクリーンショットの保持期間です。0 にすると、エラーアーカイブ用の画像だけを保持します。',
    usingSharedSettingsChangeThemInThe:
      '共通設定を使用しています。インスタンスマネージャーで変更するか、このインスタンス独自の値を使ってください。',
    hours: '時間',
    errorArchiveSizeLimit: 'エラー記録の容量上限',
    olderErrorArchivesAreRemovedWhenThe:
      '上限に達すると古いエラーアーカイブを削除します。0 は合計容量を制限しません。各アーカイブは引き続き512 MiBまでで、上限到達後の画像やログは省略されます。',
    ordinaryScreenshotsAreNotWrittenToDisk:
      '通常のスクリーンショットはディスクへ保存しません。エラー記録が必要な場合は直前5分のキャッシュ画像と直後5分の画像を保存します。メモリーキャッシュは最大16枚、32 MiB です。',
    screenshotsAreWrittenToDiskAndRetained:
      'スクリーンショットをディスクに保存し、最低5分間保持します。',
    screenshotRetentionDetails: 'スクリーンショット保持の詳細',
    ordinaryScreenshotsAreKeptFor1Hour:
      '通常のスクリーンショットは既定で1時間保持します。小数の時間も指定できます。0より大きく5分未満の値は5分として扱います。',
    errorArchivesAreLimitedTo5Gib:
      'エラー記録の容量上限は既定で5 GiB です。通常のスクリーンショットは保持期間に従い、この容量制限の対象にはなりません。'
  },
  ai: {
    localModelOpenaiCompatible: 'ローカルモデル（OpenAI 互換）',
    onlineProviderRelayOpenaiCompatible: 'オンラインサービス・中継（OpenAI 互換）',
    aiAssistantModelService: 'AI アシスタントとモデルサービス',
    configureTheModelServiceUsedByThe:
      'AI アシスタントとエラー分析に使うモデルサービスを設定します。',
    changesSaveAutomatically: '変更は自動保存されます',
    modelService: 'モデルサービス',
    selectAPresetOrEnterAModel:
      'プリセットを選択するかモデル ID を入力して、DeepSeek 公式サービスを使用します。',
    connectToAnOpenaiCompatibleServiceOn:
      'このコンピューターまたはローカルネットワークの OpenAI 互換サービスに接続します。',
    useTheHttpsEndpointAndModelId:
      'プロバイダー指定の HTTPS エンドポイントとモデル ID を使用してください。',
    deepseekModel: 'DeepSeek モデル',
    selectAPresetOrEnterAModel2: 'プリセットを選択、またはモデル ID を入力して Enter',
    apiEndpoint: 'API エンドポイント',
    modelName: 'モデル名',
    enterTheModelIdSuppliedByYour: 'プロバイダー指定のモデル ID を入力',
    apiKey: 'API キー',
    usuallyOptionalForALocalService: '通常、ローカルサービスでは省略できます',
    enterYourApiKey: 'API キーを入力',
    visit: 'アクセス先：',
    deepseekSWebsite: 'DeepSeek 公式サイト',
    toObtainAnApiKey: '。API キーを取得できます。',
    aShortenedLogForTheSelectedError:
      '選択したエラーのログを短縮し、ここで設定したモデルサービスへ送信します。',
    localServicesMustSupportOpenaiChatCompletions:
      'ローカルサービスは OpenAI Chat Completions に対応している必要があります。オンラインサービスには HTTPS が必要です。'
  },
  email: {
    sending: '送信中…',
    sendingFailedCheckYourEmailSettingsAnd:
      '送信に失敗しました。メール設定を確認して再試行してください。',
    infoBaseTasksSanityFarmingRecruitmentSummaries:
      'INFO - 基地タスク、理性消費、公開求人の概要、基地レポート、イベントのチェックインなど。',
    warningOutdatedVersionLargeMoraleDifferencesWithin:
      'WARNING - 古いバージョン、同一グループ内の大きな体力差、オーダーの取り逃し、希少な公開求人タグなど。',
    errorSchedulingOrMasteryFailureMaaErrors:
      'ERROR - シフトや特化の失敗、MAA エラー、Skland チェックイン失敗、イベントのチェックインのタイムアウト、OF-1 失敗など。',
    qqMail: 'QQ メール',
    customEmail: 'その他のメール',
    emailNotifications: 'メール通知',
    enableEmailNotifications: 'メール通知を有効にする',
    receiveTaskSummariesAndErrorNotificationsBy: 'タスクの概要とエラー通知をメールで受け取ります。',
    sender: '送信元',
    emailProvider: 'メールサービス',
    smtpServer: 'SMTP サーバー',
    encryption: '暗号化方式',
    port: 'ポート',
    account: 'アカウント',
    password: 'パスワード',
    authorizationCode: '認証コード',
    howToGetAQqMailAuthorization: 'QQ メール認証コードの取得方法',
    getAQqMailAuthorizationCode: 'QQ メール認証コードを取得',
    notificationContent: '通知内容',
    notificationLevel: '通知レベル',
    subjectPrefix: '件名の接頭辞',
    distinguishEmailsFromDifferentMowerInstances:
      '異なる Mower インスタンスからのメールを区別します。',
    timeZoneOffset: 'タイムゾーンの補正',
    aboutTheEmailTimeZoneOffset: 'メールのタイムゾーン補正について',
    adjustTaskTimesForTheDifferenceBetween:
      '受信者とこのコンピューターの時差に合わせてタスク時刻を補正します。例えば、中国で米国の友人のために Mower を動かす場合、メール内のタスク時刻を受信者の現地時間へ変換します。',
    adjustTaskTimesInEmailsForThe: 'メール内のタスク時刻を受信者のタイムゾーンに合わせます。',
    recipients: '宛先',
    leaveBlankToSendEmailsToYourself: '空欄の場合は自分自身に送信します。',
    sendTestEmail: 'テストメールを送信',
    checkEmailSettings: 'メール設定を確認',
    sendATestEmailToCheckThat: 'テストメールを送信し、受信できることを確認します。'
  },
  software: {
    operationFailedPleaseTryAgain: '操作に失敗しました。再試行してください。',
    anUpdateIsInProgressWaitFor: '更新中です。完了するまでお待ちください。',
    softwareUpdates: 'ソフトウェア更新',
    currentVersion: '現在のバージョン',
    loading: '読み込み中…',
    sourceDeployment: 'ソースからの実行',
    standaloneRelease: '単独配布版',
    checkForUpdates: '更新を確認',
    downloadInstall: 'ダウンロードしてインストール',
    latestVersion: '最新バージョン',
    checkingTheLatestVersionInTheSelected: '選択したチャンネルの最新バージョンを確認中…',
    updateAvailable: '更新があります',
    matchesSelectedChannel: '選択したチャンネルと一致しています',
    checkForUpdatesToFindTheLatest:
      '更新を確認すると、選択したチャンネルの最新バージョンを取得します。',
    operationIncomplete: '操作が完了していません',
    thisInstallationNeedsAttention: 'このインストール環境の確認が必要です',
    downloaded: 'ダウンロード済み',
    theUpdateServiceIsHandingOverReconnecting:
      '更新サービスの引き継ぎ中です。まもなく再接続します。',
    openUpdateProgress: '更新の進捗を開く',
    cancelUpdate: '更新を中止',
    installationLog: 'インストールログ',
    log: 'ログ：',
    updateChannel: '更新チャンネル',
    automaticallyCheckForUpdates: '更新を自動確認',
    checkTheSelectedSoftwareChannelWhenMower:
      'Mower 起動時に選択したソフトウェアチャンネルを確認します',
    automaticallyUpdate: '自動更新',
    installADifferentVersionFromTheSelected:
      '選択したチャンネルの異なるバージョンをインストールし、全インスタンスを再起動します',
    restartSilentlyAfterUpdates: '更新後に非表示で再起動',
    keepRunningInTheBackgroundWithoutOpening:
      'ウィンドウを開かずにバックグラウンドで実行を続けます',
    openTheWindowNormallyAfterRestarting: '再起動後に通常どおりウィンドウを開く',
    softwareUpdatesRestartAllRunningInstancesIn:
      'ソフトウェア更新では、同じインストール先で動作中の全インスタンスを再起動します。実行中だったインスタンスは保存済みの体力、配置、貿易オーダー回収や特化交代などの重要タスク、未完了の補償処理を保持します。通常タスクは現在のバージョンとシフトから再生成します。停止中のインスタンスは起動しません。設定、特化計画、データベース記録は保持します。オンライン更新とローカルパッケージの両方に、上の再起動方法を適用します。',
    updateChannelsReleaseNotes: '更新チャンネルと更新履歴',
    viewReleases: 'リリースを表示',
    updateFromALocalPackage: 'ローカルパッケージから更新',
    clickOrDropAReleasePackageOr: 'Release パッケージまたは OTA 差分をクリックして選択・ドロップ',
    clickOrDropAReleasePackage: 'Release パッケージをクリックして選択・ドロップ',
    theOtaPatchMustStartFromThe:
      'OTA 差分は現在のバージョンに対応している必要があります。バージョンはパッケージ内から読み取るため、ファイル名は変更できます。',
    versionDetailsAreReadFromThePackage:
      'バージョンはパッケージ内から読み取るため、ファイル名は変更できます。',
    uploadingPackage: 'パッケージをアップロード中',
    readingPackageVersion: 'パッケージのバージョンを読み取り中',
    installRestart: 'インストールして再起動',
    ifMacosBlocksStartupAfterAnUpdate:
      '更新後に macOS が起動をブロックする場合は、「プライバシーとセキュリティ」でアプリを許可してください。',
    rollBackToAnEarlierVersion: '以前のバージョンに戻す',
    versionRollback: 'バージョンの復元',
    chooseFromTheThreeMostRecentCompatible:
      '同じチャンネルの現在より古い互換 Release から、直近3件を選択できます。確認後に実行します。',
    findRollbackVersions: '復元可能なバージョンを検索',
    selectAnEarlierVersion: '以前のバージョンを選択',
    rollbackTargetVersion: '復元先のバージョン',
    rollBackInstall: '以前のバージョンをインストール',
    forceUpdate: '強制更新',
    aForcedUpdateOverwritesLocalSourceChanges:
      '強制更新はローカルのソース変更を上書きします。先に更新を確認し、対象バージョンを確認してください。',
    stable: '安定版',
    beta: 'ベータ版',
    dev: '開発版',
    stableHelp:
      'GitHub で Latest とされた安定 Release を使用します。日常利用向けで、変更は少なめです。',
    betaHelp:
      'ベータ版と新しい安定版を受け取り、修正や機能を早めに試せます。動作が不安定な場合があります。',
    devHelp:
      '配布版は Windows x64 Nightly と新しいベータ・安定版を取得します。ソース実行は選択した Git ブランチに従います。開発版は不安定な場合があります。'
  },
  maa: {
    enterTheComplete24CharacterMirrorchyanCdk: 'MirrorChyan CDK を24文字すべて入力してください',
    checkingMirrorchyanCdk: 'MirrorChyan CDK を確認中…',
    mirrorchyanCdkStatusUnknown: 'MirrorChyan CDK の状態が不明です',
    mirrorchyanCdkCheckFailed: 'MirrorChyan CDK の確認に失敗しました：{value0}',
    waitingForMirrorchyanCdkValidation: 'MirrorChyan CDK の検証を待機中',
    update: '更新',
    download: 'ダウンロード',
    beta: 'ベータ版',
    stable: '安定版',
    mirrorchyanCdkExpiresInDays: 'MirrorChyan CDK の残り有効期間：{value0} 日（{value1}）',
    failedToReadMaaProgress: 'MAA の{value0}進捗を取得できませんでした：{value1}',
    failedToReadMaaVersion: 'MAA の{value0}バージョンを取得できませんでした',
    failedToReadMaaVersion2: 'MAA の{value0}バージョンを取得できませんでした：{value1}',
    failedToReadMaaResourceUpdateProgress: 'MAA リソース更新の進捗を取得できませんでした：{value0}',
    failedToReadTheMaaResourceVersion: 'MAA リソースのバージョンを取得できませんでした',
    failedToReadTheMaaResourceVersion2: 'MAA リソースのバージョンを取得できませんでした：{value0}',
    setTheMaaDirectoryFirst: '先に MAA のディレクトリを設定してください',
    checkYourMirrorchyanCdk: 'MirrorChyan CDK を確認してください',
    checkingForMaaUpdates: 'MAA の更新を確認中…',
    maaUpdateCheckFailed: 'MAA の更新確認に失敗しました',
    maaIsUpToDate: 'MAA は最新です',
    aNewMaaVersionIsAvailable: 'MAA の新しいバージョンがあります',
    maaUpdateCheckFailed2: 'MAA の更新確認に失敗しました：{value0}',
    checkingForMaaResourceUpdates: 'MAA リソースの更新を確認中…',
    maaResourceUpdateCheckFailed: 'MAA リソースの更新確認に失敗しました',
    maaResourcesAreUpToDate: 'MAA リソースは最新です',
    newMaaResourcesAreAvailable: '新しい MAA リソースがあります',
    maaResourceUpdateCheckFailed2: 'MAA リソースの更新確認に失敗しました：{value0}',
    preparingUpdate: '更新を準備中',
    failedToStartMaa: 'MAA の{value0}を開始できませんでした',
    failedToStartMaa2: 'MAA の{value0}を開始できませんでした：{value1}',
    failedToStartTheMaaResourceUpdate: 'MAA リソースの更新を開始できませんでした',
    failedToStartTheMaaResourceUpdate2: 'MAA リソースの更新を開始できませんでした：{value0}',
    maaUpdates: 'MAA 更新',
    updateMaa: 'MAA を更新',
    downloadMaa: 'MAA をダウンロード',
    notChecked: '未確認',
    installed: 'インストール済み：',
    unknownManuallyInstalled: '不明・手動インストール',
    automaticallyCheckForUpdates: '更新を自動確認',
    checkForMaaCoreUpdatesWhenThis:
      'このページを開いたとき、または本体の設定を変更したときに MAA 本体の更新を確認します。',
    automaticallyUpdateMaaCore: 'MAA 本体を自動更新',
    tryUpdatingWhenANewVersionIs:
      '新しいバージョンが見つかると更新を試みます。MAA 使用中は手動更新の案内を保持します。',
    updateSource: '更新元',
    downloadSource: 'ダウンロード元',
    mirrorchyan: 'MirrorChyan',
    mirrorchyanCdk: 'MirrorChyan CDK',
    theCdkIsSavedInTheMower: 'CDK は Mower の設定ファイルに保存します。',
    getACdk: 'CDK を取得',
    windowsArm64HasNoOtaPackageAs:
      'Windows ARM64 には OTA パッケージがありません。Linux と同様に完全版をダウンロードし、ユーザーデータを保持して安全に置き換えます。',
    useTheOfficialMaaAndroidArm64Component:
      '公式 MAA Android ARM64 コンポーネントを使用します。Python API はアプリが管理します。更新後はスマートフォンのサービスを停止し、再起動してください。',
    windowsArm64HasNoOtaPackageGithub:
      'Windows ARM64 には OTA パッケージがありません。GitHub 更新では Linux と同様に完全版を取得し、ユーザーデータを保持して安全に置き換えます。',
    useTheOfficialMaaAndroidArm64Component2:
      '公式 MAA Android ARM64 コンポーネントを使用します。MirrorChyan はまだ利用できません。Python API はアプリが管理します。更新後はスマートフォンのサービスを停止し、再起動してください。',
    checkForMaaUpdates: 'MAA の更新を確認',
    updateMaaResources: 'MAA リソースを更新',
    currentResources: '現在のリソース：',
    unknown: '不明',
    latestResources: '最新のリソース：',
    latestEventResources: '最新のイベントリソース：',
    automaticallyCheckResources: 'リソースを自動確認',
    checkForMaaResourceUpdatesWhenThis:
      'このページを開いたとき、またはリソース設定を変更したときに MAA リソースの更新を確認します。',
    automaticallyUpdateResources: 'リソースを自動更新',
    tryUpdatingWhenNewResourcesAreFound:
      '新しいリソースが見つかると更新を試みます。MAA 本体の更新には上の設定を使います。',
    resourceUpdateSource: 'リソース更新元',
    onAndroidOcrModelsArePreparedAutomatically:
      'Android では OCR モデルを自動で準備します。完了後、スマートフォンのサービスを停止して再起動してください。',
    checkForMaaResourceUpdates: 'MAA リソースの更新を確認',
    latestPackage: '{operation}可能な{channel}パッケージ：{version}',
    mirrorWindowsOta:
      '現在のバージョンを MirrorChyan に送信し、Windows {arch} の OTA 差分を優先します。完全版しかない場合は、そちらを使用します。',
    mirrorWindowsInstall:
      'MAA が見つかりません。{channel}の Windows {arch} 完全版をダウンロードし、設定したディレクトリへインストールします。',
    mirrorLinuxPackage:
      'MaaCore、resource、Python を含む{channel}の Linux {arch} 完全版で{operation}します。',
    mirrorMacPackage:
      '{channel}の macOS GUI パッケージで{operation}します。DMG から実行部分と resource を展開し、同じバージョンの Windows arm64 パッケージから Python フォルダーを取り出します。',
    githubWindowsOta:
      'GitHub 更新では現在のバージョンと完全に一致する Windows {arch} OTA 差分を優先し、なければ完全版を使用します。',
    githubWindowsInstall:
      'MAA が見つかりません。GitHub から{channel}の Windows {arch} 完全版をダウンロードし、設定したディレクトリへインストールします。',
    githubLinuxPackage:
      'GitHub の{channel}の Linux {arch} 完全版 tar.gz で{operation}します。MaaCore、resource、Python を含みます。',
    githubMacPackage:
      'GitHub の{channel}の macOS universal 実行パッケージで{operation}します。必要な場合のみ、同じバージョンの Windows arm64 パッケージから Python フォルダーを取得します。',
    newInstallationBackup:
      '既存の環境をその場で更新せず、新しい MAA 環境をダウンロードします。対象ディレクトリに内容がある場合は {path} へ保存します。',
    installationBackup:
      '更新成功後、元のディレクトリを {path} に保持します。次回の更新成功時にこのバックアップを置き換え、失敗時は保持します。cache と config を新しいディレクトリへコピーして引き続き使用します。',
    resourceSourceDetails:
      'MAA リソースは安定版・ベータ版で同じバージョンを使い、{source}から更新します。resource ディレクトリへ差分を統合し、MaaCore と Python は置き換えません。',
    resourceBackup:
      '更新前のリソースを {path} に保持します。次回の更新成功時に置き換え、更新失敗時は復元します。',
    operationChannel: '{operation}チャンネル'
  },
  components: {
    restoreTheBundledVersion: '同梱バージョンに戻しますか？',
    updateTheCompatibilityApi: '互換 API を更新しますか？',
    confirm: '確定',
    cancel: 'キャンセル',
    currentVersion: '現在のバージョン：',
    updateAvailable: '更新があります：',
    theNewApiRequiresAnApkUpdate: '新しい API を使うには APK の更新が必要です',
    theCompatibilityApiHasNotChangedNo: '互換 API は変更されていないため、更新は不要です',
    automaticallyCheckTheCompatibilityApiEvery6:
      'サービス実行中、6時間ごとに互換 API の更新を自動確認',
    checkForApiUpdates: 'API の更新を確認',
    hotUpdateApi: 'API をホット更新',
    restoreBundledVersion: '同梱バージョンに戻す'
  },
  source: {
    sourceVersionManagement: 'ソースバージョン管理',
    selectOneOfThe20MostRecent: '直近20件のコミットから選択、または SHA・タグを入力',
    checkedOut: 'チェックアウト済み：',
    detachedHead: 'Detached HEAD',
    remoteRepository: 'リモートリポジトリ',
    chooseASavedRepositoryOrEnterA: '保存済みリポジトリを選択、または GitHub URL を入力して Enter',
    sourceRemoteRepository: 'ソースのリモートリポジトリ',
    useAPublicGithubUrlOrOwner:
      '公開 GitHub URL または owner/repo を使用してください。この選択はこのコンピューターにのみ保存します。',
    selectionMode: '選択方法',
    branchCommit: 'ブランチ・コミット',
    openPr: '未マージの PR',
    remoteBranch: 'リモートブランチ',
    sourceRemoteBranch: 'ソースのリモートブランチ',
    targetVersion: '対象バージョン',
    chooseACommitOrEnterASha: 'コミットを選択、または SHA を入力して Enter',
    sourceTargetVersion: 'ソースの対象バージョン',
    selectAPrWithNoMergeConflicts: 'マージの競合がない PR を選択',
    openSourcePr: 'ソースの未マージ PR',
    afterTheCheckSucceedsInstallationMergesThe:
      '確認成功後、選択した PR を対象ブランチの最新状態へマージし、成功した場合のみ再起動します。その後の更新確認は元のリポジトリ、ブランチ、チャンネルに従います。',
    rememberTheSelectedRepositoryAndBranchWhen:
      '切り替え要求時に選択したリポジトリとブランチを記録し、以後の開発版の更新確認に使用します。',
    overwriteLocalSourceChangesWithoutABackup: 'バックアップせずにローカルのソース変更を上書き',
    refreshLists: '一覧を更新',
    checkVersion: 'バージョンを確認',
    switchRestart: '切り替えて再起動',
    basedOn: '基準：',
    targetRepository: '対象リポジトリ：',
    selectedPrCommitMergedDuringInstallation: '選択した PR のコミット（インストール時にマージ）：',
    submittingAVersionSwitchDisablesAutomaticSoftware:
      'バージョン切り替えを要求するとソフトウェア自動更新を無効にします。設定とデータベースはコードとともに巻き戻さないため、古いバージョンとの互換性は選択したコミットによります。'
  },
  resource: {
    failedToApplyTheUpdatePackage: '更新パッケージを適用できませんでした',
    applyingUpdatePackage: '更新パッケージを適用中…',
    resourceUpdates: 'リソース更新',
    currentVersion: '現在のバージョン',
    notInstalled: '未インストール',
    checkForUpdates: '更新を確認',
    downloadInstall: 'ダウンロードしてインストール',
    latestVersion: '最新バージョン',
    checkingTheLatestResourceVersion: '最新のリソースバージョンを確認中…',
    updateAvailable: '更新があります',
    upToDate: '最新です',
    checkForUpdatesToFindTheLatest: '更新を確認すると、最新のリソースパッケージを取得します。',
    resourceCheckIncomplete: 'リソースの確認が完了していません',
    downloaded: 'ダウンロード済み',
    automaticallyCheckForUpdates: '更新を自動確認',
    checkForResourcePackagesWhenMowerOpens: 'Mower 起動時にリソースパッケージを確認します',
    automaticallyUpdate: '自動更新',
    installNewResourcePackagesAutomatically: '新しいリソースパッケージを自動でインストールします',
    preferAnOtaPatchAndFallBack:
      'OTA 差分を優先し、利用できなければ完全版を使います。同じ Mower インストール環境の全インスタンスでリソースを共有し、待機中に読み込みます。Mower の再起動は不要です。',
    updateFromALocalResourcePackage: 'ローカルのリソースパッケージから更新',
    clickOrDropAResourceUpdatePackage: 'リソース更新パッケージをクリックして選択・ドロップ',
    acceptsFullResourcePackagesAndOtaPatches:
      '完全版と現在のバージョン向け OTA 差分に対応しています。ネットワークが不安定な場合の手動更新に使えます。'
  },
  network: {
    operationFailedPleaseTryAgain: '操作に失敗しました。再試行してください。',
    anotherInstanceChangedTheProxySettingsReload:
      '別のインスタンスがプロキシ設定を変更しました。再読み込みしてからテストしてください。',
    copied: 'コピーしました',
    copyFailedSelectTheTextManually: 'コピーできませんでした。テキストを手動で選択してください。',
    networkDownloadProxies: 'ネットワークとダウンロードのプロキシ',
    sharedByAllInstancesAppliesToSubsequent: '全インスタンスで共有し、以後の接続に適用します。',
    loading: '読み込み中…',
    saving: '保存中…',
    waitingToSave: '保存待ち…',
    appliedToSubsequentConnections: '以後の接続に適用済み',
    changesSaveAutomatically: '変更は自動保存されます',
    globalNetworkProxy: '全体のネットワークプロキシ',
    forExampleSocks5h127001: '例：socks5h://127.0.0.1:7897',
    usedForNetworkConnectionsSupportsHttpS:
      'ネットワーク接続に使用します。HTTP(S) と SOCKS5 に対応しています。空欄では起動環境の設定を使います。',
    githubDownloadProxy: 'GitHub ダウンロードプロキシ',
    leaveBlankToChooseADownloadMethod: '空欄ではダウンロード方法を自動選択',
    usedForMowerAndMaaDownloadsFrom:
      'Mower と MAA の GitHub ファイルのダウンロードに使用します。空欄の場合は直接接続し、失敗すると ghfast.top、gh-proxy.com、gh-proxy.org、edgeone.gh-proxy.org の順に試します。指定した場合はそのサイトだけを使用します。',
    proxyConfigurationHelp: 'プロキシ設定の説明',
    supportsHttpHttpsSocks5AndSocks5hSocks:
      'http://、https://、socks5://、socks5h:// に対応しています。SOCKS にはポートが必要です。GitHub API、Git、Git LFS にもこの設定を適用します。',
    usedForInstallationPackagesResourcePackagesAnd:
      'インストールパッケージ、リソースパッケージ、生ファイルに使用します。https://ghfast.top/ などのプロキシサイトのアドレスのみ入力してください。元の URL を後ろにつなぎます。サイトを設定した場合はそちらを優先します。',
    testConnection: '接続をテスト',
    connectionTest: '接続テスト',
    testTheGithubDownloadRoutesUsingThe: '現在の設定で GitHub のダウンロード経路をテストします。',
    reload: '再読み込み',
    copyResults: '結果をコピー',
    testingGithubDownloadRoutes: 'GitHub のダウンロード経路をテスト中…',
    connectionTestResults: '接続テスト結果',
    connected: '接続済み',
    connectionFailed: '接続に失敗しました'
  },
  backup: {
    operationFailedPleaseTryAgain: '操作に失敗しました。再試行してください。',
    theBackupFileMustNotExceed16: 'バックアップファイルは16 MB 以下にしてください',
    chooseAZipBackupContainingAConfig: 'config フォルダーを含む ZIP バックアップを選択してください',
    configurationRestoredButAutomaticReloadFailedRetry:
      '設定を復元しましたが、自動再読み込みに失敗しました。ページの再読み込みを再試行してください：{value0}',
    fullBackupRestore: '完全バックアップと復元',
    backupsIncludeAccountsPasswordsAndKeysKeep:
      'バックアップにはアカウント、パスワード、キーが含まれます。安全に保管してください。',
    exportFullBackup: '完全バックアップをエクスポート',
    packageThisInstanceSSettingsSchedulingPlans:
      'このインスタンスの設定、シフト、ローカルデータを ZIP にまとめます。',
    restoreCurrentConfiguration: '現在の設定を復元',
    overwriteTheCurrentProfileSConfigurationAnd:
      '新しいプロファイルを作らずに、ZIP バックアップから現在のプロファイルの設定と対応データを上書きします。既存データは先にバックアップします。',
    selectAFullConfigurationBackup: '完全な設定バックアップを選択',
    backupContentsRestoreDetails: 'バックアップ内容と復元の詳細',
    backupContents: 'バックアップ内容',
    containsThisInstanceSConfigFilesAnd:
      'このインスタンスの config ファイル、tmp のデータテーブル、在庫、記録を含み、state.json は除外します。plan.json には主シフトとすべての予備シフトが含まれます。データベースには特化計画と履歴があります。リソースパック、更新ファイル、他のインスタンス、ブラウザー設定は含みません。',
    preservedDuringRestore: '復元時に保持する設定',
    keepTheCurrentManagementPagePortAccess:
      '現在の管理ページのポート、アクセストークン、ネットワークプロキシ、再起動が必要なトレイとウィンドウサイズの設定を保持します。その他の設定とデータはバックアップから復元します。バックアップにないデータファイルは変更しません。',
    afterRestoration: '復元後の動作',
    backUpTheCurrentSettingsAndTmp:
      '先に現在の設定と tmp データをバックアップし、スケジュール状態キャッシュを消去します。成功すると Mower を再起動せずにページを自動再読み込みします。この再読み込みではタスクを自動起動しません。',
    theRestoreResultIsNotConfirmedConfiguration:
      '復元結果を確認できていません。設定の自動保存は停止中です。編集を続ける前にページを再読み込みしてください。',
    reloadPage: 'ページを再読み込み',
    currentConfigurationRestored: '現在の設定を復元しました',
    backupFromBeforeRestoration: '復元前のバックアップ：',
    retryPageReload: 'ページの再読み込みを再試行',
    confirmRestore: '復元を確定',
    cancel: 'キャンセル',
    use: '使用するバックアップ：「',
    toRestoreSettingsAndTheBackedUp:
      '」。設定とバックアップ内の tmp データテーブル、在庫、記録を復元し、対応するローカルデータを置き換えます。含まれないデータファイルは変更しません。現在の管理ポート、アクセストークン、ネットワークプロキシを保持します。先に Mower を停止してください。復元前にバックアップします。トレイとウィンドウサイズの設定は保持します。成功後、Mower を再起動せず現在のプロファイルを再読み込みし、タスクは自動起動しません。'
  },
  profiles: {
    notLoaded: '未読み込み',
    importExportProfiles: 'プロファイルのインポートとエクスポート',
    currentProfile: '現在のプロファイル：',
    whenImportingChooseWhichPartsOfThe:
      'インポート時に現在のプロファイルから引き継ぐ内容を選びます。それ以外を ZIP から取り込み、新しいプロファイルを作成して有効にします。エクスポートには現在の設定、シフト、ローカルデータを含みます。',
    profileManagementHasNotLoadedReloadThe:
      'プロファイル管理を読み込めていません。ページを再読み込みして再試行してください。',
    importProfile: 'プロファイルをインポート',
    exportCurrentProfile: '現在のプロファイルをエクスポート'
  },
  process: {
    processOperationFailed: 'プロセス操作に失敗しました',
    theOperationTimedOutCheckThisInstance:
      '操作がタイムアウトしました。このインスタンスとプロセス操作ログを確認してください。',
    thisInstanceHasDisconnectedYouCanClose:
      'このインスタンスとの接続が終了しました。ページを閉じることができます。',
    thisInstanceIsRestartingWaitingToReconnect:
      'このインスタンスは再起動中です。再接続を待っています…',
    restarting: '再起動中…',
    reloadPage: 'ページを再読み込み',
    processControls: 'プロセス操作',
    onlyThisInstance: '対象はこのインスタンスのみです：',
    isAffectedOtherInstancesAndTheInstance:
      '。他のインスタンスとインスタンスマネージャーには影響しません。',
    restartResume: '再起動して続行',
    saveTheCurrentConfigurationRestartThisInstance:
      '現在の設定を保存してこのインスタンスを再起動し、既存のタスクキューを続行します。',
    restartMowerProcess: 'Mower プロセスを再起動',
    keepTheInstanceNameDataDirectoryPort:
      'インスタンス名、データディレクトリ、ポート、起動引数を保持します。実行中だったタスクは実行キャッシュをリセットして再開します。',
    restartThisInstanceKeepingItsNameData:
      'このインスタンスを再起動し、名前、データディレクトリ、ポート、起動引数を保持します。実行中だったタスクは実行キャッシュをリセットして再開します。',
    stopMowerProcess: 'Mower プロセスを停止',
    stopTheCurrentTaskNormallyAndExit:
      '現在のタスクを正常に停止して、このインスタンスを終了します。Web 接続も終了します。',
    noTaskIsRunningSoRestartAnd: '実行中のタスクがないため、再起動して続行する必要はありません。',
    configurationAutosaveIsPausedAfterTheImport:
      '設定の自動保存は停止中です。インポートまたはプロセス操作の終了後、ページを再読み込みして設定を確認してから編集してください。',
    operationInProgress:
      '設定のインポートまたはプロセス操作が進行中です。完了するまでお待ちください。',
    statusQueryFailed: 'プロセスの状態を取得できませんでした',
    operationRejected: 'プロセス操作が拒否されました'
  },
  version: {
    versionNumber: 'バージョン番号',
    versionType: 'バージョン種別',
    chinese: '中国語',
    softwareVersionDisplay: 'ソフトウェアバージョン表示',
    softwareVersionDisplayPreview: 'ソフトウェアバージョン表示のプレビュー',
    preview: 'プレビュー',
    versionTypeLanguage: 'バージョン種別の言語',
    saving: '保存中…',
    retry: '再試行'
  },
  watermark: {
    whenReportingAProblemAfterHidingThe:
      '透かしを非表示にした後に問題を報告する場合は、ヘルプ → このアプリについて、で完全なバージョン番号を確認して記載してください。',
    versionWatermark: 'バージョンの透かし',
    showVersionWatermark: 'バージョンの透かしを表示',
    shown: '表示中',
    hidden: '非表示',
    retry: '再試行',
    hideVersionWatermark: 'バージョンの透かしを非表示（{value0}/{value1}）',
    typeTheFollowingChinesePhraseExactly: '次の中国語の確認文をそのまま入力してください：',
    confirmHide: '非表示を確定',
    continue: '続行',
    keepWatermark: '透かしを表示したままにする'
  },
  background: {
    logBackgroundImage: 'ログの背景画像',
    appliesImmediatelySupportsPngJpegAndWebp:
      'すぐに適用します。PNG、JPEG、WebP に対応し、最大8 MiB・2400万画素までです。',
    customLogBackgroundPreview: 'カスタムログ背景のプレビュー',
    defaultLogBackgroundPreview: '既定ログ背景のプレビュー',
    chooseALogBackgroundImage: 'ログの背景画像を選択',
    chooseImage: '画像を選択',
    restoreDefault: '既定の画像に戻す',
    processing: '処理中…',
    usingCustomImage: 'カスタム画像を使用中',
    usingDefaultImage: '既定の画像を使用中',
    retry: '再試行'
  },
  history: {
    depotHistory: '倉庫の履歴',
    historyEntriesToRead: '読み込む履歴件数',
    theMaximumScanRecordsReadForDepot:
      '倉庫の推移、期間内の変化、スナップショット比較で読み込むスキャン記録の上限です。ローカルの保持件数は変更しません。',
    historyEntriesToKeep: '保持する履歴件数',
    theMaximumScanRecordsKeptLocallyDelete:
      'ローカルに保持するスキャン記録の上限です。超過すると古いものから削除します。0は全件保持です。上限を減らすと次回の倉庫スキャンで適用します。',
    readUpTo3000RecordsBy:
      '既定では最大3000件を読み込みます。3時間ごとにスキャンした場合、約1年分です。件数を増やすと倉庫ページの読み込みが遅くなります。保持件数の既定値は0です。'
  },
  dialog: {
    settings: '設定',
    settingsContent: '設定内容'
  },
  sidebar: {
    settingsNavigation: '設定ナビゲーション',
    back: '戻る',
    search: '{value0}を検索',
    settings: '設定',
    noMatchingSettings: '一致する設定はありません'
  },
  gui: {
    interfaceLanguage: '表示言語',
    interfaceLanguageDescription: 'Mowerの表示言語をすぐに切り替え、このインスタンスに保存します。',
    versionLoadFailed:
      'ソフトウェアバージョンの表示設定を読み込めませんでした。再試行してください。',
    layoutLoadFailed: '設定レイアウトを読み込めませんでした。再試行してください。',
    watermarkLoadFailed: 'バージョンの透かし設定を読み込めませんでした。再試行してください。',
    versionSaveFailed:
      'ソフトウェアバージョンの表示設定を保存できませんでした。元の表示に戻しました。再試行してください。',
    versionLanguageSaveFailed:
      'バージョン種別の言語を保存できませんでした。元の表示に戻しました。再試行してください。',
    layoutSaveFailed:
      '設定レイアウトを保存できませんでした。元のレイアウトに戻しました。再試行してください。',
    watermarkSaveFailed:
      'バージョンの透かし設定を保存できませんでした。元の表示に戻しました。再試行してください。'
  },
  logBackground: {
    invalidResponse: '背景画像の応答が不正です',
    loadFailed: 'ログの背景画像を読み込めませんでした。再試行してください。',
    chooseImage: 'PNG、JPEG、WebP の画像を選択してください。',
    tooLarge: '画像は8 MiB 以下にしてください。',
    saveFailed: 'ログの背景画像を保存できませんでした。再試行してください。',
    resetFailed: '既定のログ背景へ戻せませんでした。再試行してください。'
  },
  manualUpdate: {
    onePackage: '更新パッケージは1つずつドロップしてください',
    emptyPackage: '更新パッケージが空です。完全なファイルを選択してください。',
    packageTooLarge: '更新パッケージが2 GiB の上限を超えています',
    tooManyEntries: '更新パッケージのファイル数が多すぎます',
    unreadablePackage:
      'パッケージ内のディレクトリを読み取れませんでした。完全な Mower インストールパッケージを選択してください。',
    mixedPackage: 'ソフトウェア更新とリソース更新が混在しています。別々にアップロードしてください。'
  },
  sourceVersions: {
    operationFailed: '操作に失敗しました。再試行してください。'
  },
  softwareUpdate: {
    checkFailed: 'ソフトウェアの更新確認が完了しませんでした',
    confirmRollback: '以前のバージョンに戻しますか？',
    confirmInstall: 'インストールして再起動しますか？',
    repository: 'リポジトリ {repository} を使用します。',
    rollbackWarning:
      '{currentVersion} から {version} に戻します。古いバージョンは現在の設定や実行キャッシュと互換性がない場合があります。',
    installVersion: '{version} をインストールします。',
    restartDetails:
      '同じインストール先の {count} インスタンスを再起動します。実行中だったインスタンスは保存済みの体力、配置、貿易オーダー回収や特化交代などの重要タスク、未完了の補償処理を保持します。通常タスクは現在のバージョンとシフトから再生成します。停止中のインスタンスは起動しません。設定、特化計画、データベース記録は保持します。インストール失敗時は元のバージョンへの復元を試みます。',
    discardChanges:
      'バックアップせずにローカルのソース変更を上書きします。インストールに失敗してもローカル変更は復元しません。',
    rollback: '復元を確定',
    install: 'インストールを確定',
    cancel: 'キャンセル',
    confirmForce: '強制更新しますか？',
    forceDetails:
      '{version} へ強制的に切り替え、バックアップせずローカルのソース変更を上書きし、同じインストール先の {count} インスタンスを再起動します。実行中だったインスタンスは保存済みの体力、配置、貿易オーダー回収や特化交代などの重要タスク、未完了の補償処理を保持します。通常タスクは現在のバージョンとシフトから再生成します。停止中のインスタンスは起動しません。インストールに失敗してもローカル変更は復元しません。',
    force: '強制更新を確定',
    confirmForceSource: 'ソースバージョンを強制的に切り替えますか？',
    confirmSource: 'ソースバージョンを切り替えますか？',
    sourceRepository: 'リポジトリ {repository}{pull} を使用します。',
    pullSuffix: '（PR {number}）',
    mergeBase: '選択した PR を対象ブランチ {branch} の {commit} にマージします。',
    pullCommit: 'PR のコミットは {commit} です。マージ成功後にのみインストールします',
    switchCommit: 'コミット {commit} に切り替えます',
    sourceDetails:
      '。同じインストール先の {count} インスタンスを再起動し、ソフトウェア自動更新を無効にします。実行中だったインスタンスは保存済みの体力、配置、貿易オーダー回収や特化交代などの重要タスク、未完了の補償処理を保持します。通常タスクは現在のバージョンとシフトから再生成します。停止中のインスタンスは起動しません。設定、特化計画、データベース記録は保持します。古いバージョンは現在の設定や実行キャッシュと互換性がない場合があります。',
    restoreVersion: 'インストールに失敗した場合は元のバージョンへの復元を試みます。',
    forceSwitch: '強制切り替えを確定',
    switch: '切り替えを確定'
  },
  badge: {
    sourceStartup: 'ソースから起動',
    version: 'ソフトウェアバージョン {version}{kind}',
    checking: 'ソフトウェアの更新を確認中…',
    check: 'クリックしてソフトウェアの更新を確認'
  },
  profileDialog: {
    create: 'プロファイルを作成',
    copy: '現在のプロファイルを複製',
    rename: 'プロファイル名を変更',
    import: 'プロファイルをインポート',
    activate: 'プロファイルを切り替え',
    profile: 'プロファイル',
    createAndSwitch: '作成して切り替え',
    copyAndSwitch: '複製して切り替え',
    saveName: '名前を保存',
    importAndSwitch: 'インポートして切り替え',
    unavailable: 'プロファイル管理を利用できません',
    reloadPage: 'ページを再読み込み',
    name: 'プロファイル名',
    exampleNames: '例：メインアカウント、サブアカウント',
    selectBackup: 'ZIP バックアップを選択',
    noFile: 'ファイル未選択',
    selectProfileBackup: 'プロファイルの ZIP バックアップを選択',
    switchPrefix: '切り替え先：「',
    switchSuffix:
      '」。選択した項目は現在のプロファイルの内容を引き継ぎ、切り替え先へ書き込みます。未選択の項目は切り替え先の内容を使います。',
    importDetails:
      'ZIP バックアップをインポートすると新しいプロファイルを作成します。選択した項目は現在のプロファイルから、それ以外は ZIP から引き継ぎます。',
    inheritDetails:
      '現在のプロファイルから引き継ぐ項目を選択してください。未選択の項目は既定値になります。',
    pendingDrafts:
      '操作前に適用済みの変更を保存します。未適用のデバイス識別情報とダイアログ内の下書きは再読み込み時に破棄します。プロファイルの切り替えでタスクを自動起動することはありません。',
    cancel: 'キャンセル',
    reloadNeeded: 'プロファイルの再読み込みが必要です',
    switchedPaused:
      'プロファイルが変更されました。古いページの自動保存は停止中です。編集を続ける前に再読み込みしてください。',
    currentProfile: '現在のプロファイル：',
    checkCurrent: '現在のプロファイルを確認',
    reload: '再読み込み',
    failed: 'プロファイル操作に失敗しました。再試行してください。',
    other: 'その他',
    changed: '現在のプロファイルが変更されました。続行する前に再読み込みしてください。',
    invalidList: 'プロファイル一覧の形式が不正です',
    changedElsewhere:
      '別のページで現在のプロファイルが切り替えられました。続行する前に再読み込みしてください。',
    tooLarge: 'バックアップファイルは16 MB 以下にしてください',
    missingConfig: 'config フォルダーを含む ZIP バックアップを選択してください',
    reloaded: 'プロファイルを再読み込みしました。',
    retry: '再試行してください',
    enterName: 'プロファイル名を入力してください',
    chooseProfileBackup: 'プロファイルの ZIP バックアップを選択してください',
    stopFirst: '先にタスクを停止し、デバイス操作や更新の完了を待ってください',
    incomplete: 'プロファイル操作が完了しませんでした',
    switchedReload: 'プロファイルが変更されました。編集を続ける前に再読み込みしてください。',
    uncertain:
      '。操作結果を確認できていません。自動保存は停止中です。現在のプロファイルを確認するか、再読み込みしてください。',
    copyName: '{value0} のコピー',
    reloadFailed: 'ページを再読み込みできませんでした：{value0}'
  },
  profileCatalog: {
    sectionConnection: '接続と実行',
    sectionTasks: 'タスク設定',
    sectionPlans: 'シフト',
    sectionMower: 'Mower 設定',
    sectionData: 'データ',
    sectionHistory: '履歴',
    deviceLabel: 'デバイスとゲームの接続',
    deviceDescription:
      'デバイスの識別情報、パス、キャプチャ・タッチ方式、ゲーム、起動パラメーターをまとめます',
    runtimeLabel: '実行設定',
    runtimeDescription: '性能、キャプチャ、待機時間、自動起動、待機中の動作',
    baseLabel: '基地シフト',
    baseDescription: 'シフト交代、体力、フィアメッタ、基地のスケジュール規則',
    runorderLabel: '貿易オーダー回収',
    runorderDescription: '貿易オーダーの回収間隔とオペレーター交代方針',
    droneLabel: 'ドローン加速',
    droneDescription: 'ドローン使用施設、間隔、確保するドローン数',
    clueLabel: '手がかり',
    clueDescription: '手がかりの譲渡と交流の規則',
    trustLabel: '信頼度ローテーション',
    trustDescription: '信頼度ローテーションの有効化、間隔、対象の絞り込み',
    dailyLabel: '日常タスク',
    dailyDescription: '日常タスクの有効化と実行間隔',
    recruitLabel: '公開求人',
    recruitDescription: '公開求人のレア度、ロボット、求人票の確保数',
    creditLabel: '戦友訪問と FP',
    creditDescription: '戦友訪問、FP 受取、購買部での FP 交換規則',
    weekly_planLabel: '理性消費と週間計画',
    weekly_planDescription:
      'ステージ、理性回復剤、在庫に基づくステージ選択、すべての週間計画と選択中の計画',
    maaLabel: 'MAA 本体',
    maaDescription: 'MAA のインストール先、更新、リソース、操作方式',
    longLabel: '長時間タスク',
    longDescription: '統合戦略、生息演算などの長時間タスク設定',
    workshopLabel: '加工と特化の設定',
    workshopDescription: '加工担当、素材保護、自動加工と手動加工の設定',
    normal_planLabel: '通常シフト',
    normal_planDescription: '通常の主シフト・予備シフト、施設、スケジュール規則',
    rescue_planLabel: '緊急シフト',
    rescue_planDescription: '自動緊急対応の有効化と緊急時の主シフト・予備シフト',
    accountsLabel: 'Skland アカウントと同期',
    accountsDescription: 'Skland アカウントと一图流への同期設定',
    notificationsLabel: 'メール通知',
    notificationsDescription: '送信元アカウント、宛先、メールサービス、通知規則',
    assistantLabel: 'AI モデルサービス',
    assistantDescription: 'AI サービスのエンドポイント、モデル、キー',
    appearanceLabel: '外観とウィンドウ',
    appearanceDescription:
      'テーマとウィンドウの設定。このコンピューターの接続ポート、トークン、トレイ設定は保持します',
    maintenanceLabel: '更新と保持期間',
    maintenanceDescription: 'リソース更新、スクリーンショットと倉庫履歴の保持規則',
    other_settingsLabel: 'その他の設定',
    other_settingsDescription: '他のグループに含まれない設定項目と追加設定ファイル',
    inventoryLabel: '素材在庫',
    inventoryDescription: '素材数、更新時刻、消費記録、在庫 CSV スナップショット',
    operatorsLabel: 'オペレーターと施設のスナップショット',
    operatorsDescription: 'Skland のオペレーター育成状況、施設、プレイヤーのスナップショット',
    growthLabel: '育成目標',
    growthDescription: '保存済みのオペレーター育成目標',
    masteryLabel: '特化計画',
    masteryDescription: '特化計画、実行状態、関連する通知記録',
    mastery_routesLabel: '特化経路',
    mastery_routesDescription: '職分別の特化補助経路と既定の選択',
    recyclingLabel: 'リサイクル素材の価値',
    recyclingDescription: 'リサイクルステーションの素材評価設定',
    mood_historyLabel: '体力履歴',
    mood_historyDescription: 'オペレーターの体力とシフトの記録',
    trading_historyLabel: '貿易履歴',
    trading_historyDescription: '貿易所のオーダー収益記録',
    operation_historyLabel: '作戦履歴',
    operation_historyDescription: 'ステージの実行、ドロップ、所要時間の記録',
    recycling_historyLabel: 'リサイクル履歴',
    recycling_historyDescription:
      'リサイクルステーションの回収記録、レポート識別子、アップロードの進捗',
    report_historyLabel: '基地レポート履歴',
    report_historyDescription: '保存済みの基地レポート',
    skland_historyLabel: 'チェックイン履歴',
    skland_historyDescription: 'Skland チェックイン記録',
    growth_historyLabel: '育成履歴',
    growth_historyDescription: '育成計画の達成統計',
    other_historyLabel: 'その他の履歴',
    other_historyDescription: '他のグループに含まれない古いログとデータベーステーブル'
  },
  updateJob: {
    launchingInstaller: '独立アップデーターを起動しています',
    fetchingSource: '更新先のソースを取得しています',
    prepareVersion: '一時ディレクトリに更新先を準備しています。現在のインスタンスは稼働を続けます',
    buildFrontend:
      'フロントエンドの依存関係をインストールし、画面をビルドしています。現在のインスタンスは稼働を続けます',
    prepareUploadedPackage: 'アップロードしたインストールパッケージを準備しています',
    downloadRelease: 'Releaseのインストールパッケージをダウンロードしています',
    extractVerify: 'インストールパッケージを展開・検証しています',
    prepareUploadedOta: 'アップロードしたOTA差分パッケージを準備しています',
    downloadOta: 'バージョン間のOTA差分パッケージをダウンロードしています',
    rebuildVerify: '現在のバージョンを基にアプリ全体を再構築・検証しています',
    verifyMacSignature: 'macOSアプリの署名の完全性を確認しています',
    stopInstances:
      'タスク状態を保存し、同じインストール先のMowerインスタンスと共有OCRプロセスを終了しています',
    switchSource:
      'ソースを切り替えています。失敗時の復旧用に元のコミットとフロントエンドを保持します',
    replaceApplication: 'アプリを置き換えています。ユーザーデータと元のバージョンは保持します',
    restoreOriginal: '元のバージョンのインスタンスを復元し、Webサービスの準備を待っています',
    restoreInstances: 'インスタンスを復元し、Webサービスの準備を待っています',
    rollback: 'インストールが完了しなかったため、元のバージョンに戻しています',
    checkPythonTools: '現在のPython環境の依存関係インストールツールを確認しています',
    preparePython:
      'Pythonの依存関係をダウンロード・準備しています。現在のインスタンスは稼働を続けます',
    keepPython: 'Pythonの依存関係一覧に変更がないため、現在の環境を保持します',
    forceSource: '強制更新：ローカルのソース変更をバックアップせずに上書きします',
    installPython: '準備済みのPython依存関係をインストールしています',
    applyFrontend: 'ビルド済みのフロントエンドを適用しています',
    restorePython: '元のバージョンの依存関係一覧に従ってPython環境を復元しています',
    softwareComplete: '更新が完了し、インスタンスを復元しました',
    readyToRestart: '準備が完了しました。タスクを保存し、全インスタンスを再起動します',
    cancelled: '更新をキャンセルしました。現在のインスタンスは稼働を続けます',
    extractRuntime: 'macOSランタイムを展開しています',
    extractWindows: 'Windows MAAの完全パッケージを展開しています',
    applyWindowsOta: 'Windows MAAのOTA差分パッケージを適用しています',
    extractLinux: 'Linux MAAの完全パッケージを展開しています',
    preparePythonApi: 'Python APIファイルを準備しています',
    readPythonOnDemand: 'Windowsパッケージ内のPythonフォルダーを必要な分だけ取得しています',
    extractDmg: 'MirrorChyanのパッケージからDMGを取り出しています',
    extractAppRuntime: 'MAA.appからランタイムとリソースを取り出しています',
    downloadRuntime: 'macOSランタイムをダウンロードしています',
    preserveMaaData: 'MAAのキャッシュと設定を保持しています',
    prepareWindowsOta: 'Windows MAAのOTA更新用コピーを準備しています',
    installWindowsOta: 'Windows MAAのOTA差分更新をインストールしています',
    installWindowsPackage: 'ダウンロード済みのWindows MAA完全パッケージをインストールしています',
    backupInstallMaa: '旧バージョンをバックアップし、MAAの更新を完了しています',
    installMaa: 'ダウンロード済みのMAAをインストールしています',
    switchMaaResources: 'MAAのリソースを切り替え、復元用コピーを保持しています',
    mergeMaaResources: 'MAAの差分リソースを統合しています',
    androidComplete: 'Android MAAコンポーネントを更新しました。サービスを再起動すると反映されます',
    mergePull:
      '一時作業ディレクトリでPR {number}をマージしています。現在のインスタンスは稼働を続けます',
    pullMerged: 'PRをマージしました：{commit}',
    otaFallback: 'OTAを利用できません（{reason}）。完全インストールパッケージを使用します',
    maaChecking: 'MAA {channel}の{operation}情報を取得しています',
    maaCheckingFrom: '{source}からMAA {channel}の{operation}情報を取得しています',
    maaDownloadPackage:
      'MAAの{operation}用に{source}から{platform} {arch}の{package}をダウンロードしています',
    fullPackage: '完全パッケージ',
    otaPackage: 'OTA差分パッケージ',
    pythonPackage: 'Python取得元パッケージ',
    maaRuntimeDownload: 'MAAの{operation}用にmacOSランタイムをダウンロードしています',
    maaResourceDownload: '{source}からMAAリソースパッケージをダウンロードしています',
    maaNoUpdate: 'MAA {version}は更新不要です（{channel}）',
    maaCompletePackage:
      '{source}経由でMAA {version}（{channel}）の{operation}が完了しました。{platform} {arch}の完全パッケージをインストールしました',
    maaCompleteMacMirror:
      'MirrorChyan経由でMAA {version}（{channel}）の{operation}が完了しました。macOSとWindows arm64の完全パッケージを検証済みです',
    maaCompleteMac:
      'MAA {version}（{channel}）の{operation}が完了しました。Pythonファイルを必要な分だけ{downloaded}バイト取得しました（Windows完全パッケージは{total}バイト）',
    restartMower: '。MAAを実行する前にMowerを再起動してください',
    checkCoreVersion:
      '。インストール済みコアのバージョンを読み込めません。MAAのインストール状態を確認してください',
    maaResourceComplete: '{source}経由でMAAリソース{version}を更新しました',
    restartAndroidService: '。Androidサービスを再起動すると反映されます',
    maaResourceCurrent: 'MAAリソース{version}は最新です',
    maaVersionAvailable: 'MAA {channel}の新バージョン{version}があります（{source}）',
    maaCurrentChannel: 'MAAは{channel}の最新バージョンです',
    maaResourceAvailable: 'MAAリソースの新バージョン{version}があります（{source}）'
  }
}
