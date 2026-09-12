<template>
  <div class="home-container">
    <div class="page-header">
      <h1 class="page-title">自动专精</h1>
      <n-space align="center" :size="8">
        <n-button size="small" @click="openPlanModal">
          <template #icon><n-icon :component="ListIcon" /></template>
          专精计划
          <n-badge
            v-if="planEntries.length"
            :value="planEntries.length"
            :max="99"
            style="margin-left: 4px"
          />
        </n-button>
        <n-button size="small" @click="openSettings">
          <template #icon><n-icon :component="SettingsIcon" /></template>
          通用专精路线预览
        </n-button>
        <n-button size="small" @click="openWorkshopSettings">
          <template #icon><n-icon :component="SettingsIcon" /></template>
          加工站干员设置
        </n-button>
        <n-button size="small" type="warning" @click="autoWorkshop" :loading="workshopLoading">
          <template #icon><n-icon :component="HammerIcon" /></template>
          自动合成配置
        </n-button>
        <n-button type="primary" size="small" @click="fetchCultivate" :loading="store.loading">
          <template #icon><n-icon :component="RefreshIcon" /></template>
          刷新
        </n-button>
        <n-text v-if="store.cultivateMsg" depth="3" style="font-size: 11px"
          >更新: {{ store.cultivateMsg }}</n-text
        >
      </n-space>
    </div>

    <div
      class="mastery-global-switch"
      style="display: flex; align-items: center; gap: 8px; margin-top: 8px"
    >
      <n-switch v-model:value="configStore.enable_mastery" size="small" />
      <n-text strong>全自动专精</n-text>
      <n-text depth="3" style="font-size: 12px"
        >关闭后暂停专精自动化（训练室动作/通知/守卫），保留仓库材料扫描</n-text
      >
    </div>

    <n-space style="margin-top: 8px" :size="8" align="center" wrap>
      <n-input
        v-model:value="searchQuery"
        placeholder="搜索干员名称"
        clearable
        style="width: 200px"
        size="small"
      />
      <n-select
        v-model:value="filterRarity"
        :options="rarityOptions"
        multiple
        placeholder="稀有度"
        style="min-width: 140px"
        size="small"
        clearable
      />
      <n-select
        v-model:value="filterProfession"
        :options="professionOptions"
        multiple
        placeholder="职业"
        style="min-width: 140px"
        size="small"
        clearable
      />
    </n-space>
    <n-space style="margin-top: 4px" :size="8" align="center" wrap>
      <n-select
        v-model:value="idleFilter"
        :options="idleFilterOptions"
        size="small"
        style="min-width: 100px"
      />
      <n-checkbox v-model:checked="showOnlyPlanned">只看计划</n-checkbox>
      <n-checkbox v-model:checked="filterAchievable">材料充足或可合成</n-checkbox>
    </n-space>

    <n-divider />

    <n-text
      v-if="store.cultivateMsg"
      :type="store.cultivateOk ? 'success' : 'error'"
      depth="2"
      style="font-size: 12px"
    >
      森空岛同步：{{ store.cultivateMsg }}
    </n-text>

    <n-spin v-if="store.loading" size="large" description="正在分析干员数据..." />
    <n-alert v-else-if="store.error" type="warning" :closable="false">
      <template #header><n-text strong>暂无干员数据</n-text></template>
      <div>{{ store.error }}</div>
      <n-button
        type="primary"
        size="small"
        style="margin-top: 12px"
        @click="fetchCultivate"
        :loading="store.loading"
        >从森空岛拉取数据</n-button
      >
    </n-alert>
    <n-empty v-else-if="displayList.length === 0" :description="emptyText" />

    <div v-else class="mastery-list">
      <n-card v-if="planEntries.length" size="small" style="margin-bottom: 12px">
        <n-spin :show="materialsLoading">
          <n-alert v-if="materialsError" type="warning">{{ materialsError }}</n-alert>
          <MasteryMaterials
            v-else
            :summary="planMaterials"
            :missing-skills="missingPlanSkills"
            expand-crafting
            title="计划剩余总材料消耗"
          />
        </n-spin>
      </n-card>

      <n-collapse accordion>
        <n-collapse-item v-for="op in displayList" :key="op.char_id">
          <template #header>
            <n-space align="center" :size="8">
              <n-avatar
                :src="'/avatar/' + op.name + '.webp'"
                :size="28"
                round
                fallback-src="/avatar/阿米娅.webp"
              />
              <n-text strong>{{ op.name }}</n-text>
              <n-text depth="3">({{ op.rarity }}★)</n-text>
            </n-space>
          </template>
          <template #header-extra>
            <n-space :size="4">
              <n-tag :bordered="false" size="small">{{ professionName(op.profession) }}</n-tag>
              <n-tag :bordered="false" size="small">E{{ op.elite }} Lv{{ op.level }}</n-tag>
              <n-tag v-if="hasPlannedSkill(op)" type="success" :bordered="false" size="small"
                >计划中</n-tag
              >
              <n-button
                size="tiny"
                quaternary
                type="warning"
                @click.stop="addAllToPlan(op)"
                :disabled="!!op.mastery_error"
                v-if="!allPlanned(op)"
                >全加计划</n-button
              >
            </n-space>
          </template>

          <div v-for="rec in visibleRecs(op)" :key="rec.skill_index" class="rec-item">
            <n-card size="small">
              <template #header>
                <n-space align="center" justify="space-between" style="width: 100%">
                  <n-space align="center" :size="8">
                    <n-text strong>{{ rec.skill_name }}</n-text>
                    <n-text depth="3" style="font-size: 12px"
                      >{{ masteryLevelLabel(op.main_skill_level, rec.current_level) }} →
                      专三</n-text
                    >
                  </n-space>
                  <n-space :size="4">
                    <n-tag :type="materialStatusType(rec.material_summary)" size="small">
                      {{ materialStatus(rec.material_summary) }}
                    </n-tag>
                    <n-button
                      size="tiny"
                      :type="isSkillPlanned(op.char_id, rec.skill_index) ? 'success' : 'default'"
                      @click.stop="toggleSkillPlan(op, rec)"
                      :disabled="!!op.mastery_error && !isSkillPlanned(op.char_id, rec.skill_index)"
                    >
                      {{ isSkillPlanned(op.char_id, rec.skill_index) ? '已计划' : '加计划' }}
                    </n-button>
                    <n-button
                      type="primary"
                      size="tiny"
                      :disabled="!!op.mastery_error"
                      @click.stop="confirmSkill(op, rec)"
                      >一键专精</n-button
                    >
                    <n-button
                      v-if="planStatus[planKey(op.char_id, rec.skill_index)]?.id"
                      size="tiny"
                      @click.stop="openSupports(op, rec)"
                      >协助方案</n-button
                    >
                  </n-space>
                </n-space>
              </template>
              <n-space vertical :size="4">
                <n-text v-if="op.mastery_error" type="warning">{{ op.mastery_error }}</n-text>
                <n-text depth="2"
                  >总训练时间: {{ formatTime(rec.total_time) }} |
                  {{ rec.remaining_levels }}级专精</n-text
                >
                <MasteryMaterials :summary="rec.material_summary" />
              </n-space>
            </n-card>
          </div>
        </n-collapse-item>
      </n-collapse>
    </div>

    <!-- 确认专精 -->
    <n-modal
      v-model:show="showConfirm"
      preset="card"
      title="确认专精任务"
      style="width: min(560px, 95vw)"
      :mask-closable="false"
    >
      <n-space vertical>
        <n-text
          >干员: <n-text strong>{{ cd.op?.name }}</n-text> |
          <n-tag size="small">{{ professionName(cd.op?.profession) }}</n-tag></n-text
        >
        <n-text
          >技能: <n-text strong>{{ cd.rec?.skill_name }}</n-text> → 专精3级 |
          {{ formatTime(cd.rec?.total_time || 0) }}</n-text
        >
        <n-text v-if="workshopTrainingWarning(cd.op?.name)" type="warning">{{
          workshopTrainingWarning(cd.op?.name)
        }}</n-text>
        <n-divider />
        <n-text depth="2"
          >将根据已拥有干员和排班表自动生成协助方案，添加后可通过「协助方案」查看或修改。</n-text
        >
        <n-text v-if="trainingWarning(cd.op?.name)" type="warning">{{
          trainingWarning(cd.op?.name)
        }}</n-text>
        <n-divider />
        <MasteryMaterials :summary="cd.rec?.material_summary" />
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showConfirm = false">取消</n-button>
          <n-button type="primary" @click="doAddTask">确认添加任务</n-button>
        </n-space>
      </template>
    </n-modal>

    <MasterySupports
      v-model:show="showSupports"
      :plan="supportSelection.plan"
      :name="supportSelection.name"
      @saved="refreshPlanFromServer"
    />

    <!-- 通用专精路线预览 -->
    <n-modal
      v-model:show="showSettings"
      preset="card"
      title="通用专精路线预览"
      style="width: min(900px, 95vw); max-height: 90vh"
      content-style="overflow-y: auto; min-height: 0"
      :mask-closable="false"
      :closable="!routeCalculating"
      :close-on-esc="!routeCalculating"
    >
      <n-alert v-if="defaultsError" type="warning" style="margin-bottom: 12px">{{
        defaultsError
      }}</n-alert>
      <n-text depth="3">
        此处预览各职业的通用路线，默认按已拥有且已解锁的训练技能生成；无 BOX
        时展示原默认最佳路线。不计分支专属加成。手动下拉可选全部干员。
        添加具体干员的训练计划时，会按其职业和分支独立计算，符合条件的分支加成协助者也会参与计算，因此实际路线可能与预览不同。
      </n-text>
      <MasteryProfessionTrainers
        :trainers="bestTrainers"
        :professions="profKeys"
        style="margin: 12px 0"
      />
      <n-tabs class="mastery-route-tabs" type="segment" v-model:value="settingsTab">
        <n-tab-pane v-for="prof in profKeys" :key="prof" :name="prof" :tab="prof">
          <n-scrollbar style="max-height: 60vh">
            <n-dynamic-input v-model:value="routeSettings[prof].supports" :min="3" :max="3">
              <!-- 空插槽会回退到默认增删按钮，保留隐藏节点以覆盖默认操作。 -->
              <template #action><span hidden /></template>
              <template #default="{ value }">
                <div class="support-outer">
                  <n-select
                    v-model:value="value.skill_level"
                    disabled
                    :options="level_list"
                    style="width: 80px"
                  />
                  <div class="support-inner">
                    <div class="task-col">
                      <label style="font-size: 13px">协助位</label>
                      <n-select
                        v-model:value="value.name"
                        filterable
                        :options="operatorOptions"
                        :filter="(p, o) => pinyin_match(o.label, p)"
                        :render-label="render_op_label"
                        style="width: 178px"
                      />
                      <label class="ml" style="font-size: 13px">训练速度</label>
                      <mower-input-number
                        v-model:value="value.efficiency"
                        :min="0"
                        :max="100"
                        style="width: 80px"
                        :show-button="false"
                        ><template #suffix>%</template></mower-input-number
                      >
                    </div>
                    <div class="task-col">
                      <n-checkbox v-model:checked="value.swap">中途换人</n-checkbox>
                      <n-select
                        :disabled="!value.swap"
                        v-model:value="value.swap_name"
                        :options="swap_list"
                        :render-label="render_op_label"
                        style="width: 140px"
                      />
                      <n-select
                        :disabled="!value.swap"
                        v-model:value="value.match"
                        :options="swap_30"
                        style="width: 160px"
                      />
                    </div>
                  </div>
                </div>
              </template>
            </n-dynamic-input>
          </n-scrollbar>
          <div style="display: flex; gap: 12px; margin-top: 16px; align-items: center">
            <n-checkbox v-model:checked="routeSettings[prof].optimal">最优协助干员</n-checkbox>
            <n-checkbox v-model:checked="routeSettings[prof].half_off">有减半加成</n-checkbox>
          </div>
        </n-tab-pane>
      </n-tabs>
      <n-divider />
      <n-text depth="2">中枢干员加成</n-text>
      <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px">
        <n-switch :value="autoCentralBonus" disabled :checked-value="5" :unchecked-value="0">
          <template #checked>+5%</template>
          <template #unchecked>无</template>
        </n-switch>
        <n-text depth="3" style="font-size: 11px">
          按主排班、备用排班中枢栏的主力及替换干员自动识别 +5%
        </n-text>
      </div>
      <n-text depth="2" style="margin-top: 10px">减半换人缓冲时间（分钟）</n-text>
      <div
        v-for="item in masteryBufferFields"
        :key="item.key"
        style="
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-top: 8px;
        "
      >
        <n-text depth="2">{{ item.label }}</n-text>
        <mower-input-number
          :value="masterySettings.mastery_swap_buffers[item.key]"
          @update:value="
            (value) =>
              (masterySettings.mastery_swap_buffers[item.key] =
                value ?? DEFAULT_MASTERY_SWAP_BUFFERS[item.key])
          "
          :min="0"
          :max="60"
          clearable
          size="small"
          style="width: 120px; flex-shrink: 0"
        />
      </div>
      <n-text depth="3" style="font-size: 11px; margin-top: 2px">
        默认{{
          autoCentralBonus ? '分别为 15、30' : '为 10'
        }}分钟，可自行调整；清空单项恢复该项默认值。
      </n-text>
      <template #footer>
        <n-space justify="end" align="center">
          <n-button
            @click="calculateOptimalRoutes"
            :disabled="routeSaving || store.loading"
            :loading="routeCalculating"
            >计算最优</n-button
          >
          <HelpText label="计算最优说明">
            先同步干员数据，再按照最新 BOX 计算最优默认专精路线，应用于全部职业。
          </HelpText>
          <n-button
            type="primary"
            @click="saveRouteAndClose"
            :loading="routeSaving"
            :disabled="routeCalculating"
          >
            保存并关闭
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 专精计划 -->
    <n-modal
      v-model:show="showPlan"
      preset="card"
      title="专精计划"
      style="width: min(600px, 95vw)"
      content-style="max-height: 75vh; overflow-y: auto"
      :mask-closable="false"
      @update:show="onPlanModalShow"
    >
      <n-space vertical>
        <n-input v-model:value="planSearch" placeholder="搜索干员" clearable size="small" />
        <draggable
          v-model="sortablePlanEntries"
          item-key="key"
          handle=".drag-handle"
          @end="onPlanReorder"
        >
          <template #item="{ element: e }">
            <n-tag
              closable
              size="small"
              :type="getStatusType(e.status)"
              @close="removePlanEntry(e)"
              style="margin: 2px 4px; cursor: move"
              class="drag-handle"
            >
              {{ e.name }} {{ e.skill_name }}
              <template v-if="e.status && e.status !== 'idle'">
                ({{ getStatusLabel(e.status) }}{{ e.failed_reason ? '：' + e.failed_reason : '' }})
              </template>
            </n-tag>
          </template>
        </draggable>
        <n-text v-if="!planEntries.length" depth="3">未添加计划</n-text>
        <n-divider />
        <n-scrollbar style="max-height: 50vh">
          <div v-for="op in filteredPlanOperators" :key="op.char_id" class="plan-op-row">
            <n-space align="center" :size="4">
              <n-avatar
                :src="'/avatar/' + op.name + '.webp'"
                :size="22"
                round
                fallback-src="/avatar/阿米娅.webp"
              />
              <n-text strong style="font-size: 13px">{{ op.name }}</n-text>
              <n-text depth="3" style="font-size: 11px">{{ op.rarity }}★</n-text>
              <n-button
                size="tiny"
                quaternary
                :disabled="!!op.mastery_error"
                @click="addAllToPlan(op, true)"
                >全加</n-button
              >
            </n-space>
            <n-space :size="4" style="margin-left: 8px">
              <n-button
                v-for="rec in op.recommendations"
                :key="rec.skill_index"
                size="tiny"
                :type="isSkillPlanned(op.char_id, rec.skill_index) ? 'success' : 'default'"
                @click="toggleSkillPlan(op, rec, true)"
                :disabled="!!op.mastery_error && !isSkillPlanned(op.char_id, rec.skill_index)"
              >
                {{ rec.skill_name }}
              </n-button>
            </n-space>
          </div>
        </n-scrollbar>
      </n-space>
      <template #footer>
        <n-space justify="space-between">
          <n-button @click="clearPlan" size="small">清空</n-button>
          <n-button type="primary" @click="savePlanFn" size="small">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 加工站干员设置 -->
    <n-modal
      v-model:show="showWorkshopSettings"
      preset="card"
      title="加工站干员设置"
      style="width: min(600px, 95vw); max-height: 90vh"
      content-style="overflow-y: auto; min-height: 0"
      :mask-closable="false"
      :closable="!workshopDefaultsLoading"
      :close-on-esc="!workshopDefaultsLoading"
    >
      <n-space vertical>
        <n-alert v-if="workshopDefaultsError" type="warning">{{ workshopDefaultsError }}</n-alert>
        <n-text depth="3">
          一键设置先同步干员数据，再按最新 BOX
          填入已拥有、已解锁技能且副产品概率加成达到所设下限的干员，可继续手动增删。
          材料专属干员仅分配符合条件的材料，相关低阶材料也会生成合成配置。
          主排班及全部备用排班中的主力和替换干员，出现在宿舍、加工站以外的设施时，一键设置会跳过这些干员。
        </n-text>
        <n-space align="center">
          <n-text>副产品概率加成至少</n-text>
          <mower-input-number
            :value="workshopMinBonus"
            @update:value="workshopMinBonus = $event ?? 80"
            :min="0"
            :max="1000"
            :precision="0"
            :step="5"
            :show-button="false"
            :disabled="workshopDefaultsLoading"
            :input-props="{ 'aria-label': '副产品概率加成下限' }"
            style="width: 100px"
            ><template #suffix>%</template></mower-input-number
          >
          <n-button size="small" @click="setWorkshopOperators" :loading="workshopDefaultsLoading"
            >一键设置</n-button
          >
          <n-space align="center" :size="6">
            <n-switch
              v-model:value="workshopLowPriorityRest"
              size="small"
              aria-label="加工干员低优先休息"
            />
            <n-text>低优先休息</n-text>
            <help-text>
              加工名单、加工配置及备份中的干员优先使用空余床位，需要休息的普通干员可接管其床位。
              心情大于 22 的普通替班干员不会踢出正在休息的加工干员，加工干员之间不互踢。
              关闭后按原有宿舍优先级安排。
            </help-text>
          </n-space>
        </n-space>
        <n-space align="center" :size="6">
          <n-switch
            :value="workshopProtectT2"
            :disabled="workshopPolicySaving"
            @update:value="setWorkshopMaterialPolicy"
            size="small"
            aria-label="不使用装置/固源岩进行合成"
          />
          <n-text>不使用装置/固源岩进行合成</n-text>
          <help-text>
            仅保留 T2 装置、固源岩，其他等级照常合成。开启后，材料预算也不使用这两种原料。
          </help-text>
        </n-space>
        <div>
          <n-text depth="3">非 T5 材料加工干员</n-text>
          <help-text>九色鹿使用下方独立设置中的垫刀素材。</help-text>
        </div>
        <slick-operator-select
          v-model="fodderOps"
          :disabled="workshopDefaultsLoading"
          select_placeholder="选择干员（九色鹿带垫刀材料）"
        />
        <n-text depth="3">T5 加工干员</n-text>
        <slick-operator-select
          v-model="t5Ops"
          :disabled="workshopDefaultsLoading"
          select_placeholder="选择干员"
        />
        <n-text depth="3">技巧概要加工干员</n-text>
        <slick-operator-select
          v-model="bookOps"
          :disabled="workshopDefaultsLoading"
          select_placeholder="选择干员"
        />
        <n-collapse>
          <n-collapse-item title="九色鹿垫刀素材设置" name="deer-fodder">
            <workshop-deer-fodder v-model="deerFodder" :disabled="workshopDefaultsLoading" />
          </n-collapse-item>
          <n-collapse-item
            v-if="workshopRecommendations"
            title="值得培养的干员"
            name="workshop-materials"
          >
            <n-space vertical>
              <div v-for="category in workshopCategoryLabels" :key="category.key">
                <n-text strong>{{ category.label }}</n-text>
                <div v-for="operator in workshopRecommendations[category.key]" :key="operator.name">
                  <n-text depth="3">{{
                    workshopRecommendationText(
                      operator,
                      workshopOwnedOperators !== null && !workshopOwnedOperators.has(operator.name)
                    )
                  }}</n-text>
                </div>
                <n-text v-if="!workshopRecommendations[category.key].length" depth="3"
                  >暂无推荐干员</n-text
                >
              </div>
            </n-space>
          </n-collapse-item>
        </n-collapse>
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button
            type="primary"
            size="small"
            @click="showWorkshopSettings = false"
            :disabled="workshopDefaultsLoading"
            >保存</n-button
          >
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import {
  loadWorkshopOperators,
  loadWorkshopReference,
  syncWorkshopOperators,
  selectedWorkshopOperators,
  usesLegacyWorkshopDefaults,
  workshopRecommendationText,
  workshopTraineeWarning
} from '@/utils/workshopOperators'
import { masteryScheduleContext, masteryTraineeWarning } from '@/utils/masterySupport'
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import MasteryMaterials from '@/components/MasteryMaterials.vue'
import { materialStatus, materialStatusType } from '@/utils/masteryMaterials'
import {
  NAlert,
  NAvatar,
  NBadge,
  NButton,
  NCard,
  NCheckbox,
  NCollapse,
  NCollapseItem,
  NDivider,
  NEmpty,
  NGi,
  NGrid,
  NIcon,
  NInput,
  NModal,
  NScrollbar,
  NSelect,
  NSpace,
  NSpin,
  NTabs,
  NTabPane,
  NTag,
  NText,
  NThing,
  NDynamicInput,
  useMessage
} from 'naive-ui'
import { Settings, List } from '@vicons/carbon'
import { Build, Refresh } from '@vicons/ionicons5'
import axios from 'axios'
import draggable from 'vuedraggable'
import { useMasteryStore } from '@/stores/mastery'
import MasterySupports from '@/components/MasterySupports.vue'
import MasteryProfessionTrainers from '@/components/MasteryProfessionTrainers.vue'
import HelpText from '@/components/HelpText.vue'
import { usePlanStore } from '@/stores/plan'
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { pinyin_match } from '@/utils/common'
import {
  buildMasteryRoutePayload,
  prepareMasteryRoutes,
  completeMasterySupports,
  syncMasteryRouteDefaults,
  DEFAULT_MASTERY_SWAP_BUFFERS,
  normalizeMasterySwapBuffers
} from '@/utils/masteryRoute'
import { render_op_label } from '@/utils/op_select'
import { masteryLevelLabel } from '@/utils/masteryLevel'

