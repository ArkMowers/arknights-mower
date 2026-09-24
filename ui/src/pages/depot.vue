<template>
  <div class="depot-page">
    <!-- ① 顶部总览看板 -->
    <n-card class="depot-hero" :bordered="false">
      <!-- 头部：标题、状态与快捷操作 -->
      <div class="hero-top-bar">
        <div class="hero-title-group">
          <div class="hero-title">
            <n-icon size="22" :color="'var(--mower-primary)'">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 8.5 12 4l9 4.5-9 4.5-9-4.5Z" stroke-linejoin="round" />
                <path d="M3 8.5V16l9 4.5 9-4.5V8.5" stroke-linejoin="round" />
                <path d="M12 13v7.5" />
              </svg>
            </n-icon>
            <span>仓库总览</span>
          </div>
          <n-tag v-if="parsed.ok" size="small" :bordered="false" round class="hero-count-tag">
            已登记 {{ allItems.length }} 种物品
          </n-tag>
        </div>

        <div class="hero-actions">
          <n-button size="small" secondary :loading="loading" @click="reload">
            <template #icon>
              <n-icon>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M20 11a8 8 0 1 0-.7 3.3" stroke-linecap="round" />
                  <path d="M20 5v6h-6" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </n-icon>
            </template>
            刷新数据
          </n-button>
          <n-dropdown
            v-if="hasActiveFilters"
            :options="exportImageOptions"
            placement="bottom-end"
            trigger="click"
            @select="handleExportSelect"
          >
            <n-button
              size="small"
              secondary
              :loading="exportingImage"
              :disabled="!parsed.ok || exportingImage"
            >
              <template #icon>
                <n-icon>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
                    <circle cx="9" cy="9" r="2" />
                    <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
                  </svg>
                </n-icon>
              </template>
              导出图片 ▾
            </n-button>
          </n-dropdown>
          <n-button
            v-else
            size="small"
            secondary
            :loading="exportingImage"
            :disabled="!parsed.ok || exportingImage"
            @click="exportDepotImage('all')"
          >
            <template #icon>
              <n-icon>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
                  <circle cx="9" cy="9" r="2" />
                  <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
                </svg>
              </n-icon>
            </template>
            导出图片
          </n-button>
          <n-button size="small" type="primary" :disabled="!copyText" @click="copyToClipboard">
            复制工具箱代码
          </n-button>
          <n-tooltip trigger="hover">
            <template #trigger>
              <n-button
                size="small"
                quaternary
                tag="a"
                href="https://arkntools.app/#/material"
                target="_blank"
                rel="noreferrer"
              >
                工具箱 ↗
              </n-button>
            </template>
            在新标签页打开明日方舟工具箱的素材页，粘贴代码即可直接对比仓库库存
          </n-tooltip>
        </div>
      </div>

      <!-- 核心看板主体：左右分栏 -->
      <div class="hero-grid">
        <!-- 左侧：寻访抽数多档位折算 -->
        <div class="hero-panel hero-draws-panel">
          <div class="panel-header">
            <span class="panel-title">
              折合寻访抽数
              <help-text label="抽数换算口径说明">
                <p><b>换算规则（逐级折算）：</b></p>
                <p>1. <b>基础 (玉+券)</b>：合成玉 ÷ 600 + 寻访凭证（单抽 + 十连×10）</p>
                <p>2. <b>+ 至纯源石</b>：在基础之上，按 1 至纯源石 = 180 合成玉（0.3 抽）并入</p>
                <p>3. <b>+ 源石碎片</b>：在上述基础之上，按 2 碎片 = 1 源石（20玉/片）并入</p>
                <p>4. <b>+ 固源岩</b>：在上述基础之上，按 2 固源岩合成 1 碎片折算并入</p>
                <p class="status-dim">注：抽数为计算折算值，不计入实体物料。</p>
              </help-text>
            </span>
            <n-tag
              v-if="drawDeltaText"
              size="small"
              :type="drawDeltaType"
              round
              class="draw-delta-tag"
            >
              {{ drawDeltaText }}
            </n-tag>
          </div>

          <div class="draw-hero-value">
            <span class="draw-number">
              {{ activeDrawTier ? formatNumber(activeDrawTier.value) : '—' }}
            </span>
            <span class="draw-unit">抽</span>
          </div>

          <div class="draw-tiers-selector" v-if="highlights.draws.length">
            <button
              v-for="tier in highlights.draws"
              :key="tier.key"
              type="button"
              class="draw-tier-pill"
              :class="{ active: tier.key === activeDrawKey }"
              @click="activeDrawKey = tier.key"
              :title="tier.detail || tier.label"
            >
              <span class="draw-tier-name">{{ tier.name || tier.key }}</span>
              <span class="draw-tier-val">{{ formatCompact(tier.value) }} 抽</span>
            </button>
          </div>

          <div class="draw-tier-hint">
            <span class="hint-prefix">当前口径：</span>
            <span>{{ activeDrawTier?.detail || activeDrawTier?.hint || '暂无数据' }}</span>
          </div>
        </div>

        <!-- 右侧：重点资源 / 关注物资存量看板 -->
        <div class="hero-panel hero-assets-panel">
          <div class="panel-header assets-header">
            <!-- 切换标签：核心物资 vs 我的关注 -->
            <div class="showcase-tabs">
              <button
                type="button"
                class="showcase-tab-btn"
                :class="{ active: showcaseTab === 'core' }"
                @click="showcaseTab = 'core'"
              >
                <span>核心物资</span>
              </button>
              <button
                type="button"
                class="showcase-tab-btn"
                :class="{ active: showcaseTab === 'favorites' }"
                @click="showcaseTab = 'favorites'"
              >
                <span>我的关注</span>
              </button>
            </div>

            <!-- 右侧操作 / 分页 -->
            <div class="showcase-controls">
              <template v-if="showcaseTab === 'core'">
                <span class="panel-subtitle">最近存量及基准差额</span>
              </template>
              <template v-else>
                <!-- 关注物品有超过1页时提供翻页 -->
                <div v-if="totalFavPages > 1" class="fav-pager">
                  <button type="button" class="pager-arrow" title="上一页" @click="prevFavPage">
                    ‹
                  </button>
                  <span class="pager-indicator">{{ favPage + 1 }} / {{ totalFavPages }}</span>
                  <button type="button" class="pager-arrow" title="下一页" @click="nextFavPage">
                    ›
                  </button>
                </div>
                <span v-else-if="favoriteHighlights.length" class="panel-subtitle">
                  已关注 {{ favoriteHighlights.length }} 项物资
                </span>
              </template>
            </div>
          </div>

          <!-- Tab 1: 核心资产栅格 -->
          <div v-if="showcaseTab === 'core'" class="assets-grid">
            <div
              v-for="currency in highlights.currencies"
              :key="currency.name"
              class="asset-card"
              @click="openDetailByName(currency.name)"
            >
              <img
                class="asset-icon"
                :src="itemIconUrl(currency.icon)"
                :alt="currency.name"
                loading="lazy"
                @error="handleImageError"
              />
              <div class="asset-info">
                <div class="asset-top-row">
                  <span class="asset-name" :title="currency.name">{{ currency.name }}</span>
                  <span
                    v-if="deltaTextFor(currency.name)"
                    class="asset-delta"
                    :class="deltaClassFor(currency.name)"
                  >
                    {{ deltaTextFor(currency.name) }}
                  </span>
                </div>
                <div class="asset-number">{{ currency.compact }}</div>
              </div>
            </div>

            <!-- 全部经验折算卡片 -->
            <div
              v-if="highlights.exp"
              class="asset-card asset-card-exp"
              @click="openDetailByName('全部经验（计算）')"
            >
              <img
                class="asset-icon"
                :src="itemIconUrl(highlights.exp.icon)"
                alt="全部经验"
                loading="lazy"
                @error="handleImageError"
              />
              <div class="asset-info">
                <div class="asset-top-row">
                  <span class="asset-name">全部经验（折算）</span>
                </div>
                <div class="asset-number">{{ highlights.exp.compact }}</div>
              </div>
            </div>
          </div>

          <!-- Tab 2: 我的关注栅格 -->
          <div v-else class="favorites-showcase-wrap">
            <!-- 暂无关注空状态 -->
            <div v-if="!favoriteHighlights.length" class="favorites-empty-box">
              <div class="fav-empty-icon">
                <svg
                  viewBox="0 0 24 24"
                  class="star-empty-svg"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.6"
                >
                  <polygon :points="STAR_POLYGON" />
                </svg>
              </div>
              <div class="fav-empty-text">
                <div class="fav-empty-title">暂未添加关注物品</div>
                <div class="fav-empty-sub">
                  点击下方物品卡片右上角的星标或在详情页中关注，即可在此快速跟踪库存变动
                </div>
              </div>
            </div>

            <!-- 关注物品卡片列表 -->
            <div v-else class="assets-grid">
              <div
                v-for="item in currentFavPageItems"
                :key="item.name"
                class="asset-card fav-asset-card"
                @click="openDetail(item)"
              >
                <img
                  class="asset-icon"
                  :src="itemIconUrl(item.icon)"
                  :alt="item.name"
                  loading="lazy"
                  @error="handleImageError"
                />
                <div class="asset-info">
                  <div class="asset-top-row">
                    <span class="asset-name" :title="item.name">{{ item.name }}</span>
                    <span
                      v-if="deltaTextFor(item.name)"
                      class="asset-delta"
                      :class="deltaClassFor(item.name)"
                    >
                      {{ deltaTextFor(item.name) }}
                    </span>
                  </div>
                  <div class="asset-number">{{ item.compact }}</div>
                </div>
                <button
                  type="button"
                  class="fav-unstar-btn"
                  title="取消关注"
                  @click.stop="toggleFavorite(item.name)"
                >
                  <svg viewBox="0 0 24 24" class="star-mini-svg" fill="currentColor">
                    <polygon :points="STAR_POLYGON" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部状态条：扫描时间、快照状态与森空岛 -->
      <div class="hero-status-footer">
        <div class="status-items">
          <div class="status-item">
            <span class="status-dot" :class="freshness.class" />
            <span class="status-label">最近扫描：</span>
            <span class="status-val">{{ parsed.scannedAt || '尚未开始过扫描' }}</span>
            <span v-if="freshness.relative" class="status-dim">（{{ freshness.relative }}）</span>
          </div>

          <div class="status-divider">/</div>

          <div class="status-item">
            <span class="status-label">扫描历史快照：</span>
            <span class="status-val"
              ><b>{{ history.length }}</b> 次</span
            >
            <help-text label="关于历史快照与环比">
              <p>数据源自 <code>@app/tmp/depotresult.csv</code>，每次扫描均记录全量快照。</p>
              <p>可在工具栏自定义对比两个时间点，全页变动徽标与增减筛选将自动按所选区间计算。</p>
              <p v-if="historyError" class="status-dim">历史读取提示：{{ historyError }}</p>
              <p v-else-if="history.length < 2" class="status-dim">
                当前不足 2 次有效扫描，暂不显示假环比。
              </p>
            </help-text>
          </div>

          <template v-if="history.length >= 2">
            <div class="status-divider">/</div>
            <div class="status-item">
              <span class="status-label">对比区间：</span>
              <span class="status-val status-baseline-val">{{ activeBaselineSummary }}</span>
            </div>
          </template>

          <template v-if="parsed.cultivateMsg">
            <div class="status-divider">/</div>
            <div class="status-item">
              <span class="status-label">森空岛同步：</span>
              <span class="status-val" :class="parsed.cultivateOk ? 'status-ok' : 'status-dim'">
                {{ parsed.cultivateMsg }}
              </span>
            </div>
          </template>
        </div>

        <n-tag v-if="staleWarning" size="small" type="warning" round class="stale-warning-tag">
          {{ staleWarning }}
        </n-tag>
      </div>
    </n-card>

    <!-- 读取错误提示 -->
    <n-alert v-if="reportError" type="error" class="depot-error-alert" :show-icon="true">
      {{ reportError }}
      <template #action>
        <n-button size="tiny" @click="reload">重试读取</n-button>
      </template>
    </n-alert>

    <!-- ② 搜索、筛选与分类导航（吸顶固定） -->
    <div class="depot-sticky-bar">
      <div class="depot-toolbar">
        <!-- 第一行：搜索栏 + 对比区间 (桌面端) + 筛选开关 (移动端) + 统计计数 -->
        <div class="toolbar-primary-row">
          <div class="toolbar-search-wrap">
            <n-input
              v-model:value="query"
              clearable
              placeholder="搜索名称、拼音首字母 (如 lmb) 或数量 (如 <50, >=100)"
              class="toolbar-search-input"
            >
              <template #prefix>
                <n-icon :color="'var(--mower-segment-muted)'">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="7" />
                    <path d="m20 20-3.5-3.5" stroke-linecap="round" />
                  </svg>
                </n-icon>
              </template>
            </n-input>
          </div>

          <!-- 桌面端对比区间选择器 -->
          <div class="toolbar-baseline-wrap desktop-only" v-if="history.length >= 2">
            <span class="control-label">对比：</span>
            <depot-baseline-picker v-model="baselineConfig" :history="history" />
          </div>

          <!-- 移动端筛选展开/折叠按钮 -->
          <div class="mobile-filter-btn-wrap mobile-only">
            <n-button
              size="small"
              :type="activeFilterCount > 0 ? 'primary' : 'default'"
              :secondary="activeFilterCount === 0"
              class="mobile-filter-toggle-btn"
              @click="mobileFilterOpen = !mobileFilterOpen"
            >
              <template #icon>
                <n-icon>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
                  </svg>
                </n-icon>
              </template>
              <span>筛选</span>
              <span v-if="activeFilterCount > 0" class="mobile-filter-count-badge">
                {{ activeFilterCount }}
              </span>
              <span class="toggle-arrow">{{ mobileFilterOpen ? '▲' : '▼' }}</span>
            </n-button>
          </div>

          <div class="toolbar-stat-tag">
            显示 <b>{{ sortedItems.length }}</b> / 共 {{ allItems.length }} 项
          </div>
        </div>

        <!-- 第二行：库存状态 + 增减变动 + 折算物 + 排序 + 重置 (桌面常驻，移动端点击筛选展开) -->
        <div class="toolbar-secondary-row" :class="{ 'mobile-filters-open': mobileFilterOpen }">
          <!-- 移动端对比区间选择器（置于展开筛选区内） -->
          <div class="toolbar-baseline-wrap mobile-only" v-if="history.length >= 2">
            <span class="control-label">对比：</span>
            <depot-baseline-picker v-model="baselineConfig" :history="history" />
          </div>

          <!-- 库存状态单选 -->
          <div class="filter-group">
            <span class="control-label">库存：</span>
            <n-radio-group v-model:value="stockFilter" size="small" name="stockFilter">
              <n-radio-button value="all">全部</n-radio-button>
              <n-radio-button value="favorite">我的关注</n-radio-button>
              <n-radio-button value="owned">有货</n-radio-button>
              <n-radio-button value="empty">缺货</n-radio-button>
            </n-radio-group>
          </div>

          <!-- 增减变动单选 -->
          <div class="filter-group" v-if="history.length >= 2">
            <span class="control-label">变动：</span>
            <n-radio-group v-model:value="deltaFilter" size="small" name="deltaFilter">
              <n-radio-button value="all">全部</n-radio-button>
              <n-radio-button value="increased">仅增加</n-radio-button>
              <n-radio-button value="decreased">仅减少</n-radio-button>
              <n-radio-button value="changed">有变动</n-radio-button>
            </n-radio-group>
          </div>

          <n-checkbox v-model:checked="showDerived" class="toolbar-checkbox"> 含折算物 </n-checkbox>

          <div class="sort-selector-wrap">
            <span class="control-label">排序：</span>
            <n-select
              v-model:value="sortMode"
              :options="SORT_MODES"
              size="small"
              class="toolbar-sort-select"
            />
          </div>

          <n-button
            v-if="hasActiveFilters"
            size="tiny"
            quaternary
            type="warning"
            class="reset-filter-btn"
            @click="resetFilters"
          >
            重置筛选
          </n-button>
        </div>

        <!-- 第三行：移动端分类水平滚动导览 (移动端吸顶常驻) -->
        <div class="mobile-category-rail mobile-only" v-if="presentTiers.length">
          <div ref="mobileRailRef" class="rail-items-container">
            <button
              v-for="tier in presentTiers"
              :key="tier.key"
              :data-key="tier.key"
              type="button"
              class="rail-nav-btn"
              :class="{ active: tier.key === activeTier }"
              @click="scrollToTier(tier.key)"
            >
              <span class="rail-badge" :style="{ background: tier.color }">
                {{ tier.badge || tier.short || tier.key }}
              </span>
              <span class="rail-label" :title="tier.name">{{ tier.name }}</span>
              <span class="rail-counts">
                <span class="count-owned">{{ tier.owned }}</span>
                <span class="count-slash">/</span>
                <span class="count-total">{{ tier.total }}</span>
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ③ 主体布局：左侧档位分类导览 (桌面端) + 右侧物品卡片栅格 -->
    <div class="depot-content-body">
      <!-- 桌面端档位导航侧边栏 -->
      <aside class="depot-nav-rail desktop-only">
        <div class="rail-header">分类导航</div>
        <div class="rail-items-container">
          <button
            v-for="tier in presentTiers"
            :key="tier.key"
            type="button"
            class="rail-nav-btn"
            :class="{ active: tier.key === activeTier }"
            @click="scrollToTier(tier.key)"
          >
            <span class="rail-badge" :style="{ background: tier.color }">
              {{ tier.badge || tier.short || tier.key }}
            </span>
            <span class="rail-label" :title="tier.name">{{ tier.name }}</span>
            <span class="rail-counts">
              <span class="count-owned">{{ tier.owned }}</span>
              <span class="count-slash">/</span>
              <span class="count-total">{{ tier.total }}</span>
            </span>
          </button>
        </div>
        <div class="rail-empty-tip" v-if="!presentTiers.length">无匹配分类</div>
      </aside>

      <!-- 物品卡片展示区 -->
      <main class="depot-items-area">
        <!-- 空状态与加载状态 -->
        <n-empty
          v-if="loading && !reportLoaded"
          description="正在读取仓库数据…"
          class="area-empty-state"
        />
        <n-empty
          v-else-if="!parsed.ok"
          description="尚未检测到仓库扫描数据，请先让 Mower 在游戏内执行一次仓库扫描"
          class="area-empty-state"
        >
          <template #extra>
            <n-button size="small" type="primary" @click="reload">重新读取</n-button>
          </template>
        </n-empty>
        <n-empty
          v-else-if="!sortedItems.length"
          description="没有找到符合当前搜索与筛选条件的物品"
          class="area-empty-state"
        >
          <template #extra>
            <n-button size="small" secondary @click="resetFilters">重置筛选</n-button>
          </template>
        </n-empty>

        <!-- 物品分组列表 -->
        <div v-else class="tier-groups-list">
          <section
            v-for="group in groupedItems"
            :key="group.key"
            :ref="(el) => registerSection(group.key, el)"
            class="tier-group-section"
          >
            <div class="tier-group-header">
              <div class="tier-group-title">
                <span class="tier-pill-badge" :style="{ background: group.color }">
                  {{ group.badge || group.short || group.key }}
                </span>
                <span class="tier-group-heading">{{ group.name }}</span>
              </div>
              <div class="tier-group-meta-info">
                <span
                  >当前显示 <b>{{ group.shown }}</b> 项</span
                >
                <span class="meta-dot">·</span>
                <span>该类共 {{ group.total }} 种</span>
                <template v-if="group.shown !== group.total">
                  <span class="filtered-hint">（已按条件筛选）</span>
                </template>
              </div>
            </div>

            <div class="items-card-grid">
              <article
                v-for="row in group.rows"
                :key="row.name"
                class="inventory-card"
                :class="{
                  'is-derived': row.derived,
                  'is-empty': !(row.number > 0)
                }"
                tabindex="0"
                @click="openDetail(row)"
                @keydown.enter.prevent="openDetail(row)"
                @keydown.space.prevent="openDetail(row)"
              >
                <!-- 物品图标 -->
                <div class="card-icon-box">
                  <img
                    class="card-avatar"
                    :src="itemIconUrl(row.icon)"
                    :alt="row.name"
                    loading="lazy"
                    @error="handleImageError"
                  />
                  <span class="card-avatar-fallback">{{ row.name.slice(0, 1) }}</span>
                </div>

                <!-- 物品信息（分行排布，防止增量标签与长数字重叠溢出） -->
                <div class="card-details">
                  <div class="card-title-row">
                    <span class="card-item-name" :title="row.name">{{ row.name }}</span>
                    <span
                      v-if="deltaTextFor(row.name)"
                      class="card-delta-tag"
                      :class="deltaClassFor(row.name)"
                    >
                      {{ deltaTextFor(row.name) }}
                    </span>
                    <n-tag
                      v-if="row.derived"
                      size="tiny"
                      :bordered="false"
                      class="card-derived-tag"
                    >
                      折算
                    </n-tag>
                  </div>

                  <div class="card-stock-row">
                    <span class="card-stock-number" :class="{ 'zero-stock': !(row.number > 0) }">
                      {{ formatNumber(row.number) }}
                    </span>
                  </div>
                </div>

                <!-- 关注星标按钮 -->
                <button
                  type="button"
                  class="card-star-btn"
                  :class="{ starred: isFavorite(row.name) }"
                  :title="isFavorite(row.name) ? '取消关注' : '添加关注'"
                  @click.stop="toggleFavorite(row.name)"
                >
                  <svg viewBox="0 0 24 24" class="star-svg" fill="currentColor">
                    <polygon :points="STAR_POLYGON" />
                  </svg>
                </button>

                <!-- 历史微缩趋势线 -->
                <svg
                  v-if="sparklines[row.name]"
                  class="card-sparkline-svg"
                  viewBox="0 0 88 24"
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  <polyline :points="sparklines[row.name]" :stroke="row.color" />
                </svg>
              </article>
            </div>
          </section>
        </div>
      </main>
    </div>

    <!-- ④ 单品历史趋势与详情抽屉 -->
    <n-drawer
      v-model:show="detailOpen"
      :placement="drawerPlacement"
      :width="drawerPlacement === 'right' ? drawerWidth : undefined"
      :height="drawerPlacement === 'bottom' ? drawerHeight : undefined"
      class="depot-detail-drawer"
    >
      <n-drawer-content v-if="detailItem" closable :title="detailItem.name">
        <div class="detail-hero-box">
          <div class="detail-hero-icon-box">
            <img
              class="detail-hero-avatar"
              :src="itemIconUrl(detailItem.icon)"
              :alt="detailItem.name"
              @error="handleImageError"
            />
          </div>
          <div class="detail-hero-meta">
            <div class="detail-title-row">
              <span class="detail-item-title">{{ detailItem.name }}</span>
              <n-tag
                size="small"
                :bordered="false"
                :style="{ background: detailItem.color, color: '#fff' }"
              >
                {{ detailItem.tierName }}
              </n-tag>
              <n-tag v-if="detailItem.derived" size="small" type="info" :bordered="false">
                计算派生值
              </n-tag>
              <n-button
                size="tiny"
                round
                :type="isFavorite(detailItem.name) ? 'warning' : 'default'"
                :secondary="!isFavorite(detailItem.name)"
                class="detail-fav-btn"
                @click="toggleFavorite(detailItem.name)"
              >
                <template #icon>
                  <svg
                    viewBox="0 0 24 24"
                    class="star-btn-icon"
                    :fill="isFavorite(detailItem.name) ? 'currentColor' : 'none'"
                    stroke="currentColor"
                    stroke-width="1.8"
                  >
                    <polygon :points="STAR_POLYGON" />
                  </svg>
                </template>
                {{ isFavorite(detailItem.name) ? '我的关注' : '添加关注' }}
              </n-button>
            </div>
            <div class="detail-stock-line">
              <span class="detail-stock-label">当前库存</span>
              <span class="detail-stock-count">{{ formatNumber(detailItem.number) }}</span>
            </div>
          </div>
        </div>

        <n-alert
          v-if="detailItem.derived"
          type="info"
          class="detail-derived-alert"
          :bordered="false"
        >
          此项目属于聚合计算派生值（非游戏内独立实体道具），无独立扫描记录。您可在其基础组成材料（如合成玉、寻访凭证等）中查看各自的真实库存历史走势。
        </n-alert>

        <template v-if="detailPoints.length >= 2">
          <div class="detail-kpi-grid">
            <div class="kpi-card">
              <span class="kpi-label">历史累计变动</span>
              <span
                class="kpi-val"
                :class="
                  detailSummary.change > 0 ? 'kpi-up' : detailSummary.change < 0 ? 'kpi-down' : ''
                "
              >
                {{ formatDelta(detailSummary.change) || '无变化 (±0)' }}
              </span>
              <span class="kpi-sub">较统计起始</span>
            </div>
            <div class="kpi-card">
              <span class="kpi-label">初始记录存量</span>
              <span class="kpi-val">{{ formatNumber(detailSummary.first) }}</span>
              <span class="kpi-sub">首次扫描</span>
            </div>
            <div class="kpi-card">
              <span class="kpi-label">历史扫描记录</span>
              <span class="kpi-val">{{ detailSummary.points }} 次</span>
              <span class="kpi-sub">有效数据点</span>
            </div>
          </div>

          <div class="detail-chart-wrapper">
            <v-chart class="detail-echarts" :option="detailChartOption" autoresize />
          </div>

          <div class="detail-timespan-label">
            统计时间跨度：{{ formatTimestamp(detailPoints[0].at) }} 至
            {{ formatTimestamp(detailPoints.at(-1).at) }}
          </div>
        </template>
        <n-empty
          v-else
          class="detail-empty-view"
          :description="
            detailItem.derived
              ? '计算值不记录独立历史走势'
              : '该物品的历史快照记录少于 2 次，暂无法生成趋势曲线'
          "
        />

        <template #footer>
          <n-space justify="space-between" style="width: 100%">
            <n-button size="small" secondary @click="copyName(detailItem.name)">
              复制物品名称
            </n-button>
            <n-button size="small" @click="detailOpen = false"> 关闭 </n-button>
          </n-space>
        </template>
      </n-drawer-content>
    </n-drawer>

    <!-- ⑤ 离屏导出图片专用模板（置于 0 高度容器中，对页面背景完全不可见） -->
    <div v-if="exportingImage" class="export-offscreen-wrapper" aria-hidden="true">
      <div
        ref="exportContainer"
        class="depot-export-view"
        :class="{ 'theme-dark': theme === 'dark', 'theme-light': theme !== 'dark' }"
      >
        <!-- 头部：标题与基础元信息 -->
        <div class="export-header-box">
          <div class="export-header-left">
            <div class="export-app-title">
              <svg
                class="export-logo-icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M3 8.5 12 4l9 4.5-9 4.5-9-4.5Z" stroke-linejoin="round" />
                <path d="M3 8.5V16l9 4.5 9-4.5V8.5" stroke-linejoin="round" />
                <path d="M12 13v7.5" />
              </svg>
              <span class="export-title-text">明日方舟 · 仓库库存清单</span>
            </div>
            <div class="export-scope-desc">
              <span class="export-badge-scope">
                {{ exportScope === 'filtered' ? '当前筛选视图' : '全量物资清单' }}
              </span>
              <span class="export-meta-text">共 {{ exportItemsList.length }} 项物品</span>
            </div>
          </div>
          <div class="export-header-right">
            <div class="export-meta-line">
              <span class="export-meta-lbl">数据扫描：</span>
              <span class="export-meta-val">{{ parsed.scannedAt || '未记录' }}</span>
            </div>
            <div class="export-meta-line">
              <span class="export-meta-lbl">导出时间：</span>
              <span class="export-meta-val">{{ currentExportTime }}</span>
            </div>
            <div v-if="history.length >= 2" class="export-meta-line">
              <span class="export-meta-lbl">对比区间：</span>
              <span class="export-meta-val">{{ activeBaselineSummary }}</span>
            </div>
          </div>
        </div>

        <!-- 概览看板：寻访抽数 + 核心物资 -->
        <div class="export-overview-box">
          <!-- 寻访折算 -->
          <div class="export-draw-panel">
            <div class="export-panel-title">折合寻访抽数</div>
            <div class="export-draw-hero">
              <span class="export-draw-num">
                {{ activeDrawTier ? formatNumber(activeDrawTier.value) : '—' }}
              </span>
              <span class="export-draw-unit">抽</span>
              <span v-if="drawDeltaText" class="export-delta-tag" :class="drawDeltaType">
                {{ drawDeltaText }}
              </span>
            </div>
            <div class="export-draw-breakdown" v-if="highlights.draws.length">
              <div
                v-for="tier in highlights.draws"
                :key="tier.key"
                class="export-draw-pill"
                :class="{ active: tier.key === activeDrawKey }"
              >
                <span class="pill-name">{{ tier.name || tier.key }}</span>
                <span class="pill-val">{{ formatCompact(tier.value) }} 抽</span>
              </div>
            </div>
          </div>

          <!-- 核心物资栅格 -->
          <div class="export-assets-panel">
            <div class="export-panel-title">核心资产与折算存量</div>
            <div class="export-assets-grid">
              <div
                v-for="currency in highlights.currencies"
                :key="currency.name"
                class="export-asset-card"
              >
                <img
                  class="export-asset-icon"
                  :src="itemIconUrl(currency.icon)"
                  :alt="currency.name"
                />
                <div class="export-asset-info">
                  <div class="export-asset-top">
                    <span class="export-asset-name">{{ currency.name }}</span>
                    <span
                      v-if="deltaTextFor(currency.name)"
                      class="export-delta-text"
                      :class="deltaClassFor(currency.name)"
                    >
                      {{ deltaTextFor(currency.name) }}
                    </span>
                  </div>
                  <div class="export-asset-val">{{ currency.compact }}</div>
                </div>
              </div>

              <div v-if="highlights.exp" class="export-asset-card">
                <img
                  class="export-asset-icon"
                  :src="itemIconUrl(highlights.exp.icon)"
                  alt="全部经验"
                />
                <div class="export-asset-info">
                  <div class="export-asset-top">
                    <span class="export-asset-name">全部经验（折算）</span>
                  </div>
                  <div class="export-asset-val">{{ highlights.exp.compact }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 各分类物资清单 -->
        <div class="export-tiers-container">
          <div v-for="group in exportGroupedItems" :key="group.key" class="export-tier-group">
            <div class="export-tier-heading">
              <span class="export-tier-badge" :style="{ background: group.color }">
                {{ group.badge || group.short || group.key }}
              </span>
              <span class="export-tier-title">{{ group.name }}</span>
              <span class="export-tier-count">({{ group.rows.length }} 项)</span>
            </div>

            <div class="export-items-grid">
              <div
                v-for="row in group.rows"
                :key="row.name"
                class="export-item-card"
                :class="{ 'is-zero': !(row.number > 0), 'is-derived': row.derived }"
              >
                <div class="export-item-icon-box">
                  <img class="export-item-icon" :src="itemIconUrl(row.icon)" :alt="row.name" />
                </div>
                <div class="export-item-details">
                  <div class="export-item-top-row">
                    <span class="export-item-name" :title="row.name">{{ row.name }}</span>
                    <span
                      v-if="deltaTextFor(row.name)"
                      class="export-item-delta"
                      :class="deltaClassFor(row.name)"
                    >
                      {{ deltaTextFor(row.name) }}
                    </span>
                    <span v-if="row.derived" class="export-derived-pill">折算</span>
                  </div>
                  <div class="export-item-stock-row">
                    <span class="export-item-stock" :class="{ 'zero-stock': !(row.number > 0) }">
                      {{ formatNumber(row.number) }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部署名与快照说明 -->
        <div class="export-footer-box">
          <span>Arknights Mower · 自动化基建助手</span>
          <span class="export-footer-sep">·</span>
          <span>仓库库存数据快照</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent
} from 'echarts/components'
import VChart, { THEME_KEY } from 'vue-echarts'

import Bowser from 'bowser'
import { toPng } from 'html-to-image'
import { sleep } from '@/utils/sleep'

import { usedepotStore } from '@/stores/depot'
import { useConfigStore } from '@/stores/config'
import HelpText from '@/components/HelpText.vue'
import DepotBaselinePicker from '@/components/DepotBaselinePicker.vue'
import {
  SORT_MODES,
  alignSnapshotsToRange,
  buildDeltaDetail,
  buildDepotExportFilename,
  buildFavoriteHighlights,
  buildHighlights,
  buildItemHistory,
  computeDrawCount,
  countByTier,
  DEFAULT_BASELINE_CONFIG,
  filterItems,
  flattenItems,
  formatCompact,
  formatDelta,
  formatNumber,
  formatRelative,
  formatTimestamp,
  groupItemsByTier,
  itemIconUrl,
  loadBaselineConfig,
  loadFavorites,
  parseDepotResponse,
  resolveCopyText,
  saveBaselineConfig,
  saveFavorites,
  sortItems,
  summarizeItemHistory,
  usableSnapshots
} from '@/utils/depot_inventory'

use([
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
  LineChart,
  CanvasRenderer
])

const depotStore = usedepotStore()
const configStore = useConfigStore()
const { theme } = storeToRefs(configStore)
const message = useMessage()

// 详情曲线跟随应用主题：响应式 computed 注入
provide(
  THEME_KEY,
  computed(() => (theme.value === 'dark' ? 'dark' : undefined))
)

const mobile = inject('mobile', ref(false))
const mobileFilterOpen = ref(false)
const query = ref('')
const debouncedQuery = ref('')
let queryDebounceTimer = null

watch(query, (val) => {
  if (queryDebounceTimer) clearTimeout(queryDebounceTimer)
  if (!val) {
    debouncedQuery.value = ''
    return
  }
  queryDebounceTimer = setTimeout(() => {
    debouncedQuery.value = val
  }, 120)
})

const stockFilter = ref('all') // 'all' | 'favorite' | 'owned' | 'empty'
const deltaFilter = ref('all') // 'all' | 'increased' | 'decreased' | 'changed'
const baselineConfig = ref(loadBaselineConfig())

watch(
  baselineConfig,
  (val) => {
    saveBaselineConfig(val)
  },
  { deep: true }
)
const showDerived = ref(true)
const sortMode = ref('tier')
const activeDrawKey = ref('')
const activeTier = ref('')
const detailItem = ref(null)
const detailOpen = ref(false)

// 关注物品管理
const favorites = ref(loadFavorites())

function isFavorite(name) {
  if (!name) return false
  return favorites.value.includes(name)
}

function toggleFavorite(name) {
  if (!name) return
  const index = favorites.value.indexOf(name)
  if (index >= 0) {
    favorites.value.splice(index, 1)
    message.info(`已取消关注 "${name}"`)
  } else {
    favorites.value.push(name)
    message.success(`已添加关注 "${name}"`)
  }
  saveFavorites(favorites.value)
}

// 顶部右侧看板模式
const showcaseTab = ref('core') // 'core' | 'favorites'
const favPage = ref(0)
const PAGE_SIZE = 8

// 五角星路径：空态、缩略图、卡片角标、详情按钮四处共用一份，
// 之前是同一串坐标抄四遍，改尺寸要四处对齐。
const STAR_POLYGON =
  '12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2'

const sectionElements = new Map()
let observer = null

function registerSection(tierKey, el) {
  if (el) sectionElements.set(tierKey, el)
  else sectionElements.delete(tierKey)
}

const loading = computed(() => depotStore.loading)
const reportError = computed(() => depotStore.reportError)
const reportLoaded = computed(() => depotStore.reportLoaded)
const history = computed(() => depotStore.history || [])
const historyError = computed(() => depotStore.historyError)

const parsed = computed(() => parseDepotResponse(depotStore.report))
const allItems = computed(() => flattenItems(parsed.value.categories))

const alignedBaseline = computed(() => {
  return alignSnapshotsToRange(history.value, baselineConfig.value)
})

/** 对比基准是否还是默认（较上次）：筛选角标、重置按钮都靠它判断。 */
const baselineIsDefault = computed(() => {
  const config = baselineConfig.value || {}
  return (config.mode || 'time') === 'time' && (config.preset || 'previous') === 'previous'
})

const activeBaselineSummary = computed(() => {
  const { matchedCount, startSnapshot, endSnapshot } = alignedBaseline.value
  if (!startSnapshot || !endSnapshot) return '暂无匹配快照'

  const startLabel = formatTimestamp(startSnapshot.at).slice(5)
  const endLabel = formatTimestamp(endSnapshot.at).slice(5)

  if (baselineConfig.value.mode === 'snapshot') {
    return `${startLabel} → ${endLabel} (共 ${matchedCount} 次扫描)`
  }
  if (baselineConfig.value.preset === 'previous') {
    return `较上次 (${startLabel}) → 当前最新`
  }
  if (baselineConfig.value.preset === 'all') {
    return `最早 (${startLabel}) → 当前最新`
  }
  return `${startLabel} → ${endLabel} (共 ${matchedCount} 次扫描)`
})

/** 起始快照里有、结束快照（最新一次扫描）里没有出现的物品，在卡片上的标记。 */
const UNOBSERVED_LABEL = '未扫描'

/**
 * 差额表与"未扫描"名单。
 *
 * 只比值会漏掉物品耗尽：扫描器看不到的格子不会写进快照，差值也就无从谈起。数据层
 * 把这类名字单独放在 unobserved 里，这里按两种语气呈现——能算出差值的照旧 ±N，
 * 这次没出现的标"未扫描"，不硬折算成 −N（分不清是真的用完了还是这一格没认出来）。
 */
const deltaDetail = computed(() => {
  const { startSnapshot, endSnapshot } = alignedBaseline.value
  if (!startSnapshot || !endSnapshot || startSnapshot === endSnapshot) {
    return { deltas: new Map(), unobserved: new Set() }
  }
  return buildDeltaDetail(history.value, startSnapshot, endSnapshot)
})

const deltaMap = computed(() => deltaDetail.value.deltas)
const unobservedItems = computed(() => deltaDetail.value.unobserved)
const highlights = computed(() => buildHighlights(parsed.value.categories))

// 关注高亮看板与分页
const favoriteHighlights = computed(() => {
  return buildFavoriteHighlights(allItems.value, favorites.value, deltaMap.value)
})

const totalFavPages = computed(() => {
  const len = favoriteHighlights.value.length
  return len ? Math.ceil(len / PAGE_SIZE) : 1
})

const currentFavPageItems = computed(() => {
  const list = favoriteHighlights.value
  const start = favPage.value * PAGE_SIZE
  return list.slice(start, start + PAGE_SIZE)
})

watch(totalFavPages, (max) => {
  if (favPage.value >= max) {
    favPage.value = Math.max(0, max - 1)
  }
})

function prevFavPage() {
  if (totalFavPages.value <= 1) return
  favPage.value = (favPage.value - 1 + totalFavPages.value) % totalFavPages.value
}

function nextFavPage() {
  if (totalFavPages.value <= 1) return
  favPage.value = (favPage.value + 1) % totalFavPages.value
}

// 抽数折算档位初始化
watch(
  () => highlights.value.draws,
  (draws) => {
    if (!draws || !draws.length) {
      activeDrawKey.value = ''
      return
    }
    if (!draws.some((d) => d.key === activeDrawKey.value)) {
      activeDrawKey.value = draws[0].key
    }
  },
  { immediate: true }
)

const activeDrawTier = computed(() => {
  return (
    highlights.value.draws.find((d) => d.key === activeDrawKey.value) ||
    highlights.value.draws[0] ||
    null
  )
})

/**
 * 抽数差额。以前是从显示文案里 includes('+')/includes('-') 反推增/减配色，文案一改
 * （换个前缀、换成全角符号）配色就悄悄失效；这里留一份数值，文案和配色各取所需。
 */
const drawDelta = computed(() => {
  if (!activeDrawKey.value) return null
  const usable = usableSnapshots(history.value)
  if (usable.length < 2) return null

  const { startSnapshot, endSnapshot } = alignedBaseline.value
  if (!startSnapshot || !endSnapshot) return null

  const startDraws = computeDrawCount(startSnapshot.items, activeDrawKey.value)
  const endDraws = computeDrawCount(endSnapshot.items, activeDrawKey.value)
  if (!Number.isFinite(startDraws) || !Number.isFinite(endDraws)) return null

  return Math.round((endDraws - startDraws) * 10) / 10
})

const drawDeltaText = computed(() => {
  const diff = drawDelta.value
  if (diff === null) return ''
  const sign = diff > 0 ? `+${diff}` : diff < 0 ? `${diff}` : '±0'

  if (baselineConfig.value.mode === 'snapshot') {
    return `区间变动 ${sign} 抽`
  }
  if (baselineConfig.value.preset === 'previous') {
    return `较上次扫描 ${sign} 抽`
  }
  if (baselineConfig.value.preset === 'all') {
    return `较最早记录 ${sign} 抽`
  }
  return `区间变动 ${sign} 抽`
})

const drawDeltaType = computed(() => {
  const diff = drawDelta.value
  if (diff === null || diff === 0) return 'default'
  return diff > 0 ? 'success' : 'error'
})

// 筛选与排序
const filteredItems = computed(() => {
  return filterItems(allItems.value, {
    query: debouncedQuery.value,
    // 库存状态（全部/有货/空）整个交给 filterItems，页面不再自己补一遍 empty 判断。
    stockFilter: stockFilter.value,
    showDerived: showDerived.value,
    deltaFilter: deltaFilter.value,
    deltaMap: deltaMap.value,
    favoriteOnly: stockFilter.value === 'favorite',
    favorites: favorites.value,
    // 未扫描的条目也算"减少"的一员，否则筛"仅减少"永远看不到刚耗尽的物品。
    unobserved: unobservedItems.value
  })
})

const activeFilterCount = computed(() => {
  let count = 0
  if (stockFilter.value !== 'all') count++
  if (deltaFilter.value !== 'all') count++
  if (!showDerived.value) count++
  if (sortMode.value !== 'tier') count++
  if (!baselineIsDefault.value) count++
  return count
})

const hasActiveFilters = computed(() => {
  return (
    query.value !== '' ||
    stockFilter.value !== 'all' ||
    deltaFilter.value !== 'all' ||
    !showDerived.value ||
    sortMode.value !== 'tier' ||
    !baselineIsDefault.value
  )
})

function resetFilters() {
  if (queryDebounceTimer) clearTimeout(queryDebounceTimer)
  query.value = ''
  debouncedQuery.value = ''
  stockFilter.value = 'all'
  deltaFilter.value = 'all'
  showDerived.value = true
  sortMode.value = 'tier'
  baselineConfig.value = { ...DEFAULT_BASELINE_CONFIG }
}

const sortedItems = computed(() => {
  return sortItems(filteredItems.value, sortMode.value, deltaMap.value)
})

const tierCounts = computed(() => countByTier(allItems.value))

const groupedItems = computed(() => {
  return groupItemsByTier(sortedItems.value, tierCounts.value)
})

const presentTiers = computed(() => {
  return groupedItems.value.map((group) => {
    const counts = tierCounts.value[group.key] || { owned: 0, total: 0 }
    return {
      key: group.key,
      name: group.name,
      short: group.short,
      badge: group.badge,
      color: group.color,
      owned: counts.owned,
      total: counts.total
    }
  })
})

watch(
  presentTiers,
  (tiers) => {
    if (!tiers.length) {
      activeTier.value = ''
      return
    }
    if (!tiers.some((t) => t.key === activeTier.value)) {
      activeTier.value = tiers[0].key
    }
  },
  { immediate: true }
)

// 变化量与微缩图计算
function deltaTextFor(name) {
  if (unobservedItems.value.has(name)) return UNOBSERVED_LABEL
  return formatDelta(deltaMap.value.get(name))
}

function deltaClassFor(name) {
  if (unobservedItems.value.has(name)) return 'down gone'
  const diff = deltaMap.value.get(name)
  if (!diff) return ''
  return diff > 0 ? 'up' : 'down'
}

/** 迷你趋势线最多看最近这么多次扫描：它是 88×24 的装饰，不需要整份历史。 */
const SPARKLINE_SNAPSHOTS = 120

/**
 * 卡片右下角的迷你趋势线。
 *
 * 只算当前筛选结果里的条目，且只喂最近一段快照：网格渲染的就是这一批，按全部物品 +
 * 整份历史算，等于每次筛选都替几百个看不见的卡片重跑几十万次查找（历史可以到三千条）。
 * 详情抽屉里的曲线不受影响，那里仍然用完整历史。
 */
const sparklines = computed(() => {
  const res = {}
  if (history.value.length < 2) return res

  const recent = history.value.slice(-SPARKLINE_SNAPSHOTS)
  for (const item of sortedItems.value) {
    if (item.derived) continue
    const points = buildItemHistory(recent, item.name)
    if (points.length < 2) continue

    const values = points.map((p) => p.value)
    const min = Math.min(...values)
    const max = Math.max(...values)
    const span = max - min || 1
    const width = 88
    const height = 24
    const padding = 2

    const coords = values.map((val, idx) => {
      const x = padding + (idx / (values.length - 1)) * (width - padding * 2)
      const y = height - padding - ((val - min) / span) * (height - padding * 2)
      return `${Math.round(x * 10) / 10},${Math.round(y * 10) / 10}`
    })

    res[item.name] = coords.join(' ')
  }
  return res
})

// 数据新鲜度与过期检查
const freshness = computed(() => {
  const scanned = parsed.value.scannedAt
  if (!scanned) return { class: 'none', relative: '' }
  const rel = formatRelative(scanned)
  const dt = new Date(scanned.replace(/-/g, '/'))
  if (Number.isNaN(dt.getTime())) return { class: 'fresh', relative: rel }
  const hours = (Date.now() - dt.getTime()) / 3600000
  if (hours < 24) return { class: 'fresh', relative: rel }
  if (hours < 72) return { class: 'aged', relative: rel }
  return { class: 'stale', relative: rel }
})

const staleWarning = computed(() => {
  if (freshness.value.class === 'stale') return '数据超过 3 天未更新，建议扫描'
  return ''
})

const copyText = computed(() => resolveCopyText(parsed.value))

// 交互操作
async function reload() {
  try {
    await depotStore.loadReport({ force: true })
    message.success('仓库数据已刷新')
  } catch (error) {
    message.error(error?.message || '刷新仓库数据失败')
  }
}

async function copyToClipboard() {
  const text = copyText.value
  if (!text) {
    message.warning('没有可复制的工具箱数据')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    message.success('已复制明日方舟工具箱代码')
  } catch {
    message.error('复制失败，请手动在浏览器授权剪贴板权限')
  }
}

async function copyName(name) {
  if (!name) return
  try {
    await navigator.clipboard.writeText(name)
    message.success(`已复制 "${name}"`)
  } catch {
    message.error('复制失败')
  }
}

// 导出图片相关状态与逻辑
const exportingImage = ref(false)
const exportScope = ref('all')
const exportContainer = ref(null)

const exportImageOptions = computed(() => {
  return [
    {
      label: `导出全量库存图片 (${allItems.value.length} 种)`,
      key: 'all'
    },
    {
      label: `导出当前筛选视图 (${sortedItems.value.length} 种)`,
      key: 'filtered'
    }
  ]
})

function handleExportSelect(key) {
  exportDepotImage(key)
}

const exportItemsList = computed(() => {
  if (exportScope.value === 'filtered') {
    return sortedItems.value
  }
  return allItems.value
})

const exportGroupedItems = computed(() => {
  return groupItemsByTier(exportItemsList.value, tierCounts.value)
})

const currentExportTime = computed(() => {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})

async function exportDepotImage(scope = 'all') {
  if (exportingImage.value) return
  if (!parsed.value.ok) {
    message.warning('尚未获取到有效仓库数据，无法导出图片')
    return
  }

  exportScope.value = scope
  exportingImage.value = true
  const msgReactive = message.loading('正在生成仓库库存图片...', { duration: 0 })

  try {
    await nextTick()
    const container = exportContainer.value
    if (!container) {
      throw new Error('未找到导出容器节点')
    }

    if (document.fonts?.ready) {
      await document.fonts.ready
    }

    const imgs = Array.from(container.querySelectorAll('img'))
    await Promise.all(
      imgs.map(
        (img) =>
          new Promise((resolve) => {
            if (img.complete && img.naturalWidth > 0) {
              resolve()
            } else {
              const timer = setTimeout(resolve, 1500)
              img.onload = () => {
                clearTimeout(timer)
                resolve()
              }
              img.onerror = () => {
                clearTimeout(timer)
                resolve()
              }
            }
          })
      )
    )

    await sleep(150)

    const browser = Bowser.getParser(window.navigator.userAgent)
    const isWebKit = browser.getEngine().name === 'WebKit'

    const exportTheme = theme.value === 'dark' ? 'dark' : 'light'
    const bgColor = exportTheme === 'dark' ? '#18181c' : '#f8f9fa'

    const containerWidth = 1200
    const containerHeight = container.scrollHeight || container.offsetHeight

    if (isWebKit) {
      try {
        await toPng(container, {
          pixelRatio: 1,
          backgroundColor: bgColor,
          width: containerWidth,
          height: containerHeight,
          style: {
            left: '0px',
            top: '0px',
            position: 'static',
            transform: 'none',
            margin: '0',
            width: `${containerWidth}px`
          }
        })
      } catch {
        // ignore WebKit warmup error
      }
    }

    const dataUrl = await toPng(container, {
      pixelRatio: 2,
      backgroundColor: bgColor,
      width: containerWidth,
      height: containerHeight,
      style: {
        left: '0px',
        top: '0px',
        position: 'static',
        transform: 'none',
        margin: '0',
        width: `${containerWidth}px`,
        minWidth: `${containerWidth}px`,
        maxWidth: `${containerWidth}px`
      }
    })

    if (!dataUrl || dataUrl.length < 500) {
      throw new Error('生成图片失败，图像数据异常')
    }

    const filename = buildDepotExportFilename(parsed.value.scannedAt, scope)
    const link = document.createElement('a')
    link.href = dataUrl
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)

    msgReactive.destroy()
    message.success(`仓库库存图片已成功导出 (${filename})`)
  } catch (error) {
    console.error('Export depot image error:', error)
    msgReactive.destroy()
    message.error(error?.message ? `导出图片失败: ${error.message}` : '导出图片失败，请重试')
  } finally {
    exportingImage.value = false
  }
}

