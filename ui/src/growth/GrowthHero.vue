<script setup>
import { operatorDisplayName, skillDisplayName } from '@/i18n/gameNames'
import { i18n } from '@/i18n'
import { computed } from 'vue'
import { NButton, NIcon, NSwitch } from 'naive-ui'
import AddCircleOutline from '@vicons/ionicons5/es/AddCircleOutline'
import ListOutline from '@vicons/ionicons5/es/ListOutline'
import RefreshOutline from '@vicons/ionicons5/es/RefreshOutline'
import CloudDownloadOutline from '@vicons/ionicons5/es/CloudDownloadOutline'
import HelpText from '@/components/HelpText.vue'
import GrowthAvatar from './GrowthAvatar.vue'
import { planStatusLabel } from './growthFormatters'

const props = defineProps({
  totalGoals: { type: Number, default: 0 },
  planCount: { type: Number, default: 0 },
  training: { type: Object, default: null },
  nextUp: { type: Object, default: null },
  operators: { type: Array, default: () => [] },
  autoMastery: { type: Boolean, default: false },
  loading: Boolean,
  syncing: Boolean,
  syncHint: { type: String, default: '' },
  missingKinds: { type: Number, default: 0 },
  readyGoals: { type: Number, default: 0 },
  compact: Boolean
})
const emit = defineEmits(['update:autoMastery', 'add-target', 'open-plan', 'refresh', 'sync'])

const roster = computed(() => props.operators.filter((op) => op?.name).slice(0, 24))

const targetLevel = computed(() => props.training?.target || 3)
const currentLevel = computed(() => props.training?.rec?.current_level ?? 0)
const totalTime = computed(() => props.training?.totalTime ?? 0)
const trainingStatus = computed(() => props.training?.entry?.status || 'training')
const trainingStatusLabel = computed(() =>
  props.training ? planStatusLabel(trainingStatus.value) : i18n.global.t('growth.hero.standby')
)

function formatTime(seconds) {
  if (!seconds) return '—'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (hours > 0 && minutes > 0)
    return i18n.global.t('growth.format.hoursMinutes', { hours, minutes })
  if (hours > 0) return i18n.global.t('growth.format.hours', { hours })
  return i18n.global.t('growth.format.minutes', { minutes: minutes || 1 })
}

const stateLine = computed(() => {
  if (props.training) {
    const name =
      operatorDisplayName(props.training.op?.name) || i18n.global.t('growth.hero.operator')
    const skill =
      skillDisplayName(props.training.rec?.skill_name || props.training.entry?.skill_name) ||
      i18n.global.t('growth.hero.skill')
    const target = i18n.global.t(`growth.format.ordinal${targetLevel.value}`)
    const key =
      trainingStatus.value === 'waiting_collect'
        ? 'trainingReady'
        : trainingStatus.value === 'arranging'
          ? 'trainingArranging'
          : 'trainingActive'
    return i18n.global.t(`growth.format.${key}`, { name, skill, target })
  }
  if (!props.totalGoals) return i18n.global.t('growth.hero.noGrowthGoalsYetStartWithOne')
  if (props.nextUp)
    return i18n.global.t('growth.format.queueNext', {
      count: props.totalGoals,
      name: operatorDisplayName(props.nextUp.name),
      label: props.nextUp.label
    })
  return i18n.global.t('growth.format.queueWaiting', { count: props.totalGoals })
})

const syncLabel = computed(() => {
  if (props.syncing) return i18n.global.t('growth.hero.syncingSkland')
  if (props.syncHint) return props.syncHint
  return i18n.global.t('growth.hero.syncSkland')
})
</script>

