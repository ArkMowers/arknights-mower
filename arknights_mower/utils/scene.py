from ..data import scene_list


class Scene:
    pass


SceneComment = {}


for scene in scene_list.keys():
    id = int(scene)
    label = scene_list[scene]['label']
    comment = scene_list[scene]['comment']
    setattr(Scene, label, id)
    SceneComment[id] = comment
