const DAY = 1440
const WEEK = 7 * DAY

function minutes(time) {
  const [hour, minute] = time.split(':').map(Number)
  return hour * 60 + minute
}

export function longTaskWindowConflicts(windows, defaultType) {
  const intervals = windows.flatMap((window, row) => {
    const kind = window.task_type ?? defaultType
    let start = minutes(window.start)
    let end = minutes(window.end)
    if (start === end) {
      start = 0
      end = DAY
    } else if (end < start) {
      end += DAY
    }
    return window.weekdays.flatMap((day) => {
      const first = day * DAY + start
      const last = day * DAY + end
      const part = { row, day, kind, first, last: Math.min(last, WEEK) }
      return last > WEEK ? [part, { ...part, first: 0, last: last - WEEK }] : [part]
    })
  })
  intervals.sort((a, b) => a.first - b.first)
  const conflicts = []
  intervals.forEach((left, i) => {
    for (let j = i + 1; j < intervals.length && intervals[j].first < left.last; j++) {
      const right = intervals[j]
      if (left.kind !== right.kind) {
        conflicts.push({ left, right, start: right.first, end: Math.min(left.last, right.last) })
      }
    }
  })
  return conflicts
}

export function longTaskConflictTime({ start, end }, weekdays) {
  const format = (minute) => {
    const day = weekdays[Math.floor(minute / DAY) % 7]
    const hour = String(Math.floor(minute / 60) % 24).padStart(2, '0')
    const remainder = String(minute % 60).padStart(2, '0')
    return [day, `${hour}:${remainder}`]
  }
  const [startDay, startTime] = format(start)
  const [endDay, endTime] = format(end)
  return `${startDay} ${startTime} 至 ${endDay === startDay ? '' : endDay + ' '}${endTime}`
}
