<template>
  <div class="anomaly-panel">
    <!-- 加载状态 -->
    <div v-if="loading" class="state-msg">加载异动解读中...</div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="state-card error-card">
      <div class="error-text">异动解读加载失败</div>
      <p>{{ error }}</p>
      <button class="btn-retry" @click="$emit('reload')">重新加载</button>
    </div>

    <!-- 无数据状态 -->
    <div v-else-if="!data || !isAvailable" class="state-card empty-card">
      <div class="status-icon">📋</div>
      <div class="status-text">{{ statusText }}</div>
      <div style="margin-top: 12px;">
        <button class="btn-retry" @click="$emit('reload')">刷新数据</button>
      </div>
    </div>

    <!-- 正常状态 -->
    <div v-else class="tonghuashan-content">
      <!-- 头部标题栏 -->
      <div class="header">
        <span class="title">异动解读</span>
        <span class="date">{{ data.trade_date || '' }}</span>
        <span class="history-link" style="cursor: pointer;">历史异动 &gt;</span>
      </div>

      <!-- 核心标签行 -->
      <div class="core-tags">{{ data.core_tags_line || '无明确催化' }}</div>

      <!-- 行业原因 -->
      <div v-if="data.industry_reason" class="section">
        <div class="section-title">行业原因：</div>
        <div class="section-content">{{ data.industry_reason }}</div>
      </div>

      <!-- 公司原因 -->
      <div class="section">
        <div class="section-title">公司原因：</div>
        <div class="section-content">
          <div v-for="(item, idx) in safeReasons" :key="'reason-' + idx" class="reason-item">{{ item }}</div>
        </div>
      </div>

      <!-- 行情背景 -->
      <div v-if="data.market_background" class="market-bg" style="background: #fafafa; padding: 8px 12px; border-radius: 4px; margin-bottom: 12px; font-size: 13px; color: #666;">
        {{ data.market_background }}
      </div>

      <!-- 免责声明 -->
      <div class="disclaimer">（{{ data.disclaimer || '本内容由系统根据公开信息整理生成，仅供参考' }}）</div>

      <!-- 底部按钮 -->
      <div class="footer-buttons">
        <div class="collapse-btn" style="cursor: pointer;">
          收起 <span class="arrow">↑</span>
        </div>
        <div class="detail-btn" style="cursor: pointer;">查看详情</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: Object,
  loading: Boolean,
  error: [String, null],
})
defineEmits(['reload'])

const isAvailable = computed(() => {
  if (!props.data) return false
  return props.data.data_status &&
    !['fetch_failed', 'source_not_configured'].includes(props.data.data_status)
})

const statusText = computed(() => {
  if (!props.data) return '暂无异动解读数据'
  const s = props.data.data_status
  const map = {
    source_not_configured: '异动解读数据源未配置，请检查公告/新闻接口配置',
    fetch_failed: '异动解读数据拉取失败，请稍后重试',
    no_data: '当日未发现明确公告、新闻或题材异动，仅保留行情数据',
    generated_from_market_only: '当前解读仅基于行情和盘口生成，未匹配到公告或新闻',
    partial: '部分数据源不可用，当前结果可能不完整',
    no_3d_news: '近3个交易日无明确催化信息',
  }
  return map[s] || '暂无异动解读数据'
})

const safeReasons = computed(() => {
  if (!props.data?.company_reasons) {
    return ['近3个交易日无公司重大公告发布，股价异动主要由资金情绪驱动']
  }
  if (Array.isArray(props.data.company_reasons)) {
    return props.data.company_reasons
  }
  try {
    return JSON.parse(props.data.company_reasons)
  } catch {
    return [String(props.data.company_reasons)]
  }
})

function typeLabel(type) {
  const map = {
    announcement: '公告',
    news: '新闻',
    research: '研报',
    earnings: '业绩',
    capital_event: '资本',
    market_behavior: '行情',
    sector: '题材',
    market_background: '行情',
  }
  return map[type] || type
}
</script>

<style scoped>
/* 整体容器 - 完全复刻同花顺白色弹窗样式 */
.anomaly-panel {
  width: 100%;
  max-width: 420px;
  background: #ffffff;
  border-radius: 8px;
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 14px;
  line-height: 1.8;
  color: #333333;
}

/* 加载/状态提示 */
.state-msg {
  color: #667eea;
  text-align: center;
  padding: 40px;
}
.state-card {
  text-align: center;
  padding: 40px 20px;
  border-radius: 10px;
}
.error-card {
  background: #fff2f0;
}
.error-text {
  color: #ff4d4f;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 8px;
}
.btn-retry {
  margin-top: 12px;
  padding: 6px 18px;
  border: 1px solid #667eea;
  border-radius: 4px;
  background: white;
  color: #667eea;
  cursor: pointer;
}
.empty-card {
  background: #fafafa;
}
.status-icon {
  font-size: 32px;
  margin-bottom: 10px;
}
.status-text {
  color: #666;
  font-size: 13px;
  line-height: 1.6;
  max-width: 400px;
  margin: 0 auto;
}

