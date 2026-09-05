import { shallowRef } from 'vue'

// Preserve the native File while navigating from any page to software settings.
export const pendingSoftwarePackage = shallowRef(null)
