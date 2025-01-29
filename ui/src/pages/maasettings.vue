<script setup lang="jsx">
const scale_marks = {}
const display_marks = [0.5, 1.0, 1.5, 2.0, 3.0]
for (let i = 0.5; i <= 3.0; i += 0.25) {
  scale_marks[i] = display_marks.includes(i) ? `${i * 100}%` : ''
}
</script>

<template>
  <div class="grid-two">
    <div class="grid-left">
      <div><maa-basic /></div>
      <div><maa-weekly /></div>
      <div><maa-reward /></div>
      <div><long-tasks /></div>
    </div>

    <div class="grid-right">
      <div><clue /></div>
      <div><maa-weekly-new /></div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.threshold {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
}

.mower-basic {
  width: 100%;

  td:nth-child(1) {
    width: 120px;
  }

  td:nth-child(3) {
    padding-left: 6px;
    width: 40px;
  }
}

.riic-conf {
  width: 100%;

  td {
    &:nth-child(1) {
      width: 130px;
    }

    &:nth-child(3) {
      padding-left: 12px;
      width: 120px;
    }
  }
}

.coord {
  td {
    width: 120px;

    &:nth-child(1),
    &:nth-child(3) {
      width: 30px;
    }

    &:nth-child(2) {
      padding-right: 30px;
    }
  }
}

.coord-label {
  width: 40px;
  padding-left: 8px;
}

p {
  margin: 0 0 8px 0;
}

h4 {
  margin: 12px 0 10px 0;
}

.time-table {
  width: 100%;
  margin-bottom: 12px;

  td:nth-child(1) {
    width: 40px;
  }
}

.scale {
  width: 60px;
  text-align: right;
}

.scale-apply {
  margin-left: 24px;
}

.waiting-table {
  th,
  td {
    padding: 4px;
    min-width: 70px;
    width: 100px;

    &:first-child {
      width: auto;
      padding: 4px 8px;
    }
  }
}
</style>

<style>
/*小于1400的内容！*/
@media (max-width: 1399px) {
  .grid-two {
    margin: 0 0 -10px 0;
    width: 100%;
    max-width: 600px;
  }

  .grid-left {
    display: grid;
    row-gap: 10px;
    grid-template-columns: 100%;
  }

  .grid-right {
    display: grid;
    row-gap: 10px;
    grid-template-columns: 100%;
    margin-top: 10px;
  }
}

/*双栏 大于1400的内容 */
@media (min-width: 1400px) {
  .grid-two {
    display: grid;
    grid-template-columns: minmax(0px, 1fr) minmax(0px, 1fr);
    align-items: flex-start;
    gap: 5px;
  }

  .grid-left {
    display: grid;
    gap: 5px;
    grid-template-columns: 100%;
    max-width: 600px;
  }

  .grid-right {
    display: grid;
    gap: 5px;
    grid-template-columns: 100%;
    max-width: 600px;
  }
}

.n-divider:not(.n-divider--vertical) {
  margin: 14px 0 8px;
}

/* .results {
  display: grid;
  grid-template-rows: masonry;
  grid-template-columns: repeat(2, 600px);
  gap: 10px 10px ;
  justify-content: center;
} */
/* 实验性瀑布流（firefox nightly） */
</style>
