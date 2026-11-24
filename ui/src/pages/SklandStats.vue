<script setup>
import { storeToRefs } from 'pinia'
import { computed, inject, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import AlertCircleOutline from '@vicons/ionicons5/es/AlertCircleOutline'
import ChevronBackOutline from '@vicons/ionicons5/es/ChevronBackOutline'
import ChevronForwardOutline from '@vicons/ionicons5/es/ChevronForwardOutline'
import RefreshOutline from '@vicons/ionicons5/es/RefreshOutline'
import SwapHorizontalOutline from '@vicons/ionicons5/es/SwapHorizontalOutline'
import PageLayout from '@/components/PageLayout.vue'
import PageHeader from '@/components/PageHeader.vue'
import SessionLink from '@/components/SessionLink.vue'
import SklandCalendar from '@/skland/SklandCalendar.vue'
import SklandChannelPicker from '@/skland/SklandChannelPicker.vue'
import SkeletonField from '@/components/SkeletonField.vue'
import SklandFailures from '@/skland/SklandFailures.vue'
import SklandRewardReport from '@/skland/SklandRewardReport.vue'
import SklandRetry from '@/skland/SklandRetry.vue'
import SklandRewards from '@/skland/SklandRewards.vue'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import { buildRewardDistribution, buildRewardReport } from '@/skland/rewardReport'
import { useSklandPreferencesStore } from '@/stores/sklandPreferences'
import { isRelayPage } from '@/utils/instanceToken'
import { readSkeletonShape, saveSkeletonShape } from '@/utils/skeletonShape'
import {
  addDays,
  buildCalendar,
  buildDayMap,
  buildFailureLog,
  buildSignInSlots,
  channelChipLabel,
  daysBetween,
  formatDateLong,
  formatDateShort,
  GAME_GROUPS,
  gameGroupOf,
  groupRewardTotals,
  isAccountFailure,
  monthEnd,
  monthStart,
  number,
  shiftMonth,
  SIGNED_OUTCOMES,
  sumRewardEntries,
  summarize,
  textWidthEm,
  weekStart
} from '@/skland/statistics'
import '@/skland/skland.css'

const axios = inject('axios')
const relayPage = isRelayPage()
const preferenceStore = useSklandPreferencesStore()
const {
  preferences,
  disabled: preferencesDisabled,
  error: preferencesError
} = storeToRefs(preferenceStore)
const today = ref(localDate(Date.now()))
const month = ref(monthStart(today.value))
const detailView = ref('day')
// 选中的渠道和格子是本次访问的状态；渠道同时尽量保存为账号和区服偏好。
const channelKey = ref(null)
const slotSelection = ref(null)
const failureSelection = ref(null)
const retry = ref({ busy: false, message: '', error: false })
const data = shallowRef(null)
const loading = ref(!relayPage)
const error = ref('')
const account = computed({
  get: () => preferences.value.account,
  set: (value) => preferenceStore.update({ account: value }, axios)
})
const game = computed({
  get: () => preferences.value.game,
  set: (value) => preferenceStore.update({ game: value }, axios)
})
const statsGame = computed({
  get: () => preferences.value.statsGame,
  set: (value) => {
    if (statsGameOptions.value.some((option) => option.value === value)) {
      preferenceStore.update({ statsGame: value }, axios)
    }
  }
})
const statsData = shallowRef(null)
const statsItem = ref('')
const statsPage = ref(0)
const statsLoading = ref(false)
const statsError = ref('')
const monthlyRewards = shallowRef(null)
const earliestRewardMonth = ref(null)
const monthlyRewardsError = ref('')
const rewardRefreshes = new Map()
let requestVersion = 0
let statsRequestVersion = 0
let disposed = false

function localDate(value) {
  const date = new Date(value)
  const year = String(date.getFullYear()).padStart(4, '0')
  const part = (number) => String(number).padStart(2, '0')
  return `${year}-${part(date.getMonth() + 1)}-${part(date.getDate())}`
}

const currentMonth = computed(() => monthStart(today.value))
const earliestMonth = computed(() => {
  const firstDates = (data.value?.pairs || []).map((pair) => pair.first_date)
  return [earliestRewardMonth.value, data.value?.first_account_failure_date, ...firstDates]
    .filter(Boolean)
    .map(monthStart)
    .reduce((earliest, first) => (first < earliest ? first : earliest), currentMonth.value)
})
const monthValue = computed(() => {
  const [year, number] = month.value.split('-').map(Number)
  return new Date(year, number - 1, 1).getTime()
})
// Naive UI 的年份范围采用左闭右开区间。
const yearRange = computed(() => [
  Number(earliestMonth.value.slice(0, 4)),
  Number(currentMonth.value.slice(0, 4)) + 1
])

function monthDisabled(value, period) {
  if (period?.type === 'year') return false
  const target = monthStart(localDate(value))
  return target < earliestMonth.value || target > currentMonth.value
}

async function fetchStatistics(startDate, endDate) {
  const { data: payload } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/skland/statistics`, {
    params: { startDate, endDate }
  })
  return payload
}

async function loadMonthlyRewards(version, target, refreshProgress, inFlight) {
  const url = `${import.meta.env.VITE_HTTP_URL}/skland/rewards`
  const rewardMonth = target.slice(0, 7)
  try {
    const { data: cached } = await axios.get(url, { params: { month: rewardMonth } })
    if (version !== requestVersion || cached.month !== rewardMonth) return
    if (cached.earliest_month !== undefined) {
      earliestRewardMonth.value = cached.earliest_month ? monthStart(cached.earliest_month) : null
    }
    monthlyRewards.value = cached
    let refresh = inFlight || rewardRefreshes.get(rewardMonth)
    if ((refresh || refreshProgress || !cached.cached) && target === currentMonth.value) {
      if (!refresh) {
        refresh = axios
          .post(`${url}/refresh`, {})
          .finally(() => rewardRefreshes.delete(rewardMonth))
        rewardRefreshes.set(rewardMonth, refresh)
      }
      const { data: updated } = await refresh
      if (version === requestVersion && updated.month === rewardMonth) {
        monthlyRewards.value = updated
      }
    }
  } catch (failure) {
    if (version === requestVersion) {
      monthlyRewardsError.value = failure.response?.data?.error || '所选月份的奖励读取失败'
    }
  }
}

async function load({ refreshProgress = false } = {}) {
  const version = ++requestVersion
  const requestedMonth = month.value
  const inFlight = rewardRefreshes.get(requestedMonth.slice(0, 7))
  const viewingCurrentMonth = requestedMonth === currentMonth.value
  loading.value = true
  error.value = ''
  monthlyRewardsError.value = ''
  try {
    let payload = await fetchStatistics(requestedMonth, monthEnd(requestedMonth))
    if (version !== requestVersion) return

    const serverMonth = monthStart(payload.today.date)
    const resolvedMonth =
      viewingCurrentMonth || requestedMonth > serverMonth ? serverMonth : requestedMonth
    if (resolvedMonth !== requestedMonth) {
      payload = await fetchStatistics(resolvedMonth, monthEnd(resolvedMonth))
    }
    if (version !== requestVersion) return

    today.value = payload.today.date
    month.value = resolvedMonth
    data.value = payload
    if (
      coversStatsRange(payload) &&
      (!statsData.value ||
        !coversStatsRange(statsData.value) ||
        (payload.range.start <= statsData.value.range.start &&
          payload.range.end >= statsData.value.range.end))
    ) {
      statsData.value = payload
    }
    await Promise.all([
      loadMonthlyRewards(
        version,
        resolvedMonth,
        refreshProgress,
        resolvedMonth === requestedMonth ? inFlight : null
      ),
      !statsLoading.value && !statsSource.value ? loadRewardReport() : null
    ])
  } catch (failure) {
    if (version !== requestVersion) return
    error.value = failure.response?.data?.error || '签到统计读取失败，请重试'
    return
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

function selectMonth(target, date = null) {
  if (target < earliestMonth.value || target > currentMonth.value) return
  failureSelection.value = null
  slotSelection.value = date ? { date } : null
  if (target === month.value) return
  month.value = target
  return load()
}

function pickMonth(value) {
  if (value == null || monthDisabled(value)) return
  return selectMonth(monthStart(localDate(value)))
}

const forSelect = (values) => (values || []).map((value) => ({ label: value, value }))
const selectedMonthRewards = computed(() =>
  monthlyRewards.value?.month === month.value.slice(0, 7) ? monthlyRewards.value : null
)
const rewardPairs = computed(() => selectedMonthRewards.value?.pairs || [])
const rewardWarnings = computed(() => selectedMonthRewards.value?.warnings || [])
const statsModes = [
  { preset: 'month', label: '按月' },
  { preset: 'week', label: '按周' },
  { preset: '90', label: '90 天' },
  { preset: 'year', label: '按年' }
]
const selectedStatsPreset = computed(() => {
  const { statsPreset, statsRange } = preferences.value
  return statsPreset === 'custom' && statsRange[0] > today.value ? 'month' : statsPreset
})
const statsModeIndex = computed(() =>
  statsModes.findIndex(({ preset }) => preset === selectedStatsPreset.value)
)
const statsModeLabel = computed(() => statsModes[statsModeIndex.value]?.label ?? '自选')
const nextStatsMode = computed(() => statsModes[(statsModeIndex.value + 1) % statsModes.length])
const statsModeAction = computed(
  () => `当前${statsModeLabel.value}，切换为${nextStatsMode.value.label}`
)

function statsRangeAt(page) {
  const statsPreset = selectedStatsPreset.value
  let start, end
  if (statsPreset === 'week') {
    start = addDays(weekStart(today.value), page * 7)
    end = addDays(start, 6)
  } else if (statsPreset === 'year') {
    const year = String(Number(today.value.slice(0, 4)) + page).padStart(4, '0')
    start = `${year}-01-01`
    end = `${year}-12-31`
  } else if (statsPreset === '90') {
    end = addDays(today.value, page * 90)
    start = addDays(end, -89)
  } else if (statsPreset === 'custom') {
    const [first, last] = preferences.value.statsRange
    const offset = page * (daysBetween(first, last) + 1)
    start = addDays(first, offset)
    end = addDays(last, offset)
  } else {
    start = shiftMonth(currentMonth.value, page)
    end = monthEnd(start)
  }
  const firstDate = '0001-01-01'
  if (end < firstDate || start > today.value) return null
  return [start < firstDate ? firstDate : start, end > today.value ? today.value : end]
}

const activeStatsPage = computed(() => (statsRangeAt(statsPage.value) ? statsPage.value : 0))
const statsRange = computed(() => statsRangeAt(activeStatsPage.value))
const statsStart = computed(() => statsRange.value[0])
const statsEnd = computed(() => statsRange.value[1])
const statsRangeValue = computed(() =>
  [statsStart.value, statsEnd.value].map((date) => new Date(`${date}T00:00:00`).getTime())
)
function coversStatsRange(payload) {
  return payload?.range.start <= statsStart.value && payload.range.end >= statsEnd.value
}

const statsSource = computed(() => [data.value, statsData.value].find(coversStatsRange))
const statsOptionsSource = computed(() => statsSource.value ?? data.value)
const statsAccountOptions = computed(() => forSelect(statsOptionsSource.value?.accounts))
const activeStatsAccount = computed(() => {
  const options = statsAccountOptions.value
  return (
    [preferences.value.statsAccount, selectedChannel.value?.account].find((candidate) =>
      options.some(({ value }) => value === candidate)
    ) ?? options[0]?.value
  )
})
const statsGameOptions = computed(() =>
  forSelect([
    ...new Set(
      (statsOptionsSource.value?.pairs || [])
        .filter((pair) => pair.account === activeStatsAccount.value)
        .map((pair) => pair.game)
    )
  ])
)
const activeStatsGame = computed(() => {
  const options = statsGameOptions.value
  const channel = selectedChannel.value
  const calendarGame = channel?.account === activeStatsAccount.value ? channel?.game : null
  return (
    [statsGame.value, calendarGame].find((candidate) =>
      options.some(({ value }) => value === candidate)
    ) ??
    options[0]?.value ??
    null
  )
})
function inStatsSelection(item) {
  return item.account === activeStatsAccount.value && item.game === activeStatsGame.value
}
const canPageStatsBack = computed(() => {
  const firstDate = statsOptionsSource.value?.pairs?.find(inStatsSelection)?.first_date
  const previous = statsRangeAt(activeStatsPage.value - 1)
  return Boolean(firstDate && previous && (activeStatsPage.value === 0 || previous[1] >= firstDate))
})
const canPageStatsForward = computed(() =>
  Boolean(activeStatsGame.value && statsRangeAt(activeStatsPage.value + 1))
)
const statsRecords = computed(() =>
  statsSource.value && activeStatsGame.value
    ? statsSource.value.records.filter(inStatsSelection)
    : null
)
const rewardReport = computed(
  () =>
    statsRecords.value && buildRewardReport(statsRecords.value, statsStart.value, statsEnd.value)
)
/** 统计里选中的奖励；没有选过或所选奖励不在当前范围内时用排在最前的一种。 */
const activeStatsItem = computed(() => {
  const items = rewardReport.value?.items || []
  return (
    items.find((item) => `${item.game_group}::${item.name}` === statsItem.value) || items[0] || null
  )
})
const rewardDistribution = computed(
  () =>
    activeStatsItem.value &&
    buildRewardDistribution({
      records: statsRecords.value,
      pairs: statsSource.value.pairs.filter(inStatsSelection),
      start: statsStart.value,
      end: statsEnd.value,
      today: today.value,
      item: activeStatsItem.value
    })
)
/** 本机签到记录率从所选区服第一次有记录的日期算起。 */
const statsCoverage = computed(() => {
  if (!statsRecords.value) return null
  const range = { start: statsStart.value, end: statsEnd.value, today: today.value }
  const calendar = buildCalendar(
    statsSource.value.pairs.filter(inStatsSelection),
    statsRecords.value,
    range.start,
    range.end,
    range.today
  )
  return summarize(calendar, null, range)
})

async function loadRewardReport() {
  const version = ++statsRequestVersion
  statsError.value = ''
  statsLoading.value = false
  const start = statsStart.value
  const end = statsEnd.value
  if (statsSource.value) return
  statsLoading.value = true
  try {
    const payload = await fetchStatistics(start, end)
    if (version === statsRequestVersion) statsData.value = payload
  } catch (failure) {
    if (version === statsRequestVersion) {
      statsError.value = failure.response?.data?.error || '奖励统计读取失败'
    }
  } finally {
    if (version === statsRequestVersion) statsLoading.value = false
  }
}

function selectStatsRange(value) {
  if (!value || preferencesDisabled.value) return
  const [start, end] = value.map(localDate)
  if (end < start || end > today.value || daysBetween(start, end) > 365) {
    statsError.value = '请选择截至今天、跨度不超过 366 天的日期范围'
    return
  }
  statsPage.value = 0
  preferenceStore.update({ statsPreset: 'custom', statsRange: [start, end] }, axios)
  return loadRewardReport()
}

function cycleStatsPreset() {
  if (preferencesDisabled.value) return
  statsPage.value = 0
  preferenceStore.update({ statsPreset: nextStatsMode.value.preset, statsRange: null }, axios)
  return loadRewardReport()
}

function pageStats(direction) {
  const available = direction < 0 ? canPageStatsBack.value : canPageStatsForward.value
  if (preferencesDisabled.value || !available) return
  statsPage.value = activeStatsPage.value + direction
  return loadRewardReport()
}

function selectStatsAccount(value) {
  return preferenceStore.update({ statsAccount: value }, axios)
}

function refreshPage() {
  statsRequestVersion++
  statsLoading.value = false
  statsData.value = null
  return load({ refreshProgress: true })
}

const pairs = computed(() => data.value?.pairs || [])
const ambiguousAccounts = computed(() => data.value?.ambiguous_accounts || [])
const monthLoaded = computed(() => data.value?.range.start === month.value)
const end = computed(() =>
  month.value === currentMonth.value ? today.value : monthEnd(month.value)
)
const records = computed(() =>
  monthLoaded.value ? data.value.records.filter((row) => row.date <= end.value) : []
)
const calendar = computed(() =>
  monthLoaded.value
    ? buildCalendar(pairs.value, records.value, month.value, end.value, today.value)
    : null
)

const todayRecords = computed(
  () =>
    data.value?.today_records ??
    (data.value?.records || []).filter((row) => row.date === today.value)
)

function recordsForChannel(rows, channel) {
  if (!channel) return []
  return rows.filter((row) => {
    if (row.pair !== channel.pairKey) return false
    if (channel.roleKey) return row.role_key === channel.roleKey
    return !channel.shared
  })
}

function channelStatus(channel) {
  const reward = channel.reward
  if (reward?.progress_date === today.value && reward.signed_today === true) return 'signed'
  const rows = recordsForChannel(todayRecords.value, channel)
  const outcome = buildDayMap(rows).values().next().value?.outcome
  if (SIGNED_OUTCOMES.includes(outcome)) return 'signed'
  if (outcome === 'failed') return 'failed'
  if (reward?.progress_date === today.value && reward.signed_today === false && !reward.stale) {
    return 'pending'
  }
  if (inactivePairs.value.has(channel.pairKey)) return 'stale'
  return 'unknown'
}

/** 一个渠道是一个账号在一个游戏区服下的一个角色，每个渠道有自己的签到日历。 */
const channels = computed(() => {
  const list = new Map()
  const add = (account, game, roleIndex = 1, roleKey = null) => {
    const pairKey = `${account}::${game}`
    const key = `${pairKey}::${roleKey || roleIndex}`
    if (!list.has(key)) {
      const group = gameGroupOf(game)
      list.set(key, {
        key,
        pairKey,
        account,
        game,
        game_group: group,
        channel: game.slice(group.length) || game,
        role_index: roleIndex,
        roleKey
      })
    }
    return list.get(key)
  }
  for (const reward of rewardPairs.value) {
    Object.assign(add(reward.account, reward.game, reward.role_index || 1, reward.role_key), {
      reward,
      display_name: reward.display_name
    })
  }
  const recordedRoles = new Map()
  for (const row of [...records.value, ...todayRecords.value]) {
    if (!row.role_key) continue
    if (!recordedRoles.has(row.pair)) recordedRoles.set(row.pair, new Set())
    recordedRoles.get(row.pair).add(row.role_key)
  }
  const snapshotRoles = new Map()
  for (const channel of list.values()) {
    if (!snapshotRoles.has(channel.pairKey)) snapshotRoles.set(channel.pairKey, [])
    snapshotRoles.get(channel.pairKey).push(channel)
  }
  for (const pair of pairs.value) {
    const cached = snapshotRoles.get(pair.key) || []
    const known = recordedRoles.get(pair.key) || new Set()
    if (cached.every((channel) => channel.roleKey)) {
      const occupiedIndices = new Set(cached.map((channel) => channel.role_index))
      let index = 1
      for (const roleKey of known) {
        if (cached.some((channel) => channel.roleKey === roleKey)) continue
        while (occupiedIndices.has(index)) index++
        add(pair.account, pair.game, index++, roleKey)
      }
    }
    if (!cached.length && !known.size) add(pair.account, pair.game)
  }
  const counts = new Map()
  for (const channel of list.values()) {
    counts.set(channel.pairKey, (counts.get(channel.pairKey) || 0) + 1)
  }
  const multipleRolePairs = new Set(
    pairs.value.filter((pair) => pair.multiple_roles === true).map((pair) => pair.key)
  )
  const order = (group) => (GAME_GROUPS.includes(group) ? GAME_GROUPS.indexOf(group) : 9)
  return [...list.values()]
    .map((channel) => {
      const shared =
        counts.get(channel.pairKey) > 1 ||
        (recordedRoles.get(channel.pairKey)?.size ?? 0) > 1 ||
        multipleRolePairs.has(channel.pairKey) ||
        channel.reward?.progress_ambiguous === true
      const item = { ...channel, shared }
      return { ...item, status: channelStatus(item) }
    })
    .sort(
      (left, right) =>
        left.account.localeCompare(right.account) ||
        order(left.game_group) - order(right.game_group) ||
        left.game.localeCompare(right.game, 'zh') ||
        left.role_index - right.role_index
    )
})
const selectedChannel = computed(() => {
  const list = channels.value
  return (
    list.find((channel) => channel.key === channelKey.value) ||
    list.find((channel) => channel.account === account.value && channel.game === game.value) ||
    list.find((channel) => channel.account === account.value) ||
    list[0] ||
    null
  )
})

function channelForFailure(entry) {
  return channels.value.find(
    (channel) =>
      channel.pairKey === entry.pair &&
      (entry.roleKey
        ? channel.roleKey === entry.roleKey
        : !channel.shared && (!channel.roleKey || entry.date === today.value))
  )
}

const failureLog = computed(() => {
  const log = buildFailureLog(calendar.value, records.value, today.value)
  const roleEntries = log.entries.map((entry) => {
    const channel = channelForFailure(entry)
    const snapshot = channel?.reward
    const recovered =
      entry.recovered ||
      (entry.date === today.value && channel?.status === 'signed') ||
      snapshot?.signed_dates?.includes(entry.date) ||
      (snapshot?.progress_date === entry.date && snapshot.signed_today === true)
    return {
      ...entry,
      roleName: channel?.shared ? channel.display_name || `角色 ${channel.role_index}` : '',
      recovered: Boolean(recovered),
      pending: entry.pending && !recovered
    }
  })
  const accountFailures = monthLoaded.value ? data.value.account_failures || [] : []
  const accountEntries = accountFailures.map(({ account, date, attempts, messages, resolved }) => ({
    key: JSON.stringify(['account', account, date]),
    account,
    date,
    attempts,
    messages,
    accountFailure: true,
    recovered: resolved,
    pending: !resolved && date === today.value
  }))
  const entries = [...roleEntries, ...accountEntries].sort((a, b) => b.date.localeCompare(a.date))
  return {
    ...log,
    entries,
    attempts: log.attempts + accountEntries.reduce((sum, entry) => sum + entry.attempts, 0),
    recovered: roleEntries.filter((entry) => entry.recovered).length
  }
})

const channelRecords = computed(() => recordsForChannel(records.value, selectedChannel.value))
const signIn = computed(() => {
  const channel = selectedChannel.value
  if (!channel || !monthLoaded.value) return null
  return buildSignInSlots({
    month: month.value,
    today: today.value,
    records: channelRecords.value,
    rewardPair: channel.reward || null,
    shared: channel.shared,
    roleKey: channel.roleKey
  })
})
const activeFailure = computed(() =>
  failureLog.value.entries.find((entry) => entry.key === failureSelection.value)
)
const activeSlot = computed(() => {
  const slots = signIn.value?.slots || []
  if (activeFailure.value) return null
  const pick = slotSelection.value
  return (
    (pick?.index != null && slots.find((slot) => slot.index === pick.index)) ||
    (pick?.date && slots.find((slot) => slot.claimed && slot.date === pick.date)) ||
    slots.find((slot) => slot.state === 'today') ||
    slots.filter((slot) => slot.claimed).at(-1) ||
    slots[0] ||
    null
  )
})
const selectedRow = computed(() =>
  calendar.value?.rows.find((row) => row.key === selectedChannel.value?.pairKey)
)
const sklandProgress = computed(() => {
  if (signIn.value?.source !== 'cache') return null
  const { snapshotDate: date, snapshotClaimed: claimed } = signIn.value
  const reward = selectedChannel.value.reward
  return {
    date,
    claimed,
    hasDates: reward.signed_dates?.length === claimed,
    showDate: date < end.value || reward.stale
  }
})
const recordedDays = computed(() => {
  const channel = selectedChannel.value
  if (!signIn.value || !channel || ambiguousAccounts.value.includes(channel.account)) return null
  if (!channel.shared) return selectedRow.value?.signedDays ?? 0
  if (!channel.roleKey) return null
  const signed = channelRecords.value.filter((record) => SIGNED_OUTCOMES.includes(record.outcome))
  return new Set(signed.map((record) => record.date)).size
})
const summary = computed(
  () =>
    selectedRow.value &&
    summarize({ rows: [selectedRow.value] }, channelRecords.value, {
      start: month.value,
      end: end.value,
      today: today.value
    })
)
const sklandSkeleton = computed(() => !data.value && loading.value)
// 记下上次读完后的版面，读取中按此占位：有没有签到日历（没有任何渠道时只显示提示）、账号
// 选择框和渠道数、森空岛进度和本机记录两项读数、本机连续签到一行、奖励统计面板，以及各区服的
// 奖励数。没有用 Mower 签到时本机记录、连续签到和统计面板都不出现，骨架也不画。
const skeletonShape = readSkeletonShape('skland', {
  calendar: true,
  select: false,
  chips: 2,
  skland: true,
  local: true,
  streak: false,
  stats: true,
  game: true,
  groups: [6],
  months: 0
})
watch(
  () => [
    loading.value,
    statsLoading.value,
    selectedChannel.value,
    sklandProgress.value,
    recordedDays.value,
    summary.value,
    rewardReport.value
  ],
  () => {
    if (!data.value || loading.value || statsLoading.value) return
    const channel = selectedChannel.value
    const report = rewardReport.value
    saveSkeletonShape('skland', {
      calendar: Boolean(channel),
      select: new Set(channels.value.map((item) => item.account)).size > 1,
      chips: channels.value
        .filter((item) => item.account === channel?.account)
        .map((item) => textWidthEm(channelChipLabel(item))),
      skland: Boolean(sklandProgress.value),
      local: recordedDays.value != null,
      streak: Boolean(
        month.value === currentMonth.value &&
        !channel?.shared &&
        summary.value?.streakPair.current_streak
      ),
      stats: Boolean(statsOptionsSource.value?.pairs.length),
      game: statsGameOptions.value.length > 0,
      groups: report ? groupRewardTotals(report.items).map((group) => group.items.length) : [6],
      months: rewardDistribution.value?.months?.length ?? 0
    })
  }
)

function slotRewards(filter) {
  const game = selectedChannel.value?.game
  return sumRewardEntries(
    (signIn.value?.slots || []).filter(filter).map((slot) => ({ game, rewards: slot.rewards }))
  )
}
const receivedRewards = computed(() => slotRewards((slot) => slot.claimed))
const upcomingRewards = computed(() =>
  slotRewards((slot) => !slot.claimed && ['today', 'upcoming'].includes(slot.state))
)
const missedRewards = computed(() =>
  slotRewards((slot) => ['unreachable', 'unclaimed'].includes(slot.state))
)
const missingRewardDetails = computed(
  () => (signIn.value?.slots || []).filter((slot) => slot.claimed && !slot.rewards.length).length
)

const latestPair = computed(() => {
  let latest = null
  for (const pair of pairs.value) {
    if (
      !latest ||
      pair.last_date > latest.last_date ||
      (pair.last_date === latest.last_date && pair.last_outcome === 'failed')
    ) {
      latest = pair
    }
  }
  return latest
})
const inactivePairs = computed(() => {
  if (!latestPair.value || daysBetween(latestPair.value.last_date, today.value) > 1) {
    return new Set()
  }
  return new Set(
    pairs.value
      .filter((pair) => daysBetween(pair.last_date, today.value) >= 7)
      .map((pair) => pair.key)
  )
})

async function showLatest() {
  const latest = latestPair.value
  selectChannel(channels.value.find((channel) => channel.pairKey === latest.key)?.key)
  detailView.value = 'day'
  const historyLoad = selectMonth(monthStart(latest.last_date), latest.last_date)
  const selection = slotSelection.value
  await historyLoad
  if (!selection || slotSelection.value !== selection || !monthLoaded.value) return
  if (latest.last_outcome === 'failed') {
    const entry = failureLog.value.entries.find(
      (failure) => failure.pair === latest.key && failure.date === latest.last_date
    )
    if (entry) selectFailure(entry)
    return
  }
  const record = records.value.find(
    (row) =>
      row.pair === latest.key &&
      row.date === latest.last_date &&
      row.outcome === latest.last_outcome &&
      row.role_key
  )
  if (!record) return
  const channel = channels.value.find(
    (item) => item.pairKey === latest.key && item.roleKey === record.role_key
  )
  if (channel) {
    selectChannel(channel.key)
    slotSelection.value = selection
  }
}

function selectChannel(key) {
  const channel = channels.value.find((item) => item.key === key)
  if (!channel) return
  channelKey.value = key
  slotSelection.value = null
  failureSelection.value = null
  preferenceStore.update({ account: channel.account, game: channel.game }, axios)
}

function selectSlot(index) {
  failureSelection.value = null
  slotSelection.value = { index }
  detailView.value = 'day'
}

function selectFailure(entry) {
  const channel = channelForFailure(entry)
  if (channel) selectChannel(channel.key)
  slotSelection.value = null
  failureSelection.value = entry.key
  detailView.value = 'day'
}

/**
 * 重新签到沿用运行日志里「新增任务」的森空岛签到任务：交给正在运行的 Mower 立即执行，
 * 只会再签今天还没有成功的账号；结果写入记录后用页面右上角的刷新查看。
 */
async function retrySignIn() {
  if (retry.value.busy) return
  retry.value = { busy: true, message: '', error: false }
  const task = { time: new Date(), plan: {}, task_type: '森空岛签到', meta_data: '' }
  try {
    const { data: result } = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/task`,
      { task },
      { timeout: 30000 }
    )
    retry.value =
      result === '添加任务成功！'
        ? { busy: false, message: '已加入任务队列，签到完成后刷新查看结果', error: false }
        : { busy: false, message: String(result || '添加任务失败'), error: true }
  } catch (failure) {
    const detail = failure.response?.data
    retry.value = {
      busy: false,
      message: detail?.message || detail?.error || '添加任务失败，请稍后重试',
      error: true
    }
  }
}