const ListIcon = List
const SettingsIcon = Settings
const HammerIcon = Build
const RefreshIcon = Refresh
const message = useMessage()
const store = useMasteryStore()
const planStore = usePlanStore()
const configStore = useConfigStore()
const { operators: operatorOptions } = storeToRefs(planStore)

const profKeys = ['先锋', '近卫', '重装', '狙击', '术师', '医疗', '辅助', '特种']
const profMap = {
  WARRIOR: '近卫',
  SNIPER: '狙击',
  TANK: '重装',
  MEDIC: '医疗',
  SUPPORT: '辅助',
  CASTER: '术师',
  SPECIAL: '特种',
  PIONEER: '先锋'
}
const professionName = (p) => profMap[p] || p

const rarityOptions = [
  { label: '6★', value: 6 },
  { label: '5★', value: 5 },
  { label: '4★', value: 4 }
]
const professionOptions = profKeys.map((p) => ({ label: p, value: p }))

const searchQuery = ref('')
const filterRarity = ref([])
const filterProfession = ref([])
const filterAchievable = ref(false)
const showOnlyPlanned = ref(false)
// 空闲状态三态：all=全部 idle=空闲 busy=非空闲
const idleFilter = ref('all')
const idleFilterOptions = [
  { label: '全部', value: 'all' },
  { label: '空闲', value: 'idle' },
  { label: '非空闲', value: 'busy' }
]
const {
  workshop_min_bonus: workshopMinBonus,
  workshop_low_priority_rest: workshopLowPriorityRest,
  workshop_protect_t2_device_rock: workshopProtectT2,
  workshop_deer_fodder: deerFodder,
  fodder_operators: fodderOps,
  t5_operators: t5Ops,
  book_operators: bookOps
} = storeToRefs(configStore)
const workshopPolicySaving = ref(false)
async function setWorkshopMaterialPolicy(value) {
  workshopProtectT2.value = value
  workshopPolicySaving.value = true
  try {
    await configStore.save_config()
    await store.fetchRecommendations()
    await refreshT3Summary()
  } catch (error) {
    message.error(`合成设置保存失败：${error.message || error}`)
  } finally {
    workshopPolicySaving.value = false
  }
}
const workshopLoading = ref(false)
const showWorkshopSettings = ref(false)
const workshopRecommendations = ref(null)
const workshopOwnedOperators = ref(null)
const workshopDefaultsLoading = ref(false)
const workshopDefaultsError = ref('')
const workshopCategoryLabels = [
  { key: 'fodder_operators', label: '非 T5 材料' },
  { key: 't5_operators', label: 'T5 材料' },
  { key: 'book_operators', label: '技巧概要' }
]

