<script setup>
import { computed, h, inject, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { NTag } from 'naive-ui'
import { useRouter } from 'vue-router'
import HelpText from '../components/HelpText.vue'
import { builtinGroups } from '../data/gachaGroups.js'

const router = useRouter()
const axios = inject('axios')
const api = (path) => import.meta.env.VITE_HTTP_URL + '/gacha' + path
const writeOptions = { headers: { 'X-Mower-Gacha': '1' } }
const accounts = ref([])
const sessions = ref([])
const activeId = ref('')
const summary = ref(null)
const records = ref([])
const offset = ref(0)
const more = ref(false)
const loading = ref(false)
const sending = ref(false)
const loginBusy = ref(false)
const syncing = ref(false)
const loginExpanded = ref(true)
const loginMode = ref('sms')
const phone = ref('')
const code = ref('')
const password = ref('')
const cooldown = ref(0)
const alertText = ref('')
const alertType = ref('info')
const roleChoices = ref([])
const selectedSessionId = ref('')
const loginMask = ref('')
const category = ref('')
const poolId = ref('')
const rarity = ref('six')
const timeRange = ref('all')
const customDates = ref(null)
const search = ref('')
const newOnly = ref(false)
const avatarMissing = ref(new Set())
const selectedHit = ref('')
const eliteFilter = ref('all')
const operatorCatalog = ref({})
function conciseGroupNote(note) {
  const value = typeof note === 'string' ? note : ''
  return /来自群图|群图中金工|并非全部同时进驻/.test(value) ? '' : value
}
const facilityOptions = [
  { label: '全部设施', value: '全部' },
  ...['贸易', '金属', '源石', '通用', '加工', '宿舍', '办公室', '会客室'].map((x) => ({ label: x, value: x }))
]
const facilityFilter = ref('金属')
const selectedGroupId = ref('builtin-automation')
const customGroups = ref([])
const groupOverrides = ref({})
const hiddenGroupIds = ref([])
const groupEditorOpen = ref(false)
const draftGroup = ref({ id: '', title: '', facility: '通用', core: [], support: [], note: '' })
const availableGroups = computed(() => [
  ...builtinGroups
    .filter((g) => !hiddenGroupIds.value.includes(g.id))
    .map((g) => groupOverrides.value[g.id] || g),
  ...customGroups.value
])
const groupOptions = computed(() => availableGroups.value
  .filter((g) => facilityFilter.value === '全部' || (g.facility || '通用') === facilityFilter.value)
  .map((g) => ({ value: g.id, label: g.title })))
const activeGroup = computed(() => availableGroups.value.find((g) => g.id === selectedGroupId.value))
const ownedIds = computed(() => new Set((rosterInfo.value?.operators || []).map((x) => x.id)))
function groupOptionName(id) {
  return operatorCatalog.value[id]?.name || String(id)
}
function avatarNode(id, size = 25) {
  const name = groupOptionName(id)
  return h('img', {
    src: avatarUrl(name), alt: name, class: 'gacha-option-avatar',
    style: { width: size + 'px', height: size + 'px' },
    onError: (event) => { event.target.style.display = 'none' }
  })
}
function renderGroupOption(option) {
  return h('span', { class: 'gacha-option-inner' }, [
    avatarNode(option.value, 30),
    h('span', null, String(option.label || groupOptionName(option.value)))
  ])
}
function renderGroupTag({ option, handleClose }) {
  return h(NTag, {
    closable: true, size: 'small',
    class: 'gacha-option-tag',
    onClose: handleClose
  }, {
    default: () => h('span', { class: 'gacha-option-inner' },
      [avatarNode(option.value, 24), h('span', null, groupOptionName(option.value))])
  })
}
const catalogOptions = computed(() => Object.entries(operatorCatalog.value)
  .filter(([id, x]) => id.startsWith('char_') && x?.name)
  .sort((a, b) => Number(b[1].rarity || 0) - Number(a[1].rarity || 0) ||
    a[1].name.localeCompare(b[1].name, 'zh-CN'))
  .map(([id, x]) => ({ value: id, label: x.name + ' · ' + x.rarity + '★' })))
const groupMembers = computed(() => {
  if (!activeGroup.value) return []
  const unique = new Set()
  return [...activeGroup.value.core.map((id) => [id, 'core']),
    ...activeGroup.value.support.map((id) => [id, 'support'])]
    .filter(([id]) => { if (unique.has(id)) return false; unique.add(id); return true })
    .map(([id, kind]) => ({
      id, kind, ...operatorCatalog.value[id], name: operatorCatalog.value[id]?.name || id,
      owned: ownedIds.value.has(id)
    }))
})
const groupCount = computed(() => ({
  present: groupMembers.value.filter((m) => m.owned).length,
  absent: groupMembers.value.filter((m) => !m.owned).length
}))
function groupsStorageKey() { return 'mower-gacha-groups-v1-' + (activeId.value || 'unbound') }
function overridesStorageKey() { return 'mower-gacha-group-overrides-v1-' + (activeId.value || 'unbound') }
function hiddenStorageKey() { return 'mower-gacha-group-hidden-v1-' + (activeId.value || 'unbound') }
function readCustomGroups() {
  try {
    const original = JSON.parse(localStorage.getItem(groupsStorageKey()) || '[]')
    customGroups.value = Array.isArray(original) ? original
      .filter((g) => g?.id?.startsWith('custom-') && g.title &&
        Array.isArray(g.core) && Array.isArray(g.support))
      .slice(0, 50).map((g) => ({ ...g, facility: g.facility || '通用', kind: 'custom' })) : []
    const overrides = JSON.parse(localStorage.getItem(overridesStorageKey()) || '{}')
    groupOverrides.value = overrides && typeof overrides === 'object' && !Array.isArray(overrides)
      ? Object.fromEntries(Object.entries(overrides).filter(([id, g]) =>
        builtinGroups.some((original) => original.id === id) && g?.title &&
        Array.isArray(g.core) && Array.isArray(g.support))) : {}
    const hidden = JSON.parse(localStorage.getItem(hiddenStorageKey()) || '[]')
    hiddenGroupIds.value = Array.isArray(hidden)
      ? hidden.filter((id) => builtinGroups.some((g) => g.id === id)) : []
  } catch {
    customGroups.value = []
    groupOverrides.value = {}
    hiddenGroupIds.value = []
  }
  if (!groupOptions.value.some((g) => g.value === selectedGroupId.value)) {
    selectedGroupId.value = groupOptions.value[0]?.value || null
  }
}
function persistGroups() {
  try {
    localStorage.setItem(groupsStorageKey(), JSON.stringify(customGroups.value))
    localStorage.setItem(overridesStorageKey(), JSON.stringify(groupOverrides.value))
    localStorage.setItem(hiddenStorageKey(), JSON.stringify(hiddenGroupIds.value))
  } catch { message('本地存储不可用，组合未保存', 'warning') }
}
function startGroup(source = null) {
  const facility = source?.facility || (facilityFilter.value === '全部' ? '通用' : facilityFilter.value)
  draftGroup.value = source
    ? { id: source.id, title: source.title, facility, core: [...source.core],
        support: [...source.support], note: source.note || '' }
    : { id: '', title: '', facility, core: [], support: [], note: '' }
  groupEditorOpen.value = true
}
function storeGroup(item) {
  if (item.kind === 'built-in') {
    groupOverrides.value = { ...groupOverrides.value, [item.id]: item }
  } else {
    const index = customGroups.value.findIndex((x) => x.id === item.id)
    if (index >= 0) customGroups.value.splice(index, 1, item)
    else customGroups.value.push(item)
  }
  persistGroups()
}
function saveGroup() {
  const item = draftGroup.value
  if (!item.title?.trim() || item.title.length > 50) {
    message('名称需要在 1—50 字以内', 'warning'); return
  }
  const all = [...item.core, ...item.support]
  if (all.length > 40 || !all.every((id) => operatorCatalog.value[id])) {
    message('最多选择 40 名有效干员', 'warning'); return
  }
  if (!item.id && customGroups.value.length >= 50) {
    message('最多保存 50 个自定义组合', 'warning'); return
  }
  const kind = builtinGroups.some((g) => g.id === item.id) ? 'built-in' : 'custom'
  const saved = {
    id: item.id || 'custom-' + Date.now(),
    title: item.title.trim(), facility: item.facility,
    core: [...new Set(item.core)],
    support: [...new Set(item.support.filter((id) => !item.core.includes(id)))],
    note: (item.note || '').slice(0, 240), kind
  }
  storeGroup(saved)
  facilityFilter.value = saved.facility
  selectedGroupId.value = saved.id
  groupEditorOpen.value = false
}
function removeGroupMember(id) {
  if (!activeGroup.value) return
  storeGroup({
    ...activeGroup.value,
    core: activeGroup.value.core.filter((x) => x !== id),
    support: activeGroup.value.support.filter((x) => x !== id)
  })
}
function deleteGroup() {
  if (!activeGroup.value) return
  if (activeGroup.value.kind === 'built-in') {
    hiddenGroupIds.value = [...new Set([...hiddenGroupIds.value, selectedGroupId.value])]
    const overrides = { ...groupOverrides.value }
    delete overrides[selectedGroupId.value]
    groupOverrides.value = overrides
  } else {
    customGroups.value = customGroups.value.filter((g) => g.id !== selectedGroupId.value)
  }
  persistGroups()
  selectedGroupId.value = groupOptions.value[0]?.value || null
  groupEditorOpen.value = false
}
function restoreGroups() {
  hiddenGroupIds.value = []
  persistGroups()
  if (!groupOptions.value.some((g) => g.value === selectedGroupId.value)) {
    selectedGroupId.value = groupOptions.value[0]?.value || null
  }
}
const groupImportInput = ref(null)
const groupImportPending = ref(null)
const groupImportMode = ref('merge')
function memberForExport(id) {
  return { name: operatorCatalog.value[id]?.name || id, id }
}
function groupForExport(group) {
  return {
    id: group.id,
    title: group.title,
    facility: group.facility || '通用',
    core: group.core.map(memberForExport),
    support: group.support.map(memberForExport),
    note: conciseGroupNote(group.note)
  }
}
function exportGroups() {
  const output = {
    format: 'mower-gacha-groups-v3',
    _说明: [
      '支持 JSON 或 JSONC 顶部 // 注释；顶层 _说明、_示例 仅供阅读，导入时忽略。',
      'groups 中每项对应一个组合：title 名称、facility 设施、core 成员、support 挂件 / 备选、note 备注。',
      '成员既可写成干员名字字符串，也可写成 {name,id}；推荐保留 id 以免以后出现重名。',
      '可新增、改名、删减 groups 内成员；没有 ID 的新组合会自动生成本地 ID。',
      'hidden 为已隐藏的初始组合 ID，合并导入时会保留当前其它组合；替换导入则以此文件为准。',
      '不包含账号凭据、个人 UID、排班数据或持有状态。'
    ],
    _示例: {
      title: '我的办公室', facility: '办公室',
      core: ['凯尔希·思衡托'], support: ['迷迭香', '煌'],
      note: '挂件可按需要增减；保存后移入 groups 数组才会被导入。'
    },
    groups: availableGroups.value.map(groupForExport),
    hidden: [...hiddenGroupIds.value]
  }
  const header = [
    '// Mower 寻访 · 基建组合（可交给 AI 或直接用文本编辑器修改）',
    '// groups：每个对象一组；设施包括贸易、金属、源石、通用、加工、宿舍、办公室、会客室。',
    '// core / support：成员可写干员名字；建议保留导出的 {name,id}，用来区分角色。',
    '// 添加组可不填写 id；删除组后选择“替换”导入才会隐藏被移除的初始组合。',
    '// 仅保存在本机浏览器，不涉及账号令牌或排班；请保存好这个文件作为备份。',
    ''
  ].join('\n')
  const blob = new Blob([header + JSON.stringify(output, null, 2) + '\n'],
    { type: 'application/json;charset=utf-8' })
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = 'mower-gacha-groups.jsonc'
  a.click()
  setTimeout(() => URL.revokeObjectURL(href), 1000)
}
function resolveImportMember(item) {
  const id = typeof item === 'object' && item !== null ? item.id : item
  const name = typeof item === 'object' && item !== null ? item.name : item
  if (typeof id === 'string' && operatorCatalog.value[id]) {
    if (typeof name === 'string' && name !== id &&
        operatorCatalog.value[id].name !== name) {
      throw new Error('干员 ID 与名称不匹配：' + name)
    }
    return id
  }
  if (typeof name !== 'string' || !name.trim()) throw new Error('存在空干员名称')
  const matches = Object.entries(operatorCatalog.value)
    .filter(([key, v]) => key.startsWith('char_') && v?.name === name.trim())
  if (matches.length !== 1) {
    throw new Error(matches.length ? '干员同名，请补上 id：' + name : '干员未收录：' + name)
  }
  return matches[0][0]
}
function validateImportedGroup(raw, index) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('第 ' + (index + 1) + ' 组不是对象')
  const title = raw.title
  const facility = raw.facility || '通用'
  const facilities = facilityOptions.map((x) => x.value)
  if (typeof title !== 'string' || !title.trim() || title.length > 50) {
    throw new Error('第 ' + (index + 1) + ' 组名称无效')
  }
  if (!facilities.includes(facility) || facility === '全部') throw new Error(title + ' 的设施无效')
  if (!Array.isArray(raw.core) || !Array.isArray(raw.support || [])) {
    throw new Error(title + ' 的成员或挂件必须是数组')
  }
  if (raw.core.length + (raw.support?.length || 0) > 40) {
    throw new Error(title + ' 超出 40 人上限')
  }
  const core = [...new Set(raw.core.map(resolveImportMember))]
  const support = [...new Set((raw.support || []).map(resolveImportMember)
    .filter((id) => !core.includes(id)))]
  const builtIn = builtinGroups.find((g) => g.id === raw.id)
  const id = builtIn ? raw.id
    : (typeof raw.id === 'string' && raw.id.startsWith('custom-') && raw.id.length <= 100
      ? raw.id : 'custom-import-' + Date.now() + '-' + index)
  return {
    id, title: title.trim(), facility, core, support,
    note: typeof raw.note === 'string' ? raw.note.slice(0, 240) : '',
    kind: builtIn ? 'built-in' : 'custom'
  }
}
function stripJsonComments(input) {
  // JSONC: supports // and /* */ without altering strings, URLs or escaped quotes.
  let out = '', insideString = false, escaped = false, line = false, block = false
  for (let i = 0; i < input.length; i++) {
    const c = input[i], next = input[i + 1]
    if (line) {
      if (c === '\n' || c === '\r') { line = false; out += c }
      else out += ' '
      continue
    }
    if (block) {
      if (c === '*' && next === '/') { out += '  '; i++; block = false }
      else out += c === '\n' || c === '\r' ? c : ' '
      continue
    }
    if (insideString) {
      out += c
      if (escaped) escaped = false
      else if (c === '\\') escaped = true
      else if (c === '"') insideString = false
      continue
    }
    if (c === '"') { insideString = true; out += c }
    else if (c === '/' && next === '/') { line = true; out += '  '; i++ }
    else if (c === '/' && next === '*') { block = true; out += '  '; i++ }
    else out += c
  }
  if (block) throw new Error('JSONC 存在未结束的块注释')
  return out
}
async function readGroupImport(event) {
  const file = event.target.files?.[0]
  if (event.target) event.target.value = ''
  if (!file) return
  if (file.size > 1024 * 1024) {
    message('组合文件不能超过 1 MB', 'error'); return
  }
  try {
    await loadCatalog()
    const json = JSON.parse(stripJsonComments((await file.text()).replace(/^\uFEFF/, '')))
    if (!json || !Array.isArray(json.groups)) throw new Error('缺少 groups 数组')
    const groupsInput = json.format === 'mower-gacha-groups-v2'
      ? [...builtinGroups.filter((g) => !(json.hidden || []).includes(g.id))
        .map((g) => json.overrides?.[g.id] || g), ...json.groups]
      : json.groups
    if (!['mower-gacha-groups-v2','mower-gacha-groups-v3'].includes(json.format)) {
      throw new Error('不支持的组合文件格式')
    }
    if (groupsInput.length > 70) throw new Error('最多导入 70 组')
    const groups = groupsInput.map(validateImportedGroup)
    const ids = new Set()
    for (const g of groups) {
      if (ids.has(g.id)) throw new Error('组合 ID 重复：' + g.id)
      ids.add(g.id)
    }
    const hidden = Array.isArray(json.hidden) ?
      json.hidden.filter((id) => builtinGroups.some((g) => g.id === id)) : []
    groupImportPending.value = { groups, hidden, fileName: file.name }
    groupImportMode.value = 'merge'
  } catch (error) {
    groupImportPending.value = null
    message('导入失败：' + error.message, 'error')
  }
}
function applyGroupImport() {
  if (!groupImportPending.value) return
  const { groups, hidden } = groupImportPending.value
  const replace = groupImportMode.value === 'replace'
  const customs = replace ? [] : [...customGroups.value]
  const overrides = replace ? {} : { ...groupOverrides.value }
  for (const g of groups) {
    if (g.kind === 'built-in') {
      overrides[g.id] = g
    } else {
      const previous = customs.findIndex((x) => x.id === g.id ||
        (x.facility === g.facility && x.title === g.title))
      if (previous !== -1) customs.splice(previous, 1, g)
      else customs.push(g)
    }
  }
  if (customs.length > 50) { message('合并后超过 50 组，请选择替换导入', 'warning'); return }
  customGroups.value = customs
  groupOverrides.value = overrides
  hiddenGroupIds.value = replace
    ? [...new Set([...hidden, ...builtinGroups.filter((preset) =>
      !groups.some((g) => g.id === preset.id)).map((preset) => preset.id)])]
    : [...new Set([...hiddenGroupIds.value, ...hidden])]
  persistGroups()
  const first = groups.find((g) => !hiddenGroupIds.value.includes(g.id))
  if (first) { facilityFilter.value = first.facility; selectedGroupId.value = first.id }
  groupImportPending.value = null
  groupEditorOpen.value = false
  message('已导入 ' + groups.length + ' 个组合', 'success')
}
watch(facilityFilter, () => {
  if (!groupOptions.value.some((g) => g.value === selectedGroupId.value)) {
    selectedGroupId.value = groupOptions.value[0]?.value || null
  }
  groupEditorOpen.value = false
})
async function loadCatalog() {
  if (Object.keys(operatorCatalog.value).length) return
  const res = await axios.get(api('/catalog'), { timeout: 12000 })
  operatorCatalog.value = res.data.operators || {}
}

