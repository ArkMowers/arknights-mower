import os,glob
import time
import cv2
from paddleocr import PaddleOCR

import logging
logging.disable(logging.DEBUG)
logging.disable(logging.WARNING)
# 执行 adb 命令函数
def adb_cmd(cmd):
    result = os.system(cmd)
    return result
# adb 地址
adb_address = "adb -s emulator-5554"
# adb 截图
src_img = adb_address + " exec-out screencap -p > ./resource/image/%DATE:~0,4%%DATE:~8,2%%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%.png" 
# 获取 当前时间戳 函数
def to_git_time_str():
    timestamp = time.time()
    #将时间戳转换成元组
    val = time.localtime(timestamp)
    #将元组转换成字符串
    time_str= time.strftime("%Y%m%d%H%M%S",val)
    return time_str
# 截图 函数
def to_screen_img():
    # 获取时间戳
    res = to_git_time_str()
    scr_img = adb_address+ " exec-out screencap -p > ./resource/image/{res}.png".format(res=res)
    adb_cmd(scr_img)
    # 将 截图 处理成 1280*720
    path_screen = "./resource/image/"+res+".png"
    adb_img = cv2.imread(path_screen)
    adb_img_720p = cv2.resize(adb_img,(1280,720))#将截图720p化
    return adb_img_720p
# 图片模板匹配 函数
def to_macthing_img(temp_img_path):
    # 目标图片 
    time.sleep(1)
    target_img_bgr =  to_screen_img()
    target_img_gray = cv2.cvtColor(target_img_bgr,cv2.COLOR_BGR2GRAY)
    target_img = target_img_gray
    # 模板图片
    temp_img_bgr = cv2.imread(temp_img_path)
    target_img_gray = cv2.cvtColor(temp_img_bgr,cv2.COLOR_BGR2GRAY)#灰度处理
    temp_img = target_img_gray

    # 做一个 颜色匹配 不会写 写修改一下等待时间   
    # 进行匹配
    retval = cv2.matchTemplate(target_img,temp_img,method=cv2.TM_CCOEFF_NORMED)
    minval,maxval,minloc,maxloc = cv2.minMaxLoc(retval)
    h,w=temp_img.shape[::]
    return minval,maxval,minloc,maxloc,w,h
# 点击 函数 - 正常坐标点击
def click_axis(a,b):
    x = a*1.5
    y = b*1.5  
    click_cmd = adb_address +" shell input tap {x} {y}".format(x=x,y=y)
    adb_cmd(click_cmd)
# 点击 函数 - 需要传参
def click_axis_need(val,w,h):
    x = int((val[0]+w/2)*1.5)
    y = int((val[1]+h/2)*1.5)
    x1,y1=x,y
    click_cmd = adb_address +" shell input tap {x1} {y1}".format(x1=x1,y1=y1)
    adb_cmd(click_cmd)    
# 滑动 函数 - 需要传参数
def swipe_axis_need(val,w,h,l):
    # val,w,h 用于计算中心坐标 l 滑动的距离
    x = int((val[0]+w/2)*1.5)
    y = int((val[1]+h/2)*1.5)
    beginx = x 
    endx = x + l*1.5
    swipe_cmd = adb_address +" shell input swipe {beginx} {y} {endx} {y}".format(beginx=beginx,y=y,endx=endx)
    adb_cmd(swipe_cmd)

# 掉落物品匹配函数 
def to_macthing_drop(target,temp_img_path):
    # 目标图片 
    # time.sleep(1)
    # target_img_bgr =  to_screen_img()
    target_img_gray = cv2.cvtColor(target,cv2.COLOR_BGR2GRAY)
    target_img = target_img_gray
    # 模板图片
    temp_img_bgr = cv2.imread(temp_img_path)
    target_img_gray = cv2.cvtColor(temp_img_bgr,cv2.COLOR_BGR2GRAY)#灰度处理
    temp_img = target_img_gray

    # 做一个 颜色匹配 不会写 写修改一下等待时间   
    # 进行匹配
    retval = cv2.matchTemplate(target_img,temp_img,method=cv2.TM_CCOEFF_NORMED)
    minval,maxval,minloc,maxloc = cv2.minMaxLoc(retval)
    h,w=temp_img.shape[::]
    return minval,maxval,minloc,maxloc,w,h



# 匹配失败 函数
def match_failed():
    click_axis(267,39)
    time.sleep(1)
    click_axis(94,278)
    return print("返回首页")
# 返回值封装 -点击 函数
def return_click(temp_img):    
    res1,res2,res3,res4,res5,res6 = to_macthing_img(temp_img)
    # click_axis_need(res4,res5,res6) if res2 >= 0.9 else match_failed()
    if res2 >= 0.9:
        click_axis_need(res4,res5,res6)
        match_list.append(res2)
    else:
        match_list.append(0)  
        print("未知,匹配失败模板是：",temp_img)     
