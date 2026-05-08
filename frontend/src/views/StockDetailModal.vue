<template>
  <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-container">
      <div class="modal-header">
        <h2>{{ stock?.name || '加载中...' }} <small>{{ stock?.ts_code }}</small></h2>
        <button class="btn-close" @click="$emit('close')">&times;</button>
      </div>

      <div class="modal-body">
        <div class="tabs">
          <button 
            v-for="tab in tabs" 
            :key="tab.key"
            :class="['tab', { active: activeTab === tab.key, loading: tabLoading[tab.key] }]"
            @click="switchTab(tab.key)"
          >
            {{ tab.label }}
            <span v-if="tabLoading[tab.key]" class="loading-dot">...</span>
          </button>
        </div>

        <div v-if="isLoading" class="loading-container">
          <div class="spinner"></div>
          <p>加载中...</p>
        </div>

        <template v-else>
          <div v-if="activeTab === 'overview'" class="tab-content">
            <div class="basic-info">
              <div class="info-item"><label>收盘价</label><span>{{ formatNum(detail.basic?.close_price) }}</span></div>
              <div class="info-item"><label>涨跌幅</label><span :class="getCls(detail.basic?.change_pct)">{{ formatPct(detail.basic?.change_pct) }}</span></div>
              <div class="info-item"><label>昨涨幅</label><span :class="getCls(detail.basic?.pre_change_pct)">{{ formatPct(detail.basic?.pre_change_pct) }}</span></div>
              <div class="info-item"><label>开涨幅</label><span :class="getCls(detail.basic?.open_change_pct)">{{ formatPct(detail.basic?.open_change_pct) }}</span></div>
              <div class="info-item"><label>流通市值</label><span>{{ detail.basic?.circ_mv ? detail.basic.circ_mv.toFixed(2) + '亿' : '--' }}</span></div>
              <div class="info-item"><label>行业</label><span>{{ detail.basic?.industry || '--' }}</span></div>
            </div>
            <div v-if="tabLoading['overview']" class="section-loading">加载综合概览中...</div>
            <OverviewBrief v-else :data="detail.overview" :loading="false" />
          </div>

          <div v-if="activeTab === 'score'" class="tab-content">
            <ScoreBreakdown :score="detail.score" />
          </div>

          <div v-if="activeTab === 'news'" class="tab-content">
            <div v-if="tabLoading['news']" class="section-loading">加载新闻中...</div>
            <NewsSentimentList v-else :articles="detail.news?.articles" />
          </div>

          <div v-if="activeTab === 'limitup'" class="tab-content">
            <div v-if="tabLoading['limitup']" class="section-loading">加载异动数据中...</div>
            <AnomalyInterpretation v-else :data="detail.anomaly" :loading="false" />
          </div>

          <div v-if="activeTab === 'lhb'" class="tab-content">
            <div v-if="tabLoading['lhb']" class="section-loading">加载龙虎榜中...</div>
            <LhbPanel v-else />
          </div>

          <div v-if="activeTab === 'earnings'" class="tab-content">
            <div v-if="tabLoading['earnings']" class="section-loading">加载业绩数据中...</div>
            <EarningsPanel v-else />
          </div>

          <div v-if="activeTab === 'plan'" class="tab-content">
            <NextDayPlan :plan="detail.next_day_plan" />
          </div>
        </template>
      </div>

      <div class="modal-footer">
        <small>数据来源: Anspire 智能搜索 | 来源状态: {{ Object.values(detail.source_status || {}).filter(s => s === 'ok').length }}/4 正常</small>
        <span v-if="cacheHit" class="cache-badge">缓存命中</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import axios from 'axios'
import ScoreBreakdown from '../components/ScoreBreakdown.vue'
import NewsSentimentList from '../components/NewsSentimentList.vue'
import LhbPanel from '../components/stock/LhbPanel.vue'
import EarningsPanel from '../components/EarningsPanel.vue'
import NextDayPlan from '../components/NextDayPlan.vue'
import OverviewBrief from '../components/stock/OverviewBrief.vue'
import AnomalyInterpretation from '../components/stock/AnomalyInterpretation.vue'
import { stockPreloadService } from '../services/StockPreloadService'

const props = defineProps({
  visible: Boolean,
  tsCode: String,
  stockName: String,
  recordId: [Number, null],
})
const emit = defineEmits(['close'])

