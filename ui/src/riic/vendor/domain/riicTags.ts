import type { OperatorRecord } from './operators'

// Explicit game tooltip sets (gamedata_const.termDescriptionDict), not nation/group/team aliases.
// Source snapshot and hashes: src/data/riic-term-evidence.json.
const MEMBERS: Record<string, ReadonlySet<string>> = {
  sees: new Set(['结城理', '埃癸斯', '岳羽由加莉', '虎狼丸']),
  monsterHunter: new Set(['火龙S黑角', '麒麟R夜刀', '泰拉大陆调查团']),
  bubbleHunter: new Set(['焰狐龙梓兰', '雷狼龙S空爆', '罗德岛隐秘队']),
  knight: new Set(['耀骑士临光', '临光', '瑕光', '鞭刃', '焰尾', '远牙', '灰毫', '野鬃', '正义骑士号', '砾', '薇薇安娜']),
  workPlatform: new Set(['Lancet-2', 'Castle-3', 'THRM-EX', '正义骑士号', 'Friston-3', 'PhonoR-0', 'CONFESS-47', 'GALLUS²']),
  durin: new Set(['至简', '桃金娘', '褐果', '杜林', '特克诺']),
  exusiai: new Set(['新约能天使', '能天使']),
}
export type RiicTag = 'sees' | 'monsterHunter' | 'bubbleHunter' | 'knight' | 'workPlatform' | 'durin' | 'exusiai'
export function hasRiicTag(operator: Pick<OperatorRecord, 'name'>, tag: RiicTag): boolean {
  return MEMBERS[tag]!.has(operator.name)
}