const activePane = ref('gacha')
const poolExpanded = ref(false)
const rosterInfo = ref(null)
const rosterLoading = ref(false)
const rosterNeedsSetup = ref(false)
function openSklandSettings() {
  router.push('/mowersettings')
}

const rosterQuery = ref('')
const rosterRarity = ref('all')
const rosterLimit = ref(48)
const rosterApprovals = ref({})
try {
  rosterApprovals.value = JSON.parse(localStorage.getItem('mower-gacha-roster-approvals-v1') || '{}')
} catch { /* LocalStorage may be unavailable */ }
const visiblePools = computed(() => poolExpanded.value
  ? summary.value?.pools || []
  : (summary.value?.pools || []).slice(0, 6))
const rosterApproved = computed(() => !!(
  activeId.value && rosterInfo.value?.available &&
  rosterApprovals.value[activeId.value] === rosterInfo.value.observed_at
))
function eliteBucket(op) {
  const phase = Number(op.evolve_phase || 0)
  const level = Number(op.level || 0)
  if (phase === 2 && level >= 90) return 'e2_90'
  if (phase === 2 && level >= 60) return 'e2_60'
  if (phase === 2) return 'e2_other'
  if (phase === 1) return 'e1'
  return 'e0'
}
const matchedRoster = computed(() => {
  const keyword = rosterQuery.value.trim().toLowerCase()
  return (rosterInfo.value?.operators || []).filter((op) =>
    (!keyword || (op.name || '').toLowerCase().includes(keyword) ||
      (op.id || '').toLowerCase().includes(keyword)) &&
    (rosterRarity.value === 'all' || String(op.rarity) === rosterRarity.value) &&
    (eliteFilter.value === 'all' || eliteBucket(op) === eliteFilter.value)
  )
})
const sortedRoster = computed(() => [...matchedRoster.value].sort((a, b) => {
  const phaseRank = Number(b.evolve_phase || 0) - Number(a.evolve_phase || 0)
  if (phaseRank !== 0) return phaseRank
  const levelRank = Number(b.level || 0) - Number(a.level || 0)
  if (levelRank !== 0) return levelRank
  return Number(b.rarity || 0) - Number(a.rarity || 0)
}))
const rosterStats = computed(() => {
  const list = rosterInfo.value?.operators || []
  return {
    e2_90: list.filter((op) => eliteBucket(op) === 'e2_90').length,
    e2_60: list.filter((op) => eliteBucket(op) === 'e2_60').length,
    e2_other: list.filter((op) => eliteBucket(op) === 'e2_other').length,
    e1: list.filter((op) => eliteBucket(op) === 'e1').length,
    e0: list.filter((op) => eliteBucket(op) === 'e0').length,
  }
})
const visibleRoster = computed(() => sortedRoster.value.slice(0, rosterLimit.value))
async function loadRoster() {
  if (rosterLoading.value) return
  rosterLoading.value = true
  try {
    await loadCatalog()
    const res = await axios.get(api('/roster'), { timeout: 14000 })
    rosterInfo.value = res.data
    rosterNeedsSetup.value = !res.data.available
    rosterLimit.value = 48
  } catch (error) { message(errorText(error), 'warning') }
  finally { rosterLoading.value = false }
}
async function refreshRemoteRoster() {
  if (rosterLoading.value) return
  rosterLoading.value = true
  message('已请求 Mower 现有森空岛模块手动刷新干员数据；仅本次点击执行。')
  try {
    const res = await axios.post(api('/refresh-roster'), {}, { ...writeOptions, timeout: 90000 })
    rosterInfo.value = res.data
    rosterNeedsSetup.value = !res.data.available
    rosterLimit.value = 48
    message('干员数据已更新', 'success')
  } catch (error) {
    const detail = errorText(error)
    rosterNeedsSetup.value = /森空岛|绑定|授权|登录|配置/.test(detail)
    message(detail, 'error')
  } finally { rosterLoading.value = false }
}
function approveRoster() {
  if (!activeId.value || !rosterInfo.value?.available) return
  rosterApprovals.value[activeId.value] = rosterInfo.value.observed_at
  try { localStorage.setItem('mower-gacha-roster-approvals-v1', JSON.stringify(rosterApprovals.value)) } catch {}
}
watch(activePane, (pane) => { if (pane === 'roster' && !rosterInfo.value) loadRoster() })
watch([rosterQuery, rosterRarity, eliteFilter], () => { rosterLimit.value = 48 })
watch(activeId, readCustomGroups)