const mobileRailRef = ref(null)

function scrollRailToActive(key) {
  if (!mobileRailRef.value || !key) return
  const activeBtn = mobileRailRef.value.querySelector(`[data-key="${key}"]`)
  if (activeBtn && typeof activeBtn.scrollIntoView === 'function') {
    activeBtn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
  }
}

function scrollToTier(tierKey) {
  activeTier.value = tierKey
  scrollRailToActive(tierKey)
  const target = sectionElements.get(tierKey)
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

watch(activeTier, (newKey) => {
  if (newKey) {
    scrollRailToActive(newKey)
  }
})

function handleImageError(event) {
  const img = event.target
  if (img) img.style.display = 'none'
  const fallback = img?.nextElementSibling
  if (fallback) fallback.style.display = 'grid'
}

// 抽屉详情
const drawerPlacement = computed(() => {
  return mobile.value ? 'bottom' : 'right'
})

const drawerWidth = computed(() => {
  if (drawerPlacement.value === 'bottom') return '100%'
  if (typeof window === 'undefined') return 460
  return Math.min(500, window.innerWidth * 0.9)
})

const drawerHeight = computed(() => {
  if (drawerPlacement.value !== 'bottom') return undefined
  return '82vh'
})

function openDetail(row) {
  detailItem.value = row
  detailOpen.value = true
}

function openDetailByName(name) {
  const found = allItems.value.find((item) => item.name === name)
  if (found) openDetail(found)
}

const detailPoints = computed(() => {
  if (!detailItem.value || detailItem.value.derived) return []
  return buildItemHistory(history.value, detailItem.value.name)
})

const detailSummary = computed(() => {
  return summarizeItemHistory(detailPoints.value)
})

const detailChartOption = computed(() => {
  const pts = detailPoints.value
  if (!pts || pts.length < 2) return {}

  const xData = pts.map((p) => formatTimestamp(p.at))
  const yData = pts.map((p) => p.value)
  const isDark = theme.value === 'dark'
  const color = detailItem.value?.color || '#18a058'

  return {
    animation: true,
    grid: {
      left: 10,
      right: 18,
      top: 24,
      bottom: 40,
      containLabel: true
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: isDark ? 'rgba(36, 36, 40, 0.95)' : 'rgba(255, 255, 255, 0.95)',
      borderColor: isDark ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.1)',
      textStyle: { color: isDark ? '#fff' : '#333', fontSize: 12 },
      formatter(params) {
        const p = params[0]
        return `<div><span style="font-size:11px;opacity:0.75">${p.axisValue}</span><br/><b>${detailItem.value?.name}</b>：<b style="font-size:14px;color:${color}">${formatNumber(p.data)}</b></div>`
      }
    },
    xAxis: {
      type: 'category',
      data: xData,
      boundaryGap: false,
      axisLabel: {
        fontSize: 10,
        color: isDark ? 'rgba(255, 255, 255, 0.55)' : 'rgba(0, 0, 0, 0.55)',
        formatter: (val) => val.slice(5) // MM-DD HH:mm
      },
      axisLine: {
        lineStyle: { color: isDark ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.15)' }
      }
    },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: {
        lineStyle: { color: isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)' }
      },
      axisLabel: {
        fontSize: 10,
        color: isDark ? 'rgba(255, 255, 255, 0.55)' : 'rgba(0, 0, 0, 0.55)',
        formatter: (val) => formatCompact(val)
      }
    },
    dataZoom: [
      {
        type: 'inside',
        start: 0,
        end: 100
      }
    ],
    series: [
      {
        name: detailItem.value?.name,
        type: 'line',
        smooth: 0.25,
        showSymbol: pts.length <= 15,
        symbolSize: 6,
        data: yData,
        lineStyle: { width: 2.5, color },
        itemStyle: { color },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: color + (isDark ? '44' : '33') },
              { offset: 1, color: color + '00' }
            ]
          }
        }
      }
    ]
  }
})

