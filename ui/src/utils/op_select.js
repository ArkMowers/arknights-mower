import { NAvatar, NTag } from 'naive-ui'
import { h } from 'vue'
import OperatorSkillTooltip from '@/components/OperatorSkillTooltip.vue'
import { operatorDisplayName } from '@/i18n/gameNames'
import { match } from 'pinyin-pro'
import { i18n } from '@/i18n'

const optionName = (option) => {
  if (option.value === 'Free') return i18n.global.t('plans.freeSlotLabel')
  if (option.value === 'Current') return i18n.global.t('plans.currentOccupantLabel')
  const translated = operatorDisplayName(option.value)
  return translated && translated !== option.value
    ? translated
    : operatorDisplayName(option.label) || translated
}

export function filterOperatorOption(pattern, option) {
  const query = String(pattern).toLocaleLowerCase()
  return [option.label, option.value, optionName(option)].some(
    (name) =>
      typeof name === 'string' &&
      (name.toLocaleLowerCase().includes(query) || Boolean(match(name, pattern)))
  )
}

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
            optionName(option)
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
      optionName(option)
    ]
  )
}

const withSkillTooltip = (option, render) =>
  h(OperatorSkillTooltip, { name: option.value || option.label }, { default: render })

export const render_op_label = renderLabel
export const render_op_option = ({ option, node }) => withSkillTooltip(option, () => node)
export const render_op_tag = renderTag