async function readWorkshopDefaults(apply = false, sync = false) {
  if (workshopDefaultsLoading.value) return
  workshopDefaultsLoading.value = true
  workshopDefaultsError.value = ''
  try {
    const load = sync ? syncWorkshopOperators : loadWorkshopOperators
    const data = await load(axios, import.meta.env.VITE_HTTP_URL, workshopMinBonus.value)
    workshopRecommendations.value = data.recommendations
    workshopOwnedOperators.value = Array.isArray(data.owned_operators)
      ? new Set(data.owned_operators)
      : null
    if (apply) {
      fodderOps.value = [...data.defaults.fodder_operators]
      t5Ops.value = [...data.defaults.t5_operators]
      bookOps.value = [...data.defaults.book_operators]
    }
  } catch (e) {
    workshopDefaultsError.value = e.response?.data?.error || e.message || '加工站推荐读取失败'
    workshopOwnedOperators.value = null
    try {
      workshopRecommendations.value = await loadWorkshopReference(
        axios,
        import.meta.env.VITE_HTTP_URL
      )
    } catch {
      workshopRecommendations.value = null
    }
  } finally {
    workshopDefaultsLoading.value = false
  }
}

async function openWorkshopSettings() {
  showWorkshopSettings.value = true
  await readWorkshopDefaults(
    usesLegacyWorkshopDefaults({
      fodder_operators: fodderOps.value,
      t5_operators: t5Ops.value,
      book_operators: bookOps.value
    })
  )
}