// 滚动监听联动（ScrollSpy）
function setupIntersectionObserver() {
  if (typeof IntersectionObserver === 'undefined') return
  if (observer) observer.disconnect()

  observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((e) => e.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (visible.length) {
        for (const [key, el] of sectionElements.entries()) {
          if (el === visible[0].target) {
            activeTier.value = key
            break
          }
        }
      }
    },
    { rootMargin: '-10% 0px -70% 0px', threshold: 0.05 }
  )

  sectionElements.forEach((el) => observer.observe(el))
}

watch(
  groupedItems,
  async () => {
    await nextTick()
    setupIntersectionObserver()
  },
  { deep: true }
)

onMounted(async () => {
  depotStore.loadReport().catch(() => {})
  await nextTick()
  setupIntersectionObserver()
})

onUnmounted(() => {
  if (queryDebounceTimer) {
    clearTimeout(queryDebounceTimer)
    queryDebounceTimer = null
  }
  if (observer) {
    observer.disconnect()
    observer = null
  }
})
</script>

<style>
/* 卡片/分隔线的统一 1px 描边；之前这行字面量在样式里出现 14 次，换主题要一处一处改。
   必须放在非 scoped 的 :root 上：详情抽屉里的 .detail-hero-box / .kpi-card 由 n-drawer
   传送到 body，不走 .depot-page 的继承链，挂在 .depot-page 上它们会取不到值。 */
