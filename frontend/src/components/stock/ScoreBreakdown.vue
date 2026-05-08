<template>
  <div class="score-breakdown" v-if="hasData">
    <div class="dimension" v-for="item in dimensions" :key="item.key">
      <div class="dim-header">
        <span class="dim-name">{{ item.label }}</span>
        <span class="dim-score">{{ item.score }} / {{ item.max }}</span>
      </div>
      <div class="dim-bar">
        <div class="dim-fill" :style="{ width: pct(item) + '%' }"></div>
      </div>
      <ul v-if="item.reasons && item.reasons.length" class="dim-reasons">
        <li v-for="(r, i) in item.reasons" :key="i">{{ r }}</li>
      </ul>
    </div>
  </div>
  <div v-else class="empty">暂无评分拆解数据</div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ score: Object })

const breakdown = computed(() => props.score?.score_breakdown || {})

const dimensions = computed(() => {
  const map = {
    limit_up_gene: '涨停基因',
    seal_reliability: '封板可靠性',
    trend_strength: '短期趋势',
    auction_momentum: '竞价承接',
    risk_deduction: '风险扣分',
  }
  const bd = breakdown.value
  return Object.keys(map)
    .filter(k => bd[k] !== undefined)
    .map(k => ({
      key: k,
      label: map[k],
      score: bd[k].score ?? 0,
      max: bd[k].max ?? 0,
      reasons: bd[k].reasons || [],
    }))
})

const hasData = computed(() => dimensions.value.length > 0)

function pct(item) {
  if (!item.max) return 0
  return Math.min(100, (item.score / item.max) * 100)
}
</script>

<style scoped>
.dimension { margin-bottom: 16px; }
.dim-header { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px; }
.dim-name { color: #333; font-weight: 600; }
.dim-score { color: #667eea; }
.dim-bar { height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden; }
.dim-fill { height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); border-radius: 4px; transition: width 0.4s; }
.dim-reasons { margin: 6px 0 0; padding-left: 16px; font-size: 12px; color: #666; }
.dim-reasons li { line-height: 1.6; }
.empty { color: #999; text-align: center; padding: 40px; }
</style>
