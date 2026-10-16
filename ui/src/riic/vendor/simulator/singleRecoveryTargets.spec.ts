import { afterEach, expect, it, vi } from 'vitest'
import { createDefaultWorkspace } from '../workbench/defaults'
import { compileRosterSchedule } from '../scheduler/compileRosterSchedule'
import { simulateSchedule, type ScheduleSimulationOptions } from './scheduleSimulation'
import { resolveOperatorCharId } from '../domain/operatorIdentifiers'
import * as recovery from '../scheduler/mowerDormRecovery'

const id = resolveOperatorCharId
function run(
  moods: Record<string, number>,
  { names = ['闪灵', '芬', '香草', '翎羽', '菲亚梅塔'], confirmed, ...options }: ScheduleSimulationOptions & { names?: string[]; confirmed?: string } = {}
) {
  const workspace = createDefaultWorkspace()
  workspace.mainPlan.facilities.dormitory_1.level = 5
  workspace.mainPlan.facilities.dormitory_1.slots = names.map((name) => ({
    occupant: { kind: 'operator', operatorId: name },
    groupId: null,
    replacements: []
  }))
  if (confirmed)
    vi.spyOn(recovery, 'mowerConfirmedRecoveryTargets').mockReturnValue(
      new Map([['dormitory_1', new Map([[id('闪灵'), id(confirmed)]])]])
    )
  const schedule = compileRosterSchedule(workspace, {
    operatorMorale: Object.fromEntries(
      Object.entries(moods).map(([name, mood]) => [id(name), mood])
    )
  })
  const report = simulateSchedule(schedule, {
    schedulingModel: 'mower-alpha',
    sampleHours: 0.1,
    maxStepHours: 0.05,
    ...options
  })
  expect(report.success, JSON.stringify(report.diagnostics)).toBe(true)
  return Object.fromEntries(report.operators.map((op) => [op.operatorName, op.finalMorale]))
}
afterEach(() => vi.restoreAllMocks())

it('gives unconfirmed recovery to the lowest-morale eligible resident instead of the first slot', () => {
  const result = run({ 芬: 15, 香草: 5, 翎羽: 10 })
  expect(result.芬).toBeCloseTo(15.4, 7)
  expect(result.香草).toBeCloseTo(5.475, 7)
  expect(result.翎羽).toBeCloseTo(10.4, 7)
})
it('preserves a valid confirmed target even when another resident has lower morale', () => {
  const result = run({ 芬: 15, 香草: 5 }, { confirmed: '芬' })
  expect(result.芬).toBeCloseTo(15.475, 7)
  expect(result.香草).toBeCloseTo(5.4, 7)
})
it.each(['满心情', '已离宿'])(
  'chooses the lowest eligible morale when the confirmed target is %s',
  (kind) => {
    const result = run(
      { 芬: kind === '满心情' ? 24 : 15, 香草: 5, 翎羽: 10 },
      { confirmed: kind === '满心情' ? '芬' : '黑键' }
    )
    expect(result.香草).toBeCloseTo(5.475, 7)
    expect(result.翎羽).toBeCloseTo(10.4, 7)
  }
)
it('excludes the provider and Fiammetta even when their morale is lower', () => {
  const result = run({ 闪灵: 0, 菲亚梅塔: 0, 芬: 15, 香草: 5 })
  expect(result.闪灵).toBeCloseTo(0.4, 7)
  expect(result.菲亚梅塔).toBeCloseTo(0.2, 7)
  expect(result.香草).toBeCloseTo(5.475, 7)
})
it('uses slot order only to break an equal-morale tie', () => {
  const result = run({ 芬: 5, 香草: 5 })
  expect(result.芬).toBeCloseTo(5.475, 7)
  expect(result.香草).toBeCloseTo(5.4, 7)
})

it.each([0.05, 0.25, 1])(
  'keeps the selected automatic target across morale crossings, step=%s',
  (maxStepHours) => {
    const result = run({ 芬: 5.01, 香草: 5 }, { sampleHours: 3, maxStepHours })
    expect(result.芬).toBeCloseTo(17.01, 7)
    expect(result.香草).toBeCloseTo(19.25, 7)
  }
)
it.each([0.05, 0.25, 1])(
  'selects a new lowest-morale target after the automatic target fills, step=%s',
  (maxStepHours) => {
    const result = run({ 芬: 5.01, 香草: 5 }, { sampleHours: 4.2, maxStepHours })
    expect(result.香草).toBe(24)
    expect(result.芬).toBeCloseTo(21.96, 7)
  }
)

it('retains explicit target override precedence over confirmation and automatic selection', () => {
  const result = run(
    { 芬: 15, 香草: 5, 翎羽: 10 },
    {
      confirmed: '芬',
      recoveryTargetByProvider: { [id('闪灵')]: id('翎羽') }
    }
  )
  expect(result.芬).toBeCloseTo(15.4, 7)
  expect(result.香草).toBeCloseTo(5.4, 7)
  expect(result.翎羽).toBeCloseTo(10.475, 7)
})