:root {
  --depot-hairline: 1px solid var(--mower-divider);
}

.depot-detail-drawer.n-drawer--bottom-placement {
  border-top-left-radius: 16px;
  border-top-right-radius: 16px;
  box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.16);
  overflow: hidden;
}
</style>

<style scoped>
.depot-page {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  padding: 10px 14px 48px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin: 0 auto;
  overflow-x: hidden;
}

.desktop-only {
  display: flex;
}

.mobile-only {
  display: none !important;
}

/* =========================================================================
   ① 顶部总览看板 (Hero)
   ========================================================================= */
.depot-hero {
  border-radius: 12px;
  background:
    radial-gradient(
      120% 140% at 0% 0%,
      color-mix(in srgb, var(--mower-primary) 10%, transparent),
      transparent 60%
    ),
    var(--mower-surface);
  border: var(--depot-hairline);
  box-shadow: var(--mower-shadow-surface, none);
}

.hero-top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 14px;
}

.hero-title-group {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.hero-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.hero-count-tag {
  font-size: 11px;
}

.hero-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* 核心看板双列 */
.hero-grid {
  display: grid;
  grid-template-columns: minmax(310px, 1fr) minmax(380px, 1.4fr);
  gap: 16px;
  align-items: stretch;
}

@media (max-width: 960px) {
  .hero-grid {
    grid-template-columns: 1fr;
  }
}

.hero-panel {
  display: flex;
  flex-direction: column;
  padding: 14px 16px;
  border-radius: 10px;
  background: var(--mower-control-surface);
  border: var(--depot-hairline);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.panel-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: inherit;
}

.panel-subtitle {
  font-size: 11px;
  color: var(--mower-segment-muted);
}

.assets-header {
  min-height: 28px;
}

.showcase-tabs {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  background: var(--mower-surface);
  padding: 2px;
  border-radius: 7px;
  border: var(--depot-hairline);
}

.showcase-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 5px;
  border: none;
  background: transparent;
  color: var(--mower-segment-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.showcase-tab-btn:hover {
  color: var(--mower-primary);
}

.showcase-tab-btn.active {
  background: var(--mower-control-surface);
  color: var(--mower-primary-text, var(--mower-primary));
  font-weight: 700;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.tab-icon {
  font-size: 12px;
  line-height: 1;
}

.tab-count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--mower-warning, #e6a23c);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
}

.showcase-controls {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.fav-pager {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.pager-arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  border: var(--depot-hairline);
  background: var(--mower-surface);
  color: inherit;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s ease;
}

.pager-arrow:hover {
  border-color: var(--mower-primary);
  color: var(--mower-primary);
}

.pager-indicator {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--mower-segment-muted);
  padding: 0 2px;
}

.favorites-showcase-wrap {
  min-height: 80px;
}

.favorites-empty-box {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 14px;
  border-radius: 8px;
  background: var(--mower-surface);
  border: 1px dashed var(--mower-divider);
}

.fav-empty-icon {
  font-size: 26px;
  color: var(--mower-warning, #f5a623);
  opacity: 0.6;
}

.fav-empty-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.fav-empty-title {
  font-size: 13px;
  font-weight: 600;
}

.fav-empty-sub {
  font-size: 11px;
  color: var(--mower-segment-muted);
  line-height: 1.4;
}

.fav-asset-card {
  position: relative;
}

.fav-unstar-btn {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 18px;
  height: 18px;
  border: none;
  background: transparent;
  color: var(--mower-warning, #f5a623);
  font-size: 12px;
  cursor: pointer;
  opacity: 0;
  display: grid;
  place-items: center;
  border-radius: 4px;
  transition: all 0.15s ease;
}

.fav-asset-card:hover .fav-unstar-btn {
  opacity: 0.8;
}

.fav-unstar-btn:hover {
  opacity: 1 !important;
  transform: scale(1.15);
}

/* 左侧：抽数展示 */
.draw-hero-value {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin: 2px 0 10px;
}

.draw-number {
  font-size: 38px;
  line-height: 1;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: var(--mower-primary);
  letter-spacing: -0.02em;
}

.draw-unit {
  font-size: 16px;
  font-weight: 600;
  color: var(--mower-segment-muted);
}

.draw-tiers-selector {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
  margin-bottom: 10px;
}

@media (min-width: 600px) and (max-width: 960px) {
  .draw-tiers-selector {
    grid-template-columns: repeat(4, 1fr);
  }
}

.draw-tier-pill {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 6px;
  border: var(--depot-hairline);
  background: var(--mower-surface);
  color: inherit;
  cursor: pointer;
  font-size: 12px;
  min-width: 0;
  transition: all 0.15s ease;
}

.draw-tier-pill:hover {
  border-color: var(--mower-primary);
  background: var(--mower-control-hover);
}

.draw-tier-pill.active {
  border-color: var(--mower-primary);
  background: var(--mower-primary-block);
  color: var(--mower-primary-text);
  font-weight: 600;
}

.draw-tier-name {
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.draw-tier-val {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  flex-shrink: 0;
}

.draw-tier-hint {
  font-size: 11px;
  line-height: 1.4;
  color: var(--mower-segment-muted);
  margin-top: auto;
  padding-top: 4px;
}

.hint-prefix {
  font-weight: 600;
  opacity: 0.85;
}

/* 右侧：重点资源栅格（无彩色描边，上下分行保证数值不溢出） */
.assets-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(136px, 1fr));
  gap: 8px;
}

.asset-card {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--mower-surface);
  border: var(--depot-hairline);
  cursor: pointer;
  overflow: hidden;
  box-sizing: border-box;
  transition:
    transform 0.15s ease,
    border-color 0.15s ease;
}

.asset-card:hover {
  border-color: var(--mower-primary);
  transform: translateY(-1px);
}

.asset-icon {
  width: 30px;
  height: 30px;
  object-fit: contain;
  flex-shrink: 0;
}

.asset-exp-icon {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  background: rgba(176, 125, 59, 0.16);
  color: #b07d3b;
  font-size: 10px;
  font-weight: 800;
  flex-shrink: 0;
}

.asset-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.asset-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.asset-name {
  font-size: 11px;
  color: var(--mower-segment-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.asset-number {
  font-size: 14px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.asset-delta {
  font-size: 10px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  padding: 1px 4px;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
  line-height: 1.2;
}

.asset-delta.up {
  color: var(--mower-success-text);
  background: var(--mower-success-block);
}

.asset-delta.down {
  color: var(--mower-error-text);
  background: var(--mower-error-block);
}

/* 底部状态条 */
.hero-status-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid var(--mower-divider);
  font-size: 12px;
  color: var(--mower-segment-muted);
}

.status-items {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.status-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--mower-divider);
}

.status-dot.fresh {
  background: var(--mower-success);
}

.status-dot.aged {
  background: var(--mower-warning);
}

.status-dot.stale {
  background: var(--mower-error);
}

.status-divider {
  opacity: 0.35;
}

.status-ok {
  color: var(--mower-success-text);
}

.status-dim {
  opacity: 0.75;
}

.stale-warning-tag {
  font-size: 11px;
}

/* =========================================================================
   ② 工具栏 (Toolbar) 与吸顶结构
   ========================================================================= */
.depot-sticky-bar {
  position: sticky;
  top: 0;
  z-index: 40;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}

.depot-toolbar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--mower-surface);
  border: var(--depot-hairline);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.04);
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}