async function setWorkshopOperators() {
  await readWorkshopDefaults(true, true)
}
const workshopT3Summary = ref([])

const emptyText = computed(() => {
  if (searchQuery.value || filterRarity.value.length || filterProfession.value.length)
    return '没有匹配的干员'
  if (idleFilter.value === 'idle') return '没有空闲干员'
  if (idleFilter.value === 'busy') return '没有非空闲干员'
  if (showOnlyPlanned.value) return '没有计划中的专精项'
  return '没有推荐项'
})

// ─── 计划（技能级别）───
// 格式: { "charId_skillIndex": true, ... }
const plan = ref({})
const planStatus = ref({}) // { "charId_skillIndex": {id, status, target_level, priority, expires_at} }
const showPlan = ref(false)
const planSearch = ref('')
// 草稿式编辑：弹层内移除的 planStatus key，保存时才删后端；re-add 会移出该集合
const draftRemoved = ref(new Set())
// 保存后主动关闭弹层，不触发「关闭不保存即丢弃」的重载
let planJustSaved = false

function planKey(cid, si) {
  return `${cid}_${si}`
}
function isSkillPlanned(cid, si) {
  return !!plan.value[planKey(cid, si)]
}
function hasPlannedSkill(op) {
  return op.recommendations.some((r) => isSkillPlanned(op.char_id, r.skill_index))
}
function allPlanned(op) {
  return op.recommendations.every((r) => isSkillPlanned(op.char_id, r.skill_index))
}

function getStatusLabel(status) {
  const map = {
    idle: '待执行',
    arranging: '正在安排',
    training: '训练中',
    waiting_collect: '待收取',
    completed: '已完成',
    failed: '失败'
  }
  return map[status] || status
}

