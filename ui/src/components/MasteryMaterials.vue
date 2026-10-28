<template>
  <div v-if="summary" class="mm">
    <header v-if="showHeader" class="mm__head">
      <span class="mm__title">{{
        title || i18n.global.t('growth.materialDetails.materialCostsInventory')
      }}</span>
      <span class="mm__status" :class="'is-' + statusType">{{ statusText }}</span>
    </header>

    <p v-if="!summary.materials.length" class="mm__empty">
      {{ i18n.global.t('growth.materialDetails.noMoreMaterialsNeedPreparation') }}
    </p>

    <template v-else>
      <div class="mm__grid">
        <div
          v-for="material in summary.materials"
          :key="material.id"
          class="mm__item"
          :class="quantityClass(material)"
          :title="
            itemDisplayName(material.id, material.name) +
            i18n.global.t('growth.materialDetails.owned') +
            material.owned.toLocaleString(i18n.global.locale.value) +
            i18n.global.t('growth.materialDetails.required') +
            material.required.toLocaleString(i18n.global.locale.value)
          "
        >
          <img
            :src="iconFor(material)"
            :alt="itemDisplayName(material.id, material.name)"
            loading="lazy"
          />
          <div class="mm__item-body">
            <span class="mm__name">{{ itemDisplayName(material.id, material.name) }}</span>
            <span class="mm__numbers gp-mono">
              {{ formatAmount(material.owned) }}<em>/{{ formatAmount(material.required) }}</em>
            </span>
            <span class="mm__bar" aria-hidden="true">
              <i :style="{ width: percentFor(material) + '%' }" />
            </span>
          </div>
        </div>
      </div>

      <div v-if="showShortage && missingSkills.length" class="mm__flagged">
        <span class="mm__flagged-label">{{
          i18n.global.t('growth.materialDetails.skillsMissingMaterials')
        }}</span>
        <span v-for="skill in missingSkills" :key="skill.key" class="mm__tag mm__tag--signal">
          {{ operatorDisplayName(skill.name) }} · {{ skillDisplayName(skill.skill_name) }}
        </span>
      </div>

      <div v-if="summary.manual_chips" class="mm__hint">
        {{
          i18n.global.t('growth.materialDetails.dualchipsAndChipCatalystsRequireManualPreparation')
        }}
      </div>
      <div
        v-if="summary.crafting_gold"
        class="mm__hint"
        :title="
          i18n.global.t('growth.materialDetails.craftingFee') +
          summary.crafting_gold.toLocaleString(i18n.global.locale.value) +
          i18n.global.t('growth.materialDetails.lmdIncludedInTheTotalLmdRequirement')
        "
      >
        {{ i18n.global.t('growth.materialDetails.includesACraftingFeeOf') }}
        {{ formatAmount(summary.crafting_gold) }}
        {{ i18n.global.t('growth.materialDetails.lmdAlreadyIncludedInTheTotalLmd') }}
      </div>

      <details v-if="expandCrafting && summary.crafting.length" class="mm__crafting">
        <summary class="mm__summary">
          {{ i18n.global.t('growth.materialDetails.craftingIngredientsByTier') }}
          <span class="gp-mono"
            >{{ summary.crafting.length }} {{ i18n.global.t('growth.materialDetails.types') }}</span
          >
        </summary>
        <section v-for="group in craftingGroups" :key="group.label" class="mm__group">
          <span class="mm__group-label">{{ group.label }}</span>
          <div class="mm__grid mm__grid--compact">
            <div
              v-for="material in group.materials"
              :key="material.id"
              class="mm__item"
              :class="quantityClass(material)"
              :title="
                itemDisplayName(material.id, material.name) +
                i18n.global.t('growth.materialDetails.owned') +
                material.owned.toLocaleString(i18n.global.locale.value) +
                i18n.global.t('growth.materialDetails.required') +
                material.required.toLocaleString(i18n.global.locale.value)
              "
            >
              <img
                :src="iconFor(material)"
                :alt="itemDisplayName(material.id, material.name)"
                loading="lazy"
              />
              <div class="mm__item-body">
                <span class="mm__name">{{ itemDisplayName(material.id, material.name) }}</span>
                <span class="mm__numbers gp-mono">
                  {{ formatAmount(material.owned) }}<em>/{{ formatAmount(material.required) }}</em>
                </span>
              </div>
            </div>
          </div>
        </section>
      </details>

      <div v-if="showShortage && (blueMissing.length || otherMissing.length)" class="mm__flagged">
        <span class="mm__flagged-label">{{
          i18n.global.t('growth.materialDetails.stillMissing')
        }}</span>
        <span
          v-for="material in blueMissing.concat(otherMissing)"
          :key="material.id"
          class="mm__tag mm__tag--signal"
          :title="
            itemDisplayName(material.id, material.name) +
            ' ×' +
            material.count.toLocaleString(i18n.global.locale.value)
          "
        >
          {{ itemDisplayName(material.id, material.name) }} ×{{ formatAmount(material.count) }}
        </span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { materialDisplayName as itemDisplayName } from '@/growth/growthFormatters'
