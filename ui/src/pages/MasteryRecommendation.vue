<template>
  <div class="home-container growth-page" :style="{ color: theme.textColor1 }">
    <div class="page-header">
      <div>
        <h1 class="page-title">养成规划</h1>
        <n-text depth="3" class="page-subtitle">选定目标，准备材料，逐位完成养成</n-text>
      </div>
      <n-space align="center" :size="8">
        <n-button size="small" @click="openPlanModal">
          <template #icon><n-icon :component="ListIcon" /></template>
          我的养成计划
          <n-badge
            v-if="totalGoalCount"
            :value="totalGoalCount"
            :max="99"
            style="margin-left: 4px"
          />
        </n-button>
        <n-button size="small" @click="openSettings">
          <template #icon><n-icon :component="SettingsIcon" /></template>
          通用专精路线预览
        </n-button>
        <GrowthCraftingOrder :revision="craftingOrderRevision" @changed="refreshT3Summary" />
        <n-button size="small" @click="openWorkshopSettings">
          <template #icon><n-icon :component="SettingsIcon" /></template>
          加工站干员设置
        </n-button>
        <n-button
          size="small"
          type="warning"
          @click="autoWorkshop"
          :loading="workshopLoading"
          :disabled="!totalGoalCount || store.loading"
        >
          <template #icon><n-icon :component="HammerIcon" /></template>
          生成缺失材料合成任务
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

    <n-card size="small" class="statistics-panel" title="干员数据统计">
      <template #header-extra
        ><n-button
          size="small"
          :aria-expanded="statisticsExpanded"
          @click="statisticsExpanded = !statisticsExpanded"
        >
          {{ statisticsExpanded ? '收起统计' : '展开统计' }}
        </n-button></template
      >
      <OperatorStatistics
        v-if="statisticsExpanded"
        :statistics="store.personalStatistics"
        :history="store.history"
      />
      <n-text v-else depth="3">查看招募、练度、材料消耗与等效理智排行</n-text>
    </n-card>

    <div
      class="mastery-global-switch"
      style="display: flex; align-items: center; gap: 8px; margin-top: 8px"
    >
      <n-switch v-model:value="configStore.enable_mastery" size="small" />
      <n-text strong>全自动专精</n-text>
      <n-text depth="3" style="font-size: 12px"
        >控制自动专精与养成材料自动合成；精英化、基础技能升级与模组开启需要手动完成后同步</n-text
      >
    </div>

    <GrowthSurveyFilters
      v-model="surveyFilters"
      :survey="survey"
      :loading="surveyLoading"
      @refresh="loadSurvey"
    >
      <n-space style="margin-top: 8px" :size="8" align="center" wrap>
        <n-input
          v-model:value="searchQuery"
          placeholder="搜索干员 / 拼音"
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
        <n-select
          v-model:value="idleFilter"
          :options="idleFilterOptions"
          size="small"
          style="min-width: 130px"
          aria-label="基地空闲状态"
        />
        <n-button size="small" @click="resetFilters">
          <template #icon><n-icon :component="RefreshIcon" /></template>
          重置筛选
        </n-button>
      </n-space>
    </GrowthSurveyFilters>

    <n-space justify="space-between" align="center" class="filter-summary">
      <n-text depth="3"
        >显示 {{ displayList.length }} / {{ store.recommendations.length }} 位干员</n-text
      >
    </n-space>

    <n-card size="small" class="materials-overview">
      <n-spin :show="materialsLoading">
        <n-collapse>
          <n-collapse-item title="养成材料总览" name="materials-overview">
            <template #header-extra>
              <n-tag
                v-if="planMaterials"
                :type="materialStatusType(planMaterials)"
                size="small"
                :bordered="false"
              >
                {{ materialStatus(planMaterials) }}
              </n-tag>
            </template>
            <n-alert v-if="materialsError" type="warning">{{ materialsError }}</n-alert>
            <n-space justify="end" style="margin-bottom: 12px" v-if="hasChipShortage">
              <n-button
                :loading="chipFarmingLoading"
                :disabled="materialsLoading"
                @click="configureChipFarming"
                >一键设置芯片 / 采购凭证刷取</n-button
              >
            </n-space>
            <MasteryMaterials
              v-if="planMaterials"
              :summary="planMaterials"
              :missing-skills="missingPlanSkills"
              :show-header="false"
              expand-crafting
            />
            <n-text v-else-if="!materialsError" depth="3">尚未选择养成目标</n-text>
            <n-text v-if="totalGoalCount" depth="3" class="overview-note"
              >已扣除现有库存；同一干员的精英化与基础技能费用只计一次。芯片、龙门币、经验和模组任务需另行准备。</n-text
            >
          </n-collapse-item>
        </n-collapse>
      </n-spin>
    </n-card>

    <n-text
      v-if="store.cultivateMsg"
      :type="store.cultivateOk ? 'success' : 'error'"
      depth="2"
      style="font-size: 12px"
    >
      森空岛同步：{{ store.cultivateMsg }}
    </n-text>

    <n-alert
      v-if="store.yituliuSyncResult"
      :type="store.yituliuSyncResult.success ? 'success' : 'warning'"
      :bordered="false"
      style="margin: 12px 0"
    >
      一图流同步：{{ store.yituliuSyncResult.message }}
    </n-alert>

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
      <n-collapse v-model:expanded-names="expandedOperator" accordion class="operator-cards">
        <n-collapse-item
          v-for="op in displayList"
          :key="op.char_id"
          :name="op.char_id"
          @click="toggleOperatorHeaderSpace(op, $event)"
        >
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
            <n-space :size="4" align="center" class="operator-status">
              <n-tag :bordered="false" size="small">{{ professionName(op.profession) }}</n-tag>
              <n-tag
                :bordered="false"
                size="small"
                :type="surveyFor(op).eliteHighlight ? 'warning' : 'default'"
                >E{{ op.elite }} Lv{{ op.level }}</n-tag
              >
              <n-tooltip v-if="op.max_phase === undefined || op.max_phase >= 1"
                ><template #trigger
                  ><n-tag size="small" :bordered="false"
                    >{{ op.max_phase === 1 ? '精一' : '精二' }}
                    {{
                      formatSurveyRate(
                        op.max_phase === 1 ? surveyFor(op).elite1 : surveyFor(op).elite2
                      )
                    }}</n-tag
                  ></template
                >一图流拥有者{{ op.max_phase === 1 ? '精一' : '精二' }}率；拥有样本
                {{ surveyMap.get(op.char_id)?.own?.toLocaleString() || '暂无' }}</n-tooltip
              >
              <n-tag v-if="hasPlannedGoal(op)" type="success" :bordered="false" size="small"
                >计划中</n-tag
              >
              <n-button
                size="tiny"
                class="all-plan-button"
                type="warning"
                @click.stop="addAllToPlan(op)"
                :disabled="!!op.material_error"
                v-if="op.recommendations.length && !allPlanned(op)"
                >全部技能加入计划</n-button
              >
            </n-space>
          </template>

          <n-alert
            v-if="op.mastery_error && op.recommendations.length"
            type="info"
            :bordered="false"
            class="prerequisite-notice"
          >
            {{ op.mastery_error }}
          </n-alert>
          <n-alert v-if="op.material_error" type="warning">{{ op.material_error }}</n-alert>
          <GrowthLevelPlan
            :operator="op"
            :selected-key="levelGoalFor(op)"
            :required-key="prerequisiteLevelGoal(op, hasPlannedSkill(op), store.goals)"
            :saving="goalSaving"
            :apply-target="(key) => applyLevelTarget(op, key)"
          />
          <n-card
            v-if="op.basic_skill_summary || (op.supports_basic_skill7 && op.max_phase < 2)"
            size="small"
            class="level-card"
            :title="`基础技能 ${op.main_skill_level} → 7 级`"
          >
            <n-checkbox
              v-if="op.supports_basic_skill7"
              :checked="isGoalPlanned(op.char_id, 'skill7') || hasPlannedSkill(op)"
              :disabled="
                goalSaving ||
                hasPlannedSkill(op) ||
                (!op.basic_skill_summary && !isGoalPlanned(op.char_id, 'skill7'))
              "
              @update:checked="(value) => toggleGoal(op, 'skill7', value)"
            >
              {{ op.basic_skill_summary ? '规划至基础技能 7 级' : '基础技能已达 7 级' }}
            </n-checkbox>
            <n-text depth="3" class="overview-note">
              基础技能材料按干员只计算一次，需在游戏中手动升级。
              <template
                v-if="op.basic_skill_prerequisite && op.elite < op.basic_skill_prerequisite.elite"
                >最低前置为{{ eliteLabel(op.basic_skill_prerequisite.elite) }}
                {{ op.basic_skill_prerequisite.level }} 级，材料自动计入。</template
              >
              <template v-if="op.max_phase >= 2"
                >专精计划自动包含此项，升级并同步后才执行专精。</template
              >
            </n-text>
            <MasteryMaterials
              v-if="op.basic_skill_summary"
              :summary="op.basic_skill_summary"
              title="基础技能升级材料"
            />
          </n-card>
          <div v-for="rec in visibleRecs(op)" :key="rec.skill_index" class="rec-item">
            <n-card size="small">
              <template #header>
                <n-space align="center" justify="space-between" style="width: 100%">
                  <n-space align="center" :size="8">
                    <n-text strong>{{ rec.skill_name }}</n-text>
                    <n-tag
                      size="small"
                      :bordered="false"
                      :type="
                        surveyFor(op).skillHighlights.includes(rec.skill_index)
                          ? 'warning'
                          : 'default'
                      "
                      >专三
                      {{
                        formatSurveyRate(
                          surveyFor(op).skills.find((skill) => skill.index === rec.skill_index)
                            ?.rate
                        )
                      }}</n-tag
                    >
                    <n-text depth="3" style="font-size: 12px"
                      >{{ masteryLevelLabel(op.main_skill_level, rec.current_level) }} → 专{{
                        rec.target_level
                      }}</n-text
                    >
                  </n-space>
                  <n-space :size="8" align="center" class="rec-controls">
                    <n-select
                      :value="rec.target_level"
                      :options="targetOptions(rec)"
                      :disabled="isTargetLocked(op, rec) || targetSaving"
                      @update:value="(value) => changeTarget(op, rec, value)"
                      size="small"
                      style="width: 104px"
                      aria-label="目标专精等级"
                    />
                    <n-button
                      size="small"
                      :type="isSkillPlanned(op.char_id, rec.skill_index) ? 'success' : 'default'"
                      @click.stop="toggleSkillPlan(op, rec)"
                      :disabled="
                        !!op.material_error && !isSkillPlanned(op.char_id, rec.skill_index)
                      "
                    >
                      {{ isSkillPlanned(op.char_id, rec.skill_index) ? '移出计划' : '加入计划' }}
                    </n-button>
                    <n-button
                      type="primary"
                      size="small"
                      :disabled="!!op.mastery_error || startingMastery"
                      @click.stop="insertMasteryTask(op, rec)"
                      >一键插入专精任务</n-button
                    >
                    <n-button
                      v-if="planStatus[planKey(op.char_id, rec.skill_index)]?.id"
                      size="small"
                      @click.stop="openSupports(op, rec)"
                      >协助方案</n-button
                    >
                  </n-space>
                </n-space>
              </template>
              <n-space vertical :size="4">
                <n-text depth="2"
                  >总训练时间: {{ formatTime(rec.total_time) }} |
                  {{ rec.remaining_levels }}级专精</n-text
                >
                <MasteryMaterials :summary="rec.skill_material_summary" title="技能专精材料" />
              </n-space>
            </n-card>
          </div>
          <section v-if="op.modules?.length" class="module-section">
            <h3>模组养成 · {{ op.modules.length }}</h3>
            <n-text depth="3"
              >默认规划至满级，可选择目标等级；信赖与解锁任务仍需在游戏中完成。</n-text
            >
            <div v-for="module in visibleModules(op)" :key="module.id" class="module-row">
              <div class="module-heading">
                <n-checkbox
                  :checked="isGoalPlanned(op.char_id, module.id)"
                  :disabled="
                    goalSaving ||
                    (module.current_level >= module.max_level &&
                      !isGoalPlanned(op.char_id, module.id))
                  "
                  @update:checked="(value) => toggleGoal(op, module.id, value)"
                >
                  <n-text strong>{{ module.type }} · {{ module.name }}</n-text>
                </n-checkbox>
                <n-tag
                  size="small"
                  :bordered="false"
                  :type="surveyFor(op).moduleHighlights.includes(module.id) ? 'warning' : 'default'"
                  >解锁
                  {{
                    formatSurveyRate(
                      surveyFor(op).modules.find((item) => item.id === module.id)?.rate
                    )
                  }}</n-tag
                >
                <n-select
                  v-if="module.current_level < module.max_level"
                  :value="moduleTarget(op, module)"
                  :options="moduleTargetOptions(module)"
                  :disabled="goalSaving"
                  style="width: 135px"
                  @update:value="(value) => changeModuleTarget(op, module, value)"
                />
                <n-tag size="small" :type="module.current_level ? 'success' : 'default'">{{
                  module.current_level
                    ? `已开启 · ${module.current_level} 级`
                    : `精${module.elite} ${module.level} 级开启`
                }}</n-tag>
              </div>
              <n-alert v-if="module.material_error" type="warning">{{
                module.material_error
              }}</n-alert>
              <MasteryMaterials
                v-else-if="module.current_level < module.max_level"
                :summary="moduleSummary(op, module).opening_summary"
                title="模组升级材料"
              />
            </div>
          </section>
          <n-text
            v-if="op.rarity >= 4 && !op.recommendations.length && !op.modules?.length"
            depth="3"
            >该干员的技能已全部专三</n-text
          >
        </n-collapse-item>
      </n-collapse>
    </div>

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
      title="我的养成计划"
      style="width: min(760px, 95vw)"
      content-style="max-height: 75vh; overflow-y: auto"
      :mask-closable="false"
      @update:show="onPlanModalShow"
    >
      <n-space vertical :size="16">
        <n-text depth="3"
          >拖动调整专精执行优先级。默认优先合成下一个专精技能的材料，可在「合成顺序」中单独调整；未满足训练条件的计划保留等待。</n-text
        >
        <n-space justify="space-between" align="center">
          <n-input
            v-model:value="planSearch"
            placeholder="查找计划中的干员"
            clearable
            style="width: 220px"
          />
          <n-button :disabled="planEntries.length < 2" @click="interleavePlanEntries"
            >按职业整理顺序</n-button
          >
        </n-space>
        <n-empty v-if="!totalGoalCount" description="还没有养成目标" class="plan-empty">
          <template #extra>
            <n-text depth="3">在干员卡片中选择技能目标或勾选模组，即可加入计划。</n-text>
            <div style="margin-top: 16px">
              <n-button type="primary" @click="browseOperators">去选择干员</n-button>
            </div>
          </template>
        </n-empty>
        <draggable
          v-model="sortablePlanEntries"
          item-key="key"
          handle=".drag-handle"
          :disabled="!!planSearch"
        >
          <template #item="{ element: e, index }">
            <div v-show="matchesSearch(e.name, planSearch)" class="plan-entry">
              <span class="drag-handle" aria-label="拖动排序">⠿</span>
              <span class="plan-position">{{ index + 1 }}</span>
              <n-avatar :src="'/avatar/' + e.name + '.webp'" :size="36" round />
              <div class="plan-entry-description">
                <n-text strong
                  >{{ e.name }} <n-text depth="3">· {{ e.skill_name }}</n-text></n-text
                >
                <n-text depth="3" class="plan-entry-detail"
                  >目标专{{ e.target_level }} ·
                  {{ e.requirement || getStatusLabel(e.status) }}</n-text
                >
              </div>
              <n-button quaternary @click="removePlanEntry(e)">移除</n-button>
            </div>
          </template>
        </draggable>
        <template v-if="growthGoalEntries.length">
          <n-text strong>精英化与模组</n-text>
          <div
            v-for="entry in growthGoalEntries.filter(
              (e) => matchesSearch(e.name, planSearch) && !removedGoals.has(e.key)
            )"
            :key="entry.key"
            class="plan-entry"
          >
            <n-avatar :src="'/avatar/' + entry.name + '.webp'" :size="36" round />
            <div class="plan-entry-description">
              <n-text strong>{{ entry.name }}</n-text
              ><n-text depth="3">{{ entry.label }}</n-text>
            </div>
            <n-button quaternary @click="removedGoals.add(entry.key)">移除</n-button>
          </div>
        </template>
      </n-space>
      <template #footer>
        <n-space justify="space-between" align="center">
          <n-button :disabled="!totalGoalCount" @click="clearAllGoals">清空计划</n-button>
          <n-space
            ><n-button @click="cancelPlanChanges">取消</n-button
            ><n-button type="primary" :loading="planSaving" @click="savePlanFn"
              >保存变更</n-button
            ></n-space
          >
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
          某类名单为空时，仅该类每次降低 5% 下限，直到至少有一位干员；最低降至
          0%，已有干员的名单保持不变。
          材料专属干员仅分配符合条件的缺失材料，相关低阶材料按缺口生成。
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
          <help-text>缺口合成暂不使用需要额外垫刀的九色鹿，请同时选择其他加工干员。</help-text>
        </div>
        <slick-operator-select
          v-model="fodderOps"
          :disabled="workshopDefaultsLoading"
          select_placeholder="选择加工干员"
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
          <n-collapse-item title="九色鹿垫刀素材设置（仅手动合成使用）" name="deer-fodder">
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
import GrowthLevelPlan from '@/components/GrowthLevelPlan.vue'
import GrowthCraftingOrder from '@/components/GrowthCraftingOrder.vue'
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
  NDynamicInput,
  useMessage,
  useThemeVars
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
import { interleaveMasteryPlans } from '@/utils/masteryPlanOrder'
import OperatorStatistics from '@/components/OperatorStatistics.vue'
import GrowthSurveyFilters from '@/components/GrowthSurveyFilters.vue'
import { defaultSurveyFilters, operatorSurvey, formatSurveyRate } from '@/utils/growthSurvey'
const theme = useThemeVars()
import {
  selectedRecommendation,
  goalSelected,
  operatorLevelGoals,
  isGrowthOperatorIdle,
  prerequisiteLevelGoal,
  selectedLevelGoal
} from '@/utils/growthPlanning'

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
  { label: '4★', value: 4 },
  { label: '3★', value: 3 },
  { label: '2★', value: 2 },
  { label: '1★', value: 1 }
]
const professionOptions = profKeys.map((p) => ({ label: p, value: p }))

