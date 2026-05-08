<template>
  <div v-if="visible" class="drawer-overlay" @click.self="$emit('close')">
    <div class="drawer-container">
      <div class="drawer-header">
        <h2>{{ props.stockName || props.tsCode }} <small>{{ props.tsCode }}</small></h2>
        <button class="btn-close" @click="$emit('close')">&times;</button>
      </div>

      <div class="drawer-body">
        <!-- 初始加载：显示骨架屏 -->
        <div v-if="initialLoading" class="loading">
          <div class="skeleton skeleton-card"></div>
          <div class="skeleton skeleton-card"></div>
          <div class="skeleton skeleton-card"></div>
          <div class="loading-text">加载个股数据...</div>
        </div>

        <div v-else-if="error" class="error-section">
          <p class="error-text">{{ error }}</p>
          <button class="btn-retry" @click="loadDetail">重试</button>
        </div>

        <div v-else>
          <div class="tabs">
            <button v-for="tab in tabs" :key="tab.key"
              :class="['tab', { active: activeTab === tab.key }]"
              @click="switchTab(tab.key)">{{ tab.label }}</button>
          </div>

          <div class="tab-content">
            <div v-if="activeTab === 'overview'" class="tab-pane">
              <div v-if="tabData.overview.loading" class="skeleton skeleton-card"></div>
              <StockOverviewBrief
                v-else
                :data="tabData.overview.data"
                :loading="tabData.overview.loading"
                @reload="() => loadTab('overview')"
              />
            </div>

            <div v-if="activeTab === 'alpha_score'" class="tab-pane">
              <div v-if="tabData.alpha_score.loading" class="skeleton skeleton-card"></div>
              <template v-else>
                <div v-if="tabData.alpha_score.data?.alpha_breakdown" class="v2-header">
                  <div v-if="tabData.alpha_score.data?.explanation" class="v2-explanation">{{ tabData.alpha_score.data.explanation }}</div>
                  <StockAlphaScoreBreakdown :alpha-breakdown="tabData.alpha_score.data?.alpha_breakdown" />
                </div>
                <div v-else class="empty">暂无Alpha评分数据</div>
              </template>
            </div>

            <div v-if="activeTab === 'risk_breakdown'" class="tab-pane">
              <div v-if="tabData.risk_breakdown.loading" class="skeleton skeleton-card"></div>
              <RiskBreakdown
                v-else
                :riskData="tabData.risk_breakdown.data"
                :loading="tabData.risk_breakdown.loading"
                :error="tabData.risk_breakdown.error"
                @reload="() => loadTab('risk_breakdown')"
              />
            </div>

            <div v-if="activeTab === 'news'" class="tab-pane">
              <div v-if="tabData.news.loading" class="skeleton skeleton-card"></div>
              <StockNewsSentimentList 
                v-else 
                :newsList="tabData.news.data?.news_list" 
                :sentimentCount="tabData.news.data?.sentiment_count" 
              />
            </div>

            <div v-if="activeTab === 'anomaly'" class="tab-pane">
              <div v-if="tabData.anomaly.loading" class="skeleton skeleton-card"></div>
              <StockAnomalyInterpretation
                v-else
                :data="tabData.anomaly.data"
                :loading="tabData.anomaly.loading"
                :error="tabData.anomaly.error"
                @reload="handleAnomalyReload"
              />
            </div>

            <div v-if="activeTab === 'lhb'" class="tab-pane">
              <div v-if="tabData.lhb.loading" class="skeleton skeleton-card"></div>
              <StockLhbPanel
                v-else
                :lhb="tabData.lhb.data"
                :loading="tabData.lhb.loading"
                :error="tabData.lhb.error"
                @reload="() => loadTab('lhb')"
              />
            </div>

            <div v-if="activeTab === 'earnings'" class="tab-pane">
              <div v-if="tabData.earnings.loading" class="skeleton skeleton-card"></div>
              <StockEarningsPanel v-else :earnings="tabData.earnings.data?.earnings" />
            </div>

            <div v-if="activeTab === 'plan'" class="tab-pane">
              <div v-if="tabData.plan.loading" class="skeleton skeleton-card"></div>
              <StockNextDayPlan v-else :next-day-plan="tabData.plan.data?.next_day_plan" />
            </div>
          </div>
        </div>
      </div>

      <div class="drawer-footer">
        <small>数据来源：Anspire / Tushare</small>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import api from '../api/index'