<template>
  <section
    class="growth-hero gp-crop"
    :class="{ 'growth-hero--compact': compact }"
    aria-labelledby="growth-hero-title"
  >
    <div class="growth-hero__art" aria-hidden="true" />
    <div class="growth-hero__hatch" aria-hidden="true" />

    <div class="growth-hero__grid">
      <div class="growth-hero__lead">
        <span class="gp-kicker growth-hero__kicker">{{
          i18n.global.t('growth.hero.trainingDossier')
        }}</span>
        <h1 id="growth-hero-title" class="growth-hero__title gp-display">
          {{ i18n.global.t('growth.hero.growthPlanner')
          }}<span class="growth-hero__title-mark" aria-hidden="true">/</span>
        </h1>
        <p class="growth-hero__state">{{ stateLine }}</p>

        <div class="growth-hero__actions">
          <n-button class="gp-btn--paper" @click="emit('add-target')">
            <template #icon><n-icon :component="AddCircleOutline" /></template>
            {{ i18n.global.t('growth.hero.chooseGrowthGoals') }}
          </n-button>
          <n-button class="gp-btn--ghost-ink" @click="emit('open-plan')">
            <template #icon><n-icon :component="ListOutline" /></template>
            {{ i18n.global.t('growth.hero.growthPlan') }}
            <span v-if="totalGoals" class="growth-hero__count gp-mono">{{ totalGoals }}</span>
          </n-button>
        </div>

        <div class="growth-hero__meta">
          <div class="growth-hero__toggle">
            <n-switch
              class="gp-switch"
              size="small"
              :value="autoMastery"
              :loading="loading"
              :aria-label="i18n.global.t('growth.hero.automaticMastery')"
              @update:value="emit('update:autoMastery', $event)"
            />
            <span>{{ i18n.global.t('growth.hero.automaticMastery') }}</span>
            <HelpText :label="i18n.global.t('growth.hero.automaticMasteryScope')">
              {{ i18n.global.t('growth.hero.automaticallyTrainQueuedMasteryPlansAndCraft') }}
            </HelpText>
          </div>
          <span class="growth-hero__meta-sep" aria-hidden="true" />
          <button type="button" class="growth-hero__sync" :disabled="syncing" @click="emit('sync')">
            <n-icon :component="CloudDownloadOutline" />
            {{ syncLabel }}
          </button>
          <button
            type="button"
            class="growth-hero__sync"
            :disabled="loading"
            @click="emit('refresh')"
          >
            <n-icon :component="RefreshOutline" />
            {{ i18n.global.t('growth.hero.refresh') }}
          </button>
        </div>
      </div>

      <aside
        class="growth-hero__current"
        :aria-label="i18n.global.t('growth.hero.currentTraining')"
      >
        <div class="growth-hero__current-head">
          <span class="gp-kicker growth-hero__current-kicker">{{
            i18n.global.t('growth.format.currentTrainingHeading')
          }}</span>
          <span
            class="gp-stamp growth-hero__stamp"
            :class="training ? 'gp-stamp--warn' : 'gp-stamp--ink'"
            >{{ trainingStatusLabel }}</span
          >
        </div>

        <template v-if="training">
          <div class="growth-hero__current-body">
            <GrowthAvatar :name="training.op?.name" :rarity="training.op?.rarity" :size="76" />
            <div class="growth-hero__current-who">
              <h2>{{ operatorDisplayName(training.op?.name || training.entry?.name) }}</h2>
              <p class="growth-hero__current-skill">
                {{ skillDisplayName(training.rec?.skill_name || training.entry?.skill_name) }}
                <span class="gp-mono"
                  >{{ i18n.global.t('growth.hero.m')
                  }}{{
                    [
                      '',
                      i18n.global.t('growth.hero.1'),
                      i18n.global.t('growth.hero.2'),
                      i18n.global.t('growth.hero.3')
                    ][targetLevel]
                  }}</span
                >
              </p>
              <p class="growth-hero__current-sub">
                <template v-if="totalTime"
                  >{{ i18n.global.t('growth.hero.estimated') }}
                  {{ formatTime(totalTime) }} · </template
                >{{ i18n.global.t('growth.hero.remaining') }}
                {{ Math.max(0, targetLevel - currentLevel) }}
                {{ i18n.global.t('growth.hero.levels') }}
              </p>
            </div>
          </div>
          <div
            class="growth-hero__track"
            role="img"
            :aria-label="
              i18n.global.t('growth.format.masteryProgress', {
                current: currentLevel,
                target: targetLevel
              })
            "
          >
            <div
              v-for="level in 3"
              :key="level"
              class="growth-hero__seg"
              :class="{
                'is-done': level <= currentLevel,
                'is-next': level === currentLevel + 1 && level <= targetLevel
              }"
            >
              <i aria-hidden="true" />
              <span>{{
                [
                  i18n.global.t('growth.hero.m1'),
                  i18n.global.t('growth.hero.m2'),
                  i18n.global.t('growth.hero.m3')
                ][level - 1]
              }}</span>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="growth-hero__idle">
            <div class="growth-hero__idle-mark gp-display" aria-hidden="true">W</div>
            <div>
              <h2>{{ i18n.global.t('growth.hero.trainingRoomIdle') }}</h2>
              <p v-if="nextUp" class="growth-hero__current-sub">
                {{ i18n.global.t('growth.hero.next') }} {{ operatorDisplayName(nextUp.name) }} ·
                {{ nextUp.label }}
              </p>
              <p v-else class="growth-hero__current-sub">
                {{ i18n.global.t('growth.hero.useGrowthPlanOnTheRightTo') }}
              </p>
            </div>
          </div>
          <n-button
            class="gp-btn--ghost-ink growth-hero__idle-action"
            size="small"
            @click="emit('open-plan')"
          >
            {{ i18n.global.t('growth.hero.scheduleTraining') }}
          </n-button>
        </template>

        <dl class="growth-hero__readout">
          <div>
            <dt>{{ i18n.global.t('growth.hero.goals') }}</dt>
            <dd class="gp-num">{{ totalGoals }}</dd>
          </div>
          <div>
            <dt>{{ i18n.global.t('growth.hero.materialsReady') }}</dt>
            <dd class="gp-num">{{ readyGoals }}</dd>
          </div>
          <div>
            <dt>{{ i18n.global.t('growth.hero.shortages') }}</dt>
            <dd class="gp-num" :class="{ 'is-signal': missingKinds > 0 }">{{ missingKinds }}</dd>
          </div>
        </dl>
      </aside>
    </div>

    <div
      v-if="roster.length"
      class="growth-hero__roster"
      :aria-label="i18n.global.t('growth.hero.ownedOperators')"
    >
      <span class="growth-hero__roster-label gp-mono">OWNED {{ operators.length }}</span>
      <div class="growth-hero__roster-strip" aria-hidden="true">
        <GrowthAvatar
          v-for="op in roster"
          :key="op.char_id || op.name"
          :name="op.name"
          :rarity="op.rarity"
          :size="26"
          muted
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
.growth-hero--compact {
  padding: 22px 26px 24px;
}

