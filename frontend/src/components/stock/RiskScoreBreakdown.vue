<template>
  <div class="risk-section" v-if="isArray && items.length">
    <div v-if="riskFlags && riskFlags.length" class="risk-flags">
      <span v-for="(f, i) in riskFlags" :key="i" class="risk-flag">{{ f }}</span>
    </div>
    <div class="dim-grid">
      <div v-for="it in items" :key="it.name" class="dim-card">
        <div class="dim-header">
          <span class="dim-name">{{ it.name }}</span>
          <span class="dim-status" v-if="it.data_status !== 'available'">{{ statusLabel(it.data_status) }}</span>
          <span class="dim-score" :class="riskCls(it)">{{ it.score }} / {{ it.max_score }}</span>
        </div>
        <div class="dim-bar">
          <div class="dim-fill" :class="barCls(it)" :style="{ width: pct(it) + '%' }"></div>
        </div>
        <div class="dim-reason" v-if="it.reason">{{ it.reason }}</div>
        <div v-if="it.metrics && Object.keys(it.metrics).length" class="dim-metrics">
          <span v-for="(v, k) in it.metrics" :key="k" class="metric">{{ k }}: {{ v }}</span>
        </div>
      </div>
    </div>
    <div class="total-risk" v-if="riskScore != null">
      <span>风险总分：{{ riskScore.toFixed(0) }}</span>
      <span class="risk-level">{{ riskLevel || '--' }}</span>
    </div>
  </div>
  <div v-else class="empty">暂无风险拆解数据</div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  riskBreakdown: [Array, Object],
  riskScore: [Number, null],
  riskLevel: String,
  riskFlags: { type: Array, default: () => [] }
})

const isArray = computed(() => props.riskBreakdown && Array.isArray(props.riskBreakdown))
const items = computed(() => isArray.value ? props.riskBreakdown : [])

function statusLabel(s) {
  const map = { available: '', partial: '部分数据', not_integrated: '未接入', missing: '缺失' }
  return map[s] || s || ''
}
function pct(it) { return Math.min(100, (it.score / it.max_score) * 100) }
function riskCls(it) {
  const r = it.max_score > 0 ? it.score / it.max_score : 0
  return r >= 0.6 ? 'r-high' : r >= 0.3 ? 'r-mid' : 'r-low'
}
function barCls(it) {
  const r = it.max_score > 0 ? it.score / it.max_score : 0
  return r >= 0.6 ? 'b-high' : r >= 0.3 ? 'b-mid' : 'b-low'
}
</script>

<style scoped>
.risk-flags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
.risk-flag { background: #fff2f0; color: #ff4d4f; padding: 4px 10px; border-radius: 12px; font-size: 12px; }
.dim-grid { display: flex; flex-direction: column; gap: 10px; }
.dim-card { background: #fafafa; padding: 10px 14px; border-radius: 8px; }
.dim-header { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 4px; font-size: 13px; }
.dim-name { color: #333; font-weight: 600; }
.dim-status { font-size: 10px; color: #999; background: #f0f0f0; padding: 1px 6px; border-radius: 8px; }
.dim-score.r-high { color: #ff4d4f; }
.dim-score.r-mid { color: #fa8c16; }
.dim-score.r-low { color: #52c41a; }
.dim-bar { height: 6px; background: #f0f0f0; border-radius: 3px; overflow: hidden; }
.dim-fill { height: 100%; border-radius: 3px; transition: width 0.4s; }
.b-high { background: #ff4d4f; }
.b-mid { background: #fa8c16; }
.b-low { background: #52c41a; }
.dim-reason { font-size: 12px; color: #666; margin-top: 4px; }
.dim-metrics { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
.metric { font-size: 10px; background: #f0f0f0; padding: 2px 6px; border-radius: 6px; color: #999; }
.total-risk { display: flex; gap: 16px; padding: 12px; background: #fafafa; border-radius: 8px; margin-top: 16px; font-size: 14px; font-weight: 600; }
.risk-level { color: #fa8c16; }
.empty { color: #999; text-align: center; padding: 40px; }
</style>