import { operatorDisplayName, skillDisplayName } from '@/i18n/gameNames'
import { i18n } from '@/i18n'
import { computed } from 'vue'
import {
  formatMaterialAmount as formatAmount,
  materialStatus,
  materialStatusType
} from '@/utils/masteryMaterials'

const props = defineProps({
  summary: Object,
  showHeader: { type: Boolean, default: true },
  expandCrafting: Boolean,
  showShortage: { type: Boolean, default: true },
  missingSkills: { type: Array, default: () => [] },
  title: { type: String, default: '' }
})
const statusText = computed(() => materialStatus(props.summary))
const statusType = computed(() => materialStatusType(props.summary) || 'ok')
const craftingGroups = computed(() => {
  const groups = new Map()
  for (const material of props.summary?.crafting || []) {
    const label = material.id.startsWith('330')
      ? i18n.global.t('growth.materialDetails.skillSummaries')
      : 'T' + material.rarity + i18n.global.t('growth.materialDetails.materials')
    if (!groups.has(label)) groups.set(label, { label, rarity: material.rarity, materials: [] })
    groups.get(label).materials.push(material)
  }
  return [...groups.values()].sort((a, b) => b.rarity - a.rarity)
})
const blueMissing = computed(() => props.summary?.missing.filter((item) => item.blue) || [])
const otherMissing = computed(() => props.summary?.missing.filter((item) => !item.blue) || [])

function iconFor(material) {
  const name = material.id === 'growth_exp' ? 'EXP' : material.name
  return '/depot/' + encodeURIComponent(name) + '.webp'
}
function percentFor(material) {
  if (!material.required) return 100
  return Math.min(100, Math.round((material.owned / material.required) * 100))
}
function quantityClass(material) {
  if (material.owned >= material.required) return 'is-ready'
  return material.craftable ? 'is-craftable' : 'is-missing'
}
</script>

<style scoped>
.mm {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-variant-numeric: tabular-nums;
}

.mm__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.mm__title {
  color: var(--gp-ink);
  font-size: 12.5px;
  font-weight: 700;
}

.mm__status {
  padding: 1px 7px;
  border-radius: 4px;
  background: var(--gp-surface-2);
  color: var(--gp-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.mm__status.is-success {
  background: var(--gp-accent-block);
  color: var(--gp-accent-ink);
}

.mm__status.is-warning {
  background: var(--gp-warn-block);
  color: var(--gp-warn);
}

.mm__status.is-error {
  background: var(--gp-signal-block);
  color: var(--gp-signal);
}

.mm__empty {
  margin: 0;
  color: var(--gp-muted);
  font-size: 11.5px;
}

.mm__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 6px 10px;
}

.mm__grid--compact {
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  margin-top: 4px;
}

.mm__item {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  padding: 5px 6px;
  border-radius: 8px;
  background: var(--gp-surface-2);
}

.mm__item img {
  width: 28px;
  height: 28px;
  flex: none;
  object-fit: contain;
}

.mm__grid--compact .mm__item img {
  width: 24px;
  height: 24px;
}

.mm__item-body {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.mm__name {
  overflow: hidden;
  color: var(--gp-ink-2);
  font-size: 10.5px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mm__numbers {
  overflow: hidden;
  color: var(--gp-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mm__numbers em {
  color: var(--gp-faint);
  font-style: normal;
}

.mm__item.is-missing .mm__numbers {
  color: var(--gp-signal);
}

.mm__item.is-craftable .mm__numbers {
  color: var(--gp-warn);
}

.mm__bar {
  display: block;
  height: 2px;
  border-radius: 999px;
  background: var(--gp-surface-3);
  overflow: hidden;
}

.mm__bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--gp-accent);
}

.mm__item.is-missing .mm__bar i {
  background: var(--gp-signal);
}

.mm__item.is-craftable .mm__bar i {
  background: var(--gp-warn);
}

.mm__hint {
  color: var(--gp-faint);
  font-size: 10.5px;
  line-height: 1.5;
}

.mm__crafting {
  border-top: 1px solid var(--gp-hair-soft);
  padding-top: 8px;
}

.mm__summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--gp-muted);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  list-style: none;
}

.mm__summary::-webkit-details-marker {
  display: none;
}

.mm__summary::before {
  content: '+';
  margin-right: 6px;
  color: var(--gp-faint);
  font-family: var(--gp-mono);
}

.mm__crafting[open] .mm__summary::before {
  content: '−';
}

.mm__group {
  margin-top: 8px;
}

.mm__group-label {
  display: block;
  margin-bottom: 4px;
  color: var(--gp-faint);
  font-size: 10px;
  letter-spacing: 0.04em;
}

.mm__flagged {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.mm__flagged-label {
  color: var(--gp-faint);
  font-size: 10.5px;
}

.mm__tag {
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 10.5px;
  font-weight: 600;
}

.mm__tag--signal {
  background: var(--gp-signal-block);
  color: var(--gp-signal);
}
</style>
