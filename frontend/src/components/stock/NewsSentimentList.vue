<template>
  <div class="news-sentiment-container">
    <!-- 情感统计 -->
    <div v-if="sentimentCount" class="sentiment-summary">
      <span class="summary-item positive">
        <span class="dot"></span>
        利好：{{ sentimentCount.positive }}条
      </span>
      <span class="summary-item negative">
        <span class="dot"></span>
        利空：{{ sentimentCount.negative }}条
      </span>
      <span class="summary-item neutral">
        <span class="dot"></span>
        中性：{{ sentimentCount.neutral }}条
      </span>
    </div>

    <!-- 新闻列表 -->
    <div v-if="newsList && newsList.length" class="news-list">
      <div v-for="(item, index) in newsList" :key="index" class="news-item">
        <div class="news-header">
          <span :class="['sentiment-tag', item.sentiment_type || 'neutral']">
            {{ getSentimentLabel(item.sentiment_type) }}
          </span>
          <span v-if="item.news_category && item.news_category !== '个股'" 
                class="category-tag">
            {{ item.news_category }}
          </span>
          <span class="news-source">{{ getSourceLabel(item.source) }}</span>
          <span class="news-date">{{ item.publish_time }}</span>
        </div>
        <div class="news-title">{{ item.title }}</div>
        <div v-if="item.content" class="news-content">{{ item.content }}</div>
        <div v-if="item.sentiment_confidence" class="confidence-bar">
          <span class="confidence-label">置信度</span>
          <div class="progress-bar">
            <div class="progress-fill" 
                 :style="{ width: (item.sentiment_confidence * 100) + '%' }">
            </div>
          </div>
          <span class="confidence-value">{{ (item.sentiment_confidence * 100).toFixed(0) }}%</span>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <div class="empty-icon">📰</div>
      <p class="empty-text">暂无相关新闻数据</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  newsList: {
    type: Array,
    default: () => []
  },
  sentimentCount: {
    type: Object,
    default: null
  }
})

function getSentimentLabel(type) {
  if (type === 'positive') return '利好'
  if (type === 'negative') return '利空'
  return '中性'
}

function getSourceLabel(source) {
  if (source === 'cls') return '财联社'
  if (source === '10jqka') return '同花顺'
  return source || '未知'
}
</script>

<style scoped>
.news-sentiment-container {
  padding: 8px 0;
}

.sentiment-summary {
  display: flex;
  gap: 16px;
  padding: 12px 16px;
  background: #f8f9fa;
  border-radius: 8px;
  margin-bottom: 16px;
}

.summary-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #495057;
}

.summary-item .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.summary-item.positive .dot {
  background: #ff4d4f;
}

.summary-item.negative .dot {
  background: #52c41a;
}

.summary-item.neutral .dot {
  background: #86909c;
}

.news-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.news-item {
  padding: 16px;
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  transition: box-shadow 0.2s;
}

.news-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.news-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.sentiment-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}

.sentiment-tag.positive {
  background: #fff1f0;
  color: #cf1322;
  border: 1px solid #ffa39e;
}

.sentiment-tag.negative {
  background: #f6ffed;
  color: #389e0d;
  border: 1px solid #b7eb8f;
}

.sentiment-tag.neutral {
  background: #f5f5f5;
  color: #595959;
  border: 1px solid #d9d9d9;
}

.category-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 11px;
  background: #e6f7ff;
  color: #1890ff;
  border: 1px solid #91d5ff;
}

.news-source {
  font-size: 12px;
  color: #86909c;
}

.news-date {
  font-size: 12px;
  color: #adb5bd;
}

.news-title {
  font-size: 14px;
  font-weight: 500;
  color: #262626;
  line-height: 1.6;
  margin-bottom: 8px;
}

.news-content {
  font-size: 13px;
  color: #666;
  line-height: 1.6;
}

.confidence-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #f0f0f0;
}

.confidence-label {
  font-size: 11px;
  color: #86909c;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: #f0f0f0;
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #1890ff, #667eea);
  border-radius: 3px;
  transition: width 0.3s;
}

.confidence-value {
  font-size: 11px;
  color: #595959;
  min-width: 35px;
  text-align: right;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-text {
  font-size: 14px;
  color: #86909c;
}
</style>
