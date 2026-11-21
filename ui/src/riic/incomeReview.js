const FILE_LIMIT = 6000
const BODY_LIMIT = 4600

const interpretation = [
  '材料来自同一次成功演算保存的输入和结果；原表不等于当前保存的排班。未知字段保持 null，省略不表示没有异常。',
  'workHours 为有效工作，不含 exhaustedHours（0 心情驻岗）；mainWorkHours、substituteWorkHours 也不含它。',
  '工休比 = workHours / restHours；无休息时 workRestRatio 为 null，不能解释为 0。',
  'blockedAt、resolvedAt 与事件 time 均为从演算开始计的原始小时数，含预热；采样起点见 warmupHours。',
  '缺少 resolvedAt 只表示报告没有记录解除，不能据此认定期末死锁；相关事件只提供时间关联，不能证明根因。',
  '演算不是实测，不证明真实设备可执行、长期稳态或收益最优。'
]

// Keep each path/value JSON record whole; the attachment service retains only 6000 characters.
function records(value, path) {
  const text = JSON.stringify({ path, value: value ?? null })
  if (text.length < 1800 || value === null || typeof value !== 'object') return [text]
  return Object.entries(value).flatMap(([key, child]) => records(child, `${path}/${key}`))
}
function section(name, groups, selection = null) {
  const kept = []
  const coverage = Object.fromEntries(
    groups.map(([group, entries]) => [
      group,
      {
        totalRecords: entries.length,
        includedRecords: entries.length,
        omittedRecords: entries.length
      }
    ])
  )
  const heading = [
    `Mower 排班演算检查材料：${name}`,
    '以下每行都是完整 JSON 记录，path 表示原字段位置。省略数按记录统计；长对象拆为子字段记录。'
  ]
  const metadata = () => JSON.stringify({ coverage, ...(selection ? { selection } : {}) })
  const budget = Math.min(
    BODY_LIMIT,
    FILE_LIMIT - heading.join('\n').length - metadata().length - 10
  )
  let length = 0
  for (const [group, entries, groupLimit = Infinity] of groups) {
    let included = 0
    let groupLength = 0
    for (const row of entries) {
      if (length + row.length + 1 > budget || groupLength + row.length + 1 > groupLimit) continue
      kept.push(row)
      length += row.length + 1
      groupLength += row.length + 1
      included++
    }
    coverage[group].includedRecords = included
    coverage[group].omittedRecords = entries.length - included
  }
  const text = [...heading, metadata(), ...kept].join('\n')
  if (text.length > FILE_LIMIT) throw new Error('排班检查材料超过附件长度限制')
  return { name: `mower-income-${name}.txt`, text, coverage }
}

