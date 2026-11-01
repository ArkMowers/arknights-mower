import {describe,it,expect} from 'vitest'
import {createDefaultWorkspace} from './defaults'
import {validateRosterWorkspace} from './validate'
import {exportMowerJson,importMowerJson} from './compat/mowerJson'
describe('alpha shared group validation', () => {
  it('allows same-group working primaries as replacements but rejects self and foreign groups', () => {
    const ws = createDefaultWorkspace()
    ws.mainPlan.facilities.dormitory_4.slots = Array.from({length: 5}, () => ({occupant: {kind: 'free' as const}, groupId: null, replacements: []}))
    ws.mainPlan.facilities.room_1_1.slots[0] = {occupant: {kind: 'operator', operatorId: 'char_123_fang'}, groupId: 'A', replacements: ['char_240_wyvern']}
    ws.mainPlan.facilities.room_1_2.slots[0] = {occupant: {kind: 'operator', operatorId: 'char_240_wyvern'}, groupId: 'A', replacements: ['char_123_fang']}
    expect(validateRosterWorkspace(ws).criticalErrors.filter(e => e.code === 'CONFLICTING_REPLACEMENT')).toEqual([])
    ws.mainPlan.facilities.room_1_1.slots[0]!.replacements = ['char_123_fang']
    expect(validateRosterWorkspace(ws).criticalErrors.some(e => e.code === 'CONFLICTING_REPLACEMENT')).toBe(true)
    ws.mainPlan.facilities.room_1_1.slots[0]!.replacements = ['char_240_wyvern']
    ws.mainPlan.facilities.room_1_2.slots[0]!.groupId = 'B'
    expect(validateRosterWorkspace(ws).criticalErrors.some(e => e.code === 'CONFLICTING_REPLACEMENT')).toBe(true)
  })

  it('rejects duplicate binding names, repeated empty columns and missing shared replacements', () => {
    const ws = createDefaultWorkspace()
    ws.mainPlan.facilities.dormitory_4.slots = Array.from({length: 5}, () => ({occupant: {kind: 'free' as const}, groupId: null, replacements: []}))
    const slot = ws.mainPlan.facilities.room_1_1.slots[0] = {occupant: {kind: 'operator' as const, operatorId: 'char_123_fang'}, groupId: 'A', replacements: ['char_240_wyvern'], groupBindings: [{groupId: 'A', replacements: ['char_192_falco']}]}
    expect(validateRosterWorkspace(ws).criticalErrors.some(e => e.code === 'INVALID_CONFIG')).toBe(true)
    slot.groupBindings[0]!.groupId = ''
    expect(validateRosterWorkspace(ws).criticalErrors.some(e => e.message.includes('空组名最多一列'))).toBe(false)
    slot.groupBindings.push({groupId: '', replacements: ['char_192_falco']})
    expect(validateRosterWorkspace(ws).criticalErrors.some(e => e.message.includes('空组名最多一列'))).toBe(true)
    slot.groupBindings.pop()
    slot.groupBindings[0] = {groupId: 'B', replacements: []}
    expect(validateRosterWorkspace(ws).criticalErrors.some(e => e.code === 'INVALID_CONFIG')).toBe(true)
  })

  it.each([false, true])('accepts one personal empty column in either position and round-trips main and backup plans: %s', emptyFirst => {
    const ws = createDefaultWorkspace()
    ws.mainPlan.facilities.dormitory_4.slots = Array.from({length: 5}, () => ({occupant: {kind: 'free' as const}, groupId: null, replacements: []}))
    const named = {groupId: 'A', replacements: ['char_240_wyvern']}, personal = {groupId: null, replacements: ['char_192_falco']}
    ws.mainPlan.facilities.room_1_1.slots[0] = {occupant: {kind: 'operator', operatorId: 'char_123_fang'}, ...(emptyFirst ? personal : named), groupBindings: [emptyFirst ? named : personal]}
    ws.mainPlan.facilities.room_1_2.slots[0] = {occupant: {kind: 'operator', operatorId: 'char_286_cast3'}, groupId: 'A', replacements: ['char_500_noirc']}
    expect(validateRosterWorkspace(ws).criticalErrors).toEqual([])
    const document = JSON.parse(exportMowerJson(ws))
    document.backup_plans = [{name: 'personal', trigger: 'True', plan: {room_1_1: document.plan1.room_1_1}}]
    const imported = importMowerJson(JSON.stringify(document))
    expect(validateRosterWorkspace(imported).criticalErrors).toEqual([])
    const output = JSON.parse(exportMowerJson(imported))
    expect(output.plan1.room_1_1).toEqual(document.plan1.room_1_1)
    expect(output.backup_plans).toEqual(document.backup_plans)
    const entry = imported.mainPlan.facilities.room_1_1.slots[0]!
    entry.groupBindings!.push({...personal})
    expect(validateRosterWorkspace(imported).criticalErrors.some(e => e.message.includes('空组名最多一列'))).toBe(true)
  })

  it.each([false, true])('rejects a personal empty dorm binding in either position in main and backup plans: %s', emptyFirst => {
    const ws = createDefaultWorkspace()
    ws.mainPlan.facilities.dormitory_4.slots = Array.from({length: 5}, () => ({occupant: {kind: 'free' as const}, groupId: null, replacements: []}))
    ws.mainPlan.facilities.room_1_2.slots[0] = {occupant: {kind: 'operator', operatorId: 'char_286_cast3'}, groupId: 'A', replacements: ['char_500_noirc']}
    const named = {groupId: 'A', replacements: ['Free']}, personal = {groupId: null, replacements: ['char_192_falco']}
    ws.mainPlan.facilities.dormitory_1.slots[0] = {occupant: {kind: 'operator', operatorId: 'char_123_fang'}, ...(emptyFirst ? personal : named), groupBindings: [emptyFirst ? named : personal]}
    const message = '宿舍多绑组不能配置个人空组名列；个人轮休仅适用于非宿舍工作主班。'
    expect(validateRosterWorkspace(ws).criticalErrors).toContainEqual(expect.objectContaining({code: 'INVALID_CONFIG', roomId: 'dormitory_1', message}))

    ws.mainPlan.facilities.dormitory_1.slots[0] = {occupant: {kind: 'operator', operatorId: 'char_123_fang'}, ...named}
    expect(validateRosterWorkspace(ws).criticalErrors).toEqual([])
    const namedSource = {group: 'A', replacement: ['Free']}, personalSource = {group: '', replacement: ['翎羽']}
    ws.compatibility.backupPlans = [{name: '宿舍个人空列', trigger: 'True', plan: {dormitory_1: {plans: [{agent: '芬', ...(emptyFirst ? personalSource : namedSource), group_bindings: [emptyFirst ? namedSource : personalSource]}]}}}]
    expect(validateRosterWorkspace(ws).criticalErrors).toContainEqual(expect.objectContaining({code: 'INVALID_CONFIG', roomId: 'dormitory_1', message: `副表 宿舍个人空列：${message}`}))
  })

  it('requires fixed working anchors for every shared group and grouped Free dorm', () => {
    const ws = createDefaultWorkspace()
    ws.mainPlan.facilities.dormitory_4.slots = Array.from({length: 5}, () => ({occupant: {kind: 'free' as const}, groupId: null, replacements: []}))
    ws.mainPlan.facilities.room_1_1.slots[0] = {occupant: {kind: 'operator', operatorId: 'char_123_fang'}, groupId: 'A', replacements: ['char_240_wyvern'], groupBindings: [{groupId: 'B', replacements: ['char_240_wyvern']}]}
    expect(validateRosterWorkspace(ws).criticalErrors.filter(e => e.message.includes('缺少决定上下班')).length).toBe(2)
    ws.mainPlan.facilities.room_1_2.slots[0] = {occupant: {kind: 'operator', operatorId: 'char_192_falco'}, groupId: 'A', replacements: ['char_500_noirc']}
    ws.mainPlan.facilities.room_2_1.slots[0] = {occupant: {kind: 'operator', operatorId: 'char_286_cast3'}, groupId: 'B', replacements: ['char_500_noirc']}
    expect(validateRosterWorkspace(ws).criticalErrors.filter(e => e.message.includes('缺少决定上下班'))).toEqual([])
    ws.mainPlan.conf.resting_standby = ['char_286_cast3']
    expect(validateRosterWorkspace(ws).criticalErrors.some(e => e.message.startsWith('B 缺少决定上下班'))).toBe(true)
  })

  it('validates each additional column independently, including Free dorm restrictions', () => {
    const ws = createDefaultWorkspace()
    ws.mainPlan.facilities.dormitory_4.slots = Array.from({length: 5}, () => ({occupant: {kind: 'free' as const}, groupId: null, replacements: []}))
    const slot = ws.mainPlan.facilities.dormitory_1.slots[0] = {occupant: {kind: 'operator' as const, operatorId: 'char_123_fang'}, groupId: 'A', replacements: ['Free'], groupBindings: [{groupId: 'B', replacements: ['Free']}]}
    ws.mainPlan.facilities.room_1_2.slots[0] = {occupant: {kind: 'operator', operatorId: 'char_192_falco'}, groupId: 'A', replacements: ['char_500_noirc']}
    ws.mainPlan.facilities.room_2_1.slots[0] = {occupant: {kind: 'operator', operatorId: 'char_286_cast3'}, groupId: 'B', replacements: ['char_500_noirc']}
    expect(validateRosterWorkspace(ws).criticalErrors).toEqual([])
    ws.compatibility.backupPlans = [{name: '具名宿舍多绑组', trigger: 'True', plan: {dormitory_1: JSON.parse(exportMowerJson(ws)).plan1.dormitory_1}}]
    expect(validateRosterWorkspace(ws).criticalErrors).toEqual([])
    ws.compatibility.backupPlans = []
    slot.groupBindings[0]!.replacements = ['char_240_wyvern', 'char_240_wyvern']
    expect(validateRosterWorkspace(ws).criticalErrors.some(e => e.code === 'DUPLICATE_REPLACEMENT')).toBe(true)
    slot.groupBindings[0] = {groupId: '', replacements: ['Free']}
    expect(validateRosterWorkspace(ws).criticalErrors.some(e => e.code === 'INVALID_CONFIG')).toBe(true)
    ws.mainPlan.facilities.room_1_1.slots[0] = {occupant: {kind: 'operator', operatorId: 'char_240_wyvern'}, groupId: 'A', replacements: ['Free']}
    expect(validateRosterWorkspace(ws).criticalErrors.some(e => e.roomId === 'room_1_1' && e.code === 'INVALID_CONFIG')).toBe(true)
  })
})
