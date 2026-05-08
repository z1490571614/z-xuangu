<template>
  <div class="alpha-breakdown" v-if="isArray && items.length">
    <div class="dim-card" v-for="it in items" :key="it.name">
      <div class="dim-header">
        <span class="dim-name">{{ it.name }}</span>
        <span class="dim-score">{{ it.score }} / {{ it.max_score }}</span>
      </div>
      <div class="dim-bar">
        <div class="dim-fill" :style="{ width: pct(it) + '%' }"></div>
      </div>
      <div class="dim-reason">{{ it.reason }}</div>
      <div v-if="it.metrics && Object.keys(it.metrics).length" class="dim-metrics">
        <span v-for="(v, k) in it.metrics" :key="k" class="metric">{{ k }}: {{ v }}</span>
      </div>
    </div>
  </div>
  <div v-else-if="!isArray && hasAlt" class="v1-format">
    <div class="v1-notice">旧Alpha格式数据，即将迁移到新格式</div>
  </div>
  <div v-else class="empty">暂无Alpha评分数据</div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ alphaBreakdown: [Array, Object] })

const isArray = computed(() => props.alphaBreakdown && Array.isArray(props.alphaBreakdown))
const items = computed(() => isArray.value ? props.alphaBreakdown : [])
const hasAlt = computed(() => !isArray.value && props.alphaBreakdown && Object.keys(props.alphaBreakdown).length > 0)

function pct(it) {
  if (!it.max_score) return 0
  return Math.min(100, (it.score / it.max_score) * 100)
}
</script>

<style scoped>
.dim-card { background: #fafafa; padding: 12px 14px; border-radius: 8px; margin-bottom: 10px; }
.dim-header { display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 13px; }
.dim-name { color: #333; font-weight: 600; }
.dim-score { color: #667eea; }
.dim-bar { height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden; margin-bottom: 6px; }
.dim-fill { height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); border-radius: 4px; transition: width 0.4s; }
.dim-reason { font-size: 12px; color: #666; margin-bottom: 4px; }
.dim-metrics { display: flex; gap: 8px; flex-wrap: wrap; }
.metric { font-size: 11px; background: #f0f0f0; padding: 2px 8px; border-radius: 8px; color: #999; }
.empty { color: #999; text-align: center; padding: 40px; }
.v1-format { padding: 20px; }
.v1-notice { background: #fffbe6; padding: 10px; border-radius: 6px; font-size: 12px; color: #fa8c16; }
</style>