const activeTab = ref('overview')
const isLoading = ref(false)
const cacheHit = ref(false)
const tabLoading = reactive({
  news: false,
  limitup: false,
  lhb: false,
  earnings: false,
  plan: false,
  score: false,
  overview: false,
  anomaly: false,
})

const detail = reactive({
  basic: {},
  score: {},
  news: {},
  announcements: {},
  research: {},
  limitup: {},
  lhb: {},
  earnings: {},
  risk: {},
  next_day_plan: {},
  source_status: {},
  overview: {},
  anomaly: {},
})
const stock = ref(null)

const tabs = [
  { key: 'overview', label: '综合概览' },
  { key: 'score', label: '评分拆解' },
  { key: 'news', label: '新闻舆情' },
  { key: 'limitup', label: '涨停异动' },
  { key: 'lhb', label: '龙虎榜' },
  { key: 'earnings', label: '业绩排雷' },
  { key: 'plan', label: '次日预案' },
]

const lazyLoadModules = {
  overview: async () => {
    if (detail.overview?.brief) return
    tabLoading.overview = true
    try {
      const cached = stockPreloadService.getFromCache(props.tsCode, 'overview')
      if (cached) {
        detail.overview = cached
        return
      }
      const res = await axios.get('/api/v1/stock/overview-brief', {
        params: { ts_code: props.tsCode, stock_name: props.stockName, record_id: props.recordId }
      })
      if (res.data?.code === 200 && res.data.data) {
        detail.overview = res.data.data
      }
    } catch (e) {
      console.error('加载综合概览失败:', e)
    } finally {
      tabLoading.overview = false
    }
  },
  news: async () => {
    if (detail.news?.articles?.length) return
    tabLoading.news = true
    try {
      const res = await axios.get('/api/v1/stock/detail/news', {
        params: { stock_name: props.stockName, ts_code: props.tsCode }
      })
      detail.news = res.data?.data || {}
    } catch (e) {
      console.error('加载新闻失败:', e)
    } finally {
      tabLoading.news = false
    }
  },
  limitup: async () => {
    if (detail.anomaly?.core_tags_line) return
    tabLoading.limitup = true
    try {
      const cached = stockPreloadService.getFromCache(props.tsCode, 'anomaly')
      if (cached) {
        detail.anomaly = cached
        return
      }
      const res = await axios.get('/api/v1/stock/anomaly-interpretation', {
        params: { ts_code: props.tsCode, stock_name: props.stockName }
      })
      if (res.data?.code === 200 && res.data.data) {
        detail.anomaly = res.data.data
      }
    } catch (e) {
      console.error('加载异动解读失败:', e)
    } finally {
      tabLoading.limitup = false
    }
  },
  lhb: async () => {
    tabLoading.lhb = true
    try {
      const res = await axios.get('/api/v2/stock/score-v3/dragon-tiger', {
        params: { ts_code: props.tsCode }
      })
      if (res.data?.code === 200 && res.data.data) {
        detail.lhb = res.data.data
      }
    } catch (e) {
      console.error('加载龙虎榜失败:', e)
    } finally {
      tabLoading.lhb = false
    }
  },
  earnings: async () => {
    tabLoading.earnings = true
    try {
      const res = await axios.get('/api/v2/stock/score-v3/financial', {
        params: { ts_code: props.tsCode }
      })
      if (res.data?.code === 200 && res.data.data) {
        detail.earnings = res.data.data
      }
    } catch (e) {
      console.error('加载业绩数据失败:', e)
    } finally {
      tabLoading.earnings = false
    }
  },
  score: async () => {
    if (detail.score?.alpha_score != null) return
    tabLoading.score = true
    try {
      const res = await axios.get('/api/v2/stock/score-v3/detail', {
        params: { ts_code: props.tsCode }
      })
      if (res.data?.code === 200 && res.data.data) {
        detail.score = { ...detail.score, ...res.data.data }
      }
    } catch (e) {
      console.error('加载评分数据失败:', e)
    } finally {
      tabLoading.score = false
    }
  }
}