import { stockPreloadService } from '../services/StockPreloadService'

import StockNewsSentimentList from './stock/NewsSentimentList.vue'
import StockLhbPanel from './stock/LhbPanel.vue'
import StockEarningsPanel from './stock/EarningsPanel.vue'
import StockNextDayPlan from './stock/NextDayPlan.vue'
import StockAlphaScoreBreakdown from './stock/AlphaScoreBreakdown.vue'
import StockAnomalyInterpretation from './stock/AnomalyInterpretation.vue'
import StockOverviewBrief from './stock/OverviewBrief.vue'
import RiskBreakdown from './stock/RiskBreakdown.vue'

const props = defineProps({
  visible: Boolean,
  tsCode: String,
  stockName: String,
  tradeDate: String,
  recordId: [Number, String, null],
})
const emit = defineEmits(['close'])

const activeTab = ref('overview')
const initialLoading = ref(false)
const error = ref(null)
const forceRefreshFlag = ref(false) // 强制刷新标志

// Tab数据状态
const tabData = ref({
  overview: { data: null, loading: false, error: null },
  alpha_score: { data: null, loading: false, error: null },
  risk_breakdown: { data: null, loading: false, error: null },
  anomaly: { data: null, loading: false, error: null },
  news: { data: null, loading: false, error: null },
  lhb: { data: null, loading: false, error: null },
  earnings: { data: null, loading: false, error: null },
  plan: { data: null, loading: false, error: null },
})

const tabs = [
  { key: 'overview', label: '综合概览' },
  { key: 'alpha_score', label: 'Alpha评分' },
  { key: 'risk_breakdown', label: '风险拆解' },
  { key: 'anomaly', label: '异动解读' },
  { key: 'news', label: '新闻舆情' },
  { key: 'lhb', label: '龙虎榜' },
  { key: 'earnings', label: '业绩排雷' },
  { key: 'plan', label: '开盘预案' },
]

watch(() => props.visible, (v) => {
  if (v && props.tsCode) {
    // 打开抽屉时：先重置所有数据，确保切换股票时不显示旧数据
    resetTabData()
    loadDetail()
  }
})

function resetTabData() {
  // 重置所有Tab数据状态
  Object.keys(tabData.value).forEach(key => {
    tabData.value[key].data = null
    tabData.value[key].loading = false
    tabData.value[key].error = null
  })
}

const cacheMap = new Map()

function getCacheKey() {
  return `${props.recordId || ''}_${props.tsCode}`
}

function buildParams() {
  const params = { ts_code: props.tsCode }
  if (props.stockName) params.stock_name = props.stockName
  if (props.tradeDate) params.trade_date = props.tradeDate
  if (props.recordId) params.record_id = props.recordId
  return params
}

const TAB_API_MAP = {
  overview: { url: '/stock/overview-brief', timeout: 90000 },
  alpha_score: { url: '/score-v2/detail', timeout: 30000 },
  risk_breakdown: { url: '/stock/detail/risk', timeout: 30000 },
  anomaly: { url: '/stock/anomaly-interpretation', timeout: 90000 },
  news: { url: '/stock/news-v2', timeout: 30000 },
  lhb: { url: '/stock/detail/lhb', timeout: 30000 },
  earnings: { url: '/stock/detail', timeout: 30000 },
  plan: { url: '/stock/detail', timeout: 30000 },
}

