export const routes = [
  {
    path: '/',
    children: [
      {
        path: '',
        component: () => import('@/pages/Log.vue'),
        meta: { title: '日志' },
        name: 'log'
      },
      {
        path: 'plan-editor',
        component: () => import('@/pages/Plan.vue'),
        meta: { title: '排班' },
        name: 'plan'
      },
      {
        path: 'settings',
        component: () => import('@/pages/Settings.vue'),
        meta: { title: '设置' },
        name: 'settings'
      },
      {
        path: 'doc',
        component: () => import('@/pages/Doc.vue'),
        meta: { title: '文档' },
        name: 'doc'
      },
      {
        path: 'record',
        children: [
          {
            path: 'line',
            component: () => import('@/pages/RecordLine.vue'),
            meta: { title: '心情曲线' },
            name: 'record_line'
          },
          {
            path: 'depot',
            component: () => import('@/pages/depot.vue'),
            meta: { title: '仓库数据' },
            name: 'depot'
          },
          {
            path: 'pie',
            component: () => import('@/pages/RecordPie.vue'),
            meta: { title: '心情饼图' },
            name: 'record_pie'
          }
        ]
      }
    ]
  }
]
