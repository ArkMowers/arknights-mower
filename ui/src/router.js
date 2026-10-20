import { createRouter, createWebHistory } from 'vue-router'
import { routes } from '@/routes'
import { sessionLocation } from '@/utils/sessionNavigation'

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from) => {
  const destination = sessionLocation(to, from)
  if (destination !== to) return destination
})

export default router
