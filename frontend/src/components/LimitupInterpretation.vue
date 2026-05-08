<template>
  <div class="limitup-panel">
    <div class="grid">
      <div class="stat-card"><label>100日涨停次数</label><span class="value">{{ stock?.limit_up_count ?? '--' }}</span></div>
      <div class="stat-card"><label>100日触板次数</label><span class="value">{{ stock?.touch_days ?? '--' }}</span></div>
      <div class="stat-card"><label>100日封板次数</label><span class="value">{{ stock?.limit_up_days ?? '--' }}</span></div>
      <div class="stat-card"><label>100日封板率</label><span class="value">{{ stock?.seal_rate != null ? stock.seal_rate.toFixed(1) + '%' : '--' }}</span></div>
      <div class="stat-card"><label>10日涨幅</label><span class="value" :class="stock?.rise_10d_pct > 0 ? 'positive' : 'negative'">{{ stock?.rise_10d_pct != null ? stock.rise_10d_pct.toFixed(2) + '%' : '--' }}</span></div>
    </div>
  </div>
</template>

<script setup>
defineProps({ stock: Object })
</script>
<style scoped>
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.stat-card { background: #fafafa; padding: 16px; border-radius: 8px; text-align: center; }
.stat-card label { display: block; font-size: 12px; color: #999; margin-bottom: 6px; }
.value { font-size: 22px; font-weight: 700; color: #333; }
.positive { color: #cf1322; }
.negative { color: #389e0d; }
</style>
