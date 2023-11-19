import { NAvatar, NTag } from 'naive-ui'
import { h } from 'vue'

export const render_op_tag = ({ option, handleClose }) => {
  return h(
    NTag,
    {
      style: {
        padding: '0 6px 0 4px'
      },
      round: true,
      closable: true,
      onClose: (e) => {
        e.stopPropagation()
        handleClose()
      }
    },
    {
      default: () =>
        h(
          'div',
          {
            style: {
              display: 'flex',
              alignItems: 'center'
            }
          },
          [
            h(NAvatar, {
              src: 'avatar/' + option.value + '.png',
              round: true,
              size: 22,
              style: {
                marginRight: '4px'
              }
            }),
            option.label
          ]
        )
    }
  )
}

export const render_op_label = (option) => {
  return h(
    'div',
    {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: '12px'
      }
    },
    [
      h(NAvatar, {
        src: 'avatar/' + option.value + '.png',
        round: true,
        size: 'small'
      }),
      option.label
    ]
  )
}