#  返回值封装 - 滑动 函数
def return_swipe(temp_img,l):    
    res1,res2,res3,res4,res5,res6 = to_macthing_img(temp_img)
    # click_axis_need(res4,res5,res6) if res2 >= 0.9 else match_failed()
    if res2 >= 0.9:
        swipe_axis_need(res4,res5,res6,l)
        match_list.append(res2)
    else:
        match_list.append(0)
        print("未知,匹配失败模板是：",temp_img)
# 初始化结果数组
match_list = [] # 
counter = 1 # 作战计数器
soild_num = 0 
ec_record_num = 0 
Diketone_num = 0
Source_rock_num = 0
lmb_num = 0
isoiron_debris_num = 0
gold_num = 0
Ester_raw_materials_num = 0
Sugar_substitutes_num = 0
Broken_devices_num =0
soild_list=["固源岩掉落情况："] 
ec_record_list = ["基础作战记录掉落情况："]
Diketone_list = ["双酮掉落情况："]
Source_rock_list = ["源岩掉落情况："]
lmb_list=["龙门币掉落情况："]
isoiron_debris_list= ["异铁碎片掉落情况："]
gold_list = ["赤金掉落情况："]
Ester_raw_materials_list = ["酯原料掉落情况："]
Sugar_substitutes_list = ["代糖掉落情况："]
Broken_devices_list = ["破损装置掉落情况："]
temp_list_str = ["soild","ec_record","Diketone","Source_rock","lmb","isoiron_debris","gold","Ester_raw_materials","Sugar_substitutes","Broken_devices"]
temp_list_tatal = [soild_list,ec_record_list,Diketone_list,Source_rock_list,lmb_list,isoiron_debris_list,gold_list,Ester_raw_materials_list,Sugar_substitutes_list,Broken_devices_list]
# 封装 掉落物品 函数
def drops_handle():
    # 固源岩 1 2 soild 
    # 赤金  1 gold
    # 基础作战记录 1 2 ec_record
    # 源岩 1  Source_rock
    # 酯原料 1  Ester_raw_materials
    # 代糖 1  Sugar_substitutes
    # 异铁碎片 1   isoiron_debris
    # 双酮 1 Diketone
    # 破损装置 1 Broken_devices
    # 家具  
    drops = to_screen_img()          
    for item in temp_list_str:
        temp_num = item+"_num"
        temp_list = item+"_list"
        drops_list_handle(drops,drops,item,exec(temp_num),eval(temp_list))    # exec 是不能给数组使用的 会返回空值

    # 进行封装 传入数组 
def drops_list_handle(drops,drops_img,temp_img,temp_num,temp_list):
    res1,res2,res3,res4,res5,res6 = to_macthing_drop(drops,"./resource/temp/{temp_img}.png".format(temp_img=temp_img))
    if res2 >= 0.9:       
       top_left = (res4[0], res4[1])
       centerx =  int(top_left[0] + res5/2)
       centery =  int(top_left[1] + res6/2)
       x1 = centerx - 50
       x2 = centerx + 50
       y1 = centery- 50
       y2 = centery+ 50
       cut_drops = drops_img[y1:y2,x1:x2]
       temp1 = cv2.imread("./resource/temp/num1.png")
       temp2 = cv2.imread("./resource/temp/num2.png")
       temp3 = cv2.imread("./resource/temp/seven.png")
       res1 = cv2.matchTemplate(cut_drops,temp1,cv2.TM_CCOEFF_NORMED)
       res2 = cv2.matchTemplate(cut_drops,temp2,cv2.TM_CCOEFF_NORMED)
       res3 = cv2.matchTemplate(cut_drops,temp3,cv2.TM_CCOEFF_NORMED)
       minval1,maxval1,minloc1,maxloc1 = cv2.minMaxLoc(res1)
       minval2,maxval2,minloc2,maxloc2 = cv2.minMaxLoc(res2)
       minval3,maxval3,minloc3,maxloc3 = cv2.minMaxLoc(res3)
       if maxval1>=0.9:temp_num=1
       if maxval2>=0.9:temp_num=2
       if maxval3>=0.9:temp_num=72
    #    print(temp_list,temp_num)
       temp_list.append(temp_num)
    #    print(temp_img)
       drop_name =""
       if temp_img == "soild":
            drop_name = "固源岩"
       elif temp_img =="ec_record":
            drop_name = "基础作战记录"
       elif temp_img =="Diketone":
            drop_name = "双酮"
       elif temp_img =="Source_rock":
            drop_name = "源岩"
       elif temp_img =="lmb":
            drop_name = "龙门币"
       elif temp_img =="isoiron_debris":
            drop_name = "异铁碎片"   
       elif temp_img =="gold":
            drop_name = "赤金" 
       elif temp_img =="Ester_raw_materials":
            drop_name = "酯原料"   
       elif temp_img =="Sugar_substitutes":
            drop_name = "代糖"  
       elif temp_img =="Broken_devices":
            drop_name = "破损装置"                      
       else: 
           print("未匹配到掉落物")   
       print("检测到 {drop_name} 掉落,数量是".format(drop_name=drop_name),temp_num)
