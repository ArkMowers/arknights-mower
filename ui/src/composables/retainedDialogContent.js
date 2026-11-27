import { shallowRef, toValue, watch } from 'vue'

/**
 * 弹窗正文按打开它的状态绘制时，状态一清空弹窗就开始淡出，正文却已经变了。返回值在状态清空后
 * 仍保留清空前的值，淡出期间标题和正文保持原样，不会先变成空白或另一种弹窗；状态重新有值时
 * 立即换成新值。
 */
export function useRetainedDialogContent(source) {
  const content = shallowRef(toValue(source))
  watch(
    source,
    (value) => {
      if (value) content.value = value
    },
    { flush: 'sync' }
  )
  return content
}
