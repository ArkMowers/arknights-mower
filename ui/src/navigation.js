// Single navigation definition [INV-UI-04]: the desktop sidebar, the mobile tab bar and the
// mobile page drawer all render from these sections. Every page route appears exactly once.
import BarChartOutline from '@vicons/ionicons5/es/BarChartOutline'
import BookOutline from '@vicons/ionicons5/es/BookOutline'
import CalendarOutline from '@vicons/ionicons5/es/CalendarOutline'
import ConstructOutline from '@vicons/ionicons5/es/ConstructOutline'
import CubeOutline from '@vicons/ionicons5/es/CubeOutline'
import FlashOutline from '@vicons/ionicons5/es/FlashOutline'
import HelpCircleOutline from '@vicons/ionicons5/es/HelpCircleOutline'
import LibraryOutline from '@vicons/ionicons5/es/LibraryOutline'
import MedkitOutline from '@vicons/ionicons5/es/MedkitOutline'
import PieChartOutline from '@vicons/ionicons5/es/PieChartOutline'
import ReceiptOutline from '@vicons/ionicons5/es/ReceiptOutline'
import RefreshOutline from '@vicons/ionicons5/es/RefreshOutline'
import SchoolOutline from '@vicons/ionicons5/es/SchoolOutline'
import SettingsOutline from '@vicons/ionicons5/es/SettingsOutline'
import TerminalOutline from '@vicons/ionicons5/es/TerminalOutline'
import TimeOutline from '@vicons/ionicons5/es/TimeOutline'
import TrendingUpOutline from '@vicons/ionicons5/es/TrendingUpOutline'
import MowerAIIcon from './components/MowerAIIcon.vue'

// Entries carry either `to` (a registered route path) or `href` (an external https URL).
// `tab` sets an entry or section's mobile tab order under its `shortLabel`.
// Entries with the same `tabGroup` highlight that tab; sections with `items` open a page picker.
export const navigationSections = [
  {
    key: 'daily',
    title: '常用',
    items: [
      {
        key: 'log',
        label: '运行日志',
        shortLabel: '日志',
        icon: TerminalOutline,
        to: '/',
        tab: 4
      },
      {
        key: 'task-settings',
        label: '全部设置',
        shortLabel: '设置',
        icon: SettingsOutline,
        to: '/task-settings',
        tab: 1
      },
      {
        key: 'plan',
        label: '排班编辑',
        shortLabel: '排班',
        icon: CalendarOutline,
        to: '/plan-editor',
        tab: 2,
        tabGroup: 'plan'
      },
      {
        key: 'rescue-plan',
        label: '救急排班编辑',
        icon: MedkitOutline,
        to: '/rescue-plan-editor',
        sidebar: false,
        tabGroup: 'plan'
      },
      {
        key: 'mastery',
        label: '养成规划',
        shortLabel: '养成',
        icon: SchoolOutline,
        to: '/mastery-recommendation',
        tab: 3
      }
    ]
  },
  {
    key: 'reports',
    title: '数据报表',
    shortLabel: '报表',
    icon: BarChartOutline,
    tab: 5,
    items: [
      { key: 'record-line', label: '干员心情报表', icon: TrendingUpOutline, to: '/record/line' },
      { key: 'record-pie', label: '工休比报表', icon: PieChartOutline, to: '/record/pie' },
      { key: 'record-report', label: '基建报表', icon: BarChartOutline, to: '/record/report' },
      { key: 'record-depot', label: '仓库', icon: CubeOutline, to: '/record/depot' },
      {
        key: 'record-trading',
        label: '贸易订单分析',
        icon: ReceiptOutline,
        to: '/record/trading_analysis'
      },
      {
        key: 'record-recycling',
        label: '回收站材料统计',
        icon: RefreshOutline,
        to: '/record/recycling'
      },
      {
        key: 'record-log-schedule',
        label: '日志调度',
        icon: TimeOutline,
        to: '/record/log-schedule'
      }
    ]
  },
  {
    key: 'reference',
    title: '资料',
    items: [
      { key: 'basement-skill', label: '基建技能', icon: FlashOutline, to: '/BasementSkill' },
      { key: 'doc', label: '帮助文档', icon: HelpCircleOutline, to: '/doc' },
      { key: 'readme', label: '其他资源', icon: LibraryOutline, to: '/readme' },
      {
        key: 'arkntools',
        label: '明日方舟工具箱',
        icon: ConstructOutline,
        href: 'https://arkntools.app/'
      },
      {
        key: 'prts',
        label: '明日方舟PRTS',
        icon: BookOutline,
        href: 'https://prts.wiki/w/%E9%A6%96%E9%A1%B5'
      }
    ]
  }
]

export const navigationItems = navigationSections.flatMap((section) => section.items)

export const sidebarNavigationItems = [
  ...navigationItems.filter((item) => item.sidebar !== false),
  { key: 'chat', label: 'Mower AI 助手', icon: MowerAIIcon, action: 'chat', footer: true }
]

export const mobileTabs = [...navigationItems, ...navigationSections]
  .filter((item) => item.tab)
  .sort((a, b) => a.tab - b.tab)

export function mobileTabItems(tab) {
  return (
    tab.items ??
    (tab.tabGroup ? navigationItems.filter((item) => item.tabGroup === tab.tabGroup) : [tab])
  )
}
