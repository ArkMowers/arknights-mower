class Scene:
    UNKNOWN = -1
    "未知"
    UNDEFINED = 0
    "未定义"
    INDEX = 1
    "首页"
    MATERIEL = 2
    "物资领取确认"
    ANNOUNCEMENT = 3
    "公告"
    MAIL = 4
    "邮件信箱"
    NAVIGATION_BAR = 5
    "导航栏返回"
    UPGRADE = 6
    "升级"
    SKIP = 7
    "跳过"
    DOUBLE_CONFIRM = 8
    "二次确认"
    CONNECTING = 9
    "正在提交反馈至神经"
    NETWORK_CHECK = 10
    "网络拨测"
    LOGIN_MAIN = 101
    "登录页面"
    LOGIN_INPUT = 102
    "登录页面（输入）"
    LOGIN_QUICKLY = 103
    "登录页面（快速）"
    LOGIN_LOADING = 104
    "登录中"
    LOGIN_START = 105
    "启动"
    LOGIN_ANNOUNCE = 106
    "启动界面公告"
    LOGIN_REGISTER = 107
    "注册"
    LOGIN_CAPTCHA = 108
    "滑动验证码"
    LOGIN_BILIBILI = 109
    "B 服登录界面"
    LOGIN_MAIN_NOENTRY = 110
    "登录页面（无按钮入口）"
    LOGIN_CADPA_DETAIL = 111
    "游戏适龄提示"
    CLOSE_MINE = 112
    "产业合作洽谈会"
    CHECK_IN = 113
    "4周年签到"
    LOGIN_NEW = 114
    "新登陆界面"
    LOGIN_BILIBILI_PRIVACY = 116
    "B服隐私政策提示"
    INFRA_MAIN = 201
    "基建全局视角"
    INFRA_TODOLIST = 202
    "基建待办事项"
    INFRA_CONFIDENTIAL = 203
    "线索主界面"
    INFRA_ARRANGE = 204
    "基建干员进驻总览"
    INFRA_DETAILS = 205
    "基建放大查看"
    INFRA_ARRANGE_CONFIRM = 206
    "基建干员排班二次确认"
    INFRA_ARRANGE_ORDER = 207
    "干员进驻设施排序界面"
    RIIC_REPORT = 208
    "副手简报界面"
    CTRLCENTER_ASSISTANT = 209
    "控制中枢界面"
    RIIC_OPERATOR_SELECT = 210
    "干员选择界面"
    CLUE_DAILY = 211
    "每日线索领取"
    CLUE_RECEIVE = 212
    "接收线索"
    CLUE_GIVE_AWAY = 213
    "传递线索"
    CLUE_SUMMARY = 214
    "线索交流活动汇总"
    CLUE_PLACE = 215
    "放置线索"
    TRAIN_SKILL_UPGRADE = 216
    "技能升级"
    TRAIN_MAIN = 217
    "训练室主界面"
    TRAIN_SKILL_UPGRADE_ERROR = 218
    "技能升级失败"
    TRAIN_SKILL_SELECT = 219
    "选择技能"
    TRAIN_FINISH = 220
    "技能升级结算"
    ORDER_LIST = 221
    "贸易站订单列表"
    DRONE_ACCELERATE = 222
    "无人机加速对话框"
    FACTORY_ROOMS = 223
    "制造站设施列表"
    FRIEND_LIST_OFF = 301
    "好友列表（未选中）"
    FRIEND_LIST_ON = 302
    "好友列表（选中）"
    FRIEND_VISITING = 303
    "基建内访问好友"
    MISSION_DAILY = 401
    "日常任务"
    MISSION_WEEKLY = 402
    "周常任务"
    MISSION_TRAINEE = 403
    "见习任务"
    TERMINAL_MAIN = 501
    "终端主界面"
    TERMINAL_MAIN_THEME = 502
    "主题曲"
    TERMINAL_EPISODE = 503
    "插曲"
    TERMINAL_BIOGRAPHY = 504
    "别传"
    TERMINAL_COLLECTION = 505
    "资源收集"
    TERMINAL_REGULAR = 506
    "常态事务"
    TERMINAL_LONGTERM = 507
    "长期探索"
    TERMINAL_PERIODIC = 508
    "周期挑战"
    OPERATOR_CHOOSE_LEVEL = 601
    "作战前，关卡未选定"
    OPERATOR_BEFORE = 602
    "作战前，关卡已选定"
    OPERATOR_SELECT = 603
    "作战前，正在编队"
    OPERATOR_ONGOING = 604
    "作战中"
    OPERATOR_FINISH = 605
    "作战结束"
    OPERATOR_RECOVER_POTION = 607
    "恢复理智（药剂）"
    OPERATOR_RECOVER_ORIGINITE = 608
    "恢复理智（源石）"
    OPERATOR_DROP = 609
    "掉落物品详细说明页"
    OPERATOR_ELIMINATE = 610
    "剿灭作战前，关卡已选定"
    OPERATOR_ELIMINATE_FINISH = 611
    "剿灭作战结束"
    OPERATOR_GIVEUP = 612
    "代理失误"
    OPERATOR_FAILED = 613
    "代理作战失败"
    OPERATOR_ELIMINATE_AGENCY = 614
    "剿灭代理卡使用确认"
    OPERATOR_SUPPORT = 615
    "借助战"
    OPERATOR_STRANGER_SUPPORT = 616
    "使用非好友助战"
    SHOP_OTHERS = 701
    "商店除了信用兑换处以外的界面"
    SHOP_CREDIT = 702
    "信用兑换处"
    SHOP_CREDIT_CONFIRM = 703
    "兑换确认"
    SHOP_ASSIST = 704
    "助战使用次数"
    SHOP_UNLOCK_SCHEDULE = 705
    "累计信用消费"
    RECRUIT_MAIN = 801
    "公招主界面"
    RECRUIT_TAGS = 802
    "挑选标签时"
    RECRUIT_AGENT = 803
    "开包干员展示"
    RA_MAIN = 901
    "生息演算首页"
    RA_GUIDE_ENTRANCE = 902
    "剧情入口：众人会聚之地（后舍）"
    RA_GUIDE_DIALOG = 903
    "剧情对话"
    RA_BATTLE_ENTRANCE = 904
    "作战入口"
    RA_BATTLE = 905
    "作战中"
    RA_BATTLE_EXIT_CONFIRM = 906
    "作战退出确认对话框"
    RA_GUIDE_BATTLE_ENTRANCE = 907
    "剧情作战入口"
    RA_BATTLE_COMPLETE = 908
    "作战结算"
    RA_MAP = 909
    "地图"
    RA_SQUAD_EDIT = 910
    "作战分队编辑"
    RA_KITCHEN = 911
    "烹饪台"
    RA_GET_ITEM = 912
    "获得物资"
    RA_SQUAD_EDIT_DIALOG = 913
    "作战分队不携带干员确认"
    RA_DAY_COMPLETE = 914
    "生息日结算"
    RA_DAY_DETAIL = 915
    "当日详细信息"
    RA_WASTE_TIME_DIALOG = 916
    "跳过行动确认对话框"
    RA_PERIOD_COMPLETE = 917
    "生存周期完成"
    RA_DELETE_SAVE_DIALOG = 918
    "存档删除确认"
    RA_ADVENTURE = 919
    "奇遇"
    SSS_MAIN = 1001
    "保全作战首页"
    SSS_START = 1002
    "开始保全作战"
    SSS_EC = 1003
    "定向导能元件"
    SSS_DEVICE = 1004
    "战术装备配置"
    SSS_SQUAD = 1005
    "首批作战小队选任"
    SSS_DEPLOY = 1006
    "开始部署"
    SSS_LOADING = 1008
    "正在进入"
    SSS_GUIDE = 1009
    "保全教程"
    SF_ENTRANCE = 1101
    "隐秘战线入口"
    SF_INFO = 1102
    "隐秘战线详细说明"
    SF_SELECT_TEAM = 1103
    "选择小队"
    SF_CONTINUE = 1104
    "继续前进"
    SF_SELECT = 1105
    "选择路线"
    SF_ACTIONS = 1106
    "行动选项"
    SF_RESULT = 1107
    "行动结果"
    SF_EVENT = 1108
    "应对危机事件"
    SF_TEAM_PASS = 1109
    "小队通过危机事件"
    SF_CLICK_ANYWHERE = 1110
    "点击任意处继续"
    SF_END = 1111
    "抵达终点"
    SF_EXIT = 1112
    "暂离行动"
    DEPOT = 1301
    "仓库"
    LOADING = 9998
    "场景跳转时的等待界面"
    CONFIRM = 9999
    "确认对话框"


