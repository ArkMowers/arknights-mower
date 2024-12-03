export const routes = [
  {
    path: '/',
    children: [
      {
        path: 'readme',
        component: () => import('@/pages/readme.vue'),
        meta: { title: '帮助' },
        name: 'readme'
      },
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
        path: 'aio',
        component: () => import('@/pages/Material_all_in_one.vue'),
        meta: { title: '设置' },
        name: 'aio'
      },
      {
        path: 'doc',
        component: () => import('@/pages/Doc.vue'),
        meta: { title: '文档' },
        name: 'doc'
      },
      {
        path: 'BasementSkill',
        component: () => import('@/pages/BasementSkill.vue'),
        meta: { title: '基建技能' },
        name: 'BasementSkill'
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
          },
          {
            path: 'report',
            component: () => import('@/pages/report.vue'),
            meta: { title: '基建报告' },
            name: 'report'
          },
          {
            path: 'trading_analysis',
            component: () => import('@/pages/trading_analysis.vue'),
            meta: { title: '贸易订单分析' },
            name: 'trading_analysis'
          }
        ]
      }
    ]
  },
  { path: '/:pathMatch(.*)', component: () => import('@/pages/NotFound.vue') }
]
