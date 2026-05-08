<template>
  <div class="earnings-panel">
    <div class="status-msg" v-if="data?.data_status === 'not_integrated'">
      <span class="status-icon">🔌</span>
      <p>业绩排雷功能暂未接入</p>
      <p class="sub">{{ data?.message || '财务数据源未配置，需接入 Tushare income/fina_indicator 接口（not_integrated）' }}</p>
    </div>
    <div class="status-msg" v-else-if="hasData">
      <div v-if="data.summary" class="summary-section">
        <p>{{ data.summary }}</p>
      </div>
      <div v-if="data.items && data.items.length" class="items-section">
        <div v-for="(item, i) in data.items" :key="i" class="item">
          <span class="item-label">{{ item.label }}</span>
          <span class="item-val">{{ item.value }}</span>
        </div>
      </div>
    </div>
    <div v-else class="empty">暂无业绩风险数据</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ earnings: Object })
const data = computed(() => props.earnings || {})
const hasData = computed(() => Object.keys(data.value).length > 1)
</script>

<style scoped>
.status-msg { text-align: center; padding: 40px 20px; background: #fafafa; border-radius: 8px; }
.status-icon { font-size: 32px; display: block; margin-bottom: 10px; }
.status-msg p { margin: 4px 0; color: #666; }
.status-msg .sub { font-size: 12px; color: #999; }
.summary-section { background: #fafafa; padding: 12px 16px; border-radius: 8px; margin-bottom: 12px; }
.summary-section p { margin: 0; font-size: 13px; color: #666; line-height: 1.6; }
.items-section { display: flex; flex-direction: column; gap: 8px; }
.item { display: flex; justify-content: space-between; padding: 8px 12px; background: #fafafa; border-radius: 6px; font-size: 13px; }
.item-label { color: #666; }
.item-val { font-weight: 600; color: #333; }
.empty { color: #999; text-align: center; padding: 40px; }
</style>