.toolbar-primary-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  width: 100%;
  max-width: 100%;
}

.toolbar-search-wrap {
  flex: 1;
  min-width: 240px;
  max-width: 460px;
}

.toolbar-search-input {
  width: 100%;
}

.toolbar-baseline-wrap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.toolbar-baseline-select {
  width: 180px;
}

.baseline-arrow {
  font-size: 12px;
  color: var(--mower-segment-muted);
  opacity: 0.8;
}

.mobile-filter-btn-wrap {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

.mobile-filter-toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.mobile-filter-count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 3px;
  border-radius: 8px;
  background: var(--mower-primary);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
}

.toggle-arrow {
  font-size: 9px;
  opacity: 0.7;
  margin-left: 2px;
}

.star-empty-svg {
  width: 24px;
  height: 24px;
}

.star-mini-svg {
  width: 12px;
  height: 12px;
}

.star-btn-icon {
  width: 13px;
  height: 13px;
}

.toolbar-stat-tag {
  font-size: 12px;
  color: var(--mower-segment-muted);
  white-space: nowrap;
  margin-left: auto;
}

.toolbar-secondary-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding-top: 6px;
  border-top: 1px dashed var(--mower-divider);
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}

.filter-group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.control-label {
  font-size: 12px;
  color: var(--mower-segment-muted);
  white-space: nowrap;
}

