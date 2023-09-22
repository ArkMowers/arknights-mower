export const routes = [
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
        path: 'Advanced',
        component: () => import('@/pages/Advanced.vue'),
        meta: { title: '设置' },
        name: 'Advanced'
      },
      {
        path: 'External',
        component: () => import('@/pages/External.vue'),
        meta: { title: '任务设置' },
        name: 'External'
      },
      {
        path: 'MaaWeeklynew1',
        component: () => import('@/components/MaaWeeklynew1.vue'),
        meta: { title: '任务设置' },
        name: 'MaaWeeklynew1'
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
    component: () => import('@/pages/recordline.vue'),
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
