import time
import schedule
from arknights_mower.strategy import Solver
from arknights_mower.utils.log import logger, init_fhlr
from arknights_mower.utils import config


# 指定无人机加速第三层第三个房间的制造或贸易订单
drone_room = 'room_3_3'

# 指定使用菲亚梅塔恢复第一层第二个房间心情最差的干员的心情
# 恢复后回到原工作岗位，工作顺序不变，以保证最大效率
fia_room = 'room_1_2'

# 指定关卡序列的作战计划
ope_lists = [['AP-5', 1], ['1-7', -1]]

# 使用信用点购买东西的优先级（从高到低）
shop_priority = ['招聘许可', '赤金', '龙门币', '初级作战记录', '技巧概要·卷2', '基础作战记录', '技巧概要·卷1']

# 公招选取标签时优先选择的干员的优先级（从高到低）
recruit_priority = ['因陀罗', '火神']

# 自定义基建排班
# 这里自定义了一套排班策略，实现的是两班倒，分为四个阶段
# 阶段 1 和 2 为第一班，阶段 3 和 4 为第二班
# 第一班的干员在阶段 3 和 4 分两批休息，第二班同理
# 每个阶段耗时 6 小时
plan = {
    # 阶段 1
    'plan_1': {
        # 办公室
        'contact': ['艾雅法拉'],
        # 宿舍
        'dormitory_1': ['杜林', '闪灵', '安比尔', '空弦', '缠丸'],
        'dormitory_2': ['推进之王', '琴柳', '赫默', '杰西卡', '调香师'],
        'dormitory_3': ['夜莺', '波登可', '夜刀', '古米', '空爆'],
        'dormitory_4': ['空', 'Lancet-2', '香草', '史都华德', '刻俄柏'],
        # 会客室
        'meeting': ['陈', '红'],
        # 制造站 + 贸易站 + 发电站
        'room_1_1': ['德克萨斯', '能天使', '拉普兰德'],
        'room_1_2': ['断罪者', '食铁兽', '槐琥'],
        'room_1_3': ['阿消'],
        'room_2_1': ['巫恋', '柏喙', '慕斯'],
        'room_2_2': ['红豆', '霜叶', '白雪'],
        'room_2_3': ['雷蛇'],
        'room_3_1': ['Castle-3', '梅尔', '白面鸮'],
        'room_3_2': ['格雷伊'],
        'room_3_3': ['砾', '夜烟', '斑点']
    },
    # 阶段 2
    'plan_2': {
        # 注释掉了部分和阶段 1 一样排班计划的房间，加快排班速度
        # 'contact': ['艾雅法拉'],
        'dormitory_1': ['杜林', '闪灵', '芬', '稀音', '克洛丝'],
        'dormitory_2': ['推进之王', '琴柳', '清流', '森蚺', '温蒂'],
        'dormitory_3': ['夜莺', '波登可', '伊芙利特', '深靛', '炎熔'],
        'dormitory_4': ['空', 'Lancet-2', '远山', '星极', '普罗旺斯'],
        # 'meeting': ['陈', '红'],
        # 'room_1_1': ['德克萨斯', '能天使', '拉普兰德'],
        # 'room_1_2': ['断罪者', '食铁兽', '槐琥'],
        # 'room_1_3': ['阿消'],
        # 'room_2_1': ['巫恋', '柏喙', '慕斯'],
        # 'room_2_2': ['红豆', '霜叶', '白雪'],
        # 'room_2_3': ['雷蛇'],
        # 'room_3_1': ['Castle-3', '梅尔', '白面鸮'],
        # 'room_3_2': ['格雷伊'],
        # 'room_3_3': ['砾', '夜烟', '斑点']
    },
    'plan_3': {
        'contact': ['普罗旺斯'],
        'dormitory_1': ['杜林', '闪灵', '格雷伊', '雷蛇', '阿消'],
        'dormitory_2': ['推进之王', '琴柳', '德克萨斯', '能天使', '拉普兰德'],
        'dormitory_3': ['夜莺', '波登可', '巫恋', '柏喙', '慕斯'],
        'dormitory_4': ['空', 'Lancet-2', '艾雅法拉', '陈', '红'],
        'meeting': ['远山', '星极'],
        'room_1_1': ['安比尔', '空弦', '缠丸'],
        'room_1_2': ['赫默', '杰西卡', '调香师'],
        'room_1_3': ['伊芙利特'],
        'room_2_1': ['夜刀', '古米', '空爆'],
        'room_2_2': ['香草', '史都华德', '刻俄柏'],
        'room_2_3': ['深靛'],
        'room_3_1': ['芬', '稀音', '克洛丝'],
        'room_3_2': ['炎熔'],
        'room_3_3': ['清流', '森蚺', '温蒂']
    },
    'plan_4': {
        # 'contact': ['普罗旺斯'],
        'dormitory_1': ['杜林', '闪灵', '断罪者', '食铁兽', '槐琥'],
        'dormitory_2': ['推进之王', '琴柳', '红豆', '霜叶', '白雪'],
        'dormitory_3': ['夜莺', '波登可', 'Castle-3', '梅尔', '白面鸮'],
        'dormitory_4': ['空', 'Lancet-2', '砾', '夜烟', '斑点'],
        # 'meeting': ['远山', '星极'],
        # 'room_1_1': ['安比尔', '空弦', '缠丸'],
        # 'room_1_2': ['赫默', '杰西卡', '调香师'],
        # 'room_1_3': ['伊芙利特'],
        # 'room_2_1': ['夜刀', '古米', '空爆'],
        # 'room_2_2': ['香草', '史都华德', '刻俄柏'],
        # 'room_2_3': ['深靛'],
        # 'room_3_1': ['芬', '稀音', '克洛丝'],
        # 'room_3_2': ['炎熔'],
        # 'room_3_3': ['清流', '森蚺', '温蒂']
    }
}


def debuglog():
    '''
    在屏幕上输出调试信息，方便调试和报错
    '''
    logger.handlers[0].setLevel('DEBUG')


def savelog():
    '''
    指定日志和截屏的保存位置，方便调试和报错
    调试信息和截图默认保存在代码所在的目录下
    '''
    config.LOGFILE_PATH = './log'
    config.SCREENSHOT_PATH = './screenshot'
    config.SCREENSHOT_MAXNUM = 100
    init_fhlr()


def simulate():
    '''
    具体调用方法可见各个函数的参数说明
    '''
    global ope_lists
    cli = Solver()
    cli.mail()  # 邮件
    cli.base(clue_collect=True, drone_room=drone_room, fia_room=fia_room, arrange=plan)  # 基建
    cli.credit()  # 信用
    ope_lists = cli.ope(eliminate=True, plan=ope_lists)  # 行动，返回未完成的作战计划
    cli.shop(shop_priority)  # 商店
    cli.recruit()  # 公招
    cli.mission()  # 任务


def schedule_task():
    """
    定期运行任务
    """
    schedule.every().day.at('07:00').do(simulate)
    schedule.every().day.at('19:00').do(simulate)
    while True:
        schedule.run_pending()
        time.sleep(60)


debuglog()
savelog()
simulate()
schedule_task()