async function loadTab(tabKey, forceRefresh = false) {
  const tab = tabData.value[tabKey]
  if (!tab) return

  tab.loading = true
  tab.error = null

  try {
    const apiConf = TAB_API_MAP[tabKey]
    if (!apiConf) {
      console.warn(`No API config for tab: ${tabKey}`)
      return
    }

    const params = tabKey === 'overview' 
      ? { ...buildParams(), record_id: props.recordId }
      : buildParams()

    // 龙头战法模式默认调用
    if (tabKey === 'risk_breakdown') {
      params.strategy_type = 'dragon_leader'
      if (!params.stock_name && props.stockName) {
        params.stock_name = props.stockName
      }
    }

    // 异动解读支持强制刷新
    if (tabKey === 'anomaly' && (forceRefresh || forceRefreshFlag.value)) {
      params.force_refresh = true
      forceRefreshFlag.value = false
    }

    // 从预加载缓存读取（避免重复请求）
    if (!forceRefresh && tabKey === 'risk_breakdown' && props.tsCode) {
      const cached = stockPreloadService.getFromCache(props.tsCode, 'risk')
      if (cached) {
        tab.data = cached
        tab.loading = false
        return
      }
    }

    const res = await api.get(apiConf.url, { params, timeout: apiConf.timeout })
    tab.data = normalizeTabResponse(tabKey, res?.data)
  } catch (e) {
    tab.error = e.message || '加载失败'
    console.error(`Failed to load tab ${tabKey}:`, e)
  } finally {
    tab.loading = false
  }
}

// 处理异动解读组件的reload事件
function handleAnomalyReload() {
  forceRefreshFlag.value = true
  loadTab('anomaly', true)
}

async function loadDetail() {
  const cacheKey = getCacheKey()

  // 检查缓存，但数据必须匹配当前股票
  if (cacheMap.has(cacheKey)) {
    const cached = cacheMap.get(cacheKey)
    if (cached && cached._tsCode === props.tsCode) {
      Object.keys(cached).forEach(key => {
        if (key !== '_tsCode' && tabData.value[key]) {
          tabData.value[key].data = cached[key]
        }
      })
      return
    }
  }

  initialLoading.value = true
  error.value = null
  activeTab.value = 'overview'
  const params = buildParams()

  try {
    // === 阶段1：加载快速数据（非AI，数据库查询）→ 立即可见 ===
    const [detailRes, scoreRes, newsRes] = await Promise.allSettled([
      api.get('/stock/detail', { params, timeout: 30000 }),
      api.get('/score-v2/detail', { params, timeout: 15000 }).catch(() => ({ data: null })),
      api.get('/stock/news-v2', { params, timeout: 15000 }).catch(() => ({ data: null })),
    ])

    // 基础详情
    if (detailRes.status === 'fulfilled') {
      const detailData = detailRes.value?.data || {}
      // 龙虎榜、业绩排雷、开盘预案使用独立API懒加载
      tabData.value.earnings.data = detailData
      tabData.value.plan.data = detailData
    } else {
      error.value = '加载个股数据失败'
    }

    // 评分V2
    if (scoreRes.status === 'fulfilled' && scoreRes.value?.data) {
      tabData.value.alpha_score.data = scoreRes.value.data
    }

    // 新闻舆情
    if (newsRes.status === 'fulfilled' && newsRes.value?.data) {
      tabData.value.news.data = normalizeTabResponse('news', newsRes.value.data)
    }

    // 阶段1完成 → 取消初始加载动画
    initialLoading.value = false

    // === 阶段2：后台加载AI数据（优先读取预加载缓存，再回退到API） ===
    const cachedData = { _tsCode: props.tsCode }
    Object.keys(tabData.value).forEach(key => {
      if (key !== 'anomaly') {
        cachedData[key] = tabData.value[key].data
      }
    })
    cacheMap.set(cacheKey, cachedData)

    // 检查预加载缓存
    const preloadedOverview = stockPreloadService.getFromCache(props.tsCode, 'overview')
    const preloadedAnomaly = stockPreloadService.getFromCache(props.tsCode, 'anomaly')

    if (preloadedOverview) {
      tabData.value.overview.data = preloadedOverview
    } else {
      api.get('/stock/overview-brief', { params: { ...params, record_id: props.recordId }, timeout: 90000 })
        .then(res => {
          if (res?.data) tabData.value.overview.data = res.data
        }).catch(() => {})
    }

    if (preloadedAnomaly) {
      tabData.value.anomaly.data = preloadedAnomaly
    } else {
      api.get('/stock/anomaly-interpretation', { params, timeout: 90000 })
        .then(res => {
          if (res?.data) tabData.value.anomaly.data = res.data
        }).catch(() => {})
    }

  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '加载失败'
  } finally {
    initialLoading.value = false
  }
}