const expandedOperator = ref([])
function toggleOperatorHeaderSpace(op, event) {
  const item = event.currentTarget
  const header = item.querySelector(':scope > .n-collapse-item__header')
  // Naive UI handles its main and extra regions; cover the remaining header space.
  if (event.target !== header && event.target !== item) return
  const bounds = header.getBoundingClientRect()
  if (event.clientY < bounds.top || event.clientY > bounds.bottom) return
  expandedOperator.value = expandedOperator.value.includes(op.char_id) ? [] : [op.char_id]
}
const statisticsExpanded = ref(false)
const idleFilter = ref('all')
const idleFilterOptions = [
  { label: '空闲状态：不限', value: 'all' },
  { label: '空闲', value: 'idle' },
  { label: '忙碌', value: 'busy' }
]
const searchQuery = ref('')
const filterRarity = ref([])
const filterProfession = ref([])
const targets = ref({})
const targetSaving = ref(false)
const goalSaving = ref(false)
const planSaving = ref(false)
const removedGoals = ref(new Set())
const growthGoalEntries = computed(() =>
  store.goals.map((goal) => {
    const op = store.recommendations.find((op) => op.char_id === goal.char_id)
    const module = op?.modules?.find((module) => module.id === goal.module_id)
    return {
      ...goal,
      key: `${goal.char_id}:${goal.module_id}`,
      name: op?.name || goal.char_id,
      label:
        goal.module_id === 'skill7'
          ? '基础技能 7 级'
          : levelChoices(op || {}).find((choice) => choice.key === goal.module_id)?.label ||
            `${module?.type || ''} · ${module?.name || goal.module_id}（目标 ${goal.target_level || module?.max_level || 1} 级）`
    }
  })
)
const totalGoalCount = computed(() => planEntries.value.length + store.goals.length)
const isGoalPlanned = (cid, mid) => goalSelected(store.goals, cid, mid)
const levelGoalFor = (op) => selectedLevelGoal(op, hasPlannedSkill(op), store.goals)
const eliteLabel = (elite) => ['精零', '精一', '精二'][elite] || `精${elite}`
function levelChoices(op) {
  return operatorLevelGoals(op)
}
async function applyLevelTarget(op, key) {
  if (goalSaving.value) return
  const choice = levelChoices(op).find((entry) => entry.key === key)
  const choices = levelChoices(op).map((entry) => entry.key)
  const required = prerequisiteLevelGoal(op, hasPlannedSkill(op), store.goals)
  if (choices.indexOf(choice?.key) < choices.indexOf(required)) {
    message.info('此等级低于已选养成项目的最低前置；移除对应项目后可降低目标。')
    return
  }
  if (choice && !choice.summary) {
    message.info('该等级已经达成，无需再加入计划。')
    return
  }
  if (choice) await toggleGoal(op, choice.key, true)
  else {
    const existing = store.goals.find(
      (goal) => goal.char_id === op.char_id && choices.includes(goal.module_id)
    )
    if (existing) await toggleGoal(op, existing.module_id, false)
  }
}
const hasPlannedGoal = (op) =>
  hasPlannedSkill(op) || store.goals.some((goal) => goal.char_id === op.char_id)