function failureNeedsAccountCheck(entry) {
  return entry.accountFailure || isAccountFailure(entry.messages)
}

const todayFailureNeedsAccountCheck = computed(() =>
  failureLog.value.entries.some((entry) => entry.pending && failureNeedsAccountCheck(entry))
)
const channelFailureNeedsAccountCheck = computed(() =>
  activeFailure.value?.pending
    ? failureNeedsAccountCheck(activeFailure.value)
    : !signIn.value?.todaySigned && isAccountFailure(signIn.value?.todayRecord?.failedMessages)
)

function selectDetailView(view) {
  detailView.value = view
  return preferenceStore.update({ detailView: view }, axios)
}

function showToday() {
  detailView.value = 'day'
  slotSelection.value = null
  return selectMonth(currentMonth.value)
}

async function initialize() {
  if (relayPage) return
  await preferenceStore.load(axios)
  if (disposed) return
  detailView.value = preferences.value.detailView
  return load()
}

async function retryPreferences() {
  const wasLoaded = preferenceStore.loaded
  if ((await preferenceStore.retry(axios)) && !wasLoaded) {
    detailView.value = preferences.value.detailView
    return loadRewardReport()
  }
}

onMounted(initialize)
onUnmounted(() => {
  disposed = true
  requestVersion++
  statsRequestVersion++
})
</script>