it.each(['automatic', 'confirmed', 'explicit'] as const)(
  'does not retain a single-provider target among multiple unfinished recipients: %s',
  mode => {
    const result=run({深靛:1,芬:15},{
      names:['闪灵','深靛','芬'],
      confirmed:mode==='confirmed'?'深靛':undefined,
      recoveryTargetByProvider:mode==='explicit'?{[id('闪灵')]:id('深靛')}:undefined,
    })
    expect(result.深靛).toBeCloseTo(1.4,7)
    expect(result.芬).toBeCloseTo(15.475,7)
  },
)
it('allows another single provider as the sole unfinished recipient, ignoring full residents and Fiammetta',()=>{
  const result=run({深靛:1,菲亚梅塔:0},{names:['闪灵','深靛','芬','菲亚梅塔']})
  expect(result.深靛).toBeCloseTo(1.475,7)
  expect(result.菲亚梅塔).toBeCloseTo(.2,7)
})
it('rejects an explicit self target even when raw text does not exclude self',()=>{
  const result=run({深靛:1,芬:15},{names:['深靛','芬'],recoveryTargetByProvider:{[id('深靛')]:id('深靛')}})
  expect(result.深靛).toBeCloseTo(1.4,7)
  expect(result.芬).toBeCloseTo(15.455,7)
})

it.each(['automatic','confirmed'] as const)('transfers %s single recovery after an ordinary resident actually enters the dorm',mode=>{
  const workspace=createDefaultWorkspace()
  for(const room of Object.values(workspace.mainPlan.facilities)){room.level=0;room.slots=[]}
  const slot=(name:string)=>({occupant:{kind:'operator' as const,operatorId:name},groupId:null,replacements:[]})
  const dorm=workspace.mainPlan.facilities.dormitory_1
  dorm.level=5;dorm.slots=['闪灵','深靛','香草'].map(slot)
  const work=workspace.mainPlan.facilities.room_1_1
  work.level=3;work.product='gold';work.slots=[slot('芬')]
  workspace.mainPlan.conf.workaholic=['芬','香草']
  const plans=(names:string[])=>({plans:names.map(agent=>({agent,group:'',replacement:[]}))})
  workspace.compatibility.backupPlans=[{
    name:'ordinary resident enters',trigger:"op_data.operators['深靛'].current_mood() >= 3",
    plan:{dormitory_1:plans(['闪灵','深靛','芬']),room_1_1:plans(['香草'])},
  }]
  if(mode==='confirmed')vi.spyOn(recovery,'mowerConfirmedRecoveryTargets').mockReturnValue(new Map([['dormitory_1',new Map([[id('闪灵'),id('深靛')]])]]))
  const schedule=compileRosterSchedule(workspace,{operatorMorale:{[id('深靛')]:1,[id('芬')]:15}})
  const report=simulateSchedule(schedule,{schedulingModel:'mower-alpha',sampleHours:4,maxStepHours:.05,recordSegments:true,production:{droneTarget:'none'},consumptionOverrides:{[id('芬')]:1,[id('香草')]:1}})
  expect(report.success,JSON.stringify(report.diagnostics)).toBe(true)
  const activated=report.events.find(event=>event.type==='backup-plan'&&event.active)
  expect(activated).toBeDefined()
  expect(activated!.time).toBeGreaterThan(0)
  const dormNames=(segment:typeof report.segments[number])=>Object.entries({...segment.occupants,...segment.bedOccupants}).filter(([position])=>position.startsWith('dormitory_1_')).map(([,name])=>name)
  const intervals=report.segments.flatMap((segment,index)=>{
    const next=report.segments[index+1]
    if(!next||segment.end-segment.start<1e-4||Math.abs(segment.end-next.start)>1e-8)return []
    const names=dormNames(segment),nextNames=dormNames(next)
    if(names.join(',')!==nextNames.join(','))return []
    return [{names,start:segment.start,indigo:(next.morale[id('深靛')]!-segment.morale[id('深靛')]!)/(segment.end-segment.start),fang:(next.morale[id('芬')]!-segment.morale[id('芬')]!)/(segment.end-segment.start)}]
  })
  const before=intervals.find(interval=>!interval.names.includes(id('芬')))
  const after=intervals.find(interval=>interval.names.includes(id('芬')))
  expect(before).toBeDefined();expect(after).toBeDefined()
  expect(before!.indigo).toBeCloseTo(4.75,7)
  expect(after!.start).toBeGreaterThan(before!.start)
  expect(after!.indigo).toBeCloseTo(4,7)
  expect(after!.fang).toBeCloseTo(4.75,7)
})
