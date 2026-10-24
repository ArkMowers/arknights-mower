import { ref, watch } from 'vue'
import { createUpdateProgressSession } from '@/utils/updateProgress'

export function useUpdateProgress(job) {
  const receive = createUpdateProgressSession()
  const visible = ref(false)
  watch(
    job,
    (value) => {
      visible.value = receive(value)
    },
    { immediate: true, deep: true, flush: 'sync' }
  )
  return visible
}
