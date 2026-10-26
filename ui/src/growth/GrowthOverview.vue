<script setup>
import { computed } from 'vue'
import { NButton, NIcon } from 'naive-ui'
import ArrowForwardOutline from '@vicons/ionicons5/es/ArrowForwardOutline'
import RefreshOutline from '@vicons/ionicons5/es/RefreshOutline'
import WorkshopStatus from '@/components/WorkshopStatus.vue'
import GrowthOperatorCard from './GrowthOperatorCard.vue'
import { materialIcon, planStatusLabel } from './growthFormatters'

const props = defineProps({
  goalCount: { type: Number, default: 0 },
  planCount: { type: Number, default: 0 },
  training: { type: Object, default: null },
  nextUp: { type: Object, default: null },
  queue: { type: Array, default: () => [] },
  queueError: { type: String, default: '' },
  materials: { type: Object, default: null },
  materialsLoading: Boolean,
  materialsError: { type: String, default: '' },
  materialStats: {
    type: Object,
    default: () => ({ ready: 0, total: 0, missing: 0, craftable: 0, percent: 0 })
  },
  recommended: { type: Array, default: () => [] },
  rosterStats: {
    type: Object,
    default: () => ({ owned: 0, elite2: 0, masteries: 0, modules: 0 })
  },
  workshopStatusRevision: { type: Number, default: 0 },
  workshopLoading: Boolean,
  hasChipShortage: Boolean,
  chipFarmingLoading: Boolean
})
const emit = defineEmits([
  'open-plan',
  'open-materials',
  'open-insights',
  'open-operators',
  'open-operator',
  'add-target',
  'generate-crafting',
  'configure-chips',
  'refresh-materials'
])

const RESOURCE_IDS = new Set(['4001', 'growth_exp', '4006', '32001'])
const queueRows = computed(() => props.queue.slice(0, 5))
const overflowCount = computed(() => Math.max(0, props.queue.length - queueRows.value.length))
const missingItems = computed(() =>
  (props.materials?.missing || [])
    .filter((row) => !RESOURCE_IDS.has(row.id))
    .sort((left, right) => (right.rarity || 0) - (left.rarity || 0) || right.count - left.count)
    .slice(0, 4)
)
const resourceMissing = computed(() =>
  (props.materials?.missing || []).filter((row) => RESOURCE_IDS.has(row.id))
)
const percent = computed(() => Math.round(props.materialStats.percent || 0))
const elitePercent = computed(() =>
  props.rosterStats.owned
    ? Math.round((props.rosterStats.elite2 / props.rosterStats.owned) * 100)
    : 0
)

function statusTone(status) {
  if (status === 'training' || status === 'arranging' || status === 'waiting_collect') return 'warn'
  if (status === 'failed') return 'signal'
  if (status === 'waiting') return 'info'
  return 'idle'
}

function statusText(status) {
  return planStatusLabel(status)
}

function formatCount(value) {
  const number = Number(value) || 0
  if (number >= 10000) return (number / 10000).toFixed(1).replace(/\.0$/, '') + '万'
  return number.toLocaleString('zh-CN')
}
</script>