export function createIncomeReview(record) {
  if (!record?.result?.success || !record.input?.plan || !record.input?.settings)
    throw new Error('请先完成一次成功演算')
  const { result, input } = record
  const report = result.simulationReport
  const operators = [...(report?.operators ?? [])].sort(
    (a, b) => (b.exhaustedHours ?? 0) - (a.exhaustedHours ?? 0)
  )
  const deferrals = report?.shiftDeferrals ?? []
  const affected = new Set([
    ...operators.filter((row) => row.exhaustedHours > 0).map((row) => row.operatorId),
    ...deferrals.flatMap((row) => row.operatorIds ?? [])
  ])
  const events = report?.events ?? []
  const warmupHours = report?.assumptions?.warmupHours ?? null
  const anchors = deferrals
    .flatMap((row) => [row.blockedAt, row.resolvedAt])
    .filter(Number.isFinite)
    .sort((a, b) => a - b)
  const distanceToDeferral = (time) => {
    if (!anchors.length) return 0
    let low = 0
    let high = anchors.length
    while (low < high) {
      const mid = (low + high) >>> 1
      if (anchors[mid] < time) low = mid + 1
      else high = mid
    }
    return Math.min(
      Math.abs(time - (anchors[low] ?? Infinity)),
      Math.abs(time - (anchors[low - 1] ?? -Infinity))
    )
  }
  const related = []
  let relatedCount = 0
  let relatedSampleCount = 0
  for (const event of events) {
    if (!(event.operators ?? event.operatorIds ?? []).some((id) => affected.has(id))) continue
    relatedCount++
    const sample = warmupHours !== null && event.time >= warmupHours
    if (sample) relatedSampleCount++
    const distance = distanceToDeferral(event.time)
    related.push({ event, sample, distance })
    related.sort(
      (a, b) =>
        Number(b.sample) - Number(a.sample) ||
        a.distance - b.distance ||
        a.event.time - b.event.time
    )
    if (related.length > 24) related.pop()
  }
  const segments = report?.segments ?? []
  const firstByOperator = new Map()
  let zeroMoraleSegments = 0
  for (const segment of segments) {
    const matches = Object.entries(segment.occupants ?? {}).filter(
      ([, id]) => affected.has(id) && segment.morale?.[id] === 0
    )
    if (!matches.length || warmupHours === null || segment.start < warmupHours) continue
    zeroMoraleSegments++
    const ids = new Set(matches.map(([, id]) => id))
    if ([...ids].every((id) => firstByOperator.has(id))) continue
    const observation = {
      start: segment.start,
      end: segment.end,
      occupants: Object.fromEntries(matches),
      bedOccupants: Object.fromEntries(
        Object.entries(segment.bedOccupants ?? {}).filter(([, id]) => ids.has(id))
      ),
      morale: Object.fromEntries([...ids].map((id) => [id, segment.morale[id]]))
    }
    for (const id of ids) if (!firstByOperator.has(id)) firstByOperator.set(id, observation)
  }
  const segmentCandidates = [...new Set(firstByOperator.values())]
  const selectedSegments = segmentCandidates.slice(0, 6)
  const settings = { ...input.settings }
  const cachedOperators = settings.cachedOperators
  delete settings.cachedOperators
  const source = {
    savedAt: record.savedAt ?? null,
    label: record.snapshot?.label ?? null,
    origin: 'last-successful-income-record',
    configGenerationAtRun: record.configGeneration ?? null,
    modelProvenance: result.modelProvenance ?? null,
    reportSchemaVersion: report?.schemaVersion ?? null,
    engine: report?.engine ?? null,
    reportAvailable: !!report,
    elapsedHours: report?.elapsedHours ?? null,
    observedHours: report?.observedHours ?? result.observedHours ?? null,
    assumptions: report?.assumptions ?? result.assumptions ?? null,
    productionAssumptions: report?.production?.assumptions ?? null,
    interpretation
  }
  const planKeys = [
    'default',
    'conf',
    'advanced_settings',
    'facility_levels',
    input.plan.default,
    ...Object.keys(input.plan)
  ]
  const originalPlan = Object.fromEntries(
    [...new Set(planKeys)]
      .filter((key) => Object.hasOwn(input.plan, key))
      .map((key) => [key, input.plan[key]])
  )
  const files = [
    section('context', [
      ['source', records(source, '/source')],
      ['settings', records(settings, '/input/settings')],
      [
        'simulationOptions',
        records(report?.inputs?.options ?? null, '/simulationReport/inputs/options')
      ],
      ['cachedOperators', records(cachedOperators ?? null, '/input/settings/cachedOperators')]
    ]),
    section('original-plan', [['plan', records(originalPlan, '/input/plan')]]),
    section('operators', [
      ['summary', records(result.summary ?? null, '/result/summary')],
      ['resources', records(result.resources ?? null, '/result/resources')],
      [
        'operators',
        operators.map((row) => JSON.stringify({ path: '/simulationReport/operators', value: row }))
      ]
    ]),
    section(
      'observations',
      [
        [
          'zeroMoraleSegments',
          selectedSegments.map((row) =>
            JSON.stringify({ path: '/simulationReport/segments/selected', value: row })
          ),
          1400
        ],
        [
          'shiftDeferrals',
          deferrals.map((row) =>
            JSON.stringify({ path: '/simulationReport/shiftDeferrals', value: row })
          ),
          1000
        ],
        [
          'relatedEvents',
          related.map(({ event }) =>
            JSON.stringify({ path: '/simulationReport/events', value: event })
          ),
          1200
        ],
        ['diagnostics', records(result.diagnostics ?? null, '/result/diagnostics'), 700],
        [
          'spareBedRecoveryProjection',
          records(
            result.dormRecovery
              ? {
                  interpretation: '空余床填充干员理论恢复投影，不是实际成员恢复速度或实际恢复心情',
                  ...result.dormRecovery
                }
              : null,
            '/result/dormRecovery'
          )
        ],
        ['rooms', records(result.rooms ?? null, '/result/rooms')]
      ],
      {
        events: {
          totalEvents: events.length,
          relatedEvents: relatedCount,
          relatedSampleEvents: relatedSampleCount,
          candidateEvents: related.length,
          omittedBeforePacking: relatedCount - related.length,
          priority: 'sample first, then nearest raw deferral time; identity/time association only'
        },
        segments: {
          totalSegments: segments.length,
          zeroMoraleAtStartSegments: zeroMoraleSegments,
          candidateSegments: selectedSegments.length,
          omittedBeforePacking: zeroMoraleSegments - selectedSegments.length,
          scope:
            'first sampled observation per affected operator, at most 6 segments; morale is at segment start, does not establish whole-interval exhaustion or cause'
        }
      }
    )
  ]
  return {
    text: '请检查附件中这份成功演算对应的原排班，重点解释工休比和 0 心情驻岗时长，区分已知事实、可能原因和待核实事项。先纠正现有表的问题，再提出局部优化；基建养成只考虑已拥有干员，以当前练度为起点，说明目标练度解锁什么技能；目标不是实际练度，未知练度保持未知。不要从零生成排班，不要保存或执行修改。若查询当前 BOX 或排班，请明确它与附件原始快照的差别。附件可能有省略，请先核对来源、参数和覆盖统计。',
    files
  }
}
