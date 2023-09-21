import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/home', meta: { title: 'Redirect to Home' }, name: 'root' },
  {
    path: '/home',
    component: () => import('@/pages/Home.vue'),
    meta: { title: 'Home Page' },
    name: 'home'
  },
  {
    path: '/plan',
    component: () => import('@/pages/Plan.vue'),
    meta: { title: 'Plan Page' },
    name: 'plan'
  },
  {
    path: '/setting',
    meta: { title: '设置' },
    children: [
      {
        path: 'allsetting',
        component: () => import('@/pages/allsetting.vue'),
        meta: { title: '全部设置' },
        name: 'allsetting'
      },
      {
        path: 'mower-setting',
        component: () => import('@/components/MowerSettings.vue'),
        meta: { title: 'Mower Setting Page' },
        name: 'mower-setting'
      },
      {
        path: 'basement-setting',
        component: () => import('@/components/BasementSettings.vue'),
        meta: { title: 'Basement Setting Page' },
        name: 'basement-setting'
      },
      {
        path: 'clue',
        component: () => import('@/components/Clue.vue'),
        meta: { title: 'Clue Page' },
        name: 'clue'
      },
      {
        path: 'email',
        component: () => import('@/components/Email.vue'),
        meta: { title: 'Email Page' },
        name: 'email'
      },
      {
        path: 'maa-basic',
        component: () => import('@/components/MaaBasic.vue'),
        meta: { title: 'MAA Basic Page' },
        name: 'maa-basic'
      },
      {
        path: 'maahugmission',
        component: () => import('@/components/Maahugmission.vue'),
        meta: { title: 'MAA Hug Mission Page' },
        name: 'maahugmission'
      },
      {
        path: 'maa-weekly',
        component: () => import('@/components/MaaWeekly.vue'),
        meta: { title: 'MAA Weekly Page' },
        name: 'maa-weekly'
      },
      {
        path: 'maa-xinyi',
        component: () => import('@/components/MaaWeeklynew1.vue'),
        meta: { title: '新一' },
        name: 'xinyi'
      },
      {
        path: 'maa-xiner',
        component: () => import('@/components/MaaWeeklynew2.vue'),
        meta: { title: '新二' },
        name: 'xiner'
      },
      {
        path: 'sk-land',
        component: () => import('@/components/SKLand.vue'),
        meta: { title: 'SK Land Page' },
        name: 'sk-land'
      },
      {
        path: 'recruit',
        component: () => import('@/components/Recruit.vue'),
        meta: { title: 'Recruit Page' },
        name: 'recruit'
      }
    ]
  },
  {
    path: '/doc',
    component: () => import('@/pages/Doc.vue'),
    meta: { title: 'Documentation Page' },
    name: 'doc'
  },
  {
    path: '/record-line',
    component: () => import('@/pages/RecordLine.vue'),
    meta: { title: 'Record Page-line' },
    name: 'record-line'
  },
  {
    path: '/record-pie',
    component: () => import('@/pages/RecordPie.vue'),
    meta: { title: 'Record Page-pie' },
    name: 'record-pie'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
