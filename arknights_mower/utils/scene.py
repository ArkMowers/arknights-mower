from ..__init__ import __rootdir__


class Scene:
    pass


SceneComment = {}


with open(f'{__rootdir__}/data/scene', 'r') as f:
    for scene in [x.strip().split(',') for x in f.readlines()]:
        exec(f'Scene.{scene[1]} = {scene[0]}')
        SceneComment[int(scene[0])] = scene[2]
