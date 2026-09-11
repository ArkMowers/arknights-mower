<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
const axios = inject('axios')
const state = ref(null)
const draft = ref({})
const busy = ref(false)
const error = ref('')
const notice = ref('')
const loadedRevision = ref(0)
const baseline = ref('')
const dirty = computed(() => JSON.stringify(draft.value) !== baseline.value)
const groups = [
  { title: '后台游戏', description: '声音与窗口行为由手机接管，Mower 和 MAA 共用同一游戏。', items: [
    ['mute_game', '自动静音游戏', '游戏运行期间关闭明日方舟声音，不改变手机媒体音量。部分机型可能影响游戏音频播放；关闭后恢复原声音权限。'],
    ['preview_sound', '手动操作时恢复声音', '打开顶部「游戏画面」时恢复声音，退出预览后继续按静音设置运行。'],
    ['force_fullscreen', '后台游戏强制全屏', '在下一次启动游戏时使用全屏窗口模式，适用于后台画面异常缩小。'],
    ['recover_game', '自动移回后台', '每 5 秒检查游戏位置；游戏意外回到主屏时尝试移回后台，失败会显示原因。']
  ] },
  { title: '屏幕与唤醒', description: '通常可直接熄屏运行。只有设备需要亮屏启动游戏时，才开启自动唤醒。', items: [
    ['wake_on_launch', '启动游戏或 MAA 时唤醒手机', '检查屏幕状态后唤醒，不修改系统锁屏密码。'],
    ['dismiss_keyguard', '自动解除滑动锁屏', '仅适用于无密码锁屏；PIN、图案或指纹锁屏仍需在手机上完成系统认证。'],
    ['keep_screen_on', '查看 Mower 时保持亮屏', '仅影响手机前台的 WebUI 和游戏预览，切换到其他应用后按系统设置熄屏。']
  ] },
  { title: '后台保活', description: '由 Android 前台服务维持 Python 调度。厂商的后台限制仍需在系统设置中放行。', items: [
    ['keep_cpu_awake', '服务运行期间保持 CPU 唤醒', '帮助熄屏后继续调度；关闭可降低耗电，但系统休眠可能使任务延迟。']
  ] }
]
watch(() => draft.value.wake_on_launch, (on) => { if (!on) draft.value.dismiss_keyguard = false })
function adopt(data) {
  state.value = data
  draft.value = { ...data.settings }
  baseline.value = JSON.stringify(draft.value)
  loadedRevision.value = data.revision
}
function fail(err) { error.value = err.response?.data?.message || err.message || '连接失败，请稍后重试' }
async function refresh(reset = false) {
  if (busy.value) return
  try {
    const { data } = await axios.get(`${import.meta.env.VITE_HTTP_URL}/android/settings`)
    if (busy.value) return
    if (reset || !state.value || !dirty.value) adopt(data)
    else state.value = data
  } catch (err) { fail(err) }
}
async function save() {
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const { data } = await axios.post(`${import.meta.env.VITE_HTTP_URL}/android/settings`, { settings: draft.value, revision: loadedRevision.value })
    adopt(data)
    notice.value = data.error || '已保存。亮屏与保活立即应用；窗口模式在下次启动游戏时应用。'
  } catch (err) { fail(err) }
  finally { busy.value = false }
}
async function action(name) {
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const { data } = await axios.post(`${import.meta.env.VITE_HTTP_URL}/android/action`, { action: name })
    if (!dirty.value) adopt(data); else state.value = data
    notice.value = data.device.last_action
  } catch (err) { fail(err) }
  finally { busy.value = false }
}
let timer
onMounted(async () => { await refresh(true); timer = setInterval(() => refresh(), 10000) })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <main class="android-settings">
    <div class="page-heading">
      <div><div class="eyebrow">MOWER · ANDROID</div><h1>后台与系统</h1><p>为手机上的罗德岛，安排安静、稳定的后台环境。</p></div>
      <n-button :disabled="busy" @click="error = ''; refresh(!dirty)">刷新状态</n-button>
    </div>
    <n-alert v-if="error" type="error" class="feedback" title="操作未完成">{{ error }}</n-alert>
    <n-alert v-if="notice" type="info" class="feedback">{{ notice }}</n-alert>
    <template v-if="state">
      <n-alert v-if="state.error" type="warning" class="feedback" title="设置与实际状态可能不同">{{ state.error }}</n-alert>
      <section class="status-grid" aria-label="手机实时状态">
        <n-card size="small" :bordered="false"><span class="status-label">后台连接</span><strong>{{ state.engine.connected ? (state.engine.prepared ? '游戏引擎就绪' : 'Shizuku 已连接') : '等待 Shizuku' }}</strong><small>Android {{ state.engine.android_version }} · {{ state.device.version }}</small></n-card>
        <n-card size="small" :bordered="false"><span class="status-label">手机屏幕</span><strong>{{ state.device.screen_on ? '亮屏' : '熄屏' }} · {{ state.device.locked ? '已锁定' : '未锁定' }}</strong><small>{{ state.device.secure_lock ? '安全锁屏由系统认证' : '无密码锁屏' }}</small></n-card>
        <n-card size="small" :bordered="false"><span class="status-label">后台运行</span><strong>{{ state.device.cpu_awake ? 'CPU 保持唤醒' : '允许 CPU 休眠' }}</strong><small>{{ state.device.battery_unrestricted ? '已免除电池优化' : '尚未免除电池优化' }}</small></n-card>
      </section>
      <n-card v-for="group in groups" :key="group.title" class="settings-card" :bordered="false">
        <h2>{{ group.title }}</h2><p class="section-description">{{ group.description }}</p>
        <div v-for="[key, title, description] in group.items" :key="key" class="setting-row">
          <label :for="`setting-${key}`"><span>{{ title }}</span><small>{{ description }}</small></label>
          <div class="switch-hit"><n-switch :id="`setting-${key}`" v-model:value="draft[key]" :aria-label="title" :disabled="busy || (key === 'dismiss_keyguard' && !draft.wake_on_launch) || (key === 'preview_sound' && !draft.mute_game)" /></div>
        </div>
        <p v-if="group.title === '后台游戏'" class="footnote">当前声音权限：{{ state.audio_mode === 'ignore' ? '已静音' : state.audio_mode === 'unknown' ? '暂不可读取' : state.audio_mode }}。识别分辨率固定为 1920 × 1080。手动预览保持 16:9，与手机界面全面屏适配独立。</p>
      </n-card>
      <n-card :bordered="false" class="settings-card">
        <h2>连接与检查</h2><p class="section-description">系统入口在手机上打开。请先让手机上的 Mower 保持前台；局域网页面也可操作。</p>
        <n-flex class="actions">
          <n-button :disabled="busy" @click="action('reconnect')">重新连接引擎</n-button>
          <n-button :disabled="busy || dirty" @click="action('test_wake')">测试唤醒与锁屏状态</n-button>
          <n-button :disabled="busy || dirty || !state.audio_restore_pending" @click="action('restore_audio')">关闭静音并恢复声音</n-button>
          <n-button :disabled="busy" @click="action('shizuku')">打开 Shizuku</n-button>
          <n-button :disabled="busy" @click="action('battery_settings')">电池优化设置</n-button>
          <n-button :disabled="busy" @click="action('app_settings')">应用与通知设置</n-button>
        </n-flex>
        <p class="footnote" role="status">{{ state.device.last_action }}</p>
      </n-card>
      <n-collapse class="compatibility">
        <n-collapse-item title="Meow 功能适配说明" name="compatibility">
          <p>已核对公开发布记录 v0.0.4-alpha 至 v0.21.4，及当前源码的后台、声音、屏幕和系统设置。</p>
          <p>任务定时、任务结束后关闭游戏、更新与外部通知沿用 Mower 原有设置。局域网访问使用手机顶部入口；正常模式和深夜模式沿用 Mower 主题。</p>
          <p>暂未引入 PIN／手势录制、硬件断电熄屏、悬浮窗／画中画、帧率监测、厂商超级岛通知和独立闹钟调度。后台识别暂不开放 720p，避免影响 Mower 识别坐标。</p>
          <router-link to="/mowersettings">Mower 设置</router-link> · <router-link to="/maasettings">MAA 设置</router-link>
        </n-collapse-item>
      </n-collapse>
      <div class="save-bar">
        <span>{{ dirty ? '有尚未保存的修改' : '设置已同步到手机' }}</span>
        <n-flex><n-button :disabled="busy || !dirty" @click="refresh(true)">撤销修改</n-button><n-button type="primary" :loading="busy" :disabled="!dirty" @click="save">保存设置</n-button></n-flex>
      </div>
    </template>
    <n-empty v-else description="正在读取手机设置；若连接失败，请刷新重试。" />
  </main>