.growth-hero--compact .growth-hero__title {
  margin-top: 10px;
  font-size: clamp(32px, 3.4vw, 40px);
}

.growth-hero--compact .growth-hero__state {
  margin-top: 8px;
  font-size: 13px;
}

.growth-hero--compact .growth-hero__actions {
  margin-top: 14px;
}

.growth-hero--compact .growth-hero__meta {
  padding-top: 14px;
  margin-top: 12px;
  border-top: 1px solid var(--gp-hair-on-ink);
}

.growth-hero--compact .growth-hero__grid {
  grid-template-columns: minmax(0, 1fr);
  gap: 0;
}

.growth-hero--compact .growth-hero__current,
.growth-hero--compact .growth-hero__roster {
  display: none;
}

.growth-hero {
  position: relative;
  overflow: hidden;
  isolation: isolate;
  border-radius: 26px;
  background: var(--gp-ink-panel);
  color: var(--gp-paper-on-ink);
  padding: 30px 32px 0;
}

.growth-hero__art {
  position: absolute;
  inset: -12% -6% -12% auto;
  width: 66%;
  background-image: url('/bg.webp');
  background-size: cover;
  background-position: 52% 30%;
  filter: grayscale(1) contrast(1.05) brightness(0.82);
  mix-blend-mode: luminosity;
  opacity: 0.42;
  z-index: -2;
  mask-image: linear-gradient(90deg, transparent 0%, #000 42%, #000 100%);
  pointer-events: none;
}

.growth-hero__hatch {
  position: absolute;
  top: -40px;
  right: -40px;
  width: 40%;
  height: 70%;
  background-image: repeating-linear-gradient(
    135deg,
    rgba(244, 240, 229, 0.06) 0 1px,
    transparent 1px 10px
  );
  mask-image: linear-gradient(215deg, #000 10%, transparent 68%);
  z-index: -1;
  pointer-events: none;
}

.growth-hero__grid {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 400px);
  gap: 36px;
  align-items: start;
}

.growth-hero__lead {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding-bottom: 26px;
  min-width: 0;
}

.growth-hero__kicker {
  color: var(--gp-muted-on-ink);
}

.growth-hero__title {
  margin: 18px 0 0;
  font-size: clamp(44px, 5.4vw, 72px);
  font-weight: 700;
  letter-spacing: -0.035em;
  line-height: 0.94;
}

.growth-hero__title-mark {
  display: inline-block;
  margin-left: 6px;
  color: var(--gp-accent-on-ink);
  font-weight: 400;
  transform: skewX(-12deg);
}

.growth-hero__state {
  margin: 16px 0 0;
  max-width: 30em;
  font-size: 16px;
  line-height: 1.6;
  color: var(--gp-muted-on-ink);
}

.growth-hero__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 22px;
}

