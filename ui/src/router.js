import { createRouter, createWebHistory } from 'vue-router';

const routes = [
  { path: '/', redirect: '/home', meta: { title: 'Redirect to Home' }, name: 'root' },
  { path: '/home', component: () => import('@/pages/Home.vue'), meta: { title: 'Home Page' }, name: 'home' },
  { path: '/plan', component: () => import('@/pages/Plan.vue'), meta: { title: 'Plan Page' }, name: 'plan' },
  {
    path: '/advancedleft',
    component: () => import('@/pages/AdvancedLeft.vue'),
    meta: { title: 'Advanced Left Page' },
    name: 'advancedleft',
    children: [
      { path: 'mower-setting', component: () => import('@/components/MowerSetting.vue'), meta: { title: 'Mower Setting Page' }, name: 'mower-setting' },
      { path: 'basement-setting', component: () => import('@/components/BasementSetting.vue'), meta: { title: 'Basement Setting Page' }, name: 'basement-setting' },
      { path: 'clue', component: () => import('@/components/Clue.vue'), meta: { title: 'Clue Page' }, name: 'clue' },
      { path: 'email', component: () => import('@/components/Email.vue'), meta: { title: 'Email Page' }, name: 'email' },
      { path: 'maa-basic', component: () => import('@/components/MAABasic.vue'), meta: { title: 'MAA Basic Page' }, name: 'maa-basic' },
      { path: 'maahugmission', component: () => import('@/components/Maahugmission.vue'), meta: { title: 'MAA Hug Mission Page' }, name: 'maahugmission' },
      { path: 'maa-weekly', component: () => import('@/components/MaaWeekly.vue'), meta: { title: 'MAA Weekly Page' }, name: 'maa-weekly' },
      { path: 'sk-land', component: () => import('@/components/SKLand.vue'), meta: { title: 'SK Land Page' }, name: 'sk-land' },
      { path: 'recruit', component: () => import('@/components/Recruit.vue'), meta: { title: 'Recruit Page' }, name: 'recruit' }
    ]
  },
  { path: '/doc', component: () => import('@/pages/Doc.vue'), meta: { title: 'Documentation Page' }, name: 'doc' },
  { path: '/record-line', component: () => import('@/pages/Record-line.vue'), meta: { title: 'Record Page-line' }, name: 'record-line' },
  { path: '/record-pine', component: () => import('@/pages/Record-pine.vue'), meta: { title: 'Record Page-pine' }, name: 'record-pine' },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
