<script setup>
import { computed } from 'vue'

// 柱状图的骨架：按图表的版面画出图例、横向网格线、柱子和坐标轴刻度的占位，读完后由真实图表在
// 同一位置替换。plot 是绘图区到图表四边的距离（px），与图表的 grid 设置和坐标轴标签宽度一致；
// 柱子高低只是示意，不代表数据。放在 LoadingSkeleton 里使用，尺寸由页面给的 class 决定。
const props = defineProps({
  bars: { type: Number, default: 14 },
  legend: { type: Array, default: () => [] },
  plot: { type: Object, default: () => ({ top: 24, right: 8, bottom: 24, left: 32 }) },
  // 右侧也有一条纵轴时为 true，右侧同样画出刻度占位。
  rightAxis: { type: Boolean, default: false }
})

const HEIGHTS = [58, 66, 52, 63, 70, 55, 61, 68, 50, 64, 72, 57, 62, 67]
const GRID_LINES = 6
const style = computed(() => ({
  '--plot-top': `${props.plot.top}px`,
  '--plot-right': `${props.plot.right}px`,
  '--plot-bottom': `${props.plot.bottom}px`,
  '--plot-left': `${props.plot.left}px`
}))
const bars = computed(() =>
  Array.from({ length: Math.max(1, props.bars) }, (_, index) => HEIGHTS[index % HEIGHTS.length])
)
// 横轴标签每隔几根柱子出现一次，与图表自动省略标签后的密度相近。
const labelEvery = computed(() => Math.max(1, Math.ceil(bars.value.length / 5)))
</script>

<template>
  <span class="skeleton-bar-chart" :style="style">
    <span v-if="legend.length" class="skeleton-bar-chart__legend">
      <span v-for="(width, index) in legend" :key="index" class="skeleton-bar-chart__key">
        <span class="skeleton-bone skeleton-bar-chart__swatch" />
        <span class="skeleton-bone skeleton-bar-chart__tick" :style="{ width: `${width}px` }" />
      </span>
    </span>
    <span class="skeleton-bar-chart__plot">
      <span v-for="(height, index) in bars" :key="index" class="skeleton-bar-chart__band">
        <span class="skeleton-bone skeleton-bar-chart__bar" :style="{ height: `${height}%` }" />
        <span
          v-if="index % labelEvery === 0"
          class="skeleton-bone skeleton-bar-chart__tick skeleton-bar-chart__x"
        />
      </span>
    </span>
    <span
      v-for="line in GRID_LINES"
      :key="line"
      class="skeleton-bone skeleton-bar-chart__tick skeleton-bar-chart__y"
      :style="{ '--line': line - 1 }"
    />
    <template v-if="rightAxis">
      <span
        v-for="line in GRID_LINES"
        :key="'right' + line"
        class="skeleton-bone skeleton-bar-chart__tick skeleton-bar-chart__y skeleton-bar-chart__y--right"
        :style="{ '--line': line - 1 }"
      />
    </template>
  </span>
</template>

<style scoped>
.skeleton-bar-chart {
  --grid-color: color-mix(in srgb, var(--mower-text, #333639) 7%, transparent);
  position: relative;
  display: block;
}

.skeleton-bar-chart__legend {
  position: absolute;
  top: 6px;
  left: 4px;
  right: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
}

.skeleton-bar-chart__key {
  display: flex;
  align-items: center;
  gap: 6px;
}

.skeleton-bar-chart__swatch {
  width: 10px;
  height: 10px;
  border-radius: 3px;
}

.skeleton-bar-chart__tick {
  height: 7px;
  border-radius: 4px;
}

/* 绘图区：底边是横轴，上方等距的网格线与图表的分隔线位置相近。 */
.skeleton-bar-chart__plot {
  position: absolute;
  inset: var(--plot-top) var(--plot-right) var(--plot-bottom) var(--plot-left);
  display: flex;
  align-items: flex-end;
  background: repeating-linear-gradient(
    to top,
    var(--grid-color) 0 1px,
    transparent 1px calc((100% - 1px) / 5)
  );
}

.skeleton-bar-chart__band {
  position: relative;
  display: flex;
  flex: 1 1 0;
  justify-content: center;
  align-items: flex-end;
  height: 100%;
}

.skeleton-bar-chart__bar {
  width: 62%;
  border-radius: 3px 3px 0 0;
}

.skeleton-bar-chart__x {
  position: absolute;
  top: calc(100% + 9px);
  left: 50%;
  width: 40px;
  transform: translateX(-50%);
}

.skeleton-bar-chart__y {
  position: absolute;
  right: calc(100% - var(--plot-left) + 8px);
  top: calc(
    var(--plot-top) + (100% - var(--plot-top) - var(--plot-bottom)) * var(--line) / 5 - 3px
  );
  width: 18px;
}

.skeleton-bar-chart__y--right {
  right: auto;
  left: calc(100% - var(--plot-right) + 8px);
}
</style>
