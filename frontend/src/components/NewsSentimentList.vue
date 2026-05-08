<template>
  <div class="news-list">
    <div v-if="articles?.length" class="list">
      <div v-for="(a, i) in articles" :key="i" class="news-item" :class="sentimentClass(a)">
        <div class="news-title">
          <span class="sentiment-badge" :class="sentimentClass(a)">{{ sentimentLabel(a) }}</span>
          <a :href="a.url" target="_blank" rel="noopener">{{ a.title || '无标题' }}</a>
        </div>
        <div class="news-meta">{{ a.source }} · {{ a.publish_date }}</div>
        <div class="news-summary">{{ a.summary || '无摘要' }}</div>
      </div>
    </div>
    <div v-else class="empty">暂未获取到新闻数据</div>
  </div>
</template>

<script setup>
defineProps({ articles: Array })
function sentimentClass(a) {
  const t = (a.title || '') + (a.summary || '')
  const pos = ['利好', '涨停', '大涨', '突破', '增长', '盈利']
  const neg = ['利空', '跌停', '大跌', '亏损', '减持', '风险', '监管', '诉讼']
  for (const w of pos) { if (t.includes(w)) return 'positive' }
  for (const w of neg) { if (t.includes(w)) return 'negative' }
  return 'neutral'
}
function sentimentLabel(a) {
  const c = sentimentClass(a)
  return { positive: '利好', negative: '利空', neutral: '中性' }[c] || '中性'
}
</script>
<style scoped>
.news-item { padding: 12px; border-bottom: 1px solid #f0f0f0; }
.news-title { font-size: 14px; margin-bottom: 4px; }
.news-title a { color: #333; text-decoration: none; }
.news-title a:hover { color: #667eea; }
.sentiment-badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; margin-right: 8px; }
.sentiment-badge.positive { background: #fff1f0; color: #cf1322; }
.sentiment-badge.negative { background: #f6ffed; color: #389e0d; }
.sentiment-badge.neutral { background: #f5f5f5; color: #999; }
.news-meta { font-size: 12px; color: #999; margin-bottom: 4px; }
.news-summary { font-size: 13px; color: #666; line-height: 1.5; }
.empty { color: #999; text-align: center; padding: 40px; }
</style>