.growth-hero__count {
  margin-left: 8px;
  padding: 0 6px;
  border-radius: 4px;
  background: rgba(244, 240, 229, 0.14);
  font-size: 11px;
  line-height: 18px;
}

.growth-hero__meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: auto;
  padding-top: 26px;
  color: var(--gp-muted-on-ink);
  font-size: 12px;
}

.growth-hero__toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--gp-paper-on-ink);
  font-weight: 600;
}

.growth-hero__meta-sep {
  width: 1px;
  height: 16px;
  background: var(--gp-hair-on-ink);
}

.growth-hero__sync {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 2px;
  border: 0;
  background: none;
  color: var(--gp-muted-on-ink);
  font: inherit;
  cursor: pointer;
  border-radius: 4px;
  transition: color 160ms var(--gp-ease);
}

.growth-hero__sync:hover:not(:disabled) {
  color: var(--gp-paper-on-ink);
}

.growth-hero__sync:disabled {
  opacity: 0.6;
  cursor: default;
}

.growth-hero__sync:focus-visible {
  outline: 2px solid var(--gp-accent-on-ink);
  outline-offset: 2px;
}

/* 当前训练板 */
.growth-hero__current {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 234px;
  padding: 18px 20px;
  border: 1px solid var(--gp-hair-on-ink);
  border-radius: 18px;
  background: linear-gradient(155deg, rgba(244, 240, 229, 0.075), rgba(244, 240, 229, 0.025));
  backdrop-filter: blur(2px);
}

.growth-hero__current-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.growth-hero__current-kicker {
  color: var(--gp-muted-on-ink);
}

.growth-hero__stamp {
  color: var(--gp-accent-on-ink);
  border-color: currentColor;
  transform: rotate(2deg);
}

.growth-hero__current-body {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}

.growth-hero__current-who {
  min-width: 0;
}

