from ..data.scene import scene_list


class Scene:
    pass


SceneComment = {}


for scene in scene_list:
    setattr(Scene, scene[1], scene[0])
    SceneComment[scene[0]] = scene[2]
