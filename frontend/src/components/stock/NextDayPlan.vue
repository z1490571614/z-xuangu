<template>
  <div class="next-day-plan" v-if="hasData">
    <div v-if="data.summary" class="summary">
      <p>{{ data.summary }}</p>
    </div>
    <div v-if="data.watch_points && data.watch_points.length" class="watch-points">
      <h4>观察重点</h4>
      <ul>
        <li v-for="(p, i) in data.watch_points" :key="i">{{ p }}</li>
      </ul>
    </div>
  </div>
  <div v-else class="empty">暂无次日预案数据</div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ nextDayPlan: Object })
const data = props.nextDayPlan || {}
const hasData = computed(() => Object.keys(data).length > 0)
</script>

<style scoped>
.summary { background: #fafafa; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; }
.summary p { margin: 0; font-size: 13px; color: #666; line-height: 1.6; }
.watch-points h4 { margin: 0 0 12px; font-size: 14px; color: #333; }
.watch-points ul { margin: 0; padding-left: 20px; }
.watch-points li { font-size: 13px; color: #666; line-height: 1.8; padding: 4px 0; }
.empty { color: #999; text-align: center; padding: 40px; }
</style>
