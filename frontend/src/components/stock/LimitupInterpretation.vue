<template>
  <div class="limitup-panel" v-if="hasData">
    <div class="stats-grid">
      <div class="stat-item"><label>100日涨停次数</label><span class="val">{{ data.limit_up_count ?? '--' }}</span></div>
      <div class="stat-item"><label>100日触板次数</label><span class="val">{{ data.touch_days ?? '--' }}</span></div>
      <div class="stat-item"><label>100日封板率</label><span class="val">{{ data.seal_rate != null ? data.seal_rate.toFixed(1) + '%' : '--' }}</span></div>
      <div class="stat-item"><label>近10日涨幅</label><span :class="['val', pctCls(data.rise_10d_pct)]">{{ fmtPct(data.rise_10d_pct) }}</span></div>
      <div class="stat-item"><label>昨日涨幅</label><span :class="['val', pctCls(data.pre_change_pct)]">{{ fmtPct(data.pre_change_pct) }}</span></div>
    </div>
    <div v-if="data.summary" class="interpretation">
      <h4>解读</h4>
      <p>{{ data.summary }}</p>
    </div>
    <div v-if="data.tags && data.tags.length" class="tags-section">
      <span v-for="(t, i) in data.tags" :key="i" class="tag">{{ t }}</span>
    </div>
  </div>
  <div v-else class="empty">暂无涨停异动解读数据</div>
</template>

<script setup>
const props = defineProps({ limitup: Object })
const data = props.limitup || {}
const hasData = computed(() => Object.keys(data).length > 0)

import { computed } from 'vue'

function pctCls(v) {
  if (v == null) return ''
  return v > 0 ? 'positive' : v < 0 ? 'negative' : ''
}
function fmtPct(v) { return v != null ? Number(v).toFixed(2) + '%' : '--' }
</script>

<style scoped>
.stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-item { background: #fafafa; padding: 14px; border-radius: 8px; text-align: center; }
.stat-item label { display: block; font-size: 12px; color: #999; margin-bottom: 6px; }
.val { font-size: 20px; font-weight: 700; color: #333; }
.positive { color: #cf1322; }
.negative { color: #389e0d; }
.interpretation { background: #fafafa; padding: 12px 16px; border-radius: 8px; margin-bottom: 12px; }
.interpretation h4 { margin: 0 0 8px; font-size: 14px; color: #333; }
.interpretation p { margin: 0; font-size: 13px; color: #666; line-height: 1.6; }
.tags-section { display: flex; gap: 6px; flex-wrap: wrap; }
.tag { background: #f5f5f5; padding: 4px 10px; border-radius: 12px; font-size: 12px; color: #666; }
.empty { color: #999; text-align: center; padding: 40px; }
</style>