watch(() => props.visible, async (v) => {
  if (v && props.tsCode) {
    activeTab.value = 'overview'
    isLoading.value = true
    cacheHit.value = false
    
    try {
      const cachedData = stockPreloadService.getFromCache(props.tsCode)
      if (cachedData) {
        cacheHit.value = true
        Object.assign(detail, cachedData)
        stock.value = cachedData.basic
      } else {
        const data = await stockPreloadService.getStockDetail(
          props.tsCode, 
          props.stockName, 
          props.recordId
        )
        if (data) {
          Object.assign(detail, data)
          stock.value = data.basic
        }
      }
    } catch (e) {
      console.error('加载详情失败:', e)
    } finally {
      isLoading.value = false
    }

    // 非阻塞触发懒加载：预加载可能有缓存，也可通过 tab 切换触发
    lazyLoadModules.overview().catch(() => {})
    lazyLoadModules.score().catch(() => {})
  }
})

async function switchTab(tabKey) {
  activeTab.value = tabKey
  if (lazyLoadModules[tabKey]) {
    await lazyLoadModules[tabKey]()
  }
}

function formatNum(v) { return v != null ? Number(v).toFixed(2) : '--' }
function formatPct(v) { return v != null ? Number(v).toFixed(2) + '%' : '--' }
function getCls(v) { if (v == null) return ''; return v > 0 ? 'positive' : v < 0 ? 'negative' : '' }
</script>

<style scoped>
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5); display: flex; justify-content: center;
  align-items: center; z-index: 2000; animation: fadeIn 0.2s;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.modal-container {
  background: white; border-radius: 12px; width: 90%; max-width: 900px;
  max-height: 85vh; display: flex; flex-direction: column;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2); animation: slideUp 0.25s;
}
@keyframes slideUp { from { transform: translateY(30px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
.modal-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 24px; border-bottom: 1px solid #f0f0f0;
}
.modal-header h2 { margin: 0; font-size: 18px; }
.modal-header small { color: #999; font-weight: normal; font-size: 13px; }
.btn-close { background: none; border: none; font-size: 24px; cursor: pointer; color: #999; padding: 0 8px; }
.btn-close:hover { color: #333; }
.modal-body { flex: 1; overflow-y: auto; padding: 16px 24px; }
.modal-footer { padding: 12px 24px; border-top: 1px solid #f0f0f0; color: #999; font-size: 12px; display: flex; justify-content: space-between; align-items: center; }

.cache-badge {
  background: linear-gradient(135deg, #52c41a, #389e0d);
  color: white;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}

.tabs { display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }
.tab {
  padding: 8px 16px; border: 1px solid #d9d9d9; border-radius: 6px;
  background: white; cursor: pointer; font-size: 13px; transition: all 0.2s;
  display: flex; align-items: center; gap: 6px;
}
.tab:hover { border-color: #667eea; color: #667eea; }
.tab.active { background: linear-gradient(135deg, #667eea, #764ba2); color: white; border-color: transparent; }
.tab.loading { opacity: 0.6; pointer-events: none; }

.loading-dot {
  animation: dotPulse 1s infinite;
}
@keyframes dotPulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }

.tab-content { min-height: 200px; }

.loading-container {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 40px; color: #999;
}
.spinner {
  width: 40px; height: 40px; border: 3px solid #f0f0f0;
  border-top-color: #667eea; border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.section-loading {
  padding: 20px; text-align: center; color: #999; font-size: 14px;
}

.basic-info { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }
.info-item { background: #fafafa; padding: 10px 14px; border-radius: 8px; }
.info-item label { display: block; font-size: 11px; color: #999; margin-bottom: 4px; }
.info-item span { font-size: 15px; font-weight: 600; }

.score-summary { text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea08, #764ba208); border-radius: 12px; margin-bottom: 20px; }
.score-big { font-size: 48px; font-weight: 700; color: #667eea; line-height: 1; }
.score-level { font-size: 24px; font-weight: 600; color: #764ba2; margin: 4px 0; }
.score-label { font-size: 12px; color: #999; }

.reasons-section h4, .tags-section h4 { margin: 0 0 8px; font-size: 14px; color: #333; }
.reasons-section ul { margin: 0; padding-left: 20px; }
.reasons-section li { font-size: 13px; color: #666; line-height: 1.8; }
.risk-tag {
  display: inline-block; padding: 3px 10px; border-radius: 12px;
  background: #fff2f0; color: #ff4d4f; font-size: 12px; margin: 2px 4px;
}

.positive { color: #cf1322; }
.negative { color: #389e0d; }
</style>