.toolbar-checkbox {
  font-size: 12px;
  white-space: nowrap;
}

.sort-selector-wrap {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.toolbar-sort-select {
  width: 175px;
}

.reset-filter-btn {
  font-size: 12px;
}

.status-baseline-val {
  font-weight: 600;
  color: var(--mower-primary);
}

.mobile-category-rail {
  width: 100%;
  max-width: 100%;
  overflow: hidden;
  padding-top: 6px;
  border-top: 1px solid var(--mower-divider);
  box-sizing: border-box;
}

.mobile-category-rail .rail-items-container {
  display: flex;
  flex-direction: row;
  overflow-x: auto;
  scrollbar-width: none;
  gap: 6px;
  width: 100%;
  padding: 1px 0;
  box-sizing: border-box;
}

.mobile-category-rail .rail-items-container::-webkit-scrollbar {
  display: none;
}

.mobile-category-rail .rail-nav-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  font-size: 11px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s ease;
}

.mobile-category-rail .rail-nav-btn:hover {
  background: var(--mower-control-hover);
}

.mobile-category-rail .rail-nav-btn.active {
  background: var(--mower-primary-block);
  border-color: color-mix(in srgb, var(--mower-primary) 30%, transparent);
  color: var(--mower-primary-text);
  font-weight: 600;
}

