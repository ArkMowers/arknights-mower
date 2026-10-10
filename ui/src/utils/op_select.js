import { NAvatar, NTag } from 'naive-ui'
import { h } from 'vue'
import OperatorSkillTooltip from '@/components/OperatorSkillTooltip.vue'

const renderTag = ({ option, handleClose }) => {
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
              src: 'avatar/' + option.value + '.webp',
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

const renderLabel = (option) => {
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
        src: 'avatar/' + option.value + '.webp',
        round: true,
        size: 'small',
        style: {
          flexShrink: 0
        }
      }),
      option.label
    ]
  )
}

const withSkillTooltip = (option, render) =>
  h(OperatorSkillTooltip, { name: option.label || option.value }, { default: render })

export const render_op_label = renderLabel
export const render_op_option = ({ option, node }) => withSkillTooltip(option, () => node)
export const render_op_tag = renderTag
