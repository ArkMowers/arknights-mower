import { createRouter, createWebHistory } from 'vue-router'
import { routes } from '@/routes'

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from) => {
  if (from.query.token && !to.query.token) {
    return {
      path: to.path,
      query: from.query
    }
  }
})

export default router
