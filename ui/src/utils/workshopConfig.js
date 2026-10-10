import { ref } from 'vue'

const clone = (value) => JSON.parse(JSON.stringify(value))

export function createWorkshopState() {
  const workshop_settings = ref([])
  const workshop_settings_generation = ref(0)
  const workshop_manual_settings = ref([])
  const workshop_manual_settings_revision = ref(0)
  const workshop_preset_warning = ref('')

  function load_workshop_config(data) {
    workshop_preset_warning.value = data.workshop_preset_warning ?? ''
    workshop_settings.value = clone(data.workshop_settings || [])
    workshop_settings_generation.value = data.workshop_generation ?? 0
    workshop_manual_settings.value = clone(
      data.workshop_manual_settings ?? data.workshop_manual_backup ?? data.workshop_settings ?? []
    )
    workshop_manual_settings_revision.value = data.workshop_manual_revision ?? 0
  }

  function apply_workshop_response(data, submittedManual) {
    if (typeof data?.workshop_preset_warning === 'string') {
      workshop_preset_warning.value = data.workshop_preset_warning
    }
    if (data?.workshop_generation >= workshop_settings_generation.value) {
      workshop_settings_generation.value = data.workshop_generation
      workshop_settings.value = clone(data.workshop_settings)
    }
    if (
      submittedManual === undefined ||
      !Array.isArray(data?.workshop_manual_settings) ||
      data.workshop_manual_revision < workshop_manual_settings_revision.value
    ) {
      return
    }
    // A reply to an earlier edit must not discard typing done while it was saving.
    if (
      data.workshop_manual_conflict ||
      JSON.stringify(workshop_manual_settings.value) === JSON.stringify(submittedManual)
    ) {
      if (
        JSON.stringify(workshop_manual_settings.value) !==
        JSON.stringify(data.workshop_manual_settings)
      ) {
        workshop_manual_settings.value = clone(data.workshop_manual_settings)
      }
    }
    workshop_manual_settings_revision.value = data.workshop_manual_revision
  }

  return {
    workshop_settings,
    workshop_settings_generation,
    workshop_manual_settings,
    workshop_manual_settings_revision,
    workshop_preset_warning,
    load_workshop_config,
    apply_workshop_response
  }
}
