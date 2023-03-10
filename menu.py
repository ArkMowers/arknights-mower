import json
from multiprocessing import Pipe, Process, freeze_support
import time
from datetime import datetime
import PySimpleGUI as sg
import os
from ruamel.yaml import YAML
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.strategy import Solver
from arknights_mower.utils.device import Device
from arknights_mower.utils.log import logger, init_fhlr
from arknights_mower.utils import config
from arknights_mower.data import agent_list

yaml = YAML()
confUrl = './conf.yml';
conf = {}
plan = {}
global window
buffer = ''
line = 0
half_line_index = 0


def inialize(tasks, scheduler=None):
    device = Device()
    cli = Solver(device)
    if scheduler is None:
        base_scheduler = BaseSchedulerSolver(cli.device, cli.recog)
        base_scheduler.operators = {}
        plan1 = {}
        for key in plan:
            plan1[key] = plan[key]['plans']
        base_scheduler.global_plan = {'default': "plan_1", "plan_1": plan1}
        base_scheduler.current_base = {}
        base_scheduler.resting = []
        base_scheduler.dorm_count = 4
        base_scheduler.tasks = tasks
        # 读取心情开关，有菲亚梅塔或者希望全自动换班得设置为 true
        base_scheduler.read_mood = True
        base_scheduler.scan_time = {}
        base_scheduler.last_room = ''
        base_scheduler.free_blacklist = []
        base_scheduler.resting_treshhold = 0.5
        base_scheduler.MAA = None
        base_scheduler.ADB_CONNECT = config.ADB_CONNECT[0]
        base_scheduler.error = False
        return base_scheduler
    else:
        scheduler.device = cli.device
        scheduler.recog = cli.recog
        scheduler.handle_error(True)
        return scheduler


def simulate():
    '''
    具体调用方法可见各个函数的参数说明
    '''
    tasks = []
    reconnect_max_tries = 10
    reconnect_tries = 0
    base_scheduler = inialize(tasks)
    while True:
        try:
            if len(base_scheduler.tasks) > 0:
                (base_scheduler.tasks.sort(key=lambda x: x["time"], reverse=False))
                sleep_time = (base_scheduler.tasks[0]["time"] - datetime.now()).total_seconds()
                logger.info(base_scheduler.tasks)
                if sleep_time >= 0:
                    remaining_time = (base_scheduler.tasks[0]["time"] - datetime.now()).total_seconds()
                    logger.info(f"开始休息 {'%.2f' % (remaining_time/60)} 分钟，到{base_scheduler.tasks[0]['time'].strftime('%H:%M:%S')}")
                    time.sleep(sleep_time)
            base_scheduler.run()
            reconnect_tries = 0
        except ConnectionError as e:
            reconnect_tries += 1
            if reconnect_tries < reconnect_max_tries:
                logger.warning(f'连接端口断开....正在重连....')
                connected = False
                while not connected:
                    try:
                        base_scheduler = inialize([], base_scheduler)
                        break
                    except Exception as ce:
                        logger.error(ce)
                        time.sleep(5)
                        continue
                continue
            else:
                raise Exception(e)
        except Exception as E:
            logger.exception(f"程序出错--->{E}")


# 读取写入配置文件
def loadConf():
    global conf
    global confUrl
    if not os.path.isfile(confUrl):
        open(confUrl, 'w')  # 创建空配置文件
        conf['planFile'] = './plan.json'  # 默认排班表地址
        return
    with open(confUrl, 'r', encoding='utf8') as c:
        conf = yaml.load(c)
        if conf is None:
            conf = {}


def writeConf():
    global conf
    global confUrl
    with open(confUrl, 'w', encoding='utf8') as c:
        yaml.default_flow_style = False
        yaml.dump(conf, c)


# 读取写入排班表
def loadPlan(url):
    global plan
    if not os.path.isfile(url):
        with open(url, 'w') as f:
            json.dump(plan, f)  # 创建空json文件
        return
    try:
        with open(url, 'r', encoding='utf8') as fp:
            plan = json.loads(fp.read())
        conf['planFile'] = url
        for i in range(1, 4):
            for j in range(1, 4):
                window[f'btn_room_{str(i)}_{str(j)}'].update('待建造', button_color=('white', '#4f4945'))
        for key in plan:
            if type(plan[key]).__name__ == 'list':  # 兼容旧版格式
                plan[key] = {'plans': plan[key], 'name': ''}
            elif plan[key]['name'] == '贸易站':
                window['btn_' + key].update('贸易站', button_color=('#4f4945', '#33ccff'))
            elif plan[key]['name'] == '制造站':
                window['btn_' + key].update('制造站', button_color=('#4f4945', '#ffcc00'))
            elif plan[key]['name'] == '发电站':
                window['btn_' + key].update('发电站', button_color=('#4f4945', '#ccff66'))
    except Exception as e:
        logger.error(e)
        println('json格式错误！')


