from pathlib import Path
import platformdirs
import sys, os


appname = 'arknights_mower'
appauthor = 'ArkMower'
global_space = None


def find_git_root(directory: Path) -> Path:
    if (directory / ".git").is_dir():
        return directory
    elif directory == directory.parent:
        return None
    else:
        return find_git_root(directory.parent)


user_data_dir = Path(platformdirs.user_data_dir(appname, appauthor))
# define _app_dir
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    _internal_dir = Path(sys._MEIPASS).resolve()
    _app_dir = _internal_dir.parent
else:
    _app_dir = find_git_root(Path(os.getcwd()).resolve())
    if not _app_dir:
      _app_dir = Path(os.getcwd()).resolve()
    _internal_dir = _app_dir


def _get_path(base_path, path, space)->Path:
  if space:
    return Path(base_path) / space / path
  else:
    return Path(base_path) / path


def get_app_path(path, space = None)->Path:
  global global_space
  if space == None: # 不用 not space 是因为 not '' == True
    space = global_space
  return _get_path(_app_dir, path, space)

def get_internal_path(path, space = None)->Path:
  global global_space
  if space == None:
    space = global_space
  return _get_path(_internal_dir, path, space)

def get_user_path(path, space = None)->Path:
  global global_space
  if space == None:
    space = global_space
  return _get_path(user_data_dir, path, space)


def get_path(path: str, space = None)->Path:
  """
  使用 '@xxx/' 来表示一些特别的目录
  @user: 用户数据文件夹, 例如 get_path('@user/config.json')
  @app: mower数据文件夹, 例如 get_path('@app/logs/runtime.log')
  @internal: mower内部文件夹, 在开发时为 .git 所在目录, 打包时为 @app/_internal
  
  指定space来区分配置文件空间，如space为None(默认值)，则使用global_space
  
  特别的，如果要覆盖global_space并指定默认目录，使用space=''
  """
  global global_space
  if space == None:
    space = global_space
  path = path.replace('\\', '/')
  
  
  if isinstance(path, str) and path.startswith('@'):
    index = path.find('/')
    index = index if index != -1 else len(path)
    special_dir_name = path[1:index]
    relative_path = path[index:].strip('/')
    if special_dir_name == 'user':
      return get_user_path(relative_path, space)
    elif special_dir_name == 'app':
      return get_app_path(relative_path, space)
    elif special_dir_name == 'internal':
      return get_internal_path(relative_path, space)
    else:
      raise ValueError('{}: {} 不是一个有效的特殊目录别名'.format(path, special_dir_name))
  else:
    return Path(path)
    # raise ValueError("{} 路径必须以 '@xxx' 开头".format(path))
    
    
class SpecialDir:
    def __init__(self, method):
        self.method = method

    def __truediv__(self, path) -> Path:
      return self.method(path, None)
    
    def __str__(self):
      return str(self.method('', None))


user_dir = SpecialDir(get_user_path)
app_dir = SpecialDir(get_app_path)
internal_dir = SpecialDir(get_internal_path)