import rjieba


def get_faq(question: str) -> str:
    q_words = {word.casefold() for word in rjieba.cut(question)}
    candidates = []
    for item in FAQ_LIST:
        kw_set = {word.casefold() for word in item["keywords"]}
        if q_words & kw_set:
            candidates.append(item)
    if not candidates:
        return "[FAQ未命中] 未找到相关常见问题，请根据问题查询记录，或补充报错信息。"
    result = "找到以下相关 FAQ：\n"
    for idx, item in enumerate(candidates, 1):
        result += f"{idx}. {item['question']}\n{item['answer']}\n"
    return result


faq_tool_def = {
    "type": "function",
    "function": {
        "name": "get_faq",
        "description": (
            "查询一般软件使用问题或常见报错的 FAQ。明确的数据库查询、漏单分析、"
            "专精操作和反馈请求直接使用对应工具。"
            "内容依据当前代码和界面整理，结果按关键词匹配；"
            "结合用户版本及平台选择相关建议，不把关键词命中当作已证实的根因。"
            "未命中时根据问题查询记录或询问缺少的信息，仅在已有错误堆栈时提取路径。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "用户的问题或报错信息"}
            },
            "required": ["question"],
        },
    },
}

FAQ_LIST = [
    {
        "keywords": [
            "更新",
            "下载",
            "下载器",
            "更新器",
            "下崽",
            "下崽器",
            "升级",
            "版本",
        ],
        "question": "如何安装或更新 Mower？旧版下载器还能用吗？",
        "answer": "Mower 使用内置更新，不再使用独立的 Mower 下载器或旧更新器。已安装用户进入 Mower 设置 → "
        "软件更新，选择正式版、公测版或开发版渠道，检查更新并按提示安装。软件更新会重启同一安装目录下的运行实例并恢复原运行状态。首次安装从项目主页的 Releases "
        "https://github.com/ArkMowers/arknights-mower/releases 获取适合系统和架构的独立包；macOS 和 Linux 虽提供独立包，仍建议优先使用源码部署，"
        "安装步骤见 https://github.com/ArkMowers/arknights-mower#源码部署 。独立包也可在“手动应用”上传 "
        "Release 安装包，支持 OTA 的平台可使用与本地版本匹配的差异包。源码部署使用页面的源码更新，不上传 Release "
        "安装包。更新失败时提供当前版本、目标版本和页面中的更新日志，不再建议下载群文件中的旧下载器。",
        "sources": ["README.md", "ui/src/components/SoftwareUpdate.vue"],
    },
    {
        "keywords": ["dll", "maa", "运行库", "加载失败"],
        "question": "MAA 无法加载、缺少 DLL 或运行库怎么办？",
        "answer": "先进入 MAA 设置，检查 MAA目录是否指向与当前系统、架构匹配的完整 MAA，并点击“测试连接”。当前页面提供 MAA "
        "本体下载安装、检查更新和 MAA 资源更新；未安装时可用“下载 MAA”，已有安装可用“更新 MAA”。不要用旧版 Mower 下载器替换 "
        "DLL，也不要只复制单个 DLL。Android 的 MAA 目录和设备连接由 Android "
        "应用管理；桌面平台按页面提示选择对应组件。仍失败时提供完整错误、平台、架构及 MAA 日志，区分路径错误、库加载失败和连接失败。",
        "sources": ["ui/src/components/MaaBasic.vue"],
    },
    {
        "keywords": ["资源", "模板", "热更新", "识别资源"],
        "question": "软件更新、Mower 资源更新和 MAA 资源更新有什么区别？",
        "answer": "Mower 设置 → 软件更新用于程序版本；同页的“资源更新”用于 Mower 识别等资源。资源更新支持检查、自动更新或手动上传更新包，同一套 "
        "Mower 的实例共用资源，在任务间歇加载新资源，通常不需要为资源更新重启程序。MAA 本体和 MAA 资源在 MAA 设置中单独更新；更新 "
        "Mower 资源不等于更新 MAA。",
        "sources": [
            "ui/src/components/ResourceUpdate.vue",
            "ui/src/components/SoftwareUpdate.vue",
            "ui/src/components/MaaBasic.vue",
        ],
    },
    {
        "keywords": ["代理", "网络", "下载失败", "超时", "github"],
        "question": "内置更新下载失败或 GitHub 无法连接怎么办？",
        "answer": "在 Mower 设置 → 网络与下载代理检查全局网络代理和 GitHub 下载代理站点，并使用页面的测试功能检查实际下载路径。文件下载代理与 "
        "GitHub API、Git 使用的网络代理不是同一项。独立包可手动上传官方 Release 安装包，Mower "
        "资源可单独上传资源更新包。提供失败步骤和日志，不改用旧下载器，也不要把更新失败直接当作模拟器连接故障。",
        "sources": ["README.md", "ui/src/components/NetworkSettings.vue"],
    },
    {
        "keywords": ["频道", "qq", "联系方式", "群", "反馈", "建议"],
        "question": "遇到问题或有功能建议，如何寻求帮助？",
        "answer": "先查阅 [Mower 反馈表](https://docs.qq.com/sheet/DUEJ6UWN5VFVRU0dG?tab=BB08J2)，核对已有记录；表格填写需相应编辑权限。整理 Mower "
        "版本、系统与架构、目标模拟器或设备、实际现象、期望结果和发生时间，并附相关日志或报错归档。QQ群：521857729；QQ频道：ArkMower，频道号：2r118jwue4。助手也可按你的明确要求发送问题反馈，Bug "
        "反馈需要对应的本地时间范围和可用日志；只整理描述不会自动发送。不要公开账号密码、API密钥或访问令牌。",
        "sources": [
            "README.md",
            "ui/src/components/Feedback.vue",
            "arknights_mower/agent/tools/submit_issue.py",
        ],
    },
    {
        "keywords": [
            "模拟器",
            "mumu",
            "mumu12",
            "雷电",
            "蓝叠",
            "bluestacks",
            "连接",
            "实例",
            "路径",
        ],
        "question": "如何连接模拟器、选择多开实例和填写路径？",
        "answer": "在 Mower "
        "设置的设备连接区域选择与当前平台匹配的预设，使用页面提供的“检测实例”或“启动并检测”，有多个实例时明确选择目标。检测到的实例先保存编号和身份信息，ADB地址和游戏包在验证通过后保存；连接失败不撤销已选实例。需补路径时按当前预设字段的问号填写安装、管理器或配置路径，不再统一填写旧版 "
        "shell 文件夹、多开编号0或固定端口。下拉“测试连接（只读）”不会启动或重启模拟器；只有支持启停的预设才提供对应动作，具体以页面能力提示为准。",
        "sources": [
            "ui/src/components/DeviceSettings.vue",
            "ui/src/utils/deviceSettings.js",
            "docs/subsystems/device-control.md",
        ],
    },
    {
        "keywords": ["adb", "adb.exe", "serial", "端口", "实体", "手机"],
        "question": "没有 adb.exe，或需要手动连接其他模拟器、实体设备怎么办？",
        "answer": "未指定自定义 ADB 路径时，Mower 使用平台默认路径并优先采用自带 ADB，不需要照旧教程另找 adb-buildin "
        "文件夹。优先用对应预设检测实例；不支持自动发现的环境可在高级设置使用“其他模拟器”或“实体设备”，明确填写目标 "
        "serial，再测试连接。不要根据模拟器名称猜端口或自动换到另一台在线设备。实体设备默认检查横屏1920×1080；如页面提供临时整备，授权只对本次运行有效，结束时按恢复规则还原尺寸。",
        "sources": [
            "docs/subsystems/device-control.md",
            "ui/src/components/DeviceSettings.vue",
            "ui/src/utils/deviceSettings.js",
        ],
    },
    {
        "keywords": ["未检测", "设备", "offline", "离线", "启动失败", "未就绪"],
        "question": "检测不到设备、设备离线或模拟器启动失败怎么办？",
        "answer": "查看设备连接区域的具体状态和修复提示，核对预设、所选实例、安装或管理器路径及设备自身的 ADB "
        "设置。只读测试不会帮你启动设备；支持自动启停的预设可使用“启动并检测”或“启动并测试连接”，其他环境先手动启动目标。连接与恢复的超时和重试有上限；目标离线时保留原实例绑定，不会转连其他实例。按提示处理当前目标，不沿用旧版 "
        "MuMu 关闭时断开 ADB 的成对开关说明。",
        "sources": [
            "ui/src/utils/deviceSettings.js",
            "docs/subsystems/device-control.md",
        ],
    },
    {
        "keywords": ["目录名称无效", "winerror", "267", "目录"],
        "question": "出现 WinError 267 或目录名称无效怎么办？",
        "answer": "先从完整报错确认是哪一个路径无效，再检查对应设置。模拟器相关路径按当前设备预设的字段说明填写；MAA 路径在 MAA "
        "设置中检查；软件更新失败查看软件更新日志。不要只凭 WinError 267 "
        "就断言一定是旧版“模拟器文件夹”填错。修改设备身份相关字段后重新检测或测试连接。",
        "sources": [
            "ui/src/components/DeviceSettings.vue",
            "ui/src/components/MaaBasic.vue",
            "ui/src/components/SoftwareUpdate.vue",
        ],
    },
    {
        "keywords": ["重启", "退出", "结束", "续接", "进程"],
        "question": "如何正常重启、继续任务或退出 Mower？",
        "answer": "Mower 设置页底部的“进程操作”提供“重启 Mower 进程”和“结束 Mower "
        "进程”，只操作当前实例。运行中可用“重启续接”保存任务队列继续运行；普通进程重启会重置运行缓存后重新开始。关闭窗口不一定等于退出，托盘与后台行为取决于当前设置及多开管理器。优先使用正常进程操作，界面和进程均无响应时再根据系统工具处理明确的 "
        "Mower 实例，避免结束其他实例或模拟器。",
        "sources": [
            "ui/src/components/ProcessControl.vue",
            "ui/src/pages/Settings.vue",
        ],
    },
    {
        "keywords": ["白屏", "webview", "webview2", "webkit", "gtk"],
        "question": "Mower 窗口白屏或无法初始化界面怎么办？",
        "answer": "先区分窗口渲染失败与程序文件被拦截，查看启动日志和系统平台。Windows 检查 WebView2 "
        "运行环境，可从微软官方获取：https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/ "
        "。Linux 独立包依赖宿主的 GTK/WebKit2 原生库，按启动提示或 README "
        "安装对应发行版依赖。白屏不是文件被杀毒软件删除的证据，不要因此直接给整个程序目录添加安全排除。",
        "sources": ["webview_ui.py", "README.md"],
    },
    {
        "keywords": ["删除", "消失", "拦截", "安全", "smartscreen", "病毒"],
        "question": "下载的程序被系统拦截或运行文件消失怎么办？",
        "answer": "从官方发布入口核对下载来源及 SHA256SUMS，再查看系统的安全提示或隔离记录。Windows 与 macOS 独立包未签名，首次运行可能出现 "
        "SmartScreen "
        "或隐私与安全性提示，按官方安装说明处理。不要把防火墙白名单当作杀毒隔离的通用修复，也不要关闭安全防护或默认排除整个目录。提供实际拦截信息后再定位原因。",
        "sources": ["README.md"],
    },
    {
        "keywords": ["reshape", "opencv", "分辨率", "截图", "黑边", "横屏"],
        "question": "截图识别异常、cannot reshape 或画面尺寸错误怎么办？",
        "answer": "检查当前绑定设备的实际画面及设备连接状态，标准截图为1920×1080 "
        "RGB。模拟器使用横屏并核对分辨率、黑边及所选截图后端，设备连接验证会报告具体尺寸或后端问题。MuMu IPC 仅适用于 Windows MuMu "
        "12，截图与触控必须配套；雷电截图增强仅适用于 Windows 雷电9或14。其他平台按页面支持的后端选择，不统一改成旧版 "
        "ADB+Gzip。实体设备优先使用页面提供的本次临时整备，不长期修改显示设置。仍失败时提供完整堆栈和报错截图，不能仅凭 reshape "
        "判断唯一根因。",
        "sources": [
            "docs/subsystems/device-control.md",
            "ui/src/utils/deviceSettings.js",
        ],
    },
    {
        "keywords": ["broadcast", "shape", "数组", "布局"],
        "question": "could not broadcast input array 或基建布局识别错误怎么办？",
        "answer": "数组形状异常需要结合完整堆栈、当前截图和截图尺寸定位，不能直接等同于排班表布局错误。若日志确实指向设施位置或岗位数，再核对排班表与游戏基建的设施类型、等级、岗位数及办公室/训练室位置设置；排班编辑器可调整设施位置。主副表生产设施类型和岗位数必须兼容，校验报错时先按具体设施修正，再启动运行。",
        "sources": [
            "docs/subsystems/plan-editor.md",
            "docs/subsystems/base-scheduler.md",
            "ui/src/pages/Settings.vue",
        ],
    },
    {
        "keywords": ["基建", "推荐", "252", "243", "153", "排班"],
        "question": "如何选择基建布局、导入排班并检查兼容性？",
        "answer": "按实际设施布局、干员练度和可用替班选择排班，不存在适合所有账号的固定最优252或243方案。排班页面支持独立排班 JSON、排班图片，以及从配置 "
        "ZIP 中读取 "
        "config/plan.json；导入后核对主表、副表、设施类型和岗位数、绑组、替班及个人心情规则，再运行校验。副表不能改变主表生产设施类型与岗位数；产物和订单切换还受“自动切换产物与订单”开关约束。校验预算不足表示检查未完成，不等于已经证实所有组合可用。",
        "sources": [
            "doc/config-backup.md",
            "docs/subsystems/base-scheduler.md",
            "docs/subsystems/plan-editor.md",
        ],
    },
    {
        "keywords": ["换人", "重复", "反复", "回班", "循环"],
        "question": "反复换人、重复任务或整组提前回班怎么办？",
        "answer": "先在运行日志查看任务类型、时间、设施、干员名单及副表触发记录，区分正常任务重规划与同一操作反复失败。核对副表是否循环触发、共享主班的替班是否同时可用、床位是否被预约，以及组内恢复时间差设置。当前“组内心情差距过大时延后回班”按参与计时成员的最晚与最早预计恢复完成时间之差判断，阈值默认60分钟；不是按固定心情点差。排班异常可选择报错归档分析后再调整，不只凭“重复换人”就认定是心情差过大。",
        "sources": [
            "ui/src/components/PlanAdvancedSettings.vue",
            "docs/subsystems/base-scheduler.md",
            "ui/src/pages/Log.vue",
        ],
    },
    {
        "keywords": ["产能", "产出", "收益", "龙门币", "赤金", "基报"],
        "question": "如何核对基建产出或描述产能问题？",
        "answer": "先明确统计时间、实际布局、制造产物、贸易站订单类型、无人机使用方向及是否启用切产物。查订单和龙门币记录用 "
        "trading_history，任务执行与报错用 "
        "log；历史订单记录不等于实时设施状态。比较产能时说明钱、经验、赤金和搓玉的统计口径，不用缺少来源的固定折算公式断言某套排班更优。缺少记录时说明证据不足。",
        "sources": [
            "arknights_mower/solvers/record.py",
            "arknights_mower/agent/tools/call_db.py",
        ],
    },
    {
        "keywords": [
            "理智",
            "周计划",
            "刷图",
            "生息",
            "演算",
            "肉鸽",
            "保全",
            "大型",
            "隐秘",
        ],
        "question": "为什么不刷理智或不运行生息演算等大型任务？",
        "answer": "在 MAA 设置页分别检查“刷理智周计划”和“大型任务”。周计划有自己的开关及“执行方式”：MAA 调用 MAA，Mower 使用本地作战，不依赖 "
        "MAA；检查当前方案、当天关卡、药品、理智阈值及库存选关限制。大型任务由独立开关、任务类型和开始/停止时间控制，不需要为此开启一个空刷理智计划；开始与停止时间相同表示全天，停止时间更早表示跨天。带“(MAA)”的类型依赖 "
        "MAA，其余类型使用相应的 Mower 流程。日常任务还受 Mower 设置中的“日常任务间隔”和基建任务空闲时间约束，具体原因查看日志。",
        "sources": [
            "ui/src/components/MaaWeekly.vue",
            "ui/src/components/LongTasks.vue",
            "arknights_mower/utils/config/conf.py",
            "arknights_mower/solvers/base_schedule.py",
        ],
    },
    {
        "keywords": ["邮件", "address", "smtp", "501", "收件人", "邮箱"],
        "question": "测试邮件失败或提示 Bad address syntax 怎么办？",
        "answer": "在 Mower 设置 → 邮件提醒检查发件账号、授权码或密码、收件人，以及自定义 SMTP 的服务器、端口和 SSL/TLS 或 STARTTLS "
        "设置。收件人列表为空时发给自己；列表中有空白项或无效地址时删除或修正该项，不要只留一条空字符串。再点“发送测试邮件”查看具体返回。地址语法错误与认证、网络、加密失败分开排查，不向助手发送授权码或密码。",
        "sources": ["ui/src/components/Email.vue", "arknights_mower/utils/email.py"],
    },
    {
        "keywords": ["红脸", "不下班", "心情", "下班", "替班", "床位"],
        "question": "干员低心情、红脸或到阈值后仍不下班怎么办？",
        "answer": "下班还需满足有效心情观测、个人阈值或用尽规则、完整替班匹配、可用恢复床位及任务预约。先查日志中具体等待条件，再核对主班绑组、共享主班与替班、宿舍占用和预约、个人上下限及回满设置。当前宿舍按分床优先级、单回位归属和心情恢复缺口安排，不套用固定“4个VIP加8个非VIP”的床位公式；共享主班在各依赖组都有兼容替班时可同时休息，否则等待。卡牌心情预估只辅助筛选，不是实测回满或确认下班的证据；用尽下班依赖有效消耗速率，不保证固定提前两三小时。需要时检查自动救急配置，但不能仅凭红脸保证会启动。",
        "sources": ["docs/subsystems/base-scheduler.md", "CONTEXT.zh.md"],
    },
    {
        "keywords": ["报表", "曲线", "数据库", "清理", "历史", "清空"],
        "question": "心情报表不显示、历史数据异常或想清理记录怎么办？",
        "answer": "先核对当前实例、查询时间范围和是否已有有效心情记录；报表空白不能直接认定数据库损坏。需要清理时先用 Mower 设置 → "
        "配置导出与导入备份，再在运行日志页面打开“数据库管理”，仅选择“干员心情记录”等确实要删除的数据类别，核对范围后确认。“专精计划”“专精路线配置”“仓库库存”等是独立类别，不要全选，也不要直接删除 "
        "data.db，否则会同时丢失其他业务数据。",
        "sources": [
            "ui/src/pages/Log.vue",
            "doc/config-backup.md",
            "arknights_mower/solvers/record.py",
        ],
    },
    {
        "keywords": ["配置", "备份", "迁移", "导出", "导入", "保留"],
        "question": "升级、迁移电脑或重装时如何保留配置与数据？",
        "answer": "使用 Mower 设置 → 配置导出与导入 → 导出配置，得到当前实例的 ZIP，包含 config 原文件、主副排班以及持久化 tmp "
        "数据，包括专精计划、专精路线、历史和库存。不要只复制旧教程中的根目录 conf.yml、plan.json 或 temp 文件夹。迁移后先停止 "
        "Mower 任务，再导入 "
        "ZIP；导入前自动生成恢复备份，保留当前管理端口、访问令牌及本机网络等设置，成功后刷新页面加载。资源包、更新文件、日志、其他实例和浏览器偏好不在备份中，迁移后重新核对设备与 "
        "MAA 路径。备份含凭据，请妥善保管。",
        "sources": ["doc/config-backup.md", "ui/src/components/ConfigBackup.vue"],
    },
    {
        "keywords": ["产物", "切换", "葛朗台", "副表", "搓玉"],
        "question": "副表不切换制造产物、贸易订单或葛朗台设置不生效怎么办？",
        "answer": "检查排班高级设置中的“自动切换产物与订单”，当前默认关闭。关闭时不切制造产物或贸易订单类型，相关设施状态条件与葛朗台切产物选项隐藏；普通换班、产物收取和葛朗台跑单仍保留。副表指定与主表不同产物或订单目标会产生启动校验冲突，不能靠副表绕过开关。需要切换时明确开启并检查无人机、切换损耗设置及主副表设施兼容性。",
        "sources": [
            "ui/src/components/PlanAdvancedSettings.vue",
            "docs/subsystems/base-scheduler.md",
        ],
    },
    {
        "keywords": ["闲人", "清退", "宿舍", "单回", "优先级", "回满"],
        "question": "关闭宿舍不养闲人后还会补床或让干员离宿吗？",
        "answer": "“宿舍不养闲人”仅控制普通满心情清退任务的创建。关闭后仍安排心情恢复、补空床及按优先级接管床位，个人心情上限和令夕上限仍会要求离宿。单回位按已有归属、优先级和恢复需求安排，不会仅因心情变化把已入住者全部重新排序；预约和专项任务保护仍生效。回满目标不一定是24，达到个人上限离宿也不等于立即安排上班。",
        "sources": [
            "ui/src/components/PlanAdvancedSettings.vue",
            "docs/subsystems/base-scheduler.md",
            "CONTEXT.zh.md",
        ],
    },
    {
        "keywords": ["救急", "救急线", "救急排班"],
        "question": "自动救急在哪里开启，什么时候接管和退出？",
        "answer": "入口在 Mower 设置 → 基建设置 → "
        "自动救急，旁边“救急排班”编辑独立主表和副表，默认关闭。初始化观测发现多组正常主班低于各自救急线，仍有主班等待休息且普通轮休无法安排时才接管；正常与救急副表生效后的工作设施类型、等级及产物必须一致。救急期间冻结正常副表，按救急排班安排驻员、宿管、跑单与菲亚梅塔，不自动继承未配置的专项任务。正常排班可以接回周转时退出，仍需恢复的组继续休息，不要求所有人都回满；开关不随正常排班导入导出。",
        "sources": [
            "ui/src/pages/Settings.vue",
            "ui/src/pages/Plan.vue",
            "docs/subsystems/base-scheduler.md",
        ],
    },
    {
        "keywords": ["专精", "养成", "合成", "加工", "模组", "精英化", "材料"],
        "question": "全自动专精是否会自动完成精英化、基础技能和模组升级？",
        "answer": "“全自动专精”控制自动专精与养成材料自动合成。精英化、基础技能升级和模组开启或升级仍需在游戏手动完成后同步数据，添加养成目标不等于自动完成这些操作。技能训练要求对应干员达到精英二和基础技能7级；材料准备按统一养成计划顺序及可用本地库存安排，缺料、训练保护或协助路线问题查看计划状态和失败原因。不要把“材料可准备”当作“已具备开训条件”。",
        "sources": [
            "ui/src/pages/MasteryRecommendation.vue",
            "docs/subsystems/growth-planning.md",
        ],
    },
    {
        "keywords": ["ai", "deepseek", "模型", "助手", "key", "中转", "本地模型"],
        "question": "AI 助手是否只支持 DeepSeek？本地模型如何配置？",
        "answer": "Mower 设置 → AI 助手与模型服务支持 DeepSeek、本地 OpenAI "
        "兼容接口及在线模型或中转商。选择 DeepSeek 后，可在“DeepSeek 模型”选择 Flash / Pro 预设，或输入官方模型 ID 后回车，"
        "使用 DeepSeek 密钥。自定义接口填写实际模型ID和接口地址，本地需兼容 OpenAI Chat Completions，通常可以不填 "
        "API密钥；在线接口要求 HTTPS 和对应密钥。聊天工具调用还要求所选模型与服务支持工具调用。日志排班报错可选择对应归档进行 AI 分析；AI "
        "建议不会自动修改排班或证明推测就是根因。",
        "sources": [
            "ui/src/components/ChatBotSetting.vue",
            "arknights_mower/agent/agent.py",
            "arknights_mower/agent/schedule_error.py",
        ],
    },
]
