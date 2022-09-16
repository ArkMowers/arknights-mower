import json
import os

import fontforge
import requests

proxies = {'http': 'http://localhost:11223'}
datadir = 'arknights_mower/data/'
GitHubURL = 'https://raw.githubusercontent.com/Kengxxiao/ArknightsGameData/master/zh_CN/gamedata/'


def dump(data, filename):
    with open(datadir + filename, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=4, default=str)


def requests_get(path):
    return requests.get(GitHubURL + path, proxies=proxies).text


agent = []
character_table = json.loads(requests_get('excel/character_table.json'))
for x in character_table.values():
    if x['displayNumber'] is not None:
        agent.append(x['name'].strip())
dump(agent, 'agent.json')

agent_charset = set(''.join(agent))
Chinese, unChinese = [], []
for c in agent_charset:
    if ord(c) < 256:
        unChinese.append(c)
    else:
        Chinese.append(c)
with open('build/Chinese.txt', 'w') as f:
    f.write(''.join(Chinese))
with open('build/unChinese.txt', 'w') as f:
    f.write(''.join(unChinese))

command = 'java.exe -jar FontPruner/sfnttool.jar -c build/Chinese.txt  build/unChinese.txt FontPruner/SourceHanSansSC-Bold.ttf build/SourceHanSansSC-Bold.ttf'
if os.system(command) is False:
    raise Exception('build new font error!' + command)


ttf_file = 'build/SourceHanSansSC-Bold.ttf'
otf_file = 'arknights_mower/fonts/SourceHanSansSC-Bold.otf'

font = fontforge.open(ttf_file)
font.generate(otf_file)
font.close()


chapter = []
chapter_table = json.loads(requests_get('excel/chapter_table.json'))
for x in chapter_table.values():
    chapter.append(x['chapterName2'])
dump(chapter, 'chapter.json')


level = {}
zone = {}

zone_table = json.loads(requests_get('excel/zone_table.json'))
chapterIndex = -1
for x in zone_table['zones'].values():
    if x['type'] == 'MAINLINE':
        if x['zoneIndex'] == 0:
            chapterIndex += 1
        zone[x['zoneID']] = {
            'type': x['type'],
            'name': x['zoneNameSecond'],
            'chapterIndex': chapterIndex,
            'zoneIndex': int(x['zoneID'].split('_')[1]),
        }
    elif x['type'] == 'WEEKLY':
        zone[x['zoneID']] = {
            'type': x['type'],
            'name': x['zoneNameSecond'],
            'chapterIndex': None,
            'zoneIndex': None,
        }

stage_table = json.loads(requests_get('excel/stage_table.json'))
for x in stage_table['stages'].values():
    if (
        x['zoneId'] in zone.keys()
        and x['canBattleReplay']
        and not x['levelId'].startswith('Activities')
    ):
        level[x['code']] = {
            'zone_id': x['zoneId'],
            'ap_cost': x['apCost'],
            'code': x['code'],
            'name': x['name'],
        }

retro_table = json.loads(requests_get('excel/retro_table.json'))
for x in retro_table['retroActList'].values():
    if x['type'] == 1:
        zone[x['retroId']] = {
            'type': 'BRANCHLINE',
            'name': x['name'],
            'chapterIndex': None,
            'zoneIndex': x['index'],
        }
    elif x['type'] == 0:
        zone[x['retroId']] = {
            'type': 'SIDESTORY',
            'name': x['name'],
            'chapterIndex': None,
            'zoneIndex': x['index'],
        }
zoneToRetro = retro_table['zoneToRetro']
for x in retro_table['stageList'].values():
    if x['hardStagedId'] is None and x['canBattleReplay'] and x['zoneId'].endswith('1') and x['zoneId'] in zoneToRetro.keys():
        level[x['code']] = {
            'zone_id': zoneToRetro[x['zoneId']],
            'ap_cost': x['apCost'],
            'code': x['code'],
            'name': x['name'],
        }

dump(zone, 'zone.json')
dump(level, 'level.json')