/* =========================================================================
   ③ 主体：左侧导览 + 右侧卡片栅格
   ========================================================================= */
.depot-content-body {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 16px;
  align-items: start;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}

/* 左侧导航栏（桌面端吸顶位置随顶部工具栏顺延） */
.depot-nav-rail {
  position: sticky;
  top: 76px;
  z-index: 30;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
  border-radius: 10px;
  background: var(--mower-surface);
  border: var(--depot-hairline);
}

.rail-header {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--mower-segment-muted);
  padding: 2px 6px 6px;
  margin-bottom: 2px;
  border-bottom: 1px solid var(--mower-divider);
}

.rail-items-container {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.rail-nav-btn {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: inherit;
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s ease;
}

.rail-nav-btn:hover {
  background: var(--mower-control-hover);
}

.rail-nav-btn.active {
  background: var(--mower-primary-block);
  border-color: color-mix(in srgb, var(--mower-primary) 30%, transparent);
  color: var(--mower-primary-text);
  font-weight: 600;
}

.rail-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 20px;
  padding: 0 4px;
  box-sizing: border-box;
  border-radius: 4px;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
  flex-shrink: 0;
}

.rail-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rail-counts {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  opacity: 0.85;
}

.count-owned {
  font-weight: 600;
}

.count-slash,
.count-total {
  opacity: 0.5;
}

.rail-empty-tip {
  font-size: 12px;
  color: var(--mower-segment-muted);
  padding: 8px 6px;
}

/* =========================================================================
   移动端 / 窄屏自适应 (Mobile Responsive)
   ========================================================================= */
@media (max-width: 850px) {
  .desktop-only {
    display: none !important;
  }

  .mobile-only {
    display: flex !important;
  }

  .depot-page {
    padding: 6px 8px 36px;
    gap: 10px;
    max-width: 100%;
    overflow-x: hidden;
  }

  .hero-top-bar {
    gap: 8px;
    margin-bottom: 10px;
  }

  .hero-title {
    font-size: 15px;
  }

  .hero-actions {
    width: 100%;
    justify-content: flex-start;
    gap: 6px;
  }

  .hero-grid {
    grid-template-columns: 1fr;
  }

  .hero-panel {
    padding: 10px 12px;
    max-width: 100%;
    box-sizing: border-box;
  }

  .draw-tiers-selector {
    grid-template-columns: repeat(2, 1fr);
  }

  .assets-grid {
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 6px;
  }

  .fav-unstar-btn {
    opacity: 0.8;
  }

  .depot-sticky-bar {
    position: sticky;
    top: 0;
    z-index: 40;
    margin: -6px -8px 0;
    padding: 6px 8px 0;
    background: var(--n-color, var(--mower-body-bg, var(--mower-surface)));
  }

  .depot-toolbar {
    padding: 8px 10px;
    gap: 6px;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  }

  .toolbar-primary-row {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: nowrap;
    width: 100%;
  }

  .toolbar-search-wrap {
    flex: 1;
    min-width: 0;
    max-width: none;
  }

  .mobile-filter-btn-wrap {
    display: flex !important;
  }

  .mobile-filter-toggle-btn {
    padding: 0 8px;
    height: 32px;
  }

  .toolbar-stat-tag {
    display: none;
  }

  .toolbar-secondary-row {
    display: none;
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
    padding-top: 8px;
    border-top: 1px dashed var(--mower-divider);
  }

  .toolbar-secondary-row.mobile-filters-open {
    display: flex;
  }

  .toolbar-baseline-wrap {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .toolbar-baseline-select {
    flex: 1;
    min-width: 100px;
    width: auto;
  }

  .filter-group {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px;
  }

  .toolbar-sort-select {
    width: 140px;
  }

  .mobile-category-rail {
    display: flex !important;
  }

  .mobile-category-rail .rail-items-container {
    -webkit-overflow-scrolling: touch;
  }

  .depot-content-body {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .tier-group-section {
    content-visibility: auto;
    contain-intrinsic-size: auto 240px;
    scroll-margin-top: 98px;
  }

  .items-card-grid {
    grid-template-columns: repeat(auto-fill, minmax(136px, 1fr));
    gap: 8px;
  }

  .inventory-card {
    padding: 7px 8px;
    gap: 8px;
    -webkit-tap-highlight-color: transparent;
  }

  .card-icon-box {
    width: 34px;
    height: 34px;
  }

  .card-avatar {
    width: 34px;
    height: 34px;
  }

  .card-item-name {
    font-size: 12px;
  }

  .card-stock-number {
    font-size: 14px;
  }

  .card-star-btn {
    opacity: 0.35;
  }

  .card-star-btn.starred {
    opacity: 1;
  }
}

/* 右侧主展示区 */
.depot-items-area {
  min-width: 0;
}

.area-empty-state {
  padding: 48px 0;
  border-radius: 10px;
  background: var(--mower-surface);
  border: var(--depot-hairline);
}

.tier-groups-list {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.tier-group-section {
  content-visibility: auto;
  contain-intrinsic-size: auto 300px;
  scroll-margin-top: 68px;
}

.tier-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--mower-divider);
}

.tier-group-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.tier-pill-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 22px;
  padding: 0 6px;
  box-sizing: border-box;
  border-radius: 5px;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.tier-group-heading {
  font-size: 15px;
  font-weight: 700;
}

.tier-group-meta-info {
  font-size: 12px;
  color: var(--mower-segment-muted);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.meta-dot {
  opacity: 0.5;
}

.filtered-hint {
  color: var(--mower-primary);
  font-size: 11px;
}

/* 物品卡片栅格 */
.items-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
  gap: 10px;
}

.inventory-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 11px;
  border-radius: 10px;
  background: var(--mower-surface);
  border: var(--depot-hairline);
  cursor: pointer;
  overflow: hidden;
  box-sizing: border-box;
  transition:
    transform 0.16s ease,
    border-color 0.16s ease,
    box-shadow 0.16s ease;
}

.inventory-card:hover,
.inventory-card:focus-visible {
  transform: translateY(-2px);
  border-color: var(--mower-primary);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
  outline: none;
}

.inventory-card.is-empty {
  background: color-mix(in srgb, var(--mower-surface) 60%, var(--mower-control-surface));
}

.inventory-card.is-derived {
  border-style: dashed;
  background: var(--mower-control-surface);
}

.card-icon-box {
  position: relative;
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--mower-control-surface);
  overflow: hidden;
  z-index: 1;
}

