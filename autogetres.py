import json
import shutil
import os



################
#############人名
################
key_map = {}

with open("./ArknightsGameResource/gamedata/excel/item_table.json", "r", encoding="utf-8") as f:
    item_table = json.load(f)

items_data = item_table["items"]

for i in items_data:
    iconId = items_data[i]["iconId"]
    name = items_data[i]["name"]
    classifyType = items_data[i]["classifyType"]
    source_file = f"./ArknightsGameResource/item/{iconId}.png"
    destination_file = f"./ui/public/depot/{name}.png"
    if classifyType != "NONE":
        if os.path.exists(source_file):
            shutil.copy(source_file, destination_file)
            key_map[i] = name
            print(f"Successfully copied: {source_file} to {destination_file}")
        else:
            print(f"Source file not found: {source_file}")
    else:
        print(f"{name} is {classifyType}")

with open('./arknights_mower/data/key_mapping.json', 'w', encoding="utf8") as json_file:
    json.dump(key_map, json_file, ensure_ascii=False)
##############
############头像
##############
with open(
    "./ArknightsGameResource/gamedata/excel/character_table.json",
    "r", encoding="utf-8"
) as f:
    character_table = json.load(f)


operators = []


for i in character_table:
    if not character_table[i]["itemObtainApproach"]:
        continue

    name = character_table[i]["name"]
    operators.append(name)
    source_file = f"./ArknightsGameResource/avatar/{i}.png"
    destination_file = f"./ui/public/avatar/{character_table[i]['name']}.png"
    print(f"{name}: {i}")

    shutil.copy(
        source_file,
        destination_file
    )

with open("./arknights_mower/data/agent.json", "w", encoding="utf-8") as f:
    json.dump(operators, f, ensure_ascii=False)