<template>
  <PageLayout class="skland-page" max-width="1240px">
    <template #header>
      <PageHeader class="calendar-page-header">
        森空岛签到统计
        <help-text>
          <div>
            月度进度来自森空岛。本机统计只计算 Mower 记录到的日期，无本机记录的日期也可能已签到。
          </div>
        </help-text>
        <template v-if="!relayPage" #actions>
          <n-button
            quaternary
            circle
            size="small"
            :loading="loading"
            aria-label="刷新签到统计"
            title="刷新签到统计"
            @click="refreshPage"
          >
            <template #icon>
              <n-icon :component="RefreshOutline" />
            </template>
          </n-button>
        </template>
      </PageHeader>
    </template>

    <div v-if="relayPage" class="skland-panel" role="status">
      当前通过中转访问。请在 Mower 桌面窗口或直接连接实例的 Web UI 查看签到统计。
    </div>

    <div v-if="error" class="skland-panel skland-alert" role="alert">
      <n-icon :component="AlertCircleOutline" aria-hidden="true" />
      <span>
        {{ error }}
        <template v-if="monthLoaded"> 当前显示上次读取的记录。</template>
      </span>
      <n-button text @click="load">重试</n-button>
    </div>

    <div v-if="preferencesError" class="skland-panel skland-alert" role="alert">
      <span>{{ preferencesError }}</span>
      <n-button text @click="retryPreferences">重试</n-button>
    </div>

    <div v-if="ambiguousAccounts.length" class="skland-panel skland-alert" role="status">
      账号隐藏部分字符后显示为相同的标识（{{
        ambiguousAccounts.join('、')
      }}）。这些账号的本机签到记录无法区分，未纳入统计。
    </div>

    <!-- 首次读取时页面照常显示月份工具栏，日历按本月天数画出占位格，右栏的账号、渠道和明细
         是占位块；上次读到过奖励统计时，统计面板也先占好位置。 -->
    <template v-if="sklandSkeleton || data || rewardPairs.length">
      <section class="skland-panel calendar-workspace" aria-label="按月查看签到">
        <div class="calendar-toolbar">
          <div class="month-navigation">
            <n-button
              quaternary
              circle
              size="small"
              aria-label="上个月"
              title="上个月"
              :disabled="month <= earliestMonth"
              @click="selectMonth(shiftMonth(month, -1))"
            >
              <template #icon><n-icon :component="ChevronBackOutline" /></template>
            </n-button>
            <n-date-picker
              :value="monthValue"
              class="month-picker"
              type="month"
              format="yyyy年M月"
              size="small"
              :theme-overrides="{ peers: { Input: { fontSizeSmall: '17px' } } }"
              :bordered="false"
              :actions="['confirm']"
              :year-range="yearRange"
              :is-date-disabled="monthDisabled"
              :input-readonly="true"
              placeholder="选择月份"
              aria-label="选择月份"
              @update:value="pickMonth"
            />
            <n-button
              quaternary
              circle
              size="small"
              aria-label="下个月"
              title="下个月"
              :disabled="month >= currentMonth"
              @click="selectMonth(shiftMonth(month, 1))"
            >
              <template #icon><n-icon :component="ChevronForwardOutline" /></template>
            </n-button>
            <n-button
              size="small"
              :disabled="
                month === currentMonth &&
                (!signIn?.todayIndex ||
                  (activeSlot?.state === 'today' && !slotSelection && detailView === 'day'))
              "
              @click="showToday"
            >
              {{ month === currentMonth && signIn?.todayIndex ? '回到今天' : '回到本月' }}
            </n-button>
          </div>
        </div>

        <div v-if="monthlyRewardsError || rewardWarnings.length" class="skland-alert" role="status">
          <span v-if="monthlyRewardsError">{{ monthlyRewardsError }}</span>
          <span v-for="warning in rewardWarnings" :key="warning">{{ warning }}</span>
        </div>
        <LoadingSkeleton v-if="sklandSkeleton" label="正在读取签到记录">
          <SklandCalendar v-if="skeletonShape.calendar" :month="month" :today="today" loading>
            <template #channels>
              <SklandChannelPicker
                :channels="[]"
                :placeholder="{ select: skeletonShape.select, chips: skeletonShape.chips }"
              />
              <p v-if="skeletonShape.skland || skeletonShape.local" class="month-progress">
                <span v-if="skeletonShape.skland"
                  >森空岛已签到
                  <strong
                    ><span class="skeleton-bone skeleton-text" style="--skeleton-w: 1.2em"
                  /></strong>
                  天</span
                >
                <span v-if="skeletonShape.local"
                  >本机有签到记录
                  <strong
                    ><span class="skeleton-bone skeleton-text" style="--skeleton-w: 1.2em"
                  /></strong>
                  天</span
                >
              </p>
              <p v-if="skeletonShape.streak" class="month-summary">
                本机连续签到
                <strong
                  ><span class="skeleton-bone skeleton-text" style="--skeleton-w: 1.2em"
                /></strong>
                天
              </p>
            </template>
          </SklandCalendar>
          <!-- 上次没有任何签到渠道：不画日历，只先占好“还没有签到记录”提示的位置。 -->
          <div v-else class="no-history no-history--reserved">
            <h2>还没有签到记录</h2>
            <a>管理森空岛账号</a>
          </div>
        </LoadingSkeleton>
        <SklandCalendar
          v-else-if="selectedChannel"
          :month="month"
          :today="today"
          :sign-in="signIn"
          :game="selectedChannel.game_group"
          :selected-index="activeSlot?.index ?? null"
          :loading="loading"
          :detail-view="detailView"
          :failure-entry="activeFailure"
          :failure-count="failureLog.entries.length"
          @select="selectSlot"
          @update:detail-view="selectDetailView"
        >
          <template #channels>
            <SklandChannelPicker
              :channels="channels"
              :selected="selectedChannel"
              @select="selectChannel"
            />
            <p v-if="sklandProgress || recordedDays != null" class="month-progress">
              <span
                v-if="sklandProgress"
                :title="`森空岛记录截至 ${formatDateLong(sklandProgress.date)}`"
              >
                <template v-if="sklandProgress.hasDates">
                  森空岛已签到 <strong>{{ number(sklandProgress.claimed) }}</strong> 天
                </template>
                <template v-else>
                  森空岛已领 <strong>{{ number(sklandProgress.claimed) }}</strong> 格奖励
                </template>
                <template v-if="sklandProgress.showDate">
                  （截至 {{ formatDateShort(sklandProgress.date, today) }}）
                </template>
              </span>
              <span v-if="recordedDays != null">
                本机有签到记录 <strong>{{ number(recordedDays) }}</strong> 天
              </span>
            </p>
            <p
              v-if="
                month === currentMonth &&
                !selectedChannel.shared &&
                summary?.streakPair.current_streak
              "
              class="month-summary"
            >
              本机连续签到 <strong>{{ number(summary.streakPair.current_streak) }}</strong> 天
            </p>
          </template>
          <template #retry>
            <SklandRetry
              v-bind="retry"
              :account="channelFailureNeedsAccountCheck"
              @retry="retrySignIn"
            />
          </template>
          <template #rewards>
            <SklandRewards
              :items="receivedRewards"
              :upcoming="upcomingRewards"
              :missed="missedRewards"
              :unparsed="missingRewardDetails"
              :current="month === currentMonth"
            />
          </template>
          <template #failures>
            <SklandFailures :log="failureLog" :today="today" @select="selectFailure">
              <template #retry>
                <SklandRetry
                  v-bind="retry"
                  :account="todayFailureNeedsAccountCheck"
                  @retry="retrySignIn"
                />
              </template>
            </SklandFailures>
          </template>
        </SklandCalendar>
        <SklandFailures
          v-else-if="failureLog.entries.length"
          :log="failureLog"
          :today="today"
          :selectable="false"
        >
          <template #retry>
            <SklandRetry
              v-bind="retry"
              :account="todayFailureNeedsAccountCheck"
              @retry="retrySignIn"
            />
          </template>
        </SklandFailures>
        <div v-else class="no-history">
          <h2>还没有签到记录</h2>
          <SessionLink to="/settings#task-accounts">管理森空岛账号</SessionLink>
        </div>
        <div
          v-if="calendar && !records.length && latestPair && latestPair.last_date <= today"
          class="month-empty"
        >
          <span
            >这个月没有签到记录。最近一条记录在 {{ formatDateLong(latestPair.last_date) }}。</span
          >
          <n-button text type="primary" @click="showLatest">查看最近记录</n-button>
        </div>
      </section>

      <SklandRewardReport
        v-if="sklandSkeleton && skeletonShape.stats"
        loading
        :placeholder-groups="skeletonShape.groups"
        :placeholder-months="Number(skeletonShape.months) || 0"
      >
        <template #controls>
          <div class="stats-controls" inert>
            <SkeletonField kind="select" size="small" class="account-filter" width="6em" />
            <SkeletonField
              v-if="skeletonShape.game"
              kind="select"
              size="small"
              class="game-filter"
              width="6em"
            />
            <n-button class="stats-mode-button" size="small">
              <span class="skeleton-bone skeleton-text" style="--skeleton-w: 2em" />
              <n-icon
                class="stats-mode-icon"
                :component="SwapHorizontalOutline"
                aria-hidden="true"
              />
            </n-button>
            <div class="stats-period">
              <n-button quaternary circle size="small">
                <template #icon><n-icon :component="ChevronBackOutline" /></template>
              </n-button>
              <SkeletonField size="small" class="stats-period__range" width="13em" />
              <n-button quaternary circle size="small">
                <template #icon><n-icon :component="ChevronForwardOutline" /></template>
              </n-button>
            </div>
          </div>
        </template>
      </SklandRewardReport>
      <SklandRewardReport
        v-else-if="statsOptionsSource?.pairs.length"
        :report="rewardReport"
        :coverage="statsCoverage"
        :distribution="rewardDistribution"
        :loading="statsLoading"
        :error="statsError"
        :selected-item="
          activeStatsItem ? `${activeStatsItem.game_group}::${activeStatsItem.name}` : ''
        "
        @select-item="statsItem = $event"
        @retry="loadRewardReport"
      >
        <template #controls>
          <div class="stats-controls" aria-label="奖励统计筛选">
            <n-select
              :value="activeStatsAccount"
              :options="statsAccountOptions"
              class="account-filter"
              size="small"
              :consistent-menu-width="false"
              :input-props="{ 'aria-label': '统计账号' }"
              :disabled="preferencesDisabled"
              @update:value="selectStatsAccount"
            />
            <n-select
              v-if="statsGameOptions.length"
              :value="activeStatsGame"
              :options="statsGameOptions"
              class="game-filter"
              size="small"
              :consistent-menu-width="false"
              :input-props="{ 'aria-label': '统计游戏区服' }"
              :disabled="preferencesDisabled"
              @update:value="statsGame = $event"
            />
            <n-button
              class="stats-mode-button"
              size="small"
              :aria-label="statsModeAction"
              :title="statsModeAction"
              :disabled="preferencesDisabled"
              @click="cycleStatsPreset"
            >
              {{ statsModeLabel }}
              <n-icon
                class="stats-mode-icon"
                :component="SwapHorizontalOutline"
                aria-hidden="true"
              />
            </n-button>
            <div class="stats-period" role="group" aria-label="统计日期范围">
              <n-button
                quaternary
                circle
                size="small"
                aria-label="上一个统计周期"
                title="上一个统计周期"
                :disabled="preferencesDisabled || !canPageStatsBack"
                @click="pageStats(-1)"
              >
                <template #icon><n-icon :component="ChevronBackOutline" /></template>
              </n-button>
              <n-date-picker
                :value="statsRangeValue"
                type="daterange"
                size="small"
                :clearable="false"
                :input-readonly="true"
                :is-date-disabled="(value) => localDate(value) > today"
                :disabled="preferencesDisabled"
                @update:value="selectStatsRange"
              />
              <n-button
                quaternary
                circle
                size="small"
                aria-label="下一个统计周期"
                title="下一个统计周期"
                :disabled="preferencesDisabled || !canPageStatsForward"
                @click="pageStats(1)"
              >
                <template #icon><n-icon :component="ChevronForwardOutline" /></template>
              </n-button>
            </div>
          </div>
        </template>
      </SklandRewardReport>
    </template>
  </PageLayout>