const activeAccount = computed(() => accounts.value.find((a) => a.id === activeId.value))
const accountOptions = computed(() => accounts.value.map((a) => ({
  label: a.nickname + ' · ' + serverText(a.channel) + ' · UID ' + a.uid,
  value: a.id
})))
const selectedSession = computed(() =>
  sessions.value.find((s) =>
    s.selected && s.selected.channel + ':' + s.selected.uid === activeId.value
  )
)
const categories = computed(() => [
  { label: '所有卡池类型', value: '' },
  ...Object.keys(summary.value?.categories || {}).map((key) => ({ label: categoryLabel(key), value: key }))
])
const poolOptions = computed(() => [
  { label: '全部卡池', value: '' },
  ...(summary.value?.pools || []).filter((p) => !category.value || p.category === category.value)
    .map((p) => ({ label: p.pool_name + ' · ' + p.count + '抽', value: p.pool_id }))
])
const rarityOptions = [
  { label: '仅六星', value: 'six' },
  { label: '五星及以上', value: 'rare' },
  { label: '仅五星', value: 'five' },
  { label: '全部星级', value: 'all' },
  { label: '仅四星', value: 'four' },
  { label: '仅三星', value: 'three' }
]
const starRows = computed(() => [
  { star: 6, label: '六星', count: summary.value?.stars?.['6'] || 0 },
  { star: 5, label: '五星', count: summary.value?.stars?.['5'] || 0 },
  { star: 4, label: '四星', count: summary.value?.stars?.['4'] || 0 },
  { star: 3, label: '三星', count: summary.value?.stars?.['3'] || 0 }
])
function serverText(channel) {
  return { official: '官服', bilibili: 'B服', other: '其他渠道' }[channel] || '未知区服'
}
function categoryLabel(id) {
  return { normal: '常规寻访', classic: '中坚寻访', anniver_fest: '周年限定', summer_fest: '夏日限定' }[id] || id
}
function message(text, type = 'info') {
  alertText.value = String(text || '')
  alertType.value = type
}
function errorText(error) {
  return error?.response?.data?.message || error?.message || '请求失败，请检查本机连接'
}
function formatDate(ms) {
  return ms ? new Date(Number(ms)).toLocaleString('zh-CN', { hour12: false }) : '—'
}
function avatarUrl(name) {
  return '/avatar/' + encodeURIComponent(name || '') + '.webp'
}
function markMissing(name) {
  avatarMissing.value = new Set([...avatarMissing.value, name])
}
function restoreCooldown() {
  try {
    const saved = JSON.parse(sessionStorage.getItem('mower-gacha-sms-cooldown') || '{}')
    if (saved.lastFour === phone.value.slice(-4) && phone.value.length === 11) {
      cooldown.value = Math.max(0, Math.ceil((saved.expires - Date.now()) / 1000))
    } else {
      cooldown.value = 0
    }
  } catch {
    cooldown.value = 0
  }
}
function setCooldown(seconds) {
  const retry = Math.max(0, Math.min(600, Number(seconds) || 0))
  const expires = Date.now() + retry * 1000
  try {
    sessionStorage.setItem('mower-gacha-sms-cooldown', JSON.stringify({
      lastFour: phone.value.slice(-4), expires
    }))
  } catch { /* Timer still works if browser storage is disabled. */ }
  restoreCooldown()
}
let cooldownTimer
watch(phone, restoreCooldown)
async function refreshAccounts() {
  const res = await axios.get(api('/accounts'))
  accounts.value = res.data.accounts || []
  sessions.value = res.data.sessions || []
  if (!accounts.value.some((a) => a.id === activeId.value)) {
    activeId.value = accounts.value[0]?.id || ''
  }
}
function queryParams(extra = {}) {
  const params = { account_id: activeId.value, limit: 50, category: category.value, pool_id: poolId.value,
    search: search.value.trim(), new_only: newOnly.value ? '1' : '0', ...extra }
  if (rarity.value === 'six') params.rarity = 6
  if (rarity.value === 'five') params.rarity = 5
  if (rarity.value === 'four') params.rarity = 4
  if (rarity.value === 'three') params.rarity = 3
  if (rarity.value === 'rare') params.rarity_min = 5
  if (timeRange.value === '30d') params.start_ms = Date.now() - 30 * 86400000
  if (timeRange.value === '90d') params.start_ms = Date.now() - 90 * 86400000
  if (timeRange.value === 'custom' && Array.isArray(customDates.value) && customDates.value.length === 2) {
    params.start_ms = customDates.value[0]
    params.end_ms = customDates.value[1] + 86399999
  }
  return params
}
let viewRequest = 0
async function loadData() {
  if (!activeId.value) { summary.value = null; records.value = []; more.value = false; return }
  const requestNo = ++viewRequest
  loading.value = true
  try {
    const [stats, page] = await Promise.all([
      axios.get(api('/summary'), { params: { account_id: activeId.value } }),
      axios.get(api('/records'), { params: queryParams() })
    ])
    if (requestNo !== viewRequest) return
    summary.value = stats.data
    records.value = page.data.records || []
    offset.value = records.value.length
    more.value = records.value.length === 50
  } catch (error) { if (requestNo === viewRequest) message(errorText(error), 'error') }
  finally { if (requestNo === viewRequest) loading.value = false }
}
async function loadMore() {
  if (!activeId.value || !more.value || loading.value) return
  loading.value = true
  try {
    const page = await axios.get(api('/records'), { params: queryParams({ offset: offset.value }) })
    const batch = page.data.records || []
    records.value.push(...batch)
    offset.value += batch.length
    more.value = batch.length === 50
  } catch (error) { message(errorText(error), 'error') }
  finally { loading.value = false }
}
async function sendSms() {
  if (!/^1[3-9]\d{9}$/.test(phone.value)) { message('请先输入正确的手机号', 'warning'); return }
  if (sending.value || cooldown.value > 0) return
  sending.value = true
  try {
    const res = await axios.post(api('/send-code'), { phone: phone.value }, writeOptions)
    setCooldown(res.data.retry_after_seconds || 90)
    message('验证码已发送，请在下方输入。发送按钮倒计时结束后才能重发。', 'success')
  } catch (error) {
    const remaining = error?.response?.data?.retry_after_seconds
    if (remaining) setCooldown(remaining)
    message(errorText(error), 'warning')
  } finally { sending.value = false }
}
async function login() {
  if (loginBusy.value) return
  if (!/^1[3-9]\d{9}$/.test(phone.value)) { message('手机号格式不正确', 'warning'); return }
  if (loginMode.value === 'sms' && !/^\d{4,8}$/.test(code.value)) { message('请输入正确的短信验证码', 'warning'); return }
  if (loginMode.value === 'password' && !password.value) { message('请输入通行证密码', 'warning'); return }
  loginBusy.value = true
  try {
    const currentPhone = phone.value
    const path = loginMode.value === 'password' ? '/login-password' : '/login'
    const credentials = loginMode.value === 'password'
      ? { phone: currentPhone, password: password.value }
      : { phone: currentPhone, code: code.value }
    const res = await axios.post(api(path), credentials, { ...writeOptions, timeout: 40000 })
    selectedSessionId.value = res.data.session_id
    roleChoices.value = res.data.roles || []
    loginMask.value = res.data.account
    phone.value = ''
    code.value = ''
    password.value = ''
    await refreshAccounts()
    if (roleChoices.value.length === 1) {
      await chooseRole(selectedSessionId.value, roleChoices.value[0])
    } else {
      message('已验证账号。请选择要查看的官服或 B服角色，首次连接后会立即读取历史。', 'success')
    }
  } catch (error) { message(errorText(error), 'error') }
  finally {
    password.value = ''
    loginBusy.value = false
  }
}
async function chooseRole(sessionId, role) {
  if (loginBusy.value && !roleChoices.value.length) return
  const old = accounts.value.find((a) => a.id === role.channel + ':' + role.uid)
  loginBusy.value = true
  try {
    const res = await axios.post(api('/select-role'),
      { session_id: sessionId, uid: role.uid, channel: role.channel }, writeOptions)
    activeId.value = res.data.account_id
    roleChoices.value = []
    loginExpanded.value = false
    category.value = ''
    poolId.value = ''
    await refreshAccounts()
    await loadData()
    if (!old || old.total === 0) {
      // Only the first authorization automatically fetches records.
      await sync()
    } else {
      message('已切换到 ' + role.nickname + '（' + serverText(role.channel) + '）。后续更新请点击「手动同步」。', 'success')
    }
  } catch (error) { message(errorText(error), 'error') }
  finally { loginBusy.value = false }
}
async function sync() {
  if (syncing.value) return
  const session = selectedSession.value
  if (!session) {
    message('当前角色授权已失效，请重新登录。已存档历史可以离线查看。', 'warning')
    loginExpanded.value = true
    return
  }
  syncing.value = true
  message('正在查询官方各卡池记录，已存档历史不会被删除。')
  try {
    const res = await axios.post(api('/sync'),
      { session_id: session.session_id, account_id: activeId.value },
      { ...writeOptions, timeout: 240000 })
    await refreshAccounts()
    await loadData()
    const warnings = res.data.warnings || []
    message('同步完成：新增 ' + res.data.added + ' 抽，读取 ' + res.data.fetched + ' 条。' +
      (warnings.length ? ' 部分卡池出现提示：' + warnings.join('；') : ''),
      warnings.length ? 'warning' : 'success')
  } catch (error) {
    message(errorText(error), 'error')
    await loadData()
  } finally { syncing.value = false }
}
async function logout(sessionId) {
  try {
    await axios.post(api('/logout'), { session_id: sessionId }, writeOptions)
    await refreshAccounts()
    message('已退出登录，历史仍保留在本机。', 'success')
  } catch (error) { message(errorText(error), 'error') }
}
async function exportBackup() {
  if (!activeId.value) return
  try {
    const res = await axios.get(api('/export'), { params: { account_id: activeId.value }, responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const link = document.createElement('a')
    link.href = url
    link.download = (activeAccount.value?.channel || 'ark') + '-' + (activeAccount.value?.uid || 'records') + '-gacha.json'
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) { message(errorText(error), 'error') }
}
watch(activeId, () => { category.value = ''; poolId.value = ''; loadData() })
watch(category, () => { poolId.value = ''; loadData() })
watch([poolId, rarity, timeRange, customDates, newOnly], loadData)
let searchTimer
watch(search, () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadData, 300) })
onMounted(async () => {
  cooldownTimer = setInterval(restoreCooldown, 1000)
  try {
    await refreshAccounts()
    loginExpanded.value = accounts.value.length === 0
    await loadData()
  } catch (error) { message(errorText(error), 'error') }
})
onBeforeUnmount(() => { clearInterval(cooldownTimer); clearTimeout(searchTimer) })
</script>