def writePlan():
    with open(conf['planFile'], 'w', encoding='utf8') as c:
        json.dump(plan, c, ensure_ascii=False)


# 执行自动排班
def start(c, p, child_conn):
    global plan
    global conf
    conf = c
    plan = p
    config.LOGFILE_PATH = './log'
    config.SCREENSHOT_PATH = './screenshot'
    config.SCREENSHOT_MAXNUM = 1000
    config.ADB_DEVICE = [conf['adb']]
    config.ADB_CONNECT = [conf['adb']]
    init_fhlr(child_conn)
    logger.info('开始运行Mower')
    simulate()


# 主页面
def menu():
    global window
    global buffer
    loadConf()
    sg.theme('LightBlue2')
    # maa_title = sg.Text('MAA:')
    # maa_select = sg.InputCombo(['启用', '停用'], default_value='停用', size=(20, 3))
    # adb
    adb_title = sg.Text('adb连接地址:', size=10)
    adb = sg.InputText(conf['adb'] if 'adb' in conf.keys() else '', size=60)
    # 排班表json
    plan_title = sg.Text('排班表:', size=10)
    planFile = sg.InputText(conf['planFile'], readonly=True, size=60, key='planFile', enable_events=True)
    plan_select = sg.FileBrowse('...', size=(3, 1), file_types=(("JSON files", "*.json"),))
    # 总开关
    on_btn = sg.Button('开始执行', key='on')
    off_btn = sg.Button('立即停止', key='off', visible=False, button_color='red')
    # 日志栏
    output = sg.Output(size=(150, 25), key='log', text_color='#808069', font=('微软雅黑', 9))

    # 宿舍区
    central = sg.Button('控制中枢', key='btn_central', size=(18, 3), button_color='#303030')
    dormitory_1 = sg.Button('宿舍', key='btn_dormitory_1', size=(18, 2), button_color='#303030')
    dormitory_2 = sg.Button('宿舍', key='btn_dormitory_2', size=(18, 2), button_color='#303030')
    dormitory_3 = sg.Button('宿舍', key='btn_dormitory_3', size=(18, 2), button_color='#303030')
    dormitory_4 = sg.Button('宿舍', key='btn_dormitory_4', size=(18, 2), button_color='#303030')
    centralArea = sg.Column([[central], [dormitory_1], [dormitory_2], [dormitory_3], [dormitory_4]])
    # 制造站区
    room_1_1 = sg.Button('待建造', key='btn_room_1_1', size=(12, 2), button_color='#4f4945')
    room_1_2 = sg.Button('待建造', key='btn_room_1_2', size=(12, 2), button_color='#4f4945')
    room_1_3 = sg.Button('待建造', key='btn_room_1_3', size=(12, 2), button_color='#4f4945')
    room_2_1 = sg.Button('待建造', key='btn_room_2_1', size=(12, 2), button_color='#4f4945')
    room_2_2 = sg.Button('待建造', key='btn_room_2_2', size=(12, 2), button_color='#4f4945')
    room_2_3 = sg.Button('待建造', key='btn_room_2_3', size=(12, 2), button_color='#4f4945')
    room_3_1 = sg.Button('待建造', key='btn_room_3_1', size=(12, 2), button_color='#4f4945')
    room_3_2 = sg.Button('待建造', key='btn_room_3_2', size=(12, 2), button_color='#4f4945')
    room_3_3 = sg.Button('待建造', key='btn_room_3_3', size=(12, 2), button_color='#4f4945')
    leftArea = sg.Column([[room_1_1, room_1_2, room_1_3],
                          [room_2_1, room_2_2, room_2_3],
                          [room_3_1, room_3_2, room_3_3]])
    # 功能区
    meeting = sg.Button('会客室', key='btn_meeting', size=(24, 2), button_color='#303030')
    factory = sg.Button('加工站', key='btn_factory', size=(24, 2), button_color='#303030')
    contact = sg.Button('办公室', key='btn_contact', size=(24, 2), button_color='#303030')
    rightArea = sg.Column([[meeting], [factory], [contact]])

    settingLayout = [[sg.Column([[sg.Text('设施类别:'), sg.InputCombo(['贸易站', '制造站', '发电站'], size=12, key='station_type')]],
                                key='station_type_col', visible=False)]]
    # 排班表设置标签
    for i in range(1, 6):
        setArea = sg.Column([[sg.Text('干员：'),
                              sg.InputCombo(['Free'] + agent_list, size=20, key='agent' + str(i)),
                              sg.Text('组：'),
                              sg.InputText('', size=15, key='group' + str(i)),
                              sg.Text('替换：'),
                              sg.InputText('', size=30, key='replacement' + str(i))
                              ]], key='setArea' + str(i), visible=False)
        settingLayout.append([setArea])
    settingLayout.append([sg.Button('保存', key='savePlan', visible=False)])
    settingArea = sg.Column(settingLayout, element_justification="center",
                            vertical_alignment="bottom",
                            expand_x=True)
    # 组装页面
    mainTab = sg.Tab('  主页  ', [[adb_title, adb],
                                [plan_title, planFile, plan_select],
                                [output],
                                [on_btn, off_btn]])

    planTab = sg.Tab('  排班表 ', [[leftArea, centralArea, rightArea], [settingArea]], element_justification="center")
    window = sg.Window('Mower', [[sg.TabGroup([[mainTab, planTab]], border_width=0,
                                              tab_border_width=0, focus_color='#bcc8e5',
                                              selected_background_color='#d4dae8', background_color='#aab6d3',
                                              tab_background_color='#aab6d3')]], font='微软雅黑', finalize=True)

    loadPlan(conf['planFile'])
    while True:
        event, value = window.Read()
        if event == sg.WIN_CLOSED:
            conf['adb'] = adb.get()
            break
        elif event == 'planFile' and planFile.get() != conf['planFile']:
            writePlan()
            loadPlan(planFile.get())
            planFile.update(conf['planFile'])
        elif event.startswith('btn_'):
            btn = event
            initBtn(event)
        elif event == 'savePlan':
            saveBtn(btn)
        elif event == 'on':
            if adb.get() == '':
                println('adb未设置！')
                continue
            conf['adb'] = adb.get()

            on_btn.update(visible=False)
            off_btn.update(visible=True)
            clear()
            parent_conn, child_conn = Pipe()
            main_thread = Process(target=start, args=(conf, plan, child_conn), daemon=True)
            main_thread.start()
            window.perform_long_operation(lambda: log(parent_conn), 'log')
        elif event == 'off':
            println('停止运行')
            child_conn.close()
            main_thread.terminate()
            on_btn.update(visible=True)
            off_btn.update(visible=False)

    window.close()
    writeConf()
    writePlan()