function getStatusType(status) {
  const map = {
    idle: 'default',
    arranging: 'info',
    training: 'success',
    waiting_collect: 'warning',
    completed: 'success',
    failed: 'error'
  }
  return map[status] || 'default'
}

async function warnMaterialShortage(additions) {
  const keys = [
    ...new Set([...Object.keys(plan.value).filter((key) => plan.value[key]), ...additions])
  ]
  try {
    const response = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/mastery-t3-summary`,
      {
        planned_skills: keys
      },
      { timeout: 5000 }
    )
    const summary = response.data?.material_summary
    if (!summary) throw new Error('材料数据不可用')
    if (!summary.available) {
      message.warning(
        summary.craftable
          ? '计划总需求超出成品库存，可由现有材料合成；仍可加入计划。'
          : '计划总材料不足（含技巧概要），缺口可在主页查看；仍可加入计划。'
      )
    }
  } catch {
    message.warning('暂时无法核对总材料库存，仍可加入计划，请稍后刷新查看。')
  }
}

async function toggleSkillPlan(op, rec, draft = false) {
  const k = planKey(op.char_id, rec.skill_index)
  if (!plan.value[k] && op.mastery_error) {
    message.warning(op.mastery_error)
    return
  }
  if (!plan.value[k]) await warnMaterialShortage([k])
  if (!plan.value[k] && workshopTrainingWarning(op.name)) {
    message.warning(workshopTrainingWarning(op.name))
  }
  if (!plan.value[k] && trainingWarning(op.name)) {
    message.warning(trainingWarning(op.name))
  }
  if (plan.value[k]) {
    // 删除计划
    const info = planStatus.value[k]
    if (!draft && info && info.id) {
      try {
        await axios.delete(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, {
          data: { id: info.id }
        })
      } catch (e) {
        message.error(`删除失败: ${e.message}`)
        return
      }
    }
    delete plan.value[k]
    if (draft) {
      draftRemoved.value.add(k) // 草稿：保留 id，保存时删后端
    } else {
      delete planStatus.value[k] // 主列表 quick-add：已删后端，同步本地
    }
  } else if (draft) {
    // 弹层内草稿：只动本地，保存时 POST
    plan.value[k] = true
    draftRemoved.value.delete(k)
  } else {
    // 主列表 quick-add：立即写后端
    try {
      const body = { items: [{ name: op.name, skill_index: rec.skill_index }] }
      const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, body)
      const results = r.data?.results || []
      for (const warning of new Set(results.map((result) => result.warning).filter(Boolean))) {
        message.warning(warning)
      }
      if (results[0]?.status === 'added') {
        plan.value[k] = true
        // #65：target_level 由服务端默认专三（与推荐一致）
        planStatus.value[k] = { id: results[0].id, status: 'idle', target_level: 3, priority: 0 }
        await refreshPlanFromServer()
      } else {
        message.warning(results[0]?.reason || '添加失败')
      }
    } catch (e) {
      message.error(`保存失败: ${e.message}`)
    }
  }
}

async function addAllToPlan(op, draft = false) {
  if (op.mastery_error) {
    message.warning(op.mastery_error)
    return
  }
  if (trainingWarning(op.name)) {
    message.warning(trainingWarning(op.name))
  }
  const recs = op.recommendations
  const additions = recs
    .map((rec) => planKey(op.char_id, rec.skill_index))
    .filter((key) => !plan.value[key])
  if (additions.length) await warnMaterialShortage(additions)
  if (
    recs.some((rec) => !plan.value[planKey(op.char_id, rec.skill_index)]) &&
    workshopTrainingWarning(op.name)
  ) {
    message.warning(workshopTrainingWarning(op.name))
  }
  if (draft) {
    // 计划弹窗内草稿：只动本地，保存时 POST
    for (const rec of recs) {
      const k = planKey(op.char_id, rec.skill_index)
      plan.value[k] = true
      draftRemoved.value.delete(k)
    }
    message.success(`${op.name} 全部技能已加入计划`)
    return
  }
  // 主列表 quick-add：立即写后端（跳过已计划技能，后端无 (char,skill) 唯一约束，重复 POST 会建重复行）
  const toAdd = recs.filter((rec) => !plan.value[planKey(op.char_id, rec.skill_index)])
  if (!toAdd.length) {
    message.info(`${op.name} 所有推荐技能都已在计划中`)
    return
  }
  try {
    const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, {
      items: toAdd.map((rec) => ({ name: op.name, skill_index: rec.skill_index }))
    })
    const results = r.data?.results || []
    for (const warning of new Set(results.map((result) => result.warning).filter(Boolean))) {
      message.warning(warning)
    }
    const errs = []
    results.forEach((res, i) => {
      const rec = toAdd[i]
      if (res.status === 'added') {
        const k = planKey(op.char_id, rec.skill_index)
        plan.value[k] = true
        // #65：target_level 由服务端默认专三（与推荐一致）
        planStatus.value[k] = { id: res.id, status: 'idle', target_level: 3, priority: 0 }
      } else {
        errs.push(res.reason || '添加失败')
      }
    })
    if (errs.length) {
      message.warning(`${op.name} 有 ${errs.length} 项未加入: ${errs.join('；')}`)
    } else {
      message.success(`${op.name} 全部技能已加入计划`)
    }
  } catch (e) {
    message.error(`保存失败: ${e.message}`)
  }
}

function removePlanEntry(e) {
  // 弹层内草稿式删除：只动本地，保存时删后端（planStatus 保留 id）
  delete plan.value[e.key]
  draftRemoved.value.add(e.key)
}
function clearPlan() {
  // 草稿式清空：只清本地视图，保存时才删后端计划（已挪到左侧，远离保存）
  for (const k in planStatus.value) draftRemoved.value.add(k)
  plan.value = {}
}
async function savePlanFn() {
  const toAdd = []
  for (const k in plan.value) {
    if (planStatus.value[k]?.id) continue // 已是后端计划
    const [cid, si] = parsePlanKey(k)
    const op = store.recommendations.find((o) => o.char_id === cid)
    if (op && si !== undefined) {
      // #65：不传 target_level，服务端默认专三
      toAdd.push({ name: op.name, skill_index: parseInt(si) })
    }
  }
  // 草稿中被移除且未重新加回的计划（清空/单删/技能反选）
  const toDel = [...draftRemoved.value].filter((k) => !plan.value[k] && planStatus.value[k]?.id)
  const orderUpdates = sortablePlanEntries.value
    .map((e, idx) => ({ id: planStatus.value[e.key]?.id, priority: idx }))
    .filter((u) => u.id)
  if (!toAdd.length && !toDel.length && !orderUpdates.length) {
    message.info('没有变更需要保存')
    showPlan.value = false
    return
  }
  if (toAdd.length) {
    const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, { items: toAdd })
    const results = r.data?.results || []
    for (const warning of new Set(results.map((result) => result.warning).filter(Boolean))) {
      message.warning(warning)
    }
    const err = results.filter((x) => x.status === 'error')
    if (err.length) {
      message.warning(`保存完成，${err.length} 项失败: ${err.map((x) => x.reason).join('；')}`)
    }
  }
  for (const k of toDel) {
    try {
      await axios.delete(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, {
        data: { id: planStatus.value[k].id }
      })
    } catch (e) {
      message.error(`删除失败: ${e.message}`)
    }
  }
  if (orderUpdates.length) {
    try {
      await axios.patch(`${import.meta.env.VITE_HTTP_URL}/mastery-plan/order`, orderUpdates)
    } catch (e) {
      message.error(`排序失败: ${e.message}`)
    }
  }
  planJustSaved = true
  await refreshPlanFromServer()
  showPlan.value = false
  message.success(`计划已保存${toAdd.length ? `（新增 ${toAdd.length} 项）` : ''}`)
}

async function refreshPlanFromServer() {
  try {
    const r = await axios.get(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`)
    const data = r.data || {}
    const p = {}
    const ps = {}
    for (const item of data.plans || []) {
      const k = planKey(item.char_id, item.skill_index)
      // failed 计划也要显示（带失败原因），不能从列表凭空消失（#69）
      if (item.status !== 'completed') {
        p[k] = true
      }
      ps[k] = {
        id: item.id,
        status: item.status,
        target_level: item.target_level,
        priority: item.priority,
        expires_at: item.expires_at,
        failed_reason: item.failed_reason,
        support_plan: item.support_plan,
        support_runtime: item.support_runtime
      }
    }
    plan.value = p
    planStatus.value = ps
    draftRemoved.value.clear() // 以服务端为准，丢弃未落库的删除意图
  } catch (e) {
    console.error('refreshPlanFromServer failed', e)
  }
}

