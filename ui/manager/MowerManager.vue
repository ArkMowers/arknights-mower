<script setup>
import PlayIcon from '@vicons/ionicons5/Play'
import PlusIcon from '@vicons/ionicons5/Add'
import TrashOutline from '@vicons/ionicons5/TrashOutline'
import PencilIcon from '@vicons/ionicons5/Pencil'
import DotIcon from '@vicons/ionicons5/EllipsisHorizontal'
import CheckIcon from '@vicons/ionicons5/CheckmarkSharp'
import CrossIcon from '@vicons/ionicons5/CloseSharp'
</script>

<template>
  <div class="mower-list">
    <n-card size="small">
      <template #header>
        <div class="header">
          <div>实例名称</div>
          <n-button size="tiny">
            <template #icon>
              <n-icon>
                <pencil-icon />
              </n-icon>
            </template>
          </n-button>
          <n-button type="error" ghost size="tiny">
            <template #icon>
              <n-icon>
                <trash-outline />
              </n-icon>
            </template>
          </n-button>
          <div class="expand"></div>
          <n-button type="primary" size="small">
            <template #icon>
              <n-icon>
                <play-icon />
              </n-icon>
            </template>
          </n-button>
        </div>
      </template>
      <div class="folder">
        <code class="folder-content">/home/zhao/Documents/mower-profile</code>
        <n-button size="tiny">
          <template #icon>
            <n-icon>
              <dot-icon />
            </n-icon>
          </template>
        </n-button>
      </div>
    </n-card>
    <n-card size="small">
      <template #header>
        <div class="header">
          <n-input placeholder="实例名称" />
          <n-button type="primary" size="tiny" circle>
            <template #icon>
              <n-icon>
                <check-icon />
              </n-icon>
            </template>
          </n-button>
          <n-button type="error" size="tiny" circle>
            <template #icon>
              <n-icon>
                <cross-icon />
              </n-icon>
            </template>
          </n-button>
        </div>
      </template>
      <div class="folder">
        <code class="folder-content">/home/zhao/Documents/mower-profile</code>
      </div>
    </n-card>
    <n-button size="large" dashed>
      <template #icon>
        <n-icon>
          <plus-icon />
        </n-icon>
      </template>
      添加实例
    </n-button>
  </div>
</template>

<style scoped>
.mower-list {
  box-sizing: border-box;
  width: 100vw;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.header {
  display: flex;
  gap: 6px;
  align-items: center;
}

.expand {
  flex-grow: 1;
}

.folder {
  display: flex;
  gap: 6px;
  align-items: center;
}

.folder-content {
  word-break: break-all;
  flex-grow: 1;
}
</style>
