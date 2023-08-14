#!Environment yolov8_Env
# -*- coding: UTF-8 -*-
"""
@Project ：arknights-mower 
@File    ：recruit.py
@Author  ：EightyDollars
@Date    ：2023/8/13 19:12
"""
from arknights_mower.utils.log import logger


def filter_result(tag_list, result_list, type=0):
    """
    temp_list
    {"tags": tag,
     "level":item['level'],
     "opers":item['opers']}
    """
    temp_list = []
    for tag in tag_list:
        logger.debug(tag)
        for result_dict in result_list:
            for item in result_dict["result"]:
                '''高资'''
                if type == 0:
                    if tag == result_dict['tags'] and item['level'] == result_dict['level']:
                        temp_list.append(item)
                elif type == 1:
                    if tag == item['tags']:
                        temp_list.append(
                            {"tags": tag,
                             "level": item['level'],
                             "opers": item['opers']})

    # 筛选好干员和对应tag存入返回用于后续jinja传输
    # logger.debug(temp_list)
    return temp_list
