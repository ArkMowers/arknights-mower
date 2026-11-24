// 骨架按上次读到的内容排版：页面读完数据后记下版面的大致形状（有没有数据、分了哪些组、
// 每组几项），下次读取时骨架照这个形状占位，读完后内容落在骨架原来的位置，不再整片移动。
// 上次没有数据时骨架也保持空白。没有记录或记录读不出时用页面给的默认形状。
const PREFIX = 'mower_skeleton_shape:'

function storage() {
  return typeof localStorage === 'undefined' ? null : localStorage
}

export function readSkeletonShape(key, fallback) {
  try {
    const saved = JSON.parse(storage()?.getItem(PREFIX + key) ?? 'null')
    if (saved && typeof saved === 'object' && !Array.isArray(saved))
      return { ...fallback, ...saved }
  } catch {
    // 记录损坏时按默认形状占位。
  }
  return { ...fallback }
}

export function saveSkeletonShape(key, shape) {
  try {
    storage()?.setItem(PREFIX + key, JSON.stringify(shape))
  } catch {
    // 存不下时下次仍用默认形状，不影响页面。
  }
}