.growth-hero__current-who h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.15;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.growth-hero__current-skill {
  margin: 6px 0 0;
  color: var(--gp-paper-on-ink);
  font-size: 13.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.growth-hero__current-skill .gp-mono {
  color: var(--gp-accent-on-ink);
}

.growth-hero__current-sub {
  margin: 5px 0 0;
  color: var(--gp-muted-on-ink);
  font-size: 12px;
  line-height: 1.5;
}

.growth-hero__track {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.growth-hero__seg {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 11px;
  color: var(--gp-muted-on-ink);
}

.growth-hero__seg i {
  display: block;
  height: 5px;
  border-radius: 999px;
  background: rgba(244, 240, 229, 0.14);
}

.growth-hero__seg.is-done i {
  background: var(--gp-accent-on-ink);
}

.growth-hero__seg.is-next i {
  background: repeating-linear-gradient(
    90deg,
    var(--gp-accent-on-ink) 0 6px,
    rgba(244, 240, 229, 0.14) 6px 10px
  );
}

.growth-hero__seg.is-done span,
.growth-hero__seg.is-next span {
  color: var(--gp-paper-on-ink);
}

.growth-hero__idle {
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 96px;
}

.growth-hero__idle h2 {
  margin: 0;
  font-size: 21px;
  font-weight: 700;
}

.growth-hero__idle-mark {
  display: grid;
  place-items: center;
  width: 64px;
  height: 64px;
  flex: none;
  border: 1px dashed var(--gp-hair-on-ink);
  border-radius: 12px;
  color: var(--gp-muted-on-ink);
  font-size: 28px;
}

.growth-hero__idle-action {
  align-self: flex-start;
}

.growth-hero__readout {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin: auto 0 0;
  padding-top: 14px;
  border-top: 1px solid var(--gp-hair-on-ink);
}

.growth-hero__readout dt {
  color: var(--gp-muted-on-ink);
  font-size: 11px;
  letter-spacing: 0.04em;
}

.growth-hero__readout dd {
  margin: 2px 0 0;
  font-size: 26px;
  color: var(--gp-paper-on-ink);
}

.growth-hero__readout dd.is-signal {
  color: #f0a58d;
}

/* 干员剪影条 */
.growth-hero__roster {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 8px;
  padding: 14px 0 16px;
  border-top: 1px solid var(--gp-hair-on-ink);
  overflow: hidden;
}

.growth-hero__roster-label {
  flex: none;
  font-size: 10px;
  letter-spacing: 0.14em;
  color: var(--gp-muted-on-ink);
}

.growth-hero__roster-strip {
  display: flex;
  gap: 6px;
  min-width: 0;
  mask-image: linear-gradient(90deg, #000 0%, #000 86%, transparent 100%);
}

.growth-hero__roster-strip :deep(.growth-avatar) {
  border-radius: 6px;
  flex: none;
}

@media (max-width: 1080px) {
  .growth-hero {
    padding: 24px 24px 0;
  }
  .growth-hero__grid {
    grid-template-columns: 1fr;
    gap: 22px;
  }
  .growth-hero__current {
    min-height: 0;
  }
  .growth-hero__lead {
    padding-bottom: 0;
  }
  .growth-hero__meta {
    padding-top: 18px;
  }
}

@media (max-width: 620px) {
  .growth-hero {
    padding: 18px 16px 0;
    border-radius: 20px;
  }
  .growth-hero__title {
    font-size: 40px;
  }
  .growth-hero__roster {
    display: none;
  }
  .growth-hero__current {
    padding: 14px 15px;
    gap: 12px;
    border-radius: 14px;
  }
  .growth-hero__readout dd {
    font-size: 22px;
  }
  .growth-hero__lead {
    padding-bottom: 18px;
  }
  .growth-hero__state {
    font-size: 14.5px;
  }
  .growth-hero__art {
    width: 120%;
    opacity: 0.3;
  }
  .growth-hero__readout dd {
    font-size: 22px;
  }
  .growth-hero__roster-strip :deep(.growth-avatar:nth-child(n + 13)) {
    display: none;
  }
}
</style>
