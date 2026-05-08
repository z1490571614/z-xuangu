<template>
  <div class="plan-panel" v-if="plan?.key_observations?.length">
    <div class="section">
      <h4>开盘情景</h4>
      <p>{{ plan.open_scenario }}</p>
    </div>
    <div class="section">
      <h4>观察要点</h4>
      <ul><li v-for="(o, i) in plan.key_observations" :key="i">{{ o }}</li></ul>
    </div>
    <div class="section" v-if="plan.risk_reminder">
      <h4>风险提示</h4>
      <p class="risk">{{ plan.risk_reminder }}</p>
    </div>
  </div>
  <div v-else class="empty">暂无次日预案数据</div>
</template>

<script setup>
defineProps({ plan: Object })
</script>
<style scoped>
.section { margin-bottom: 16px; }
.section h4 { margin: 0 0 8px; font-size: 14px; color: #333; }
.section p { margin: 0; font-size: 13px; color: #666; line-height: 1.6; }
.section ul { margin: 0; padding-left: 20px; }
.section li { font-size: 13px; color: #666; line-height: 1.8; }
.risk { color: #ff4d4f; font-weight: 600; }
.empty { color: #999; text-align: center; padding: 40px; }
</style>
