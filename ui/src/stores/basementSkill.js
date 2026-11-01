import { ref } from 'vue'
import axios from 'axios'
import skillBundled from '../../../arknights_mower/data/building_skill.json'
import bufferBundled from '@/pages/basement_skill/buffer.json'

// 基建技能页数据：构建期内联的 JSON 作为内置兜底，运行时优先用资源包下发的版本。
// 模块级 ref 让技能页和干员技能提示共用目录及练度快照，避免重复保存状态。
const skill = ref(skillBundled)
const buffer = ref(bufferBundled)
const snapshot = ref(null)
let snapshotRequest = null
let loaded = false

function loadOwnedOperators() {
  if (!snapshotRequest) {
    snapshotRequest = axios
      .get(`${import.meta.env.VITE_HTTP_URL}/basement-skill/operators`)
      .then(({ data }) => {
        snapshot.value = data
      })
      .finally(() => {
        snapshotRequest = null
      })
  }
  return snapshotRequest
}

export function useBasementSkill() {
  const load = async () => {
    if (loaded) return
    try {
      const [sk, bf] = await Promise.all([
        axios.get(`${import.meta.env.VITE_HTTP_URL}/basement_skill/skill.json`),
        axios.get(`${import.meta.env.VITE_HTTP_URL}/basement_skill/buffer.json`)
      ])
      skill.value = sk.data
      buffer.value = bf.data
      loaded = true // 拉取成功才置位；失败则本次保留内置兜底，下次进入页面会重试
    } catch {
      // 资源包未安装或加载失败：保留内置兜底，下次进入页面再试
    }
  }
  return { skill, buffer, load, snapshot, loadOwnedOperators }
}