/* ======================================== */
/* 同花顺1:1复刻样式 */
/* ======================================== */

.tonghuashan-content {
  /* 同花顺样式专用容器 */
}

/* 头部标题栏 */
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
}

.title {
  color: #333;
}

.date {
  color: #666666;
  font-weight: 400;
  margin-left: 8px;
}

.history-link {
  color: #1890ff;
  font-size: 14px;
  font-weight: 400;
  cursor: pointer;
}

/* 核心标签行 - 无背景，纯文字+号连接 */
.core-tags {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 16px;
  color: #333333;
}

/* 通用区块样式 */
.section {
  margin-bottom: 16px;
}

.section-title {
  font-weight: 600;
  margin-bottom: 8px;
  color: #333333;
}

.section-content {
  color: #333333;
  text-align: justify;
}

/* 公司原因分点 */
.reason-item {
  margin-bottom: 12px;
}

/* 免责声明 */
.tonghuashan-content .disclaimer {
  font-size: 12px;
  color: #999999;
  line-height: 1.6;
  margin: 20px 0;
}

/* 底部按钮 */
.footer-buttons {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

.collapse-btn {
  color: #1890ff;
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
}

.arrow {
  margin-left: 4px;
  font-size: 12px;
}

.detail-btn {
  color: #1890ff;
  font-size: 14px;
  cursor: pointer;
}

/* ======================================== */
/* 旧版兼容样式 */
/* ======================================== */

.summary-card {
  background: linear-gradient(135deg, #f8f9ff, #f0f0ff);
  padding: 16px;
  border-radius: 10px;
  margin-bottom: 16px;
}
.title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.title-row h3 {
  margin: 0;
  font-size: 14px;
  color: #333;
}
.date-badge {
  background: #e6f7ff;
  color: #1890ff;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
}
.summary-title {
  margin: 8px 0;
  font-size: 18px;
  color: #262626;
  line-height: 1.4;
}
.summary-text {
  color: #666;
  font-size: 13px;
  line-height: 1.6;
  margin: 8px 0;
}

.tags-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 10px;
}
.tag-badge {
  background: #f0f0f0;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  color: #666;
}

.event-card {
  padding: 14px;
  border-radius: 8px;
  margin-bottom: 10px;
  border: 1px solid #f0f0f0;
  background: white;
}
.event-card.high {
  border-left: 3px solid #ff4d4f;
}
.event-card.medium {
  border-left: 3px solid #fa8c16;
}
.event-card.low {
  border-left: 3px solid #d9d9d9;
}
.event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.event-left {
  display: flex;
  align-items: center;
  gap: 6px;
}
.event-type-badge {
  padding: 1px 8px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 600;
}
.event-type-badge.announcement {
  background: #fff1f0;
  color: #cf1322;
}
.event-type-badge.news {
  background: #e6f7ff;
  color: #1890ff;
}
.event-type-badge.research {
  background: #fff7e6;
  color: #fa8c16;
}
.event-type-badge.earnings {
  background: #f6ffed;
  color: #52c41a;
}
.event-type-badge.capital_event {
  background: #fff7e6;
  color: #d46b08;
}
.event-type-badge.market_behavior {
  background: #f9f0ff;
  color: #722ed1;
}
.importance-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}
.importance-dot.high {
  background: #ff4d4f;
}
.importance-dot.medium {
  background: #fa8c16;
}
.importance-dot.low {
  background: #d9d9d9;
}
.event-date {
  font-size: 12px;
  color: #999;
}
.event-title {
  font-size: 14px;
  color: #262626;
  font-weight: 500;
  margin-bottom: 4px;
}
.event-content {
  font-size: 13px;
  color: #666;
  line-height: 1.5;
}
.event-keywords {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 6px;
}
.kw-tag {
  background: #f5f5f5;
  padding: 1px 8px;
  border-radius: 8px;
  font-size: 11px;
  color: #999;
}
.event-source {
  font-size: 11px;
  color: #bbb;
  margin-top: 6px;
}

.risk-card {
  background: #fffbe6;
  border: 1px solid #ffe58f;
  padding: 14px;
  border-radius: 8px;
  margin-top: 12px;
}
.risk-card h3 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #d46b08;
}
.risk-card ul {
  margin: 0;
  padding-left: 16px;
}
.risk-card li {
  font-size: 13px;
  color: #666;
  line-height: 1.8;
}

.anomaly-content .disclaimer {
  font-size: 11px;
  color: #bbb;
  text-align: center;
  margin-top: 16px;
  padding: 10px;
  line-height: 1.5;
}
</style>
