import { i18n } from '@/i18n'

const displayKeys = {
  贸易站: 'tradingPost',
  制造站: 'factory',
  发电站: 'powerPlant',
  控制中枢: 'controlCenter',
  宿舍: 'dormitory',
  办公室: 'office',
  人力办公室: 'office',
  会客室: 'receptionRoom',
  加工站: 'workshop',
  训练室: 'trainingRoom',
  回收站: 'recycling',
  活动室: 'activityRoom',
  未知: 'unknown',
  赤金: 'pureGold',
  中级作战记录: 'intermediateRecord',
  作战记录: 'battleRecord',
  '源石碎片（固源岩）': 'originiumShardsRock',
  '源石碎片（装置）': 'originiumShardsDevice',
  龙门商法: 'lmdTrade',
  开采协力: 'orundumTrade',
  源石碎片: 'originiumShards',
  固源岩: 'orirock',
  装置: 'device',
  龙门币: 'lmd',
  '全部经验（计算）': 'computedExp',
  最低心情: 'minimumMorale',
  最高心情: 'maximumMorale',
  不限: 'unlimited',
  'max（最大值）': 'maxFunction',
  'min（最小值）': 'minFunction',
  'sum（求和）': 'sumFunction',
  'any（任一成立）': 'anyFunction',
  'all（全部成立）': 'allFunction',
  'abs（绝对值）': 'absFunction'
}

export function planDisplayName(name) {
  return displayKeys[name] ? i18n.global.t(`plans.${displayKeys[name]}`) : name
}

export function localizedPlanOptions(options) {
  return options.map((option) => ({ ...option, label: planDisplayName(option.label) }))
}

export function backupGroupDisplayName(group) {
  return group.id === 'default' && group.name === '默认分组'
    ? i18n.global.t('plans.defaultGroup')
    : group.name
}

export function planValidationMessage(issue, power) {
  return issue.code === 'POWER_DEFICIT' && power
    ? i18n.global.t('plans.powerDeficitDetail', {
        consumption: power.consumption,
        generation: power.generation
      })
    : issue.message
}