<template>
  <div class="gacha-page">
    <div class="gacha-stack">
      <div class="gacha-nav">
        <n-radio-group v-model:value="activePane" size="large" class="gacha-tabs">
          <n-radio-button value="gacha">寻访统计</n-radio-button>
          <n-radio-button value="roster">我的干员</n-radio-button>
        </n-radio-group>
        <HelpText label="页面说明">
          {{ activePane === 'gacha' ? '仅手动更新寻访记录。' : '只读取当前设备森空岛缓存。' }}
        </HelpText>
      </div>
      <n-alert v-if="alertText" :type="alertType" closable @close="alertText = ''">
        {{ alertText }}
      </n-alert>
      <div class="gacha-toolbar">
        <n-select v-if="accountOptions.length" v-model:value="activeId" :options="accountOptions"
          class="gacha-toolbar-account" placeholder="选择账号" size="medium"/>
        <n-text v-else depth="3" class="gacha-toolbar-account">未添加账号</n-text>
        <n-button v-if="activePane === 'gacha'" class="gacha-toolbar-sync" type="primary" :loading="syncing"
          :disabled="!selectedSession" title="只在点击时向鹰角同步寻访记录" @click="sync">
          同步寻访
        </n-button>
        <n-button v-else class="gacha-toolbar-sync" type="primary" :loading="rosterLoading"
          title="只在点击时使用 Mower 当前森空岛账号同步" @click="refreshRemoteRoster">
          同步干员
        </n-button>
        <template v-if="activePane === 'gacha'">
          <n-button secondary size="small" @click="loginExpanded = !loginExpanded"
            :title="selectedSession ? '切换或添加授权账号' : '同步前需要鹰角账号授权'">
            {{ loginExpanded ? '收起授权' : '账号授权' }}
          </n-button>
          <n-button quaternary size="small" :disabled="!activeAccount" @click="exportBackup" title="导出本机寻访记录">
            导出
          </n-button>
          <n-text depth="3" class="gacha-toolbar-meta"
            :title="'最近同步：' + (activeAccount?.last_sync ? formatDate(activeAccount.last_sync * 1000) : '未同步')">
            {{ activeAccount?.total || 0 }} 抽{{ activeAccount && !selectedSession ? ' · 待授权' : '' }}
          </n-text>
        </template>
        <template v-else>
          <n-button secondary size="small" :loading="rosterLoading" @click="loadRoster"
            title="只读取本机缓存，不请求森空岛">读取缓存</n-button>
          <n-button v-if="!rosterApproved && rosterInfo?.available && activeAccount" secondary size="small"
            title="确认本机森空岛缓存属于所选账号，无需重新登录" @click="approveRoster">确认归属</n-button>
          <n-text depth="3" class="gacha-toolbar-meta"
            :title="'缓存时间：' + formatDate(rosterInfo?.observed_at * 1000)">
            {{ rosterInfo?.operator_count || 0 }} 干员
          </n-text>
        </template>
      </div>

      <div v-if="activePane === 'roster'" class="gacha-roster-container">
      <n-card key="roster-profile-card" title="干员档案" size="medium">
        <n-space vertical :size="12">
          <n-alert v-if="rosterNeedsSetup || rosterInfo?.available === false" type="warning" :bordered="false">
            <n-space align="center" :wrap="true">
              <n-text>未读取到森空岛干员数据</n-text>
              <n-button text type="primary" @click="openSklandSettings">前往 Mower 设置 → 森空岛</n-button>
              <HelpText label="森空岛说明">请先在 Mower 设置配置森空岛，已有数据可直接读取缓存。</HelpText>
            </n-space>
          </n-alert>
          <template v-if="rosterInfo?.available">
            <n-text v-if="rosterInfo.unknown_id_count" depth="3" class="gacha-muted"
              :title="'当前本机干员资源仍有 ' + rosterInfo.unknown_id_count + ' 个无法识别的 ID'">
              待识别 {{ rosterInfo.unknown_id_count }}
            </n-text>
            <n-space align="center" :wrap="true">
              <n-input v-model:value="rosterQuery" clearable placeholder="搜索名称或干员 ID，例如结城理"
                style="max-width:320px;width:100%" />
              <n-radio-group v-model:value="rosterRarity" size="small">
                <n-radio-button value="all">全部</n-radio-button>
                <n-radio-button value="6">六星</n-radio-button>
                <n-radio-button value="5">五星</n-radio-button>
                <n-radio-button value="4">四星</n-radio-button>
                <n-radio-button value="3">三星</n-radio-button>
                <n-radio-button value="2">二星</n-radio-button>
                <n-radio-button value="1">一星</n-radio-button>
              </n-radio-group>
              <n-text depth="3" class="gacha-muted">{{ matchedRoster.length }} 名</n-text>
            </n-space>
            <n-space align="center" :wrap="true" class="gacha-roster-stats">
              <n-button size="small" :type="eliteFilter === 'all' ? 'primary' : 'default'"
                :secondary="eliteFilter !== 'all'" @click="eliteFilter = 'all'">全部 {{ rosterInfo.operator_count }}</n-button>
              <n-button size="small" :type="eliteFilter === 'e2_90' ? 'primary' : 'default'"
                :secondary="eliteFilter !== 'e2_90'" @click="eliteFilter = eliteFilter === 'e2_90' ? 'all' : 'e2_90'">
                精二90 {{ rosterStats.e2_90 }}
              </n-button>
              <n-button size="small" :type="eliteFilter === 'e2_60' ? 'primary' : 'default'"
                :secondary="eliteFilter !== 'e2_60'" @click="eliteFilter = eliteFilter === 'e2_60' ? 'all' : 'e2_60'">
                精二60—89 {{ rosterStats.e2_60 }}
              </n-button>
              <n-button size="small" :type="eliteFilter === 'e2_other' ? 'primary' : 'default'"
                :secondary="eliteFilter !== 'e2_other'" @click="eliteFilter = eliteFilter === 'e2_other' ? 'all' : 'e2_other'">
                精二1—59 {{ rosterStats.e2_other }}
              </n-button>
              <n-button size="small" :type="eliteFilter === 'e1' ? 'primary' : 'default'"
                :secondary="eliteFilter !== 'e1'" @click="eliteFilter = eliteFilter === 'e1' ? 'all' : 'e1'">
                精一 {{ rosterStats.e1 }}
              </n-button>
              <n-button size="small" :type="eliteFilter === 'e0' ? 'primary' : 'default'"
                :secondary="eliteFilter !== 'e0'" @click="eliteFilter = eliteFilter === 'e0' ? 'all' : 'e0'">
                精零 {{ rosterStats.e0 }}
              </n-button>
            </n-space>
            <div class="gacha-roster-grid">
              <div v-for="op in visibleRoster" :key="op.id" class="gacha-roster-op">
                <div class="gacha-record-avatar" :class="'star-' + op.rarity">
                  <img v-if="!avatarMissing.has(op.name)" :src="avatarUrl(op.name)"
                    :alt="op.name" loading="lazy" @error="markMissing(op.name)" />
                  <span v-else>{{ op.name.slice(0, 1) }}</span>
                </div>
                <div class="gacha-roster-name">
                  <strong :title="op.name">{{ op.name }}</strong>
                  <n-text depth="3" class="gacha-muted">{{ op.rarity }}★ · 精英{{ op.evolve_phase }} · Lv{{ op.level }}</n-text>
                </div>
              </div>
            </div>
            <n-empty v-if="!matchedRoster.length" description="没有结果" />
            <n-button v-if="matchedRoster.length > rosterLimit" block secondary
              @click="rosterLimit += 48">显示更多干员（{{ matchedRoster.length - rosterLimit }}）</n-button>
          </template>
        </n-space>
      </n-card>

      <n-card key="roster-groups-card" v-if="rosterInfo?.available" title="基建组合" size="medium">
        <div class="gacha-group-stack">
          <div class="gacha-group-toolbar">
            <n-select v-model:value="facilityFilter" :options="facilityOptions" size="medium"
              class="gacha-facility-select" placeholder="设施"/>
            <n-select v-model:value="selectedGroupId" filterable :options="groupOptions" size="medium"
              class="gacha-group-select" placeholder="选择组合"/>
            <n-button size="small" type="primary" secondary @click="startGroup()">新建</n-button>
            <n-button v-if="activeGroup" size="small" secondary @click="startGroup(activeGroup)">编辑</n-button>
            <n-popconfirm v-if="activeGroup" placement="bottom" positive-text="删除" negative-text="取消" @positive-click="deleteGroup">
              <template #trigger><n-button size="small" quaternary type="error">删除</n-button></template>
              删除此组合？
            </n-popconfirm>
            <n-button v-if="hiddenGroupIds.length" size="small" quaternary @click="restoreGroups"
              title="恢复已删除的初始组合">恢复</n-button>
            <n-button size="small" quaternary @click="groupImportInput?.click()"
              title="导入 JSON 组合文件，可选择合并或替换">导入</n-button>
            <input ref="groupImportInput" type="file" accept=".json,.jsonc,application/json"
              class="gacha-hidden-input" @change="readGroupImport" />
            <n-button size="small" quaternary @click="exportGroups"
              title="导出可人工或 AI 修改的 JSON 组合文件">导出</n-button>
            <HelpText label="分享组合">
              导出组合文件，分享你的基建搭配；导入其他博士分享的组合，查看自己还缺哪些干员。
              导入不会修改实际基建排班。
            </HelpText>
          </div>
          <n-card v-if="groupImportPending" size="small" title="导入预览">
            <n-space vertical :size="9">
              <n-text>{{ groupImportPending.fileName }} · {{ groupImportPending.groups.length }} 组</n-text>
              <n-radio-group v-model:value="groupImportMode" size="small">
                <n-radio-button value="merge">合并（保留现有组合）</n-radio-button>
                <n-radio-button value="replace">替换（覆盖当前组合）</n-radio-button>
              </n-radio-group>
              <n-space>
                <n-button type="primary" @click="applyGroupImport">确认导入</n-button>
                <n-button secondary @click="groupImportPending = null">取消</n-button>
              </n-space>
            </n-space>
          </n-card>
          <template v-if="activeGroup">
            <div class="gacha-group-summary">
              <n-text depth="3" :title="rosterApproved ? '当前账号已持有 / 组合总数' : '当前缓存已收录 / 组合总数（归属待确认）'">
                {{ groupCount.present }} / {{ groupMembers.length }}
              </n-text>
            </div>
            <div v-if="groupMembers.length" class="gacha-group-grid">
              <div v-for="op in groupMembers" :key="op.id"
                :class="['gacha-group-member', { 'gacha-group-member-missing': !op.owned }]"
                :title="op.owned ? '当前缓存已持有' : (rosterApproved ? '当前缓存未见' : '缓存未见，账号归属待确认')">
                <div class="gacha-group-avatar">
                  <img v-if="!avatarMissing.has(op.name)" :src="avatarUrl(op.name)"
                    :alt="op.name" loading="lazy" @error="markMissing(op.name)" />
                  <span v-else>{{ op.name.slice(0,1) }}</span>
                </div>
                <div class="gacha-group-name">
                  <strong>{{ op.name }}</strong>
                  <n-text v-if="op.kind === 'support'" depth="3" class="gacha-muted">挂件</n-text>
                </div>
                <n-button size="tiny" quaternary circle class="gacha-group-remove"
                  :title="'从组合中移除 ' + op.name" @click.stop="removeGroupMember(op.id)">×</n-button>
              </div>
            </div>
            <n-empty v-else description="暂无成员" />
          </template>
          <n-empty v-else description="该分类暂无组合" />
          <n-card v-if="groupEditorOpen" title="编辑组合" size="small">
            <n-space vertical :size="10">
              <n-space align="center" :wrap="true">
                <n-input v-model:value="draftGroup.title" class="gacha-group-edit-name"
                  placeholder="组合名称" :maxlength="50"/>
                <n-select v-model:value="draftGroup.facility"
                  :options="facilityOptions.filter((x) => x.value !== '全部')"
                  class="gacha-facility-select" placeholder="所属设施"/>
              </n-space>
              <n-text depth="3" class="gacha-muted">成员</n-text>
              <n-select v-model:value="draftGroup.core" :options="catalogOptions"
                multiple filterable clearable max-tag-count="responsive" placeholder="添加干员"
                :render-label="renderGroupOption" :render-tag="renderGroupTag"/>
              <n-text depth="3" class="gacha-muted">挂件 / 替补</n-text>
              <n-select v-model:value="draftGroup.support" :options="catalogOptions"
                multiple filterable clearable max-tag-count="responsive" placeholder="添加挂件"
                :render-label="renderGroupOption" :render-tag="renderGroupTag"/>
              <n-input v-model:value="draftGroup.note" type="textarea" :rows="2"
                placeholder="备注（仅悬停查看，可留空）" :maxlength="240" />
              <n-space>
                <n-button type="primary" @click="saveGroup">保存</n-button>
                <n-button secondary @click="groupEditorOpen = false">取消</n-button>
              </n-space>
            </n-space>
          </n-card>
        </div>
      </n-card>

      </div>
      <n-card v-if="loginExpanded && activePane === 'gacha'" title="账号授权" size="medium">
        <n-space vertical :size="12">
          <n-radio-group v-model:value="loginMode" size="medium">
            <n-radio-button value="sms">短信验证码登录</n-radio-button>
            <n-radio-button value="password">密码登录</n-radio-button>
          </n-radio-group>
          <div class="gacha-auth-fields">
            <div class="gacha-input">
              <n-text depth="3">手机号</n-text>
              <n-input v-model:value="phone" placeholder="鹰角通行证手机号" :maxlength="11" clearable />
            </div>
            <template v-if="loginMode === 'sms'">
              <div class="gacha-input gacha-code">
                <n-text depth="3">短信验证码</n-text>
                <n-input v-model:value="code" placeholder="请输入验证码" :maxlength="8" clearable />
              </div>
              <n-button :loading="sending" :disabled="sending || cooldown > 0 || !/^1[3-9]\d{9}$/.test(phone)"
                @click="sendSms">
                {{ cooldown > 0 ? cooldown + ' 秒后重发' : '发送验证码' }}
              </n-button>
            </template>
            <div v-else class="gacha-input gacha-password">
              <n-text depth="3">鹰角通行证密码</n-text>
              <n-input v-model:value="password" type="password" show-password-on="click"
                placeholder="本地输入，不保存" autocomplete="new-password" />
            </div>
            <n-button type="primary" :loading="loginBusy" :disabled="loginBusy || !/^1[3-9]\d{9}$/.test(phone) || (loginMode === 'sms' ? !code : !password)"
              @click="login">
              验证并读取角色
            </n-button>
          </div>

          <n-card v-if="roleChoices.length" size="small" :title="'已验证 ' + loginMask + ' · 请选择角色'">
            <n-space vertical>
              <n-space v-for="role in roleChoices" :key="role.channel + ':' + role.uid" align="center">
                <n-tag :type="role.channel === 'official' ? 'success' : 'info'">{{ serverText(role.channel) }}</n-tag>
                {{ role.nickname }} · {{ role.uid }}
                <n-button size="small" type="primary" :loading="loginBusy"
                  @click="chooseRole(selectedSessionId, role)">连接此角色</n-button>
              </n-space>
            </n-space>
          </n-card>
          <n-collapse v-if="sessions.length">
            <n-collapse-item title="已登录账号与角色切换" name="sessions">
              <n-space vertical>
                <n-space v-for="session in sessions" :key="session.session_id" align="center">
                  <n-button v-for="role in session.roles" :key="role.channel + ':' + role.uid"
                    size="small" secondary :loading="loginBusy" @click="chooseRole(session.session_id, role)">
                    {{ role.nickname }} · {{ serverText(role.channel) }}
                  </n-button>
                  <n-button size="small" quaternary type="error" @click="logout(session.session_id)">退出</n-button>
                </n-space>
              </n-space>
            </n-collapse-item>
          </n-collapse>
        </n-space>
      </n-card>

      <template v-if="activePane === 'gacha' && summary && activeAccount">
        <div class="gacha-summary-grid">
          <n-card size="small"><n-statistic label="已存档抽数" :value="summary.total" /></n-card>
          <n-card size="small"><n-statistic label="六星记录" :value="summary.six_star" /></n-card>
          <n-card size="small"><n-statistic label="五星次数" :value="summary.five_star" /></n-card>
          <n-card size="small"><n-statistic label="不同干员" :value="summary.distinct_operators" /></n-card>
        </div>

        <n-card title="卡池概览" size="medium">
          <template #header-extra>
            <n-text v-if="summary.pools?.length > 6" depth="3" class="gacha-muted">
              最近 6 / {{ summary.pools.length }}
            </n-text>
          </template>
          <div v-if="summary.pools?.length" :class="['gacha-pool-grid', { 'gacha-pool-grid-expanded': poolExpanded }]">
            <div v-for="pool in visiblePools" :key="pool.category + ':' + pool.pool_id" class="gacha-pool">
              <n-space justify="space-between" align="start" :wrap="false">
                <div>
                  <n-text depth="3" class="gacha-muted">{{ categoryLabel(pool.category) }}</n-text>
                  <div class="gacha-pool-name">{{ pool.pool_name }}</div>
                </div>
                <n-tag type="success" :bordered="false">{{ pool.count }} 抽</n-tag>
              </n-space>
              <n-space align="center" :size="10">
                <n-text><strong>{{ pool.six_star }}</strong> 次六星</n-text>
                <n-text depth="3">{{ pool.five_star }} 次五星</n-text>
              </n-space>
              <div v-if="pool.six_operators.length" class="gacha-six-timeline">
                <div v-for="op in pool.six_operators" :key="op.char_id + ':' + op.pool_index"
                  :class="['gacha-six-hit', {
                    'gacha-six-hit-target': selectedHit === pool.pool_id + ':' + op.pool_index
                  }]"
                  :title="op.char_name + ' · 本池已存档第 ' + op.pool_index + ' 抽；' +
                    (op.interval_complete ? '距上一六星 ' + op.interval_count + ' 抽' :
                    '本池首个已存档六星，前序可能缺失')"
                  tabindex="0" role="button"
                  @click="selectedHit = pool.pool_id + ':' + op.pool_index"
                  @keydown.enter.prevent="selectedHit = pool.pool_id + ':' + op.pool_index"
                  @keydown.space.prevent="selectedHit = pool.pool_id + ':' + op.pool_index">
                  <div class="gacha-six-hit-head">
                    <div class="gacha-avatar-wrap">
                      <img v-if="!avatarMissing.has(op.char_name)" :src="avatarUrl(op.char_name)"
                        :alt="op.char_name" loading="lazy" @error="markMissing(op.char_name)" />
                      <span v-else class="gacha-avatar-fallback">{{ op.char_name.slice(0, 1) }}</span>
                    </div>
                    <strong class="gacha-six-name" :title="op.char_name">{{ op.char_name }}</strong>
                    <strong class="gacha-six-number">{{ op.interval_count }}</strong>
                  </div>
                </div>
              </div>
              <n-text v-else depth="3" class="gacha-muted">本池尚无六星记录</n-text>
            </div>
          </div>
          <n-empty v-else description="还没有已保存的卡池数据" />
          <n-button v-if="summary.pools?.length > 6" block secondary style="margin-top:14px"
            @click="poolExpanded = !poolExpanded">
            {{ poolExpanded ? '收起，仅显示最近6池' : '查看其余 ' + (summary.pools.length - 6) + ' 个卡池' }}
          </n-button>

        </n-card>

        <n-card title="星级分布" size="medium">
          <template #header-extra>
            <HelpText label="历史完整性">仅统计已保存的记录。</HelpText>
          </template>
          <div class="gacha-stars">
            <div v-for="star in starRows" :key="star.star" class="gacha-stars-row">
              <n-text depth="3">{{ star.label }}</n-text>
              <div class="gacha-stars-track">
                <div :class="'gacha-stars-fill star-' + star.star"
                  :style="{ width: summary.total ? (star.count / summary.total * 100) + '%' : '0%' }"></div>
              </div>
              <strong>{{ star.count }}</strong>
              <n-text depth="3" class="gacha-star-percent">
                {{ summary.total ? (star.count / summary.total * 100).toFixed(1) : '0.0' }}%
              </n-text>
            </div>
          </div>

        </n-card>

        <n-card title="寻访流水" size="medium">
          <n-space vertical>
            <div class="gacha-filters">
              <n-select v-model:value="category" :options="categories" placeholder="卡池分类" />
              <n-select v-model:value="poolId" :options="poolOptions" placeholder="具体卡池" />
              <n-select v-model:value="rarity" :options="rarityOptions" placeholder="星级筛选" />
              <n-select v-model:value="timeRange" :options="[
                { label: '全部历史', value: 'all' }, { label: '最近30天', value: '30d' },
                { label: '最近90天', value: '90d' }, { label: '自选日期', value: 'custom' }
              ]" />
            </div>
            <n-date-picker v-if="timeRange === 'custom'" v-model:value="customDates" type="daterange"
              clearable style="max-width:380px" />
            <n-space align="center">
              <n-input v-model:value="search" clearable placeholder="搜索干员名称" style="max-width:260px" />
              <n-checkbox v-model:checked="newOnly">仅首次获得</n-checkbox>
              <n-text depth="3" class="gacha-muted">默认只显示六星，其他星级可在筛选器中查看。</n-text>
            </n-space>
            <div class="gacha-record-list">
              <div v-for="(r, index) in records" :key="r.gacha_ts + ':' + r.position + ':' + index"
                class="gacha-record">
                <div :class="'gacha-record-avatar star-' + r.rarity">
                  <img v-if="!avatarMissing.has(r.char_name)" :src="avatarUrl(r.char_name)"
                    :alt="r.char_name" loading="lazy" @error="markMissing(r.char_name)" />
                  <span v-else>{{ r.char_name.slice(0, 1) }}</span>
                </div>
                <div class="gacha-record-main">
                  <n-space align="center" :size="7">
                    <strong>{{ r.char_name }}</strong>
                    <n-tag size="small" :type="r.rarity === 6 ? 'warning' : 'default'">
                      {{ r.rarity }}★
                    </n-tag>
                    <n-tag v-if="r.is_new" size="small" type="success">首次获得</n-tag>
                  </n-space>
                  <n-text depth="3" class="gacha-muted">{{ r.pool_name }}</n-text>
                </div>
                <n-text depth="3" class="gacha-record-date">{{ formatDate(r.gacha_ts) }}</n-text>
              </div>
              <n-empty v-if="!records.length && !loading" description="当前筛选下没有记录" />
            </div>
            <n-button v-if="more" block secondary :loading="loading" @click="loadMore">加载更多</n-button>
          </n-space>
        </n-card>
      </template>
    </div>
  </div>
