import json
from pathlib import Path

from .. import __rootdir__

# agents list in Arknights
agent_list = json.loads(
    Path(f'{__rootdir__}/data/agent.json').read_text('utf-8'))

# # agents base skills
# agent_base_config = json.loads(
#     Path(f'{__rootdir__}/data/agent-base.json').read_text('utf-8'))

# name of each room in the basement
base_room_list = json.loads(
    Path(f'{__rootdir__}/data/base.json').read_text('utf-8'))


# the camps to which the clue belongs
clue_name = json.loads(
    Path(f'{__rootdir__}/data/clue.json').read_text('utf-8'))


# goods sold in shop
shop_items = json.loads(
    Path(f'{__rootdir__}/data/shop.json').read_text('utf-8'))


# collection of the obtained ocr error
ocr_error = json.loads(
    Path(f'{__rootdir__}/data/ocr.json').read_text('utf-8'))


# chapter name in English
chapter_list = json.loads(
    Path(f'{__rootdir__}/data/chapter.json').read_text('utf-8'))


# list of supported levels
level_list = json.loads(
    Path(f'{__rootdir__}/data/level.json').read_text('utf-8'))


# open zones
zone_list = json.loads(
    Path(f'{__rootdir__}/data/zone.json').read_text('utf-8'))


# list of supported weekly levels
weekly_zones = json.loads(
    Path(f'{__rootdir__}/data/weekly.json').read_text('utf-8'))


# list of scene defined
scene_list = json.loads(
    Path(f'{__rootdir__}/data/scene.json').read_text('utf-8'))


# recruit database
recruit_agent = json.loads(
    Path(f'{__rootdir__}/data/recruit.json').read_text('utf-8'))

recruit_tag = ['资深干员', '高级资深干员']
for x in recruit_agent.values():
    recruit_tag += x['tags']
recruit_tag = list(set(recruit_tag))