async function openPlanModal() {
  // 打开即重载：丢弃上次未保存的草稿（与路线编辑「关闭不保存即丢弃」一致）
  await refreshPlanFromServer()
  showPlan.value = true
}

function onPlanModalShow(show) {
  if (!show && !planJustSaved) {
    refreshPlanFromServer() // 未保存关闭 → 还原草稿
  }
  planJustSaved = false
}

function parsePlanKey(k) {
  const i = k.lastIndexOf('_')
  return [k.slice(0, i), parseInt(k.slice(i + 1))]
}

const planEntries = computed(() => {
  const entries = []
  for (const k in plan.value) {
    const [cid, si] = parsePlanKey(k)
    const op = store.recommendations.find((o) => o.char_id === cid)
    if (op) {
      const rec = op.recommendations.find((r) => r.skill_index === si)
      const info = planStatus.value[k] || {}
      if (rec)
        entries.push({
          key: k,
          id: info.id,
          char_id: cid,
          skill_index: si,
          name: op.name,
          skill_name: rec.skill_name,
          status: info.status || 'idle',
          priority: info.priority || 0,
          failed_reason: info.failed_reason
        })
    }
  }
  entries.sort((a, b) => {
    // failed 计划排到列表底部（待重试，不参与正常优先级排序）
    if (a.status === 'failed' && b.status !== 'failed') return 1
    if (b.status === 'failed' && a.status !== 'failed') return -1
    return a.priority - b.priority
  })
  return entries
})

const sortablePlanEntries = ref([])
watch(
  planEntries,
  (val) => {
    sortablePlanEntries.value = [...val]
  },
  { immediate: true }
)

function onPlanReorder() {
  // 草稿式排序：只更新本地优先级，保存时才写后端
  sortablePlanEntries.value.forEach((e, idx) => {
    if (planStatus.value[e.key]) planStatus.value[e.key].priority = idx
  })
}

const filteredPlanOperators = computed(() => {
  let list = allOperatorList.value.filter((o) => hasPlannedSkill(o))
  const q = planSearch.value.trim().toLowerCase()
  if (q) list = list.filter((o) => o.name.toLowerCase().includes(q))
  return list
})

async function autoWorkshop() {
  workshopLoading.value = true
  try {
    const resp = await axios.post(`${import.meta.env.VITE_HTTP_URL}/workshop-auto-config`, {
      fodder_operators: fodderOps.value,
      t5_operators: t5Ops.value,
      book_operators: bookOps.value
    })
    const ws = resp.data?.workshop_settings
    if (!ws) {
      message.warning('生成失败')
      return
    }
    configStore.apply_workshop_response(resp.data)
    if (resp.data.workshop_preset_warning) {
      message.warning(resp.data.workshop_preset_warning)
      return
    }
    workshopT3Summary.value = resp.data?.t3_summary || []

    if (!resp.data.automatic || !ws.length) {
      message.info(
        resp.data.restored ? '专精材料已准备完毕，已恢复手动合成配置' : '当前没有可准备的专精材料'
      )
      return
    }

    const tasksResp = await axios.get(`${import.meta.env.VITE_HTTP_URL}/task`)
    const tasks = tasksResp.data || []
    const hasTask = (opName) =>
      tasks.some((t) => {
        const tType =
          typeof t.type === 'string' ? t.type : t.type?.display_value || t.type?.value || ''
        return tType === '加工材料' && (t.meta_data === '' || t.meta_data === opName)
      })

    let added = []
    let skipped = []
    for (const entry of ws) {
      if (!entry.operator || !entry.items?.length) continue
      const op = entry.operator
      if (hasTask(op)) {
        skipped.push(op)
        continue
      }
      const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/task`, {
        task: {
          time: new Date(Date.now() + added.length * 2000).toISOString(),
          plan: {},
          task_type: '加工材料',
          workshop_generation: resp.data.workshop_generation,
          meta_data: op
        }
      })
      if (r.data === '添加任务成功！') {
        added.push(op)
      } else {
        message.warning(`${op} 任务添加失败: ${r.data}`)
      }
    }

    const parts = []
    if (added.length) parts.push(`已添加任务: ${added.join(', ')}`)
    if (skipped.length) parts.push(`已有任务: ${skipped.join(', ')}`)
    message.success(`已为下一待专精技能生成合成配置${parts.length ? '，' + parts.join('；') : ''}`)
  } catch (e) {
    message.error(`生成失败: ${e.message}`)
  } finally {
    workshopLoading.value = false
  }
}

// ─── 通用专精路线预览 ───
const showSettings = ref(false)
const settingsTab = ref('近卫')
const swap_list = [
  { value: '艾丽妮', label: '艾丽妮' },
  { value: '逻各斯', label: '逻各斯' }
]
const swap_30 = [
  { value: 'yes', label: '有30%速度加成' },
  { value: 'no', label: '无训练速度加成' }
]
const level_list = [
  { value: 1, label: '专一' },
  { value: 2, label: '专二' },
  { value: 3, label: '专三' }
]
// 全局路线设置（#91 修订）：中枢加成（0/5）+ 换人缓冲时间，存路线配置设置行，不走 conf。
const masterySettings = reactive({
  central_bonus: 0,
  mastery_swap_buffers: { ...DEFAULT_MASTERY_SWAP_BUFFERS }
})
const masteryBufferFields = computed(() =>
  autoCentralBonus.value
    ? [
        { key: 'central', label: '中枢加成 +5%' },
        { key: 'central_unhalved_m2', label: '中枢加成 +5%，专二未继承减半' }
      ]
    : [{ key: 'no_central', label: '无中枢加成' }]
)

const defaultsCache = ref(null)
const bestTrainers = ref({})
const defaultsError = ref('')

const routeSettings = reactive(
  Object.fromEntries(
    profKeys.map((p) => [p, { supports: completeMasterySupports([]), half_off: true }])
  )
)
let _autoSaveReady = false
let _routeSaveChain = Promise.resolve()
const _dirtyRouteProfessions = new Set()
const _suggestedRouteProfessions = new Set()
let _dirtyMasterySettings = false
const routeSaving = ref(false)
const routeCalculating = ref(false)

function persistRouteSettings() {
  const professions = [...new Set([..._dirtyRouteProfessions, ..._suggestedRouteProfessions])]
  if (!professions.length) return _routeSaveChain
  _dirtyRouteProfessions.clear()
  _suggestedRouteProfessions.clear()
  const payloads = professions.map((profession) =>
    buildMasteryRoutePayload(profession, routeSettings[profession])
  )
  routeSaving.value = true
  const savePromise = _routeSaveChain
    .catch(() => {})
    .then(() =>
      Promise.all(
        payloads.map((payload) =>
          axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-route`, payload)
        )
      )
    )
  _routeSaveChain = savePromise
  savePromise.then(
    () => {
      if (_routeSaveChain === savePromise) routeSaving.value = false
    },
    () => {
      professions.forEach((profession) => _dirtyRouteProfessions.add(profession))
      if (_routeSaveChain === savePromise) routeSaving.value = false
    }
  )
  return savePromise
}

