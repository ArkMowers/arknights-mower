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
        path: 'task-settings',
        component: () => import('@/pages/TaskSettings.vue'),
        meta: { title: '全部设置' },
        name: 'task-settings'
      },
      {
        path: 'plan-editor',
        component: () => import('@/pages/Plan.vue'),
        meta: { title: '排班' },
        name: 'plan'
      },
      {
        path: 'rescue-plan-editor',
        component: () => import('@/pages/RescuePlan.vue'),
        meta: { title: '救急排班' },
        name: 'rescue_plan'
      },
      {
        path: 'mowersettings',
        redirect: (to) => ({ name: 'task-settings', query: to.query, hash: to.hash }),
        name: 'mowersettings'
      },
      {
        path: 'maasettings',
        redirect: (to) => ({ name: 'task-settings', query: to.query, hash: to.hash }),
        name: 'maasettings'
      },
      // PROTOTYPE：任务编排原型，选定方案后删除
      ...(import.meta.env.DEV
        ? [
            {
              path: 'taskflow-prototype',
              component: () => import('@/pages/taskflow-prototype/TaskflowPrototype.vue'),
              meta: { title: '任务编排原型' },
              name: 'taskflow-prototype'
            }
          ]
        : []),
      {
        path: 'doc',
        component: () => import('@/pages/Doc.vue'),
        meta: { title: '文档' },
        name: 'doc'
      },
      {
        path: 'mastery-recommendation',
        component: () => import('@/pages/MasteryRecommendation.vue'),
        meta: { title: '养成规划' },
        name: 'mastery_recommendation'
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
          },
          {
            path: 'recycling',
            component: () => import('@/pages/RecyclingStats.vue'),
            meta: { title: '回收站材料统计' },
            name: 'recycling'
          },
          {
            path: 'log-schedule',
            component: () => import('@/pages/LogSchedule.vue'),
            meta: { title: '日志调度' },
            name: 'log_schedule'
          }
        ]
      }
    ]
  },
  { path: '/:pathMatch(.*)', component: () => import('@/pages/NotFound.vue') }
]