</template>

<style scoped>
.gacha-page { padding: 10px; box-sizing: border-box; width: 100%; max-width: 1300px; margin: auto; }
.gacha-auth-fields { display: flex; align-items: flex-end; flex-wrap: wrap; gap: 10px; }
.gacha-input { min-width: 190px; display: flex; flex-direction: column; gap: 6px; flex: 1; }
.gacha-code { min-width: 135px; max-width: 175px; }
.gacha-password { max-width: 340px; }
.gacha-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; }
.gacha-pool-grid { display: flex; flex-direction: column; gap: 10px; }
.gacha-pool-name { font-size: 15px; font-weight: 600; }
.gacha-avatar-wrap { position: relative; width: 49px; height: 49px; border: 1px solid rgba(204,156,65,.6); border-radius: 7px; overflow: visible; background: rgba(204,156,65,.1); }
.gacha-avatar-wrap img { width: 100%; height: 100%; object-fit: cover; border-radius: 6px; }
.gacha-avatar-fallback { display: grid; place-items: center; height: 100%; }
.gacha-stars { display: flex; flex-direction: column; gap: 10px; }
.gacha-stars-row { display: grid; grid-template-columns: 48px minmax(0,1fr) 40px 50px; align-items: center; gap: 12px; }
.gacha-stars-track { background: var(--mower-control-surface, rgba(127,127,127,.15)); height: 9px; border-radius: 10px; overflow: hidden; }
.gacha-stars-fill { height: 100%; border-radius: 10px; min-width: 0; }
.gacha-stars-fill.star-6 { background: #d2a054; }
.gacha-stars-fill.star-5 { background: #ad89ca; }
.gacha-stars-fill.star-4 { background: var(--mower-primary, #18a058); }
.gacha-stars-fill.star-3 { background: #83939c; }
.gacha-star-percent { text-align: right; }
.gacha-filters { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 10px; }
.gacha-record-list { max-height: 680px; overflow: auto; }
.gacha-record { display: flex; align-items: center; gap: 13px; border-bottom: 1px solid var(--mower-divider, rgba(127,127,127,.14)); padding: 10px 4px; }
.gacha-record-avatar { width: 47px; height: 47px; flex: 0 0 47px; background: var(--mower-control-surface, rgba(127,127,127,.1)); border-radius: 7px; display: grid; place-items: center; overflow: hidden; }
.gacha-record-avatar.star-6 { border: 1px solid rgba(210,160,84,.7); }
.gacha-record-avatar.star-5 { border: 1px solid rgba(173,137,202,.55); }
.gacha-record-avatar img { display: block; width: 100%; height: 100%; object-fit: cover; }
.gacha-record-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 5px; }
.gacha-record-date { font-size: 12px; white-space: nowrap; text-align: right; }
@media(max-width:850px) {
 .gacha-summary-grid { grid-template-columns: repeat(2,minmax(0,1fr)); }
 .gacha-filters { grid-template-columns: repeat(2,minmax(0,1fr)); }
}
@media(max-width:550px) {
 .gacha-page { padding: 8px; }
 .gacha-auth-fields > * { flex-basis: 100%; max-width: none; }
 .gacha-record-date { font-size: 11px; }
 .gacha-record { gap: 8px; }
}
.gacha-tabs { padding: 0 2px; }
.gacha-pool-grid-expanded { max-height: 850px; overflow-y: auto; padding-right: 3px; }
.gacha-pool { display: flex; flex-direction: column; width: 100%; box-sizing: border-box;
  gap: 8px; padding: 11px 13px; min-width: 0; border-radius: 10px;
  border: 1px solid var(--mower-divider,rgba(120,120,120,.16));
  background: var(--mower-control-surface,rgba(127,127,127,.035)); }
.gacha-six-timeline { display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr));
  gap: 8px; width: 100%; overflow: visible; }
.gacha-six-hit { min-width: 0; padding: 8px 10px; border-radius: 9px;
  border: 1px solid var(--mower-divider,rgba(120,120,120,.16));
  display: flex; flex-direction: column; justify-content: center; gap: 6px;
  cursor: pointer; transition: border-color .12s ease, background-color .12s ease; }
.gacha-six-hit:focus-visible { outline: 2px solid var(--mower-primary,#18a058); outline-offset: 2px; }
.gacha-six-hit-target { border-color: var(--mower-primary,#18a058);
  background: var(--mower-primary-block,rgba(24,160,88,.08)); }
.gacha-six-hit-head { display: flex; align-items: center; gap: 8px; min-width: 0; width: 100%; }
.gacha-six-name { flex: 1 1 auto; min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.gacha-six-hit .gacha-avatar-wrap { flex: 0 0 44px; width: 44px; height: 44px; }
.gacha-six-number { display: block; margin-left: auto; flex: 0 0 auto; font-size: 27px; font-weight: 750; line-height: 1;
  color: var(--mower-primary,#18a058); font-variant-numeric: tabular-nums; }
.gacha-roster-grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(160px,1fr)); gap: 9px; }
.gacha-roster-op { border: 1px solid var(--mower-divider,rgba(120,120,120,.15));
  border-radius: 8px; padding: 9px; display: flex; gap: 9px; align-items: center; min-width: 0; }
.gacha-roster-name { min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.gacha-roster-name strong { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.gacha-stack { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.gacha-nav { display: flex; align-items: center; gap: 12px; }
.gacha-toolbar { display: flex; align-items: center; gap: 9px; flex-wrap: wrap;
  padding: 9px 12px; border: 1px solid var(--mower-divider,rgba(120,120,120,.14));
  border-radius: 10px; min-width: 0; }
.gacha-toolbar-account { flex: 1 1 260px; max-width: 480px; min-width: 190px; }
.gacha-toolbar-sync { min-width: 94px; }
.gacha-toolbar-meta { margin-left: auto; font-size: 12px; white-space: nowrap; }
.gacha-roster-container { display: flex; flex-direction: column; gap: 10px; }
.gacha-group-stack { display: flex; flex-direction: column; gap: 12px; }
.gacha-group-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.gacha-facility-select { width: 130px; }
.gacha-group-select { flex: 1 1 220px; max-width: 420px; min-width: 150px; }
.gacha-group-summary { display: flex; align-items: baseline; gap: 10px; }
.gacha-group-edit-name { flex: 1 1 240px; min-width: 190px; }
.gacha-group-grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(170px,1fr)); gap: 10px; }
.gacha-group-member { display: flex; align-items: center; gap: 10px; padding: 9px;
  border-radius: 8px; border: 1px solid var(--mower-divider,rgba(120,120,120,.16)); min-width: 0; }
.gacha-group-member-missing { border-style: dashed; }
.gacha-group-member-missing .gacha-group-avatar { opacity: .42; filter: grayscale(.38); }
.gacha-group-remove { opacity: .45; margin-left: auto; }
.gacha-group-member:hover .gacha-group-remove, .gacha-group-remove:focus-visible { opacity: 1; }
.gacha-group-avatar { width: 51px; height: 51px; flex: 0 0 51px; border-radius: 7px;
  background: var(--mower-control-surface,rgba(127,127,127,.1));
  overflow: hidden; display: grid; place-items: center; }
.gacha-group-avatar img { width: 100%; height: 100%; object-fit: cover; }
.gacha-group-name { min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.gacha-group-name strong { text-overflow: ellipsis; overflow: hidden; white-space: nowrap; }
.gacha-hidden-input { display: none; }
.gacha-option-inner { display: inline-flex; align-items: center; gap: 7px; min-width: 0; vertical-align: middle; }
.gacha-option-inner > span { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.gacha-option-avatar { width: 25px; height: 25px; flex: 0 0 auto; border-radius: 4px;
  object-fit: cover; background: var(--mower-control-surface, rgba(127,127,127,.08)); }
.gacha-option-tag { max-width: 100%; }

@media(max-width:550px) {
 .gacha-roster-container .n-radio-group.n-radio-group--button-group { display: flex; flex-wrap: wrap; max-width: 100%; width: 100%; gap: 4px; }
 .gacha-roster-container .n-radio-button { flex: 0 0 auto; }
 .gacha-toolbar-account { min-width: 100%; max-width: 100%; }
 .gacha-toolbar-meta { margin-left: 0; }
 .gacha-facility-select { width: 108px; }
 .gacha-group-select { min-width: 130px; }
 .gacha-group-grid { grid-template-columns: repeat(auto-fill,minmax(136px,1fr)); gap: 8px; }
}
</style>
