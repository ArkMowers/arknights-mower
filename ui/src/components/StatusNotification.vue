<script setup>
import { h, onScopeDispose, onUpdated, useSlots, watch } from 'vue'
import { useNotification } from 'naive-ui'

defineOptions({ render: () => null })

const props = defineProps({
  show: { type: Boolean, default: true },
  title: { type: String, default: '' },
  type: { type: String, default: 'info' },
  role: { type: String, default: 'status' },
  content: { type: String, default: '' }
})
const emit = defineEmits(['close'])
const slots = useSlots()
const notifications = useNotification()
let current
let dismissed = false

function destroy() {
  const previous = current
  current = undefined
  previous?.destroy()
}

function syncNotification() {
  if (!props.show) {
    destroy()
    dismissed = false
    return
  }
  if (dismissed) return
  const options = {
    title: props.title,
    type: props.type,
    content: () => h('div', { role: props.role }, slots.default ? slots.default() : props.content),
    action: slots.action ? () => h('div', slots.action()) : undefined,
    duration: 0
  }
  if (current) {
    Object.assign(current, options)
    return
  }
  const entry = notifications.create({
    ...options,
    onClose: () => {
      dismissed = true
      emit('close')
    },
    onAfterLeave: () => {
      if (current === entry) {
        current = undefined
        dismissed = true
      }
    }
  })
  current = entry
}

watch(() => [props.show, props.title, props.type, props.role, props.content], syncNotification, {
  immediate: true
})

onUpdated(syncNotification)
onScopeDispose(destroy)
</script>
