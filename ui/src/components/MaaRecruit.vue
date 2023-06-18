<script setup></script>

<template>
  <n-card>
    <template #header>
      <n-checkbox>
        <div class="card-title">Maa公招</div>
      </n-checkbox>
    </template>
    <n-h4>加急许可</n-h4>
    <p>不使用加急许可。</p>
    <n-h4>三星招募策略</n-h4>
    <p>招聘许可数量大于招募阈值时，招募三星干员。</p>
    <table class="recruit-3">
      <tr>
        <td>招募阈值</td>
        <td>
          <n-input-number />
        </td>
      </tr>
      <tr>
        <td>招募时限</td>
        <td>
          <n-radio-group class="radio-group">
            <n-radio value="false">7:40</n-radio>
            <n-radio value="true">9:00</n-radio>
          </n-radio-group>
        </td>
      </tr>
    </table>
    <n-table :single-line="false" size="small" class="big-table">
      <thead>
        <tr>
          <th>可保底</th>
          <th>招募选项</th>
          <th>邮件提醒</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>四星</td>
          <td>
            <n-radio-group class="radio-group">
              <n-radio value="keep">保留</n-radio>
              <n-radio value="740">7:40</n-radio>
              <n-radio value="900">9:00</n-radio>
            </n-radio-group>
          </td>
          <td>
            <n-checkbox />
          </td>
        </tr>
        <tr>
          <td>五星</td>
          <td>
            <n-radio-group class="radio-group">
              <n-radio value="keep">保留</n-radio>
              <n-radio value="900">9:00</n-radio>
            </n-radio-group>
          </td>
          <td>
            <n-checkbox />
          </td>
        </tr>
        <tr>
          <td>六星</td>
          <td>
            <n-radio-group class="radio-group">
              <n-radio value="keep">保留</n-radio>
              <n-radio value="900">9:00</n-radio>
            </n-radio-group>
          </td>
          <td>
            <n-checkbox />
          </td>
        </tr>
        <tr>
          <td>一星</td>
          <td>
            <n-radio-group class="radio-group">
              <n-radio value="keep">保留</n-radio>
              <n-radio value="100">1:00</n-radio>
              <n-radio value="350">3:50</n-radio>
            </n-radio-group>
          </td>
          <td>
            <n-checkbox />
          </td>
        </tr>
        <tr>
          <td>冲突</td>
          <td>
            <n-radio-group class="radio-group">
              <n-radio value="keep">保留</n-radio>
              <n-radio value="low" disabled>一星</n-radio>
              <n-radio value="high">高星</n-radio>
            </n-radio-group>
          </td>
          <td>
            <n-checkbox />
          </td>
        </tr>
      </tbody>
    </n-table>
    <p class="final">“冲突”表示支援机械词条与保底出现四星及更高稀有度干员的词条组合同时出现。</p>
  </n-card>
</template>

<style scoped lang="scss">
.card-title {
  font-weight: 500;
  font-size: 18px;
}

p {
  margin: 0 0 8px 0;
}

h4 {
  margin: 12px 0 10px 0;
}

.recruit-3 td {
  &:nth-child(1) {
    width: 64px;
  }

  &:nth-child(2) {
    width: 200px;
  }
}

.radio-group {
  display: inline-flex;
  gap: 10px;
  width: 200px;
}

.big-table {
  margin-top: 10px;
  width: 400px;

  th,
  td {
    text-align: center;
  }

  td {
    height: 24px;
  }
}

.final {
  margin: 16px 0 0;
}
</style>
