import { planBindings } from '@/utils/plan_bindings'

export function incomeMoraleReport(rows, plan, warmupHours) {
  const series = rows.map((row) => ({
    name: row.name,
    data: row.points.map(([hours, y], index, points) => ({
      x: hours * 3600000,
      y,
      ...(points[index - 1]?.[0] === hours && points[index - 1][1] !== y
        ? { moodEvent: 'simulation_jump' }
        : {})
    }))
  }))
  const byName = new Map(series.map((row) => [row.name, row]))
  const members = new Map()
  for (const table of [plan?.plan1, ...(plan?.backup_plans ?? []).map((backup) => backup.plan)]) {
    for (const room of Object.values(table ?? {})) {
      for (const slot of room?.plans ?? []) {
        if (!byName.has(slot.agent)) continue
        for (const binding of planBindings(slot)) {
          if (!binding.group) continue
          if (!members.has(binding.group)) members.set(binding.group, new Set())
          members.get(binding.group).add(slot.agent)
        }
      }
    }
  }
  return {
    warmupHours,
    series,
    catalog: series.map((row) => ({ name: row.name, sampleCount: row.data.length })),
    groups: [...members].map(([groupName, names]) => ({
      groupName,
      moodData: {
        datasets: [...names].map((name) => ({ label: name, data: byName.get(name).data }))
      }
    }))
  }
}