function normalizeTabResponse(tabKey, payload) {
  if (!payload) return null
  if (tabKey === 'news' && payload.data) {
    return payload.data
  }
  return payload
}

function switchTab(key) {
  activeTab.value = key
  // 按需加载：Tab首次切换时自动加载
  const tab = tabData.value[key]
  if (tab && tab.data === null && !tab.loading) {
    loadTab(key)
  }
}

function fmtScore(v) {
  if (v == null) return '--'
  return Number(v).toFixed(1)
}
</script>

<style scoped>
.drawer-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 2000;
  display: flex;
  justify-content: flex-end;
  animation: fadeIn 0.15s;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.drawer-container {
  width: 80%;
  max-width: 900px;
  background: white;
  height: 100vh;
  display: flex;
  flex-direction: column;
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.12);
  animation: slideIn 0.2s ease-out;
}
@keyframes slideIn { from { transform: translateX(30px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}
.drawer-header h2 { margin: 0; font-size: 16px; color: #262626; }
.drawer-header h2 small { color: #999; font-weight: normal; font-size: 12px; margin-left: 6px; }
.btn-close { background: none; border: none; font-size: 24px; cursor: pointer; color: #999; padding: 0 6px; line-height: 1; }
.btn-close:hover { color: #333; }

.drawer-body { flex: 1; overflow-y: auto; padding: 12px 20px; }
.drawer-footer { padding: 10px 20px; border-top: 1px solid #f0f0f0; color: #999; font-size: 11px; flex-shrink: 0; }

.tabs { display: flex; gap: 3px; margin-bottom: 12px; flex-wrap: wrap; }
.tab {
  padding: 5px 10px; border: 1px solid #d9d9d9; border-radius: 4px;
  background: white; cursor: pointer; font-size: 12px; transition: all 0.15s; color: #333;
}
.tab:hover { border-color: #667eea; color: #667eea; }
.tab.active { background: linear-gradient(135deg, #667eea, #764ba2); color: white; border-color: transparent; }

.tab-pane { min-height: 150px; }

/* 骨架屏 */
.loading { padding: 40px 20px; }
.skeleton {
  height: 60px; background: linear-gradient(90deg, #f0f0f0 25%, #e8e8e8 50%, #f0f0f0 75%);
  background-size: 200% 100%; animation: shimmer 1.2s infinite;
  border-radius: 8px; margin-bottom: 16px;
}
.skeleton-card { height: 80px; }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
.loading-text { text-align: center; color: #999; font-size: 13px; margin-top: 8px; }

.error-section { text-align: center; padding: 60px; }
.error-text { color: #ff4d4f; margin-bottom: 16px; }
.btn-retry { padding: 8px 20px; border: 1px solid #667eea; border-radius: 4px; background: white; color: #667eea; cursor: pointer; }
.btn-retry:hover { background: #f0f0ff; }

.v2-header { width: 100%; }
.v2-explanation { background: #f0f0ff; padding: 10px 14px; border-radius: 8px; margin-bottom: 14px; font-size: 13px; color: #555; line-height: 1.6; }
.v1-notice { background: #fffbe6; border: 1px solid #ffe58f; padding: 8px 12px; border-radius: 6px; font-size: 12px; color: #d46b08; margin-bottom: 12px; }
.empty { color: #999; text-align: center; padding: 40px; font-size: 13px; }
</style>
