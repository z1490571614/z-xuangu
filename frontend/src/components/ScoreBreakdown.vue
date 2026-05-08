<template>
  <div class="score-breakdown" v-if="score?.score_breakdown">
    <div class="dimension" v-for="(val, key) in score.score_breakdown" :key="key">
      <div class="dim-header">
        <span class="dim-name">{{ dimLabel(key) }}</span>
        <span class="dim-score">{{ val.score || 0 }} / {{ val.max }}</span>
      </div>
      <div class="dim-bar">
        <div class="dim-fill" :style="{ width: (val.score / val.max * 100) + '%' }"></div>
      </div>
      <ul v-if="val.reasons?.length" class="dim-reasons">
        <li v-for="r in val.reasons" :key="r">{{ r }}</li>
      </ul>
    </div>
    <div class="total-score">
      <span>总分: {{ score.rule_score?.toFixed(1) }}</span>
      <span class="level">等级: {{ score.score_level }}</span>
    </div>
  </div>
  <div v-else class="empty">暂无评分数据</div>
</template>

<script setup>
const props = defineProps({ score: Object })
function dimLabel(key) {
  const labels = {
    limit_up_gene: '涨停基因',
    seal_reliability: '封板可靠性',
    trend_strength: '短期趋势',
    auction_momentum: '竞价承接',
    risk_deduction: '风险扣分',
  }
  return labels[key] || key
}
</script>
<style scoped>
.dimension { margin-bottom: 16px; }
.dim-header { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px; }
.dim-name { color: #333; font-weight: 600; }
.dim-score { color: #667eea; }
.dim-bar { height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden; }
.dim-fill { height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); border-radius: 4px; transition: width 0.5s; }
.dim-reasons { margin: 6px 0 0; padding-left: 16px; font-size: 12px; color: #666; }
.dim-reasons li { line-height: 1.6; }
.total-score { display: flex; gap: 20px; padding: 12px; background: #fafafa; border-radius: 8px; font-size: 14px; font-weight: 600; }
.level { color: #764ba2; }
.empty { color: #999; text-align: center; padding: 40px; }
</style>