<template>
  <div class="gp-overview">
    <div class="gp-overview__top">
      <section class="gp-sheet gp-overview__queue" aria-labelledby="growth-queue-title">
        <header class="gp-section-head">
          <div>
            <span class="gp-kicker">Training queue</span>
            <h2 id="growth-queue-title" class="gp-section-head__title">训练队列</h2>
          </div>
          <div class="gp-section-head__meta">
            <span class="gp-mono">{{ goalCount }} 项</span>
            <button type="button" class="gp-link" @click="emit('open-plan')">
              调整顺序
              <n-icon :component="ArrowForwardOutline" :size="14" />
            </button>
          </div>
        </header>

        <p v-if="queueError" class="gp-muted" role="status">{{ queueError }}</p>
        <ol v-if="queueRows.length" class="gp-queue">
          <li v-for="(item, index) in queueRows" :key="item.key" class="gp-queue__row">
            <span class="gp-queue__index gp-mono">{{ String(index + 1).padStart(2, '0') }}</span>
            <span class="gp-queue__avatar">
              <img
                :src="'/avatar/' + encodeURIComponent(item.name) + '.webp'"
                :alt="item.name"
                loading="lazy"
                @error="(event) => (event.target.src = '/avatar/阿米娅.webp')"
              />
            </span>
            <div class="gp-queue__text">
              <b>{{ item.name }}</b>
              <span class="gp-queue__label">{{ item.label }}</span>
            </div>
            <span
              v-if="statusTone(item.status) === 'warn' || statusTone(item.status) === 'signal'"
              class="gp-stamp gp-overview__stamp"
              :class="{
                'gp-stamp--warn': statusTone(item.status) === 'warn',
                'gp-stamp--signal': statusTone(item.status) === 'signal'
              }"
            >
              {{ statusText(item.status) }}
            </span>
            <span
              v-else
              class="gp-overview__status gp-mono"
              :class="'is-' + statusTone(item.status)"
            >
              {{ statusText(item.status) }}
            </span>
          </li>
        </ol>

        <div v-else class="gp-empty gp-overview__empty">
          <p class="gp-empty__title">队列还是空的</p>
          <p class="gp-muted">
            选择干员并设置养成目标；开启全自动专精后自动训练技能，精英化与模组升级仍需手动完成。
          </p>
          <div class="gp-empty__actions">
            <n-button size="small" type="primary" @click="emit('add-target')"
              >选择养成目标</n-button
            >
          </div>
        </div>

        <footer v-if="queueRows.length" class="gp-overview__queue-foot">
          <span v-if="overflowCount" class="gp-muted">还有 {{ overflowCount }} 项在计划中</span>
          <span v-else class="gp-muted">进行中的训练固定在队列最前。</span>
          <button type="button" class="gp-link" @click="emit('open-plan')">打开完整计划</button>
        </footer>
      </section>

      <section class="gp-panel gp-overview__materials" aria-labelledby="growth-materials-title">
        <header class="gp-section-head gp-overview__materials-head">
          <h2 id="growth-materials-title" class="gp-section-head__title">材料准备</h2>
          <button type="button" class="gp-link" @click="emit('open-materials')">查看明细</button>
        </header>

        <div v-if="materialsLoading && !materials" class="gp-overview__loading">
          <div class="gp-skeleton" style="height: 64px" />
          <div class="gp-skeleton" style="height: 26px" />
        </div>

        <div v-else-if="materialsError" class="gp-overview__material-error">
          <p>{{ materialsError }}</p>
          <button type="button" class="gp-link" @click="emit('refresh-materials')">
            <n-icon :component="RefreshOutline" :size="13" />
            重新计算
          </button>
        </div>

        <div v-else-if="!goalCount" class="gp-overview__material-empty">
          <p class="gp-muted">添加目标后，这里会按库存算出差额与可合成项。</p>
        </div>

        <template v-else>
          <div class="gp-overview__readiness">
            <div class="gp-overview__readiness-value gp-num">{{ percent }}<small>%</small></div>
            <div class="gp-overview__readiness-meta">
              <span>材料种类备齐</span>
              <span class="gp-mono">{{ materialStats.ready }} / {{ materialStats.total }}</span>
            </div>
          </div>
          <div
            class="gp-meter gp-overview__meter"
            :class="{ 'gp-meter--signal': percent < 60 && materialStats.missing }"
          >
            <span :style="{ width: percent + '%' }" />
          </div>
          <dl class="gp-overview__material-stats">
            <div>
              <dt>材料缺口</dt>
              <dd class="gp-mono" :class="{ 'is-signal': missingItems.length }">
                {{ materialStats.missing }} 种
              </dd>
            </div>
            <div>
              <dt>可合成</dt>
              <dd class="gp-mono">{{ materialStats.craftable }} 种</dd>
            </div>
            <div>
              <dt>已备齐</dt>
              <dd class="gp-mono">{{ materialStats.ready }} 种</dd>
            </div>
          </dl>
          <div v-if="missingItems.length" class="gp-overview__missing">
            <div
              v-for="material in missingItems"
              :key="material.id"
              class="gp-overview__missing-item"
              :title="material.name + ' 缺 ' + material.count"
            >
              <img :src="materialIcon(material)" :alt="material.name" loading="lazy" />
              <span class="gp-mono">×{{ formatCount(material.count) }}</span>
            </div>
          </div>
          <div v-if="resourceMissing.length" class="gp-overview__resources">
            <span class="gp-overview__resources-label">资源缺口</span>
            <span
              v-for="resource in resourceMissing"
              :key="resource.id"
              class="gp-overview__resource"
            >
              <img :src="materialIcon(resource)" :alt="resource.name" loading="lazy" />
              {{ resource.name }} ×{{ formatCount(resource.count) }}
            </span>
          </div>
          <div class="gp-overview__material-actions">
            <n-button
              size="small"
              secondary
              type="primary"
              :loading="workshopLoading"
              :disabled="!goalCount"
              @click="emit('generate-crafting')"
            >
              生成合成任务
            </n-button>
            <button
              v-if="hasChipShortage"
              type="button"
              class="gp-link"
              :disabled="chipFarmingLoading"
              @click="emit('configure-chips')"
            >
              芯片刷取
            </button>
          </div>
          <div class="gp-overview__workshop">
            <WorkshopStatus :revision="workshopStatusRevision" />
          </div>
        </template>
      </section>
    </div>

    <div class="gp-overview__bottom">
      <section class="gp-panel gp-overview__roster" aria-labelledby="growth-roster-title">
        <header class="gp-section-head gp-overview__roster-head">
          <h2 id="growth-roster-title" class="gp-section-head__title">BOX 概览</h2>
          <button type="button" class="gp-link" @click="emit('open-insights')">统计</button>
        </header>
        <dl class="gp-overview__roster-grid">
          <div>
            <dt>已拥有</dt>
            <dd class="gp-num">{{ rosterStats.owned }}</dd>
          </div>
          <div>
            <dt>精二</dt>
            <dd class="gp-num">{{ rosterStats.elite2 }}</dd>
          </div>
          <div>
            <dt>专三技能</dt>
            <dd class="gp-num">{{ rosterStats.masteries }}</dd>
          </div>
          <div>
            <dt>已开模组</dt>
            <dd class="gp-num">{{ rosterStats.modules }}</dd>
          </div>
        </dl>
        <div class="gp-overview__roster-meter">
          <div class="gp-overview__roster-meter-head">
            <span>精二率</span>
            <span class="gp-mono">{{ elitePercent }}%</span>
          </div>
          <div class="gp-meter">
            <span :style="{ width: elitePercent + '%' }" />
          </div>
        </div>
        <p class="gp-overview__roster-note">按本地已同步练度统计，未同步的干员不计入。</p>
      </section>

      <section class="gp-panel gp-overview__pick" aria-labelledby="growth-pick-title">
        <header class="gp-section-head">
          <div class="gp-overview__pick-head">
            <span class="gp-kicker">Suggested next</span>
            <h2 id="growth-pick-title" class="gp-section-head__title">值得练</h2>
            <p class="gp-overview__pick-sub">按一图流公开样本比例排序，点开档案核对材料与前置。</p>
          </div>
          <button type="button" class="gp-link" @click="emit('open-operators')">
            全部干员
            <n-icon :component="ArrowForwardOutline" :size="14" />
          </button>
        </header>

        <div v-if="recommended.length" class="gp-overview__cards">
          <GrowthOperatorCard
            v-for="(card, index) in recommended"
            :key="card.operator.char_id"
            class="gp-rise"
            :style="{ '--gp-delay': index }"
            layout="compact"
            :operator="card.operator"
            :survey="card.survey"
            :planned="card.planned"
            :planned-count="card.plannedCount"
            :rank="index + 1"
            @open="(op) => emit('open-operator', op)"
          />
        </div>
        <div v-else class="gp-empty gp-overview__pick-empty">
          <p class="gp-empty__title">暂时没有新的推荐</p>
          <p class="gp-muted">已拥有的干员要么已在计划里，要么暂无未完成的技能与模组。</p>
          <div class="gp-empty__actions">
            <n-button size="small" @click="emit('open-operators')">查看全部干员</n-button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.gp-overview {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gp-overview__top {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(320px, 1fr);
  gap: 16px;
  align-items: stretch;
}

.gp-overview__bottom {
  display: grid;
  grid-template-columns: minmax(240px, 0.85fr) minmax(0, 2.15fr);
  gap: 16px;
  align-items: stretch;
}

.gp-overview__queue {
  display: flex;
  flex-direction: column;
  min-height: 420px;
}

.gp-queue {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.gp-queue__row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 62px;
  padding: 8px 6px;
  border-radius: 10px;
  transition: background 160ms var(--gp-ease);
}

.gp-queue__row:hover {
  background: var(--gp-surface-2);
}

.gp-queue__index {
  flex: none;
  width: 22px;
  color: var(--gp-faint);
  font-size: 10.5px;
}

.gp-queue__avatar {
  display: block;
  width: 38px;
  height: 38px;
  flex: none;
  overflow: hidden;
  border-radius: 9px;
  background: var(--gp-surface-3);
  box-shadow: inset 0 0 0 1px var(--gp-hair-soft);
}

.gp-queue__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 22%;
}

