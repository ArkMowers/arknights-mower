from arknights_mower.data import scene_list

scene_class = "class Scene:"
scene_comment = "SceneComment = {"


for scene, data in scene_list.items():
    id = int(scene)
    label = data["label"]
    comment = data["comment"]
    scene_class += f'\n    {label} = {id}\n    "{comment}"'
    scene_comment += f'\n    {id}: "{comment}",'

scene_comment += "\n}"
code = scene_class + "\n\n\n" + scene_comment + "\n"

with open("./arknights_mower/utils/scene.py", "w", encoding="utf-8") as f:
    f.write(code)