SceneComment = {
    -1: "未知",
    0: "未定义",
    1: "首页",
    2: "物资领取确认",
    3: "公告",
    4: "邮件信箱",
    5: "导航栏返回",
    6: "升级",
    7: "跳过",
    8: "二次确认",
    9: "正在提交反馈至神经",
    10: "网络拨测",
    101: "登录页面",
    102: "登录页面（输入）",
    103: "登录页面（快速）",
    104: "登录中",
    105: "启动",
    106: "启动界面公告",
    107: "注册",
    108: "滑动验证码",
    109: "B 服登录界面",
    110: "登录页面（无按钮入口）",
    111: "游戏适龄提示",
    112: "产业合作洽谈会",
    113: "4周年签到",
    114: "新登陆界面",
    116: "B服隐私政策提示",
    201: "基建全局视角",
    202: "基建待办事项",
    203: "线索主界面",
    204: "基建干员进驻总览",
    205: "基建放大查看",
    206: "基建干员排班二次确认",
    207: "干员进驻设施排序界面",
    208: "副手简报界面",
    209: "控制中枢界面",
    210: "干员选择界面",
    211: "每日线索领取",
    212: "接收线索",
    213: "传递线索",
    214: "线索交流活动汇总",
    215: "放置线索",
    216: "技能升级",
    217: "训练室主界面",
    218: "技能升级失败",
    219: "选择技能",
    220: "技能升级结算",
    221: "贸易站订单列表",
    222: "无人机加速对话框",
    223: "制造站设施列表",
    301: "好友列表（未选中）",
    302: "好友列表（选中）",
    303: "基建内访问好友",
    401: "日常任务",
    402: "周常任务",
    403: "见习任务",
    501: "终端主界面",
    502: "主题曲",
    503: "插曲",
    504: "别传",
    505: "资源收集",
    506: "常态事务",
    507: "长期探索",
    508: "周期挑战",
    601: "作战前，关卡未选定",
    602: "作战前，关卡已选定",
    603: "作战前，正在编队",
    604: "作战中",
    605: "作战结束",
    607: "恢复理智（药剂）",
    608: "恢复理智（源石）",
    609: "掉落物品详细说明页",
    610: "剿灭作战前，关卡已选定",
    611: "剿灭作战结束",
    612: "代理失误",
    613: "代理作战失败",
    614: "剿灭代理卡使用确认",
    615: "借助战",
    616: "使用非好友助战",
    701: "商店除了信用兑换处以外的界面",
    702: "信用兑换处",
    703: "兑换确认",
    704: "助战使用次数",
    705: "累计信用消费",
    801: "公招主界面",
    802: "挑选标签时",
    803: "开包干员展示",
    901: "生息演算首页",
    902: "剧情入口：众人会聚之地（后舍）",
    903: "剧情对话",
    904: "作战入口",
    905: "作战中",
    906: "作战退出确认对话框",
    907: "剧情作战入口",
    908: "作战结算",
    909: "地图",
    910: "作战分队编辑",
    911: "烹饪台",
    912: "获得物资",
    913: "作战分队不携带干员确认",
    914: "生息日结算",
    915: "当日详细信息",
    916: "跳过行动确认对话框",
    917: "生存周期完成",
    918: "存档删除确认",
    919: "奇遇",
    1001: "保全作战首页",
    1002: "开始保全作战",
    1003: "定向导能元件",
    1004: "战术装备配置",
    1005: "首批作战小队选任",
    1006: "开始部署",
    1008: "正在进入",
    1009: "保全教程",
    1101: "隐秘战线入口",
    1102: "隐秘战线详细说明",
    1103: "选择小队",
    1104: "继续前进",
    1105: "选择路线",
    1106: "行动选项",
    1107: "行动结果",
    1108: "应对危机事件",
    1109: "小队通过危机事件",
    1110: "点击任意处继续",
    1111: "抵达终点",
    1112: "暂离行动",
    1301: "仓库",
    9998: "场景跳转时的等待界面",
    9999: "确认对话框",
}