.gp-queue__text {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.gp-queue__text b {
  overflow: hidden;
  font-size: 13.5px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gp-queue__label {
  overflow: hidden;
  color: var(--gp-muted);
  font-size: 11.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gp-overview__stamp {
  flex: none;
  font-size: 9.5px;
}

.gp-overview__status {
  flex: none;
  color: var(--gp-faint);
  font-size: 10.5px;
}

.gp-overview__status.is-signal {
  color: var(--gp-signal);
}

.gp-overview__status.is-warn {
  color: var(--gp-warn);
}

.gp-overview__empty {
  flex: 1;
  justify-content: center;
}

.gp-overview__queue-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: auto;
  padding-top: 14px;
  border-top: 1px solid var(--gp-hair-soft);
  font-size: 11.5px;
}

.gp-overview__materials {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.gp-overview__materials-head {
  margin-bottom: 10px;
}

.gp-overview__loading {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.gp-overview__material-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--gp-signal);
  font-size: 12px;
}

.gp-overview__material-error p {
  margin: 0;
}

.gp-overview__material-empty {
  padding: 12px 0 4px;
  font-size: 12px;
}

.gp-overview__readiness {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.gp-overview__readiness-value {
  font-size: 54px;
  line-height: 0.9;
  color: var(--gp-ink);
}

.gp-overview__readiness-value small {
  margin-left: 2px;
  color: var(--gp-muted);
  font-size: 20px;
  font-weight: 600;
}

.gp-overview__readiness-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  color: var(--gp-muted);
  font-size: 11px;
}

.gp-overview__meter {
  margin: 12px 0 14px;
  height: 7px;
}

.gp-overview__material-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: 0;
}

.gp-overview__material-stats dt {
  color: var(--gp-faint);
  font-size: 10.5px;
}

.gp-overview__material-stats dd {
  margin: 2px 0 0;
  font-size: 14px;
  font-weight: 700;
}

.gp-overview__material-stats dd.is-signal {
  color: var(--gp-signal);
}

.gp-overview__missing {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 9px 10px;
  border-radius: 10px;
  background: var(--gp-surface-2);
}

.gp-overview__missing-item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.gp-overview__missing-item img {
  width: 28px;
  height: 28px;
  object-fit: contain;
}

.gp-overview__missing-item span {
  color: var(--gp-muted);
  font-size: 10px;
}

.gp-overview__resources {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
  padding: 7px 10px;
  border-radius: 10px;
  background: var(--gp-signal-block);
}

.gp-overview__resources-label {
  color: var(--gp-signal);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.gp-overview__resource {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--gp-signal);
  font-size: 10.5px;
}

.gp-overview__resource img {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.gp-overview__material-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: auto;
  padding-top: 14px;
}

.gp-overview__material-actions .gp-link {
  font-size: 11.5px;
}

.gp-overview__workshop {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--gp-hair-soft);
}