</template>

<style scoped>
.calendar-toolbar,
.month-navigation,
.stats-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}
.stats-controls {
  flex-wrap: wrap;
}
.stats-period {
  display: flex;
  flex: 0 1 325px;
  min-width: 0;
  align-items: center;
  gap: 3px;
}
.stats-period .n-date-picker,
.stats-period .stats-period__range {
  flex: 1;
  min-width: 0;
  font-variant-numeric: tabular-nums;
}
.stats-period :deep(.n-button) {
  flex: none;
}
.stats-mode-button {
  min-width: 86px;
}
.stats-mode-icon {
  margin-inline-start: 6px;
}
.calendar-toolbar {
  justify-content: space-between;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.month-progress,
.month-summary {
  margin: 6px 10px;
  color: var(--mower-text-muted);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
.month-progress {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 12px;
}
.month-progress strong,
.month-summary strong {
  color: var(--mower-text);
  font-size: 15px;
  font-weight: 650;
}
.month-picker {
  width: 154px;
}
.month-picker :deep(.n-input) {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.game-filter {
  width: 158px;
}
.account-filter {
  width: 144px;
}
.month-empty {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin-top: 12px;
  color: var(--skland-muted);
  font-size: 13px;
}
.skland-alert {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 9px 12px;
  color: var(--mower-error-text, var(--mower-error));
  font-size: 13px;
}
.no-history--reserved {
  visibility: hidden;
}
.no-history h2 {
  margin: 0;
  font-size: 18px;
}
.no-history a {
  display: inline-block;
  margin-top: 8px;
  color: var(--skland-link);
}
@container main-content (max-width: 640px) {
  .calendar-page-header :deep(.page-header__actions) {
    width: auto;
  }
  .calendar-workspace {
    padding: 12px;
  }
  .month-navigation {
    gap: 3px;
    flex-wrap: wrap;
  }
}
@container main-content (max-width: 400px) {
  .stats-controls .account-filter,
  .stats-controls .game-filter {
    flex: 1 1 104px;
  }
  .stats-period {
    flex-basis: 100%;
  }
  .stats-period :deep(.n-input-wrapper) {
    padding-inline: 4px;
  }
  .stats-period :deep(.n-input__input-el) {
    font-size: 12px;
  }
}
</style>