# 清理文件夹下的所有文件
def to_clean():
    for file in glob.glob('D:\\my_demo\\ak-totasks\\resource\\image\\*'):
        os.remove(file)
# 递归处理函数
def to_digui(first_img,end_img):
    res1,res2,res3,res4,res5,res6 = to_macthing_img(first_img)
    if res2 >=0.9:
       print("正常作战中，等待15.5秒继续截图进行模板匹配")
       time.sleep(15.5)             
       res1,res2,res3,res4,res5,res6 = to_macthing_img(end_img)
       if res2>=0.9:                   
            time.sleep(5)
            print("作战结束,掉落物品统计-----------------------------------------------------------------------------")
            # 匹配 固源岩 
            # 先截图
            # 封装
            drops_handle()    
            return_click(end_img)
       else : 
            to_digui(first_img,end_img)
    # 没有匹配到作战结束 此时在跳转 

# 等待战斗结束 函数
def await_end(first_img,end_img):    
   print("等待画面跳转") 
   time.sleep(10)
   to_digui(first_img,end_img)
# 刷完图之后的体力识别
def reason_judge(x,y,w,h):
    time.sleep(3)
    res1,res2,res3,res4,res5,res6= to_macthing_img("./resource/temp/reason_judge.png")
    if res2>=0.9:
        # 截图 理智分析 
       current_reason = to_screen_img()
       print("作战结束，截图分析理智")
       # 将图片 进行裁剪 1121,11,78,52 "recommended roi" : [1120,9,80,52]
       x1=x
       y1=y
       x2=x1+w
       y2=y1+h
       new_screen = current_reason[y1:y2,x1:x2]
       ocr = PaddleOCR(use_angle_cls=False,ir_optim=True,use_gpu=False,lang="ch")
       result = ocr.ocr(new_screen,cls=False,det=False)       
       # 置信度
       confidence = result[0][0][1]
       if confidence >= 0.9:
           # 识别结果
            res = int(result[0][0][0].split("/")[0])
            return res
       else :
           print("理智识别失败")
           return 0
# 递归函数 循环刷1-7
def loop_despot(x,y,w,h):
    time.sleep(2) # 上来先等待5秒
    res = reason_judge(x,y,w,h)
    if res == None:
        print("识别出错了，估计是识别到了黑屏，将理智设置成30，等待下一次识别重新赋值")
        click_axis(300,200)
        res = 30
        print("当前理智：",res)
    else :
         print("当前理智：",res)   
    if res >=6:
        global counter #定义全局变量 计数器
        global soild_list
        global Diketone_list
        global ec_record_list
        print("理智大于等于6继续刷图,当前作战次数：",counter) 
        counter =counter+1  
        return_click("./resource/temp/start.png")
        return_click("./resource/temp/start_button.png")
        await_end("./resource/temp/operation.png","./resource/temp/end_action.png")
        loop_despot(x,y,w,h)         
    else:
       # 计算总掉落情况 - 
       # 将所有情况全部添加进一个合计list 然后遍历 extend
       for item in temp_list_tatal:
           if len(item)>=2:
                print(item[0])
                item.pop(0) # 移除第一项
                res = sum(item)        #    进行求和
                item.append(str(res))
                avg = res / counter
                item.append(avg)
                print(item)
       print("理智低于6,停止刷图，总共刷图次数：",counter) 
       counter = 1  
def to_despot(): # 刷1-7 函数 
    # 有无上次作战
    # 判断体力刷次数
    # 掉落物品计算
    # 从首页导航    
    print("猿神，起洞！")
    print("清理上一次任务的截图")
    to_clean()
    return_click("./resource/temp/fin.png")     #匹配成功进入终端 这里就需要进行判断
    return_click("./resource/temp/Theme_song.png") # 匹配成功进入主题曲
    return_click("./resource/temp/disillusionment.png") #匹配成功进入幻灭
    return_click("./resource/temp/arousal.png")
    return_swipe("./resource/temp/breathe.png",350)
    return_swipe("./resource/temp/Co_birth.png",350)
    return_click("./resource/temp/Dark_Ages.png")
    return_click("./resource/temp/1_7.png")
    return_click("./resource/temp/refresh.png")
    return_click("./resource/temp/one.png")
    return_click("./resource/temp/start.png")
    return_click("./resource/temp/start_button.png")
    await_end("./resource/temp/operation.png","./resource/temp/end_action.png")
    #刷图结束后 计算一下平均掉落情况
    
    # 判断理智
    loop_despot(1140,15,91,51)
     # 匹配失败 添加一个匹配机制，上述添加一个返回值，如果有一个为false，直接执行匹配失败函数,并将数组清空
    for res in match_list:
        if res == 0:
            match_list.append([])
            match_failed()
            print("存在匹配失败！即将返回首页")
            break
    #"recommended roi" : [1116,8,84,51]
# 存源石锭     Source_stone_ingot
def to_save_source_stone_ingot():
    print("猿神，起洞！")
    print("清理上一次任务的截图")
    return_click("./resource/temp/Enabling_Parameters.png") #"template" : "Enabling_Parameters.png"
to_despot()