.gp-overview__workshop :deep(.n-space) {
  font-size: 11px;
  margin-top: 0 !important;
}

.gp-overview__workshop :deep(.n-text) {
  font-size: 11px;
}

.gp-overview__roster {
  display: flex;
  flex-direction: column;
}

.gp-overview__roster-head {
  margin-bottom: 12px;
}

.gp-overview__roster-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px 10px;
  margin: 0;
}

.gp-overview__roster-grid dt {
  color: var(--gp-faint);
  font-size: 10.5px;
}

.gp-overview__roster-grid dd {
  margin: 4px 0 0;
  font-size: 30px;
  color: var(--gp-ink);
}

.gp-overview__roster-meter {
  margin-top: 18px;
}

.gp-overview__roster-meter-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  color: var(--gp-muted);
  font-size: 10.5px;
}

.gp-overview__roster-meter-head .gp-mono {
  color: var(--gp-ink-2);
  font-weight: 700;
}

.gp-overview__roster-meter .gp-meter {
  height: 6px;
}

.gp-overview__roster-note {
  margin: auto 0 0;
  padding-top: 12px;
  color: var(--gp-faint);
  font-size: 10.5px;
  line-height: 1.5;
}

.gp-overview__pick {
  display: flex;
  flex-direction: column;
}

.gp-overview__pick-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gp-overview__pick-sub {
  margin: 0;
  color: var(--gp-muted);
  font-size: 11.5px;
}

.gp-overview__cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}

.gp-overview__pick-empty {
  margin-top: 4px;
}

@media (max-width: 1080px) {
  .gp-overview__top,
  .gp-overview__bottom {
    grid-template-columns: 1fr;
  }
  .gp-overview__queue {
    min-height: 0;
  }
}

@media (max-width: 720px) {
  .gp-overview__cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .gp-overview__readiness-value {
    font-size: 44px;
  }
  .gp-overview__roster-grid dd {
    font-size: 24px;
  }
}
</style>