// 编辑只改内存，持久化仅在「保存并关闭」触发（改错可关掉弹窗还原，不被自动保存覆盖）
function markRouteDirty(profession) {
  if (!_autoSaveReady) return
  _dirtyRouteProfessions.add(profession)
}

function flushRouteSettings() {
  return persistRouteSettings()
}

for (const profession of profKeys) {
  watch(
    () => routeSettings[profession],
    () => markRouteDirty(profession),
    { deep: true }
  )
}

// #115：modal 级中枢加成/缓冲与逐职业路线同源走草稿语义——改了不保存关掉要还原
watch(
  () => [masterySettings.central_bonus, ...Object.values(masterySettings.mastery_swap_buffers)],
  () => {
    if (_autoSaveReady) _dirtyMasterySettings = true
  }
)

function applyRoute(d) {
  for (const p of profKeys) {
    if (d[p]) {
      routeSettings[p].supports = completeMasterySupports(d[p].supports, d._jsonDefaults?.[p])
      routeSettings[p].optimal = !!d[p].optimal
      routeSettings[p].half_off = d[p].half_off !== undefined ? d[p].half_off : true
    } else {
      routeSettings[p].supports = completeMasterySupports([], d._jsonDefaults?.[p])
      routeSettings[p].optimal = false
      routeSettings[p].half_off = false
    }
  }
}

async function loadRoute() {
  const r = await axios.get(`${import.meta.env.VITE_HTTP_URL}/mastery-route`)
  const routes = r.data?.routes || []
  const routeDefaults = r.data?.defaults || {}
  const settings = r.data?.settings || {}
  _autoSaveReady = false
  masterySettings.central_bonus = settings.central_bonus ?? 0
  masterySettings.mastery_swap_buffers = normalizeMasterySwapBuffers(settings)
  bestTrainers.value = r.data?.best_trainers || {}
  defaultsError.value = r.data?.defaults_error || ''
  const { routes: merged, suggestedProfessions } = prepareMasteryRoutes(
    routes,
    routeDefaults,
    profKeys
  )
  _suggestedRouteProfessions.clear()
  suggestedProfessions.forEach((p) => _suggestedRouteProfessions.add(p))
  defaultsCache.value = merged
  applyRoute(merged)
  await nextTick()
  _autoSaveReady = true
}
async function openSettings() {
  try {
    await loadRoute()
  } catch (e) {
    defaultsError.value = '路线加载失败，请稍后重试'
    console.error('openSettings: loadRoute failed', e)
  }
  showSettings.value = true
}
async function discardRouteChanges() {
  // 关闭弹窗未保存：丢弃内存修改，从 DB 重载还原。
  // _autoSaveReady 先置 false，避免还原过程（applyRoute 触发 watcher）被误标记 dirty。
  _autoSaveReady = false
  _dirtyRouteProfessions.clear()
  _dirtyMasterySettings = false
  try {
    await loadRoute()
  } catch (e) {
    _autoSaveReady = true
    throw e
  }
}
watch(showSettings, (val) => {
  if (!val && (_dirtyRouteProfessions.size || _dirtyMasterySettings)) {
    discardRouteChanges()
      .then(() => message.warning('通用专精路线修改未保存，已还原'))
      .catch((e) => console.error('discard route changes failed', e))
  }
})