def initBtn(event):
    room_key = event[4:]
    station_name = plan[room_key]['name'] if room_key in plan.keys() else ''
    plans = plan[room_key]['plans'] if room_key in plan.keys() else []
    if room_key.startswith('room'):
        window['station_type_col'].update(visible=True)
        window['station_type'].update(station_name)
        visibleCnt = 3  # 设施干员需求数量
    else:
        if room_key == 'meeting':
            visibleCnt = 2
        elif room_key == 'factory' or room_key == 'contact':
            visibleCnt = 1
        else:
            visibleCnt = 5
        window['station_type_col'].update(visible=False)
        window['station_type'].update('')
    window['savePlan'].update(visible=True)
    for i in range(1, 6):
        if i > visibleCnt:
            window['setArea' + str(i)].update(visible=False)
            window['agent' + str(i)].update('')
            window['group' + str(i)].update('')
            window['replacement' + str(i)].update('')
        else:
            window['setArea' + str(i)].update(visible=True)
            window['agent' + str(i)].update(plans[i - 1]['agent'] if len(plans) >= i else '')
            window['group' + str(i)].update(plans[i - 1]['group'] if len(plans) >= i else '')
            window['replacement' + str(i)].update(','.join(plans[i - 1]['replacement']) if len(plans) >= i else '')


def saveBtn(btn):
    plan1 = {'name': window['station_type'].get(), 'plans': []}
    for i in range(1, 6):
        agent = window['agent' + str(i)].get()
        group = window['group' + str(i)].get()
        replacement = list(filter(None, window['replacement' + str(i)].get().split(',')))
        if agent != '':
            plan1['plans'].append({'agent': agent, 'group': group, 'replacement': replacement})
    plan[btn[4:]] = plan1
    writePlan()
    loadPlan(conf['planFile'])


# 输出日志
def log(pipe):
    try:
        while True:
            msg = pipe.recv()
            println(msg)
    except EOFError:
        pipe.close()


def println(msg):
    global buffer
    global line
    global half_line_index
    maxLen = 500  # 最大行数
    buffer = f'{buffer}\n{time.strftime("%m-%d %H:%M:%S")} {msg}'.strip()
    window['log'].update(value=buffer)
    if line == maxLen // 2:
        half_line_index = len(buffer)
    if line >= maxLen:
        buffer = buffer[half_line_index:]
        line = maxLen // 2
    else:
        line += 1


# 清空输出栏
def clear():
    global buffer
    global line
    buffer = ''
    window['log'].update(value=buffer)
    line = 0


if __name__ == '__main__':
    freeze_support()
    menu()