</template>

<style scoped>
.android-settings { max-width: 1060px; margin: 0 auto; padding: 24px 20px 20px; font-variant-numeric: tabular-nums; }
.page-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
h1 { margin: 4px 0 6px; font-size: 28px; text-wrap: balance; }
h2 { font-size: 18px; margin: 0 0 6px; }
p { margin: 0; line-height: 1.7; text-wrap: pretty; }
.eyebrow { font-size: 11px; letter-spacing: 1.6px; opacity: .65; }
.page-heading p, .section-description, .footnote, small, .status-label { opacity: .7; }
.feedback { margin-bottom: 16px; }
.status-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 20px; }
.status-grid strong { display: block; font-size: 17px; margin: 8px 0 4px; }
.status-grid small { display: block; }
.status-label { font-size: 12px; }
.settings-card { margin-bottom: 16px; border-radius: 14px; }
.section-description { margin-bottom: 8px; }
.setting-row { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 17px 0; }
.setting-row + .setting-row { border-top: 1px solid rgba(128,128,128,.14); }
.setting-row label { cursor: pointer; flex: 1; }
.setting-row label > span { font-size: 15px; font-weight: 500; }
.setting-row small { display: block; line-height: 1.7; margin-top: 5px; max-width: 690px; }
.switch-hit { display: flex; align-items: center; justify-content: center; min-width: 44px; min-height: 44px; }
.switch-hit :deep(.n-switch)::before { content: ''; position: absolute; inset: -10px 0; }
.footnote { font-size: 12px; margin-top: 12px; }
.actions { margin-top: 18px; }
.android-settings :deep(.n-button) { min-height: 40px; }
.compatibility { margin: 24px 0; }
.compatibility p { margin-bottom: 10px; }
.save-bar { position: sticky; bottom: 0; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 0; background: var(--mower-surface); }
.save-bar > span { font-size: 13px; opacity: .7; }
@media (max-width: 640px) { .android-settings { padding: 20px 12px 12px; } .status-grid { grid-template-columns: 1fr; gap: 8px; } .page-heading { align-items: flex-start; } h1 { font-size: 24px; } .setting-row { gap: 12px; } .save-bar { flex-wrap: wrap; } }
</style>