.card-avatar {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.card-avatar-fallback {
  display: none;
  position: absolute;
  inset: 0;
  place-items: center;
  font-size: 14px;
  font-weight: 700;
  opacity: 0.6;
}

.card-details {
  min-width: 0;
  flex: 1;
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.card-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.card-item-name {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.card-derived-tag {
  flex-shrink: 0;
  transform: scale(0.85);
  transform-origin: right center;
}

.card-stock-row {
  display: flex;
  align-items: baseline;
}

.card-stock-number {
  font-size: 16px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-stock-number.zero-stock {
  font-size: 13px;
  font-weight: 500;
  color: var(--mower-segment-muted);
  opacity: 0.7;
}

.card-delta-tag {
  font-size: 10px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  padding: 1px 4px;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
  line-height: 1.2;
}

.card-delta-tag.up {
  color: var(--mower-success-text);
  background: var(--mower-success-block);
}

.card-delta-tag.down {
  color: var(--mower-error-text);
  background: var(--mower-error-block);
}

/* 未扫描：大概率是耗尽，但也可能是这一格没认出来，用中性色而不是"减少"的红。 */
.card-delta-tag.gone {
  color: var(--mower-text-muted, rgba(31, 30, 28, 0.55));
  background: var(--mower-surface-hover, rgba(0, 0, 0, 0.06));
}

.card-sparkline-svg {
  position: absolute;
  right: 6px;
  bottom: 4px;
  width: 64px;
  height: 18px;
  opacity: 0.15;
  pointer-events: none;
  transition: opacity 0.2s ease;
  z-index: 0;
}

.inventory-card:hover .card-sparkline-svg {
  opacity: 0.5;
}

.card-sparkline-svg polyline {
  fill: none;
  stroke-width: 1.8;
  vector-effect: non-scaling-stroke;
}

/* 物品卡片星标按钮 */
.card-star-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 20px;
  height: 20px;
  border: none;
  background: transparent;
  cursor: pointer;
  display: grid;
  place-items: center;
  padding: 0;
  border-radius: 4px;
  color: var(--mower-segment-muted);
  opacity: 0;
  z-index: 2;
  transition:
    opacity 0.15s ease,
    transform 0.15s ease,
    color 0.15s ease;
}

.card-star-btn .star-svg {
  width: 13px;
  height: 13px;
}

.inventory-card:hover .card-star-btn {
  opacity: 0.5;
}

.card-star-btn:hover {
  opacity: 1 !important;
  color: var(--mower-warning, #f5a623) !important;
  transform: scale(1.15);
}

.card-star-btn.starred {
  opacity: 1;
  color: var(--mower-warning, #f5a623);
}

.detail-fav-btn {
  margin-left: 2px;
}

/* =========================================================================
   ④ 详情抽屉 (Detail Drawer)
   ========================================================================= */
.detail-hero-box {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  border-radius: 10px;
  background: var(--mower-control-surface);
  border: var(--depot-hairline);
  margin-bottom: 16px;
}

.detail-hero-icon-box {
  width: 52px;
  height: 52px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--mower-surface);
  border: var(--depot-hairline);
}

.detail-hero-avatar {
  width: 44px;
  height: 44px;
  object-fit: contain;
}

.detail-hero-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

.detail-title-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-item-title {
  font-size: 15px;
  font-weight: 700;
}

.detail-stock-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.detail-stock-label {
  font-size: 12px;
  color: var(--mower-segment-muted);
}

.detail-stock-count {
  font-size: 22px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}

.detail-derived-alert {
  margin-bottom: 16px;
}

.detail-kpi-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 16px;
}

.kpi-card {
  display: flex;
  flex-direction: column;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--mower-control-surface);
  border: var(--depot-hairline);
}

.kpi-label {
  font-size: 11px;
  color: var(--mower-segment-muted);
  white-space: nowrap;
}

.kpi-val {
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  margin: 2px 0 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kpi-val.kpi-up {
  color: var(--mower-success);
}

.kpi-val.kpi-down {
  color: var(--mower-error);
}

.kpi-sub {
  font-size: 10px;
  color: var(--mower-segment-muted);
  opacity: 0.8;
  white-space: nowrap;
}

.detail-chart-wrapper {
  border-radius: 10px;
  background: var(--mower-control-surface);
  border: var(--depot-hairline);
  padding: 10px;
}

.detail-echarts {
  height: 280px;
  width: 100%;
}

.detail-timespan-label {
  margin-top: 8px;
  font-size: 11px;
  color: var(--mower-segment-muted);
  text-align: center;
}

.detail-empty-view {
  padding: 40px 0;
}

/* =========================================================================
   ⑤ 离屏导出图片样式 (Export View)
   ========================================================================= */
.export-offscreen-wrapper {
  position: fixed;
  top: 0;
  left: 0;
  width: 0;
  height: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: -99999;
}

.depot-export-view {
  width: 1200px;
  flex-shrink: 0;
  box-sizing: border-box;
  padding: 28px 32px 32px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  font-family:
    -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans',
    sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji';
}

.depot-export-view.theme-dark {
  background-color: #18181c;
  color: #f0f0f2;
  --exp-card-bg: #232328;
  --exp-card-border: rgba(255, 255, 255, 0.08);
  --exp-panel-bg: #1f1f24;
  --exp-panel-border: rgba(255, 255, 255, 0.1);
  --exp-muted: rgba(255, 255, 255, 0.6);
  --exp-subtle: rgba(255, 255, 255, 0.38);
  --exp-hero-bg:
    radial-gradient(120% 140% at 0% 0%, rgba(24, 160, 88, 0.16), transparent 60%), #1f1f24;
  --exp-pill-bg: #2b2b32;
}

.depot-export-view.theme-light {
  background-color: #f5f6f8;
  color: #2c3e50;
  --exp-card-bg: #ffffff;
  --exp-card-border: rgba(0, 0, 0, 0.08);
  --exp-panel-bg: #ffffff;
  --exp-panel-border: rgba(0, 0, 0, 0.08);
  --exp-muted: rgba(0, 0, 0, 0.58);
  --exp-subtle: rgba(0, 0, 0, 0.38);
  --exp-hero-bg:
    radial-gradient(120% 140% at 0% 0%, rgba(24, 160, 88, 0.12), transparent 60%), #ffffff;
  --exp-pill-bg: #edf1f5;
}

.export-header-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: var(--exp-hero-bg);
  border: 1px solid var(--exp-panel-border);
  border-radius: 12px;
}

.export-header-left {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.export-app-title {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.export-logo-icon {
  width: 24px;
  height: 24px;
  color: #18a058;
}

.export-title-text {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.export-scope-desc {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.export-badge-scope {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(24, 160, 88, 0.16);
  color: #18a058;
  font-size: 11px;
  font-weight: 600;
}

.export-meta-text {
  font-size: 12px;
  color: var(--exp-muted);
}

.export-header-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
}

.export-meta-line {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.export-meta-lbl {
  color: var(--exp-muted);
}

.export-meta-val {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* 概览看板 */
.export-overview-box {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 14px;
  align-items: stretch;
}

.export-draw-panel,
.export-assets-panel {
  padding: 14px 18px;
  border-radius: 10px;
  background: var(--exp-panel-bg);
  border: 1px solid var(--exp-panel-border);
  display: flex;
  flex-direction: column;
}

.export-panel-title {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 8px;
  color: var(--exp-muted);
}

.export-draw-hero {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 10px;
}

.export-draw-num {
  font-size: 32px;
  font-weight: 800;
  line-height: 1;
  color: #18a058;
  font-variant-numeric: tabular-nums;
}

.export-draw-unit {
  font-size: 14px;
  font-weight: 600;
  color: var(--exp-muted);
}

.export-delta-tag {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 10px;
  margin-left: 6px;
  font-weight: 600;
}

.export-delta-tag.success {
  background: rgba(24, 160, 88, 0.16);
  color: #18a058;
}

.export-delta-tag.error {
  background: rgba(208, 58, 82, 0.16);
  color: #d03a52;
}

.export-draw-breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: auto;
}

.export-draw-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
  background: var(--exp-pill-bg);
  font-size: 11px;
}

.export-draw-pill.active {
  background: rgba(24, 160, 88, 0.16);
  color: #18a058;
  font-weight: 600;
}

.export-draw-pill .pill-name {
  color: var(--exp-muted);
}

.export-draw-pill.active .pill-name {
  color: #18a058;
}

.export-draw-pill .pill-val {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.export-assets-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}

.export-asset-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--exp-card-bg);
  border: 1px solid var(--exp-card-border);
}

.export-asset-icon {
  width: 36px;
  height: 36px;
  object-fit: contain;
  flex-shrink: 0;
}

.export-asset-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.export-asset-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.export-asset-name {
  font-size: 11px;
  color: var(--exp-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.export-delta-text {
  font-size: 10px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.export-delta-text.up {
  color: #18a058;
}

.export-delta-text.down {
  color: #d03a52;
}

/* 导出的长图与页面同语气：未扫描用中性灰，别和真实减少混在一起。 */
.export-delta-text.gone {
  color: #8a8a8a;
}

.export-asset-val {
  font-size: 14px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  margin-top: 1px;
}

/* 分类物资清单 */
.export-tiers-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.export-tier-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.export-tier-heading {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.export-tier-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 7px;
  border-radius: 4px;
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
}

.export-tier-title {
  font-size: 14px;
  font-weight: 700;
}

.export-tier-count {
  font-size: 12px;
  color: var(--exp-muted);
}

.export-items-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 8px;
}

.export-item-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 8px;
  background: var(--exp-card-bg);
  border: 1px solid var(--exp-card-border);
  box-sizing: border-box;
}

.export-item-card.is-zero {
  opacity: 0.55;
}

.export-item-icon-box {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.export-item-icon {
  width: 36px;
  height: 36px;
  object-fit: contain;
}

.export-item-details {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.export-item-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.export-item-name {
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.export-item-delta {
  font-size: 10px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.export-item-delta.up {
  color: #18a058;
}

.export-item-delta.down {
  color: #d03a52;
}

.export-derived-pill {
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 3px;
  background: rgba(32, 128, 240, 0.15);
  color: #2080f0;
  font-weight: 600;
}

.export-item-stock-row {
  margin-top: 2px;
}

.export-item-stock {
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.export-item-stock.zero-stock {
  color: var(--exp-subtle);
}

/* 底部署名 */
.export-footer-box {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding-top: 14px;
  border-top: 1px dashed var(--exp-card-border);
  font-size: 11px;
  color: var(--exp-muted);
}

.export-footer-sep {
  opacity: 0.5;
}
</style>