function matchesSearch(name, search) {
  return (
    !search.trim() ||
    name.toLowerCase().includes(search.trim().toLowerCase()) ||
    !!pinyin_match(name, search.trim())
  )
}
function resetFilters() {
  searchQuery.value = ''
  filterRarity.value = []
  filterProfession.value = []
  idleFilter.value = 'all'
  surveyFilters.value = defaultSurveyFilters()
}
function browseOperators() {
  showPlan.value = false
  resetFilters()
}
function clearAllGoals() {
  clearPlan()
  removedGoals.value = new Set(growthGoalEntries.value.map((e) => e.key))
}
function targetFor(op, rec) {
  return (
    targets.value[planKey(op.char_id, rec.skill_index)] ||
    planStatus.value[planKey(op.char_id, rec.skill_index)]?.target_level ||
    3
  )
}
function targetOptions(rec) {
  return [1, 2, 3]
    .filter((level) => level > rec.current_level)
    .map((value) => ({ value, label: `目标专${value}` }))
}
function isTargetLocked(op, rec) {
  const status = planStatus.value[planKey(op.char_id, rec.skill_index)]?.status
  return status && !['idle', 'failed'].includes(status)
}
async function changeTarget(op, rec, value) {
  const key = planKey(op.char_id, rec.skill_index)
  targetSaving.value = true
  try {
    if (planStatus.value[key]?.id) {
      await axios.patch(`${import.meta.env.VITE_HTTP_URL}/mastery-plan/target`, {
        id: planStatus.value[key].id,
        target_level: value
      })
      await refreshPlanFromServer()
    }
    targets.value[key] = value
  } catch (error) {
    message.error(error.response?.data?.error || '目标保存失败')
  } finally {
    targetSaving.value = false
  }
}
const moduleTargets = ref({})
function moduleTarget(op, module) {
  return (
    store.goals.find((goal) => goal.char_id === op.char_id && goal.module_id === module.id)
      ?.target_level ||
    moduleTargets.value[`${op.char_id}:${module.id}`] ||
    module.max_level ||
    1
  )
}
function moduleTargetOptions(module) {
  return Array.from({ length: module.max_level || 1 }, (_, i) => i + 1)
    .filter((level) => level > module.current_level)
    .map((level) => ({ label: `目标 ${level} 级`, value: level }))
}
function moduleSummary(op, module) {
  return module.targets?.[moduleTarget(op, module)] || module
}
async function changeModuleTarget(op, module, value) {
  if (isGoalPlanned(op.char_id, module.id)) {
    await toggleGoal(op, module.id, true, value)
  } else {
    moduleTargets.value[`${op.char_id}:${module.id}`] = value
  }
}
async function toggleGoal(op, moduleId, selected, targetLevel) {
  goalSaving.value = true
  try {
    const response = await axios.post(`${import.meta.env.VITE_HTTP_URL}/growth-plan`, {
      char_id: op.char_id,
      module_id: moduleId,
      selected,
      target_level:
        targetLevel ||
        moduleTarget(op, op.modules?.find((m) => m.id === moduleId) || { id: moduleId })
    })
    store.goals = response.data.goals
  } catch (error) {
    message.error(error.response?.data?.error || '养成目标保存失败')
  } finally {
    goalSaving.value = false
  }
}
const {
  workshop_min_bonus: workshopMinBonus,
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

const emptyText = computed(() =>
  idleFilter.value === 'idle'
    ? '没有符合当前筛选的空闲干员'
    : idleFilter.value === 'busy'
      ? '没有符合当前筛选的忙碌干员'
      : '没有匹配当前筛选条件的干员'
)

// ─── 计划（技能级别）───
// 格式: { "charId_skillIndex": true, ... }
const plan = ref({})
const planStatus = ref({}) // { "charId_skillIndex": {id, status, target_level, priority, expires_at} }
const showPlan = ref(false)
const planSearch = ref('')
const craftingOrderRevision = computed(() =>
  JSON.stringify({
    skills: Object.entries(planStatus.value).map(([key, entry]) => [
      key,
      entry.id,
      entry.status,
      entry.target_level,
      entry.priority
    ]),
    goals: store.goals,
    cultivate: store.cultivateMsg
  })
)
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

async function warnMaterialShortage(additions) {
  const keys = [
    ...new Set([...Object.keys(plan.value).filter((key) => plan.value[key]), ...additions])
  ]
  try {
    const response = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/mastery-t3-summary`,
      {
        planned_skills: keys,
        goals: store.goals,
        targets: targets.value
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
  if (!plan.value[k] && op.mastery_error) message.info(op.mastery_error)
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
      const body = {
        planning: true,
        items: [{ name: op.name, skill_index: rec.skill_index, target_level: targetFor(op, rec) }]
      }
      const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, body)
      const results = r.data?.results || []
      for (const warning of new Set(results.map((result) => result.warning).filter(Boolean))) {
        message.warning(warning)
      }
      if (results[0]?.status === 'added') {
        plan.value[k] = true
        planStatus.value[k] = {
          id: results[0].id,
          status: 'idle',
          target_level: targetFor(op, rec),
          priority: 0
        }
        await refreshPlanFromServer()
      } else if (results[0]?.status === 'existing') {
        // 已有计划：服务端不再新建重复行，直接复用那条去派发。本地状态可能过期，
        // 重新拉一次服务器计划让按钮/状态收敛。
        plan.value[k] = true
        await refreshPlanFromServer()
        message.success(results[0]?.reason || '已在计划中，已安排立即开始')
      } else if (results[0]?.status === 'insufficient' || results[0]?.status === 'deferred') {
        await refreshPlanFromServer()
        message.warning(results[0]?.reason || '材料不足，暂不开始')
      } else {
        message.warning(results[0]?.reason || '添加失败')
      }
    } catch (e) {
      message.error(`保存失败: ${e.message}`)
    }
  }
}

async function addAllToPlan(op, draft = false) {
  if (op.mastery_error) message.info(op.mastery_error)
  if (trainingWarning(op.name)) {
    message.warning(trainingWarning(op.name))
  }
  const recs = visibleRecs(op)
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
  // 主列表 quick-add：立即写后端。已计划技能在本地就跳过；后端按 (干员, 技能) 拦重复，
  // 万一本地状态过期撞上已有计划，服务端会回 existing 而不是再建一行。
  const toAdd = recs.filter((rec) => !plan.value[planKey(op.char_id, rec.skill_index)])
  if (!toAdd.length) {
    message.info(`${op.name} 所有推荐技能都已在计划中`)
    return
  }
  try {
    const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, {
      planning: true,
      items: toAdd.map((rec) => ({
        name: op.name,
        skill_index: rec.skill_index,
        target_level: targetFor(op, rec)
      }))
    })
    const results = r.data?.results || []
    for (const warning of new Set(results.map((result) => result.warning).filter(Boolean))) {
      message.warning(warning)
    }
    const errs = []
    const infos = []
    results.forEach((res, i) => {
      const rec = toAdd[i]
      if (res.status === 'added' || res.status === 'existing') {
        const k = planKey(op.char_id, rec.skill_index)
        plan.value[k] = true
        planStatus.value[k] = {
          id: res.id,
          status: 'idle',
          target_level: targetFor(op, rec),
          priority: 0
        }
        if (res.status === 'existing') infos.push(res.reason || '已在计划中')
      } else if (res.status === 'insufficient' || res.status === 'deferred') {
        infos.push(`${rec.skill_index + 1}技能：${res.reason || '材料不足，暂不开始'}`)
      } else {
        errs.push(res.reason || '添加失败')
      }
    })
    await refreshPlanFromServer()
    if (errs.length) {
      message.warning(`${op.name} 有 ${errs.length} 项未加入: ${errs.join('；')}`)
    } else if (infos.length) {
      // 材料不足 / 已有计划都明说，别静默当成「全部加入」
      message.info(`${op.name} ${infos.join('；')}`)
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
  if (planSaving.value) return
  planSaving.value = true
  try {
    await persistPlanChanges()
  } catch (error) {
    message.error(error.response?.data?.error || '计划保存失败，请重试')
  } finally {
    planSaving.value = false
  }
}
async function persistPlanChanges() {
  for (const entry of growthGoalEntries.value.filter((e) => removedGoals.value.has(e.key))) {
    const response = await axios.post(`${import.meta.env.VITE_HTTP_URL}/growth-plan`, {
      char_id: entry.char_id,
      module_id: entry.module_id,
      selected: false
    })
    store.goals = response.data.goals
  }
  removedGoals.value.clear()
  const orderedKeys = sortablePlanEntries.value.map((entry) => entry.key)
  const toAdd = []
  for (const [priority, k] of orderedKeys.entries()) {
    if (!plan.value[k]) continue
    if (planStatus.value[k]?.id) continue // 已是后端计划
    const [cid, si] = parsePlanKey(k)
    const op = store.recommendations.find((o) => o.char_id === cid)
    if (op && si !== undefined) {
      toAdd.push({
        name: op.name,
        skill_index: parseInt(si),
        priority,
        target_level: targets.value[k] || 3
      })
    }
  }
  // 草稿中被移除且未重新加回的计划（清空/单删/技能反选）
  const toDel = [...draftRemoved.value].filter((k) => !plan.value[k] && planStatus.value[k]?.id)
  const orderUpdates = orderedKeys
    .map((key, priority) => ({ id: planStatus.value[key]?.id, priority }))
    .filter((u) => u.id)
  if (!toAdd.length && !toDel.length && !orderUpdates.length) {
    message.info('没有变更需要保存')
    showPlan.value = false
    return
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
      return
    }
  }
  if (toAdd.length) {
    // 先保存已有计划的顺序，再添加新计划；服务端立即派发时便能看到完整顺序。
    const r = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan`, {
      items: toAdd,
      planning: true
    })
    const results = r.data?.results || []
    for (const warning of new Set(results.map((result) => result.warning).filter(Boolean))) {
      message.warning(warning)
    }
    const err = results.filter((x) => x.status === 'error')
    if (err.length) {
      message.warning(`保存完成，${err.length} 项失败: ${err.map((x) => x.reason).join('；')}`)
    } else {
      // 材料不足和排班冲突的项都没排上，展示服务端返回的真实原因
      const poor = results.filter((x) => x.status === 'insufficient' || x.status === 'deferred')
      if (poor.length) {
        message.info(`保存完成；${poor.length} 项暂未开始: ${poor.map((x) => x.reason).join('；')}`)
      }
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
  removedGoals.value.clear()
  planSearch.value = ''
  showPlan.value = true
}

function cancelPlanChanges() {
  showPlan.value = false
  onPlanModalShow(false)
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
          profession: op.profession,
          status: info.status || 'idle',
          priority: info.priority || 0,
          failed_reason: info.failed_reason,
          target_level: targetFor(op, rec),
          requirement: op.mastery_error
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
    if (!showPlan.value) {
      sortablePlanEntries.value = [...val]
      return
    }
    // Adding/removing a draft entry must not discard a manual or automatic draft order.
    const byKey = new Map(val.map((entry) => [entry.key, entry]))
    const retained = sortablePlanEntries.value.map((entry) => byKey.get(entry.key)).filter(Boolean)
    const seen = new Set(retained.map((entry) => entry.key))
    const added = val.filter((entry) => !seen.has(entry.key))
    const merged = [...retained, ...added]
    sortablePlanEntries.value = added.length ? interleaveMasteryPlans(merged) : merged
  },
  { immediate: true }
)

function interleavePlanEntries() {
  sortablePlanEntries.value = interleaveMasteryPlans(sortablePlanEntries.value)
}

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
      message.warning(resp.data?.error || '生成失败')
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
        resp.data.restored
          ? '当前可合成材料已备齐，已恢复手动合成配置'
          : '当前缺口没有可执行的合成配方，请查看材料总览与加工干员设置'
      )
      return
    }

    const tasksResp = await axios.get(`${import.meta.env.VITE_HTTP_URL}/task`)
    const tasks = tasksResp.data || []
    const hasTask = (opName) =>
      tasks.some((t) => {
        const tType =
          typeof t.type === 'string' ? t.type : t.type?.display_value || t.type?.value || ''
        return (
          tType === '加工材料' &&
          t.workshop_generation === resp.data.workshop_generation &&
          (t.meta_data === '' || t.meta_data === opName)
        )
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
    if (!added.length && !skipped.length) return
    message.success(
      `已按合成顺序生成当前缺口的合成任务${parts.length ? '，' + parts.join('；') : ''}`
    )
  } catch (e) {
    message.error(`生成失败: ${e.response?.data?.error || e.message}`)
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

// 排班上下文用于加入计划时提示训练冲突。
const supportSchedule = computed(() =>
  masteryScheduleContext(planStore.plan, planStore.backup_plans)
)
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
const routeOperatorSet = computed(
  () =>
    new Set(
      profKeys.flatMap((profession) =>
        (routeSettings[profession]?.supports || [])
          .flatMap((support) => [support.name, support.swap_name])
          .filter(Boolean)
      )
    )
)
const workshopOperators = computed(() => selectedWorkshopOperators(configStore))
function isIdleOperator(op) {
  return isGrowthOperatorIdle(
    op.name,
    supportSchedule.value.scheduled,
    routeOperatorSet.value,
    workshopOperators.value,
    configStore.free_blacklist || []
  )
}
function workshopTrainingWarning(name) {
  return workshopTraineeWarning(name, workshopOperators.value)
}

const surveyFilters = ref(defaultSurveyFilters())
const survey = ref({ operators: [], error: '', fetched_at: null, stale: false })
const surveyLoading = ref(false)
async function loadSurvey() {
  if (surveyLoading.value) return
  surveyLoading.value = true
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/growth-survey`, {
      timeout: 20000
    })
    survey.value = response.data
  } catch (error) {
    survey.value = {
      ...survey.value,
      stale: Boolean(survey.value.operators?.length),
      error: '一图流统计暂时不可用'
    }
  } finally {
    surveyLoading.value = false
  }
}
const surveyMap = computed(
  () => new Map((survey.value.operators || []).map((row) => [row.charId, row]))
)
const operatorSurveys = computed(
  () =>
    new Map(
      store.recommendations.map((op) => [
        op.char_id,
        operatorSurvey(op, surveyMap.value.get(op.char_id), surveyFilters.value)
      ])
    )
)
const surveyFor = (op) => operatorSurveys.value.get(op.char_id)
function visibleRecs(op) {
  return op.recommendations.map((rec) => selectedRecommendation(rec, targetFor(op, rec)))
}
function visibleModules(op) {
  return op.modules || []
}
const displayList = computed(() => {
  const list = store.recommendations.filter(
    (op) =>
      (idleFilter.value === 'all' || (idleFilter.value === 'idle') === isIdleOperator(op)) &&
      matchesSearch(op.name, searchQuery.value) &&
      (!filterRarity.value.length || filterRarity.value.includes(op.rarity)) &&
      (!filterProfession.value.length || filterProfession.value.includes(profMap[op.profession])) &&
      surveyFor(op).visible
  )
  if (surveyFilters.value.sort === 'recommendation')
    list.sort((a, b) => surveyFor(b).score - surveyFor(a).score)
  if (surveyFilters.value.sort === 'level')
    list.sort((a, b) => b.elite - a.elite || b.level - a.level)
  return list
})

const planMaterials = ref(null)
const chipFarmingLoading = ref(false)
const hasChipShortage = computed(() =>
  planMaterials.value?.missing?.some(
    (row) => (/^32[1-8][12]$/.test(row.id) || row.id === '4006') && row.count > 0
  )
)
async function configureChipFarming() {
  chipFarmingLoading.value = true
  try {
    await configStore.flush_config_saves()
    const response = await axios.post(`${import.meta.env.VITE_HTTP_URL}/growth-chip-farming`)
    await configStore.load_config()
    const stages = response.data.stages || []
    message.success(
      stages.length
        ? `已开启「${response.data.active}」的库存刷关并加入 ${stages.join('、')}；芯片仍需手动合成。`
        : '当前芯片与采购凭证库存已满足需求'
    )
  } catch (error) {
    message.error(error.response?.data?.error || '芯片刷取设置失败')
  } finally {
    chipFarmingLoading.value = false
  }
}
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
  if (!keys.length && !store.goals.length) {
    planMaterials.value = null
    materialsLoading.value = false
    return
  }
  materialsLoading.value = true
  materialsError.value = ''
  try {
    const response = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-t3-summary`, {
      planned_skills: keys,
      goals: store.goals,
      targets: targets.value
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
  [plan, planStatus, targets, () => store.goals, () => store.recommendations],
  () => {
    ++materialRequest
    clearTimeout(materialTimer)
    materialsLoading.value = totalGoalCount.value > 0
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

// ─── 插入已确认材料的专精任务 ───
const startingMastery = ref(false)

async function insertMasteryTask(op, rec) {
  if (startingMastery.value) return
  if (op.mastery_error) {
    message.warning(op.mastery_error)
    return
  }
  startingMastery.value = true
  try {
    const { data } = await axios.post(`${import.meta.env.VITE_HTTP_URL}/mastery-plan/start`, {
      char_id: op.char_id,
      skill_index: rec.skill_index,
      target_level: rec.target_level
    })
    if (data.warning) message.warning(data.warning)
    if (data.status === 'inserted' || data.status === 'queued') {
      message.success(data.reason)
    } else {
      message.warning(data.reason || '任务未插入，请刷新后重试')
    }
    await refreshPlanFromServer()
  } catch (error) {
    message.error(error.response?.data?.reason || `插入失败: ${error.message}`)
  } finally {
    startingMastery.value = false
  }
}

// ─── 初始化 ───
onMounted(async () => {
  await refreshPlanFromServer()
  await Promise.all([loadOperators(), store.fetchRecommendations(), loadSurvey()])
  // 载入专精路线；打开设置时刷新拥有情况和解锁技能。
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
.statistics-panel {
  margin: 18px 0;
}
.rec-controls :deep(.n-button),
.rec-controls :deep(.n-base-selection) {
  height: 28px;
  --n-height: 28px !important;
}
.operator-status :deep(.n-tag),
.operator-status :deep(.n-button) {
  height: 22px;
  --n-height: 22px !important;
}
.operator-status :deep(.all-plan-button) {
  padding: 0 8px;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.page-title {
  margin: 0 0 4px;
  font-size: 26px;
  font-weight: 650;
  letter-spacing: -0.5px;
}
.mastery-list {
  width: 100%;
  max-width: 1280px;
  /* Short filtered lists can still scroll past the filters into the viewport. */
  min-height: calc(100dvh - 128px);
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
.growth-page {
  max-width: 1440px;
  margin: 0 auto;
  -webkit-font-smoothing: antialiased;
  font-variant-numeric: tabular-nums;
}
.page-subtitle {
  font-size: 13px;
}
.mastery-global-switch {
  padding: 16px 0;
  flex-wrap: wrap;
}
.filter-summary {
  margin: 16px 0;
}
.materials-overview {
  margin: 16px 0 24px;
  border-radius: 14px;
}
.overview-note {
  display: block;
  font-size: 12px;
  margin-top: 14px;
}
.mastery-list :deep(.operator-cards) {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 560px), 1fr));
  align-items: start;
  gap: 8px;
}
.mastery-list :deep(.operator-cards > .n-collapse-item) {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
  margin: 0;
  padding: 0 10px;
  border: none;
  border-radius: 8px;
  background: var(--mower-control-surface, var(--n-color));
}
.mastery-list :deep(.operator-cards > .n-collapse-item--active) {
  grid-column: 1 / -1;
  max-width: 880px;
  padding-bottom: 10px;
}
.mastery-list :deep(.operator-cards > .n-collapse-item > .n-collapse-item__header) {
  padding: 6px 0;
  gap: 12px;
  flex-wrap: wrap;
  cursor: pointer;
}
.mastery-list
  :deep(
    .operator-cards > .n-collapse-item > .n-collapse-item__header > .n-collapse-item__header-main
  ) {
  flex: none;
}
.mastery-list
  :deep(
    .operator-cards > .n-collapse-item > .n-collapse-item__header > .n-collapse-item__header-extra
  ) {
  margin-left: auto;
  min-width: 0;
  max-width: 100%;
}
.prerequisite-notice {
  margin-bottom: 16px;
}
.level-card {
  margin: 16px 0;
  border-radius: 12px;
}
.promotion-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
  margin: 14px 0;
}
.promotion-row > :last-child {
  font-size: 12px;
}
.rec-item {
  margin: 14px 0;
}
.rec-item :deep(.n-card) {
  border-radius: 12px;
}
.module-section {
  margin-top: 18px;
}
.module-row {
  padding: 18px 0;
}
.module-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}
.plan-empty {
  padding: 28px 0;
  text-align: center;
}
.plan-entry {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 14px 6px;
  border-radius: 10px;
}
.plan-entry-description {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}
.plan-entry-detail {
  font-size: 12px;
}
.plan-position {
  opacity: 0.55;
  min-width: 18px;
  font-size: 12px;
}
.drag-handle {
  cursor: grab;
  font-size: 22px;
  opacity: 0.5;
  padding: 8px;
  touch-action: none;
}
.growth-page :deep(.n-checkbox) {
  padding-block: 8px;
}
@media (max-width: 650px) {
  .page-header {
    align-items: flex-start;
    gap: 18px;
  }
  .plan-entry {
    gap: 8px;
  }
  .page-title {
    font-size: 23px;
  }
  .growth-page :deep(.n-collapse-item__header-main) {
    flex-wrap: wrap;
    gap: 10px;
  }
}
</style>
