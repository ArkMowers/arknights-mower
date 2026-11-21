import {simulationActivityFindings,type SimulationActivityFinding} from './simulationActivityFindings'
import type {RuntimeState, RuntimeEvent} from '../scheduler/rosterRuntime'
import {OPERATOR_MAP} from '../domain/operators'
import type {MowerTask} from '../scheduler/mowerTaskQueue'

export interface SimulationActivity {
  findings?: SimulationActivityFinding[]
  status: 'running' | 'slow'
  message: string
  capturedHours: number
  windowSeconds: number
  advancedHours: number
  iterations: number
  operators: {id: string; name: string; morale: number; upperLimit: number; groups: string[]; room: string; eventCount: number}[]
  recentEvents: {label: string; count: number}[]
  task?: {label: string; metadata: string; rooms: string[]; dueHours: number; source: 'active' | 'queued'}
}

const labels: Record<RuntimeEvent['type'], string> = {
  'shift-off': '下班', 'shift-on': '上班', fiammetta: '菲亚充能', 'backup-plan': '副表切换',
  'backup-task': '副表安排', 'rest-limit-release': '宿舍清退', 'rest-bed-takeover': '床位接替', 'exhaust-support': '耗尽协助',
}
const WINDOW_MS = 15_000
const HEARTBEAT_MS = 1_000

/** Read-only, bounded wall-clock observations. Slow progress identifies activity, not its cause. */
export function createSimulationActivityMonitor(now: () => number = () => performance.now()) {
  let lastCapture = -Infinity, eventCursor = 0
  const samples: {wall: number; hours: number; iterations: number}[] = []
  const events: {wall: number; event: RuntimeEvent}[] = []
  let latest: SimulationActivity | undefined
  return {
    capture(state: RuntimeState, iterations: number): SimulationActivity | undefined {
      const wall = now()
      if (wall - lastCapture < HEARTBEAT_MS) return undefined
      lastCapture = wall
      // Only inspect a bounded tail even if a single native dispatch emitted many events.
      for (let index = Math.max(eventCursor, state.events.length - 256); index < state.events.length; index++) {
        events.push({wall, event: state.events[index]!})
      }
      eventCursor = state.events.length
      while (events.length > 256 || events[0] && events[0].wall < wall - WINDOW_MS) events.shift()
      samples.push({wall, hours: state.time, iterations})
      while (samples.length > 2 && samples[1]!.wall <= wall - WINDOW_MS) samples.shift()
      const first = samples[0]!, seconds = (wall - first.wall) / 1000
      const advanced = Math.max(0, state.time - first.hours)
      const slow = seconds >= WINDOW_MS / 1000 && advanced < .25
      const counts = new Map<string, number>(), kinds = new Map<string, number>()
      for (const {event} of events) {
        const label = labels[event.type] + (event.backupName ? `：${event.backupName}` : '')
        kinds.set(label, (kinds.get(label) ?? 0) + 1)
        for (const id of new Set(event.operators)) counts.set(id, (counts.get(id) ?? 0) + 1)
      }
      const source = state.mowerSource
      const active = source?.activeTask ?? source?.execution?.task
      const task = active ?? source?.queue.tasks.reduce<MowerTask | undefined>((earliest, entry) => !earliest || entry.time < earliest.time ? entry : earliest, undefined)
      const findings=simulationActivityFindings(state,events.map(item=>item.event))
      const ids = [...new Set([...findings.filter(finding=>finding.kind==='constraint').flatMap(finding=>finding.operatorIds),...[...counts].sort((a, b) => b[1] - a[1]).map(([id]) => id)])]
      if (task) for (const id of [...Object.values(task.plan).flat(), ...task.metadata.split(',')]) {
        if (id in state.morale && !ids.includes(id)) ids.push(id)
      }
      latest = {
        findings: findings.length?findings:undefined,
        status: slow ? 'slow' : 'running',
        message: slow ? '演算推进较慢。以下是最近涉及的干员与任务，仅供排查，尚不能确定是哪位干员或配置导致。' : '演算正在推进。',
        capturedHours: state.time, windowSeconds: seconds, advancedHours: advanced,
        iterations: Math.max(0, iterations - first.iterations),
        operators: ids.slice(0, 5).map(id => {
          const op = source?.data.operators[id], position = state.config.positions.find(p => p.primary === id)
          const room = op?.currentRoom || Object.entries({...state.occupants, ...state.bedOccupants}).find(([, name]) => name === id)?.[0].replace(/_\d+$/, '') || ''
          return {id, name: OPERATOR_MAP.get(id)?.name ?? op?.nativeName ?? id, morale: state.morale[id] ?? 0,
            upperLimit: op?.upperLimit ?? position?.upperLimit ?? state.config.mowerPolicy?.restMoodLimits?.[id] ?? 24,
            groups: [...new Set([op?.group ?? position?.group ?? '', ...(op?.groupBindings.map(binding => binding.group) ?? [])].filter(Boolean))],
            room, eventCount: counts.get(id) ?? 0}
        }),
        recentEvents: [...kinds].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([label, count]) => ({label, count})),
        task: task ? {label: task.type.key === 'FIAMMETTA' ? '菲亚充能' : task.type.displayValue,
          metadata: task.metadata.split(/([,\s]+)/).map(value => OPERATOR_MAP.get(value)?.name ?? value).join(''), rooms: Object.keys(task.plan), dueHours: task.time, source: active ? 'active' : 'queued'} : undefined,
      }
      return latest
    },
    get latest() { return latest },
  }
}
