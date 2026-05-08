<template>
  <div class="overview-brief">
    <!-- loading -->
    <div v-if="loading" class="status-box">正在生成综合简报...</div>

    <!-- error -->
    <div v-else-if="error" class="status-box error-box">
      <p class="status-title">综合概览生成失败</p>
      <p class="status-desc">{{ error }}</p>
      <button class="btn-retry" @click="$emit('reload')">重新生成</button>
    </div>

    <!-- empty (无数据时) -->
    <div v-else-if="!data || !data.data_status" class="status-box">
      暂无综合概览数据，AI简报生成中或服务暂不可用
    </div>

    <!-- fallback / available -->
    <div v-else>
      <div v-if="data.data_status === 'fallback_generated'" class="fallback-badge">
        ⚠️ 当前为系统模板简报，AI服务暂不可用
      </div>
      <div v-if="data.data_status === 'ai_disabled'" class="fallback-badge">
        ℹ️ AI简报服务未启用
      </div>

      <!-- AI建议 -->
      <div class="suggestion-card" v-if="data.ai_suggestion">
        <div class="suggestion-row">
          <span class="suggestion-label">AI建议</span>
          <span :class="['suggestion-value', suggestCls(data.ai_suggestion)]">{{ data.ai_suggestion }}</span>
        </div>
        <div v-if="data.suggestion_reason" class="suggestion-reason">{{ data.suggestion_reason }}</div>
      </div>

      <!-- 简报 -->
      <div v-if="data.brief" class="brief-card">
        <h4>综合简报</h4>
        <p>{{ data.brief }}</p>
      </div>

      <!-- 正面标签 -->
      <div v-if="data.positive_tags?.length" class="tags-section">
        <h4 class="positive-title">正面因素</h4>
        <div class="tags-row">
          <span v-for="t in data.positive_tags" :key="t" class="tag tag-positive">{{ t }}</span>
        </div>
      </div>

      <!-- 负面标签 -->
      <div v-if="data.negative_tags?.length" class="tags-section">
        <h4 class="negative-title">负面因素</h4>
        <div class="tags-row">
          <span v-for="t in data.negative_tags" :key="t" class="tag tag-negative">{{ t }}</span>
        </div>
      </div>

      <!-- 核心要点 -->
      <div v-if="data.key_points?.length" class="points-section">
        <h4>核心要点</h4>
        <ul><li v-for="(p, i) in data.key_points" :key="i">{{ p }}</li></ul>
      </div>

      <!-- 免责声明 -->
      <div v-if="data.disclaimer" class="disclaimer">{{ data.disclaimer }}</div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  data: Object,
  loading: Boolean,
  error: [String, null],
})
defineEmits(['reload'])

function suggestCls(s) {
  const map = { '不关注': 'level-low', '只观察': 'level-mid', '开盘确认': 'level-high', '小仓试错': 'level-high', '不参与': 'level-low' }
  return map[s] || ''
}
</script>

<style scoped>
.status-box { text-align: center; padding: 40px; color: #667eea; }
.error-box { color: #ff4d4f; }
.status-title { font-size: 15px; font-weight: 600; margin-bottom: 8px; }
.status-desc { font-size: 13px; color: #666; }
.btn-retry { margin-top: 12px; padding: 6px 18px; border: 1px solid #667eea; border-radius: 4px; background: white; color: #667eea; cursor: pointer; }

.fallback-badge { background: #fffbe6; border: 1px solid #ffe58f; padding: 8px 14px; border-radius: 6px; font-size: 12px; color: #d46b08; margin-bottom: 12px; }

.suggestion-card { background: linear-gradient(135deg, #f8f9ff, #f0f0ff); padding: 16px; border-radius: 10px; margin-bottom: 14px; }
.suggestion-row { display: flex; align-items: center; gap: 12px; }
.suggestion-label { font-size: 14px; color: #666; font-weight: 600; }
.suggestion-value { font-size: 20px; font-weight: 700; padding: 4px 14px; border-radius: 8px; }
.suggestion-value.level-high { background: #f6ffed; color: #52c41a; }
.suggestion-value.level-mid { background: #fff7e6; color: #fa8c16; }
.suggestion-value.level-low { background: #f5f5f5; color: #999; }
.suggestion-reason { font-size: 13px; color: #666; margin-top: 8px; }

.brief-card { background: #fafafa; padding: 14px; border-radius: 8px; margin-bottom: 14px; }
.brief-card h4 { margin: 0 0 8px; font-size: 14px; color: #333; }
.brief-card p { margin: 0; font-size: 13px; color: #555; line-height: 1.7; }

.tags-section { margin-bottom: 14px; }
.tags-section h4 { margin: 0 0 8px; font-size: 14px; }
.positive-title { color: #52c41a; }
.negative-title { color: #ff4d4f; }
.tags-row { display: flex; gap: 6px; flex-wrap: wrap; }
.tag { padding: 3px 10px; border-radius: 12px; font-size: 12px; }
.tag-positive { background: #f6ffed; color: #52c41a; }
.tag-negative { background: #fff2f0; color: #ff4d4f; }

.points-section { background: #fafafa; padding: 12px 16px; border-radius: 8px; margin-bottom: 14px; }
.points-section h4 { margin: 0 0 8px; font-size: 14px; color: #333; }
.points-section ul { margin: 0; padding-left: 18px; }
.points-section li { font-size: 13px; color: #666; line-height: 1.7; }

.disclaimer { font-size: 11px; color: #bbb; text-align: center; margin-top: 14px; line-height: 1.5; }
</style>