async function saveRouteAndClose() {
  try {
    await Promise.all([
      flushRouteSettings(),
      axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-route/settings`, {
        central_bonus: autoCentralBonus.value,
        mastery_swap_buffers: { ...masterySettings.mastery_swap_buffers }
      })
    ])
    _dirtyMasterySettings = false // 已落库，关弹窗不再触发「未保存还原」
    showSettings.value = false
    message.success('通用专精路线已保存')
  } catch (e) {
    console.error('saveRouteAndClose: failed', e)
    message.error('保存失败')
  }
}

async function calculateOptimalRoutes() {
  if (routeCalculating.value || routeSaving.value || store.loading) return
  routeCalculating.value = true
  try {
    const data = await syncMasteryRouteDefaults(axios, import.meta.env.VITE_HTTP_URL)
    const { routes: def } = prepareMasteryRoutes([], data.defaults, profKeys)
    bestTrainers.value = data.best_trainers || {}
    defaultsError.value = ''
    defaultsCache.value = def
    if (!profKeys.some((p) => def._jsonDefaults[p]?.length)) {
      message.info('没有已拥有且已解锁训练技能的可用干员')
      return
    }
    for (const p of profKeys) {
      routeSettings[p].supports = (def._jsonDefaults[p] || []).map((s) => ({ ...s }))
      routeSettings[p].half_off = !!def._defaultFlags[p]?.half_off
      routeSettings[p].optimal = false
      _dirtyRouteProfessions.add(p)
    }
    message.success('已同步干员数据并计算全部职业的最优路线（保存并关闭后生效）')
  } catch (e) {
    message.error(e.response?.data?.message || e.response?.data?.error || e.message || '计算失败')
  } finally {
    routeCalculating.value = false
  }
}

// ─── 显示列表 ───
const allOperatorList = computed(() => store.recommendations)

// ─── 空闲干员筛选 ───
// 空闲 = 不在排班表（主/副表槽位 + 候补 replacement）& 不在专精路线配置（协助位 name/换人 swap_name）
// & 不在加工站工具人 & 不在宿舍黑名单。
// 与「是否有专精计划」正交：空闲/非空闲只看基地占用，计划状态由「只看计划」管——
// 非空闲干员同样可以加入计划，添加时仅提示排班冲突。
// 排班由 App 启动时全局 load（router-view 以 loaded 门控，进入本页必然已加载）。
const supportSchedule = computed(() =>
  masteryScheduleContext(planStore.plan, planStore.backup_plans)
)
const scheduledOperatorSet = computed(() => supportSchedule.value.scheduled)
const autoCentralBonus = computed(() => supportSchedule.value.centralBonus)
function trainingWarning(name) {
  return masteryTraineeWarning(name, supportSchedule.value.blocked)
}

const showSupports = ref(false)
const supportSelection = reactive({ plan: null, name: '' })
async function openSupports(op, rec) {
  await refreshPlanFromServer()
  supportSelection.plan = planStatus.value[planKey(op.char_id, rec.skill_index)]
  supportSelection.name = op.name
  showSupports.value = true
}
const routeOperatorSet = computed(() => {
  const busy = new Set()
  for (const p of profKeys) {
    for (const sup of routeSettings[p]?.supports || []) {
      if (sup.name) busy.add(sup.name)
      if (sup.swap_name) busy.add(sup.swap_name)
    }
  }
  return busy
})
const workshopOperators = computed(() => selectedWorkshopOperators(configStore))
function workshopTrainingWarning(name) {
  return workshopTraineeWarning(name, workshopOperators.value)
}
function isIdleOperator(op) {
  if (scheduledOperatorSet.value.has(op.name)) return false
  if (routeOperatorSet.value.has(op.name)) return false
  if (workshopOperators.value.has(op.name)) return false
  if ((configStore.free_blacklist || []).includes(op.name)) return false
  return true
}

const displayList = computed(() => {
  let list = store.recommendations
  if (showOnlyPlanned.value) list = list.filter((op) => hasPlannedSkill(op))
  if (idleFilter.value === 'idle') list = list.filter((op) => isIdleOperator(op))
  if (idleFilter.value === 'busy') list = list.filter((op) => !isIdleOperator(op))
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter((op) => op.name.toLowerCase().includes(q))
  }
  if (filterRarity.value.length) list = list.filter((op) => filterRarity.value.includes(op.rarity))
  if (filterProfession.value.length)
    list = list.filter((op) => filterProfession.value.includes(profMap[op.profession]))
  if (filterAchievable.value)
    list = list
      .map((op) => ({
        ...op,
        recommendations: op.recommendations.filter((r) => r.material_summary?.craftable)
      }))
      .filter((op) => op.recommendations.length > 0)
  return list
})

function visibleRecs(op) {
  if (showOnlyPlanned.value)
    return op.recommendations.filter((r) => isSkillPlanned(op.char_id, r.skill_index))
  return op.recommendations
}

const planMaterials = ref(null)
const missingPlanSkills = computed(() => {
  const keys = new Set(planMaterials.value?.missing_skills || [])
  return planEntries.value.filter((entry) => keys.has(entry.key))
})
const materialsLoading = ref(false)
const materialsError = ref('')
let materialRequest = 0
let materialTimer

async function refreshT3Summary() {
  const request = ++materialRequest
  const keys = planEntries.value.map((entry) => entry.key)
  if (!keys.length) {
    planMaterials.value = null
    materialsLoading.value = false
    return
  }
  materialsLoading.value = true
  materialsError.value = ''
  try {
    const response = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-t3-summary`, {
      planned_skills: keys
    })
    if (request !== materialRequest) return
    if (response.data.error) throw new Error(response.data.error)
    planMaterials.value = response.data.material_summary
  } catch (error) {
    if (request === materialRequest) {
      planMaterials.value = null
      materialsError.value = error.response?.data?.error || '材料计算失败，请刷新后重试'
    }
  } finally {
    if (request === materialRequest) materialsLoading.value = false
  }
}

watch(
  [plan, planStatus, () => store.recommendations],
  () => {
    ++materialRequest
    clearTimeout(materialTimer)
    materialsLoading.value = !!Object.values(plan.value).some(Boolean)
    materialTimer = setTimeout(refreshT3Summary, 200)
  },
  { deep: true }
)
onUnmounted(() => {
  ++materialRequest
  clearTimeout(materialTimer)
})

// ─── 工具函数 ───
function formatTime(s) {
  const h = Math.floor(s / 3600),
    m = Math.floor((s % 3600) / 60)
  if (h > 0 && m > 0) return `${h}小时${m}分钟`
  if (h > 0) return `${h}小时`
  if (m > 0) return `${m}分钟`
  return `${s}秒`
}
async function fetchCultivate() {
  await store.fetchCultivate()
  if (store.cultivateOk) {
    message.success(`森空岛数据同步成功 ${store.cultivateMsg}`)
  } else if (store.cultivateMsg) {
    message.error(`森空岛同步失败: ${store.cultivateMsg}`)
  }
}

// ─── 确认 & 提交 ───
const showConfirm = ref(false)
const cd = reactive({ op: null, rec: null })

function confirmSkill(op, rec) {
  if (op.mastery_error) {
    message.warning(op.mastery_error)
    return
  }
  cd.op = op
  cd.rec = rec
  showConfirm.value = true
}

async function doAddTask() {
  showConfirm.value = false
  const { op, rec } = cd
  await warnMaterialShortage([planKey(op.char_id, rec.skill_index)])
  if (workshopTrainingWarning(op.name)) message.warning(workshopTrainingWarning(op.name))
  if (trainingWarning(op.name)) message.warning(trainingWarning(op.name))
  try {
    // #71：一键专精走 DB 计划创建 API（POST /mastery-plan），不再发原始 /task「技能专精」
    // （死流：server 只认 DB 计划）。target_level 由服务端默认专三，与确认弹窗「→ 专精3级」一致。
    const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, {
      items: [{ name: op.name, skill_index: rec.skill_index }]
    })
    const results = r.data?.results || []
    for (const warning of new Set(results.map((result) => result.warning).filter(Boolean))) {
      message.warning(warning)
    }
    if (results[0]?.status === 'added') {
      message.success(`${op.name} ${rec.skill_name} 专精任务已添加！`)
      await refreshPlanFromServer()
    } else {
      message.warning(results[0]?.reason || '添加失败')
    }
  } catch (e) {
    message.error(`添加失败: ${e.message}`)
  }
}

// ─── 初始化 ───
onMounted(async () => {
  await refreshPlanFromServer()
  await Promise.all([loadOperators(), store.fetchRecommendations()])
  // 空闲干员筛选需要路线配置；打开设置时再刷新一次，反映最新拥有情况和解锁技能。
  if (!defaultsCache.value) {
    try {
      await loadRoute()
    } catch (e) {
      console.error('mount: loadRoute failed', e)
    }
  }
  await refreshT3Summary()
})

async function loadOperators() {
  try {
    const r = await axios.get(`${import.meta.env.VITE_HTTP_URL}/operator`)
    operatorOptions.value = (r.data || []).map((n) => ({ label: n, value: n }))
  } catch (e) {
    console.error('loadOperators: failed', e)
  }
}
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.page-title {
  margin: 0;
  font-size: 20px;
}
.mastery-list {
  width: 100%;
  max-width: 960px;
}
.mastery-route-tabs {
  /* Keep the segment capsule inside the scrolling content's coordinate space. */
  position: relative;
}
.rec-item .n-card {
  margin-bottom: 0;
}
.section-label {
  display: block;
  margin-bottom: 2px;
}
.missing-section {
  margin-top: 4px;
}
.support-outer {
  margin-bottom: 8px;
}
.support-inner {
  margin-top: 4px;
}
.task-col {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0;
}
.ml {
  margin-left: 12px;
}
.confirm-support-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 2px 0;
}
.plan-op-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
</style>
