<template>
  <div class="dashboard">
    <h2>仪表盘</h2>

    <div class="stats-grid" v-if="loaded">
      <div class="stat-card">
        <h3>最新选出</h3>
        <p class="stat-value">{{ stats.latestCount }}</p>
        <p class="stat-label">只股票</p>
      </div>
      <div class="stat-card">
        <h3>历史记录</h3>
        <p class="stat-value">{{ stats.totalRecords }}</p>
        <p class="stat-label">条选股记录</p>
      </div>
      <div class="stat-card">
        <h3>系统状态</h3>
        <p :class="['stat-value', stats.healthy ? 'ok' : 'err']">{{ stats.healthy ? '正常' : '异常' }}</p>
      </div>
      <div class="stat-card">
        <h3>交易日</h3>
        <p class="value stat-date">{{ stats.tradeDate || '--' }}</p>
      </div>
      <div class="stat-card">
        <div class="stat-card-head">
          <h3>训练数据同步至</h3>
          <button
            class="sync-refresh-btn"
            type="button"
            :disabled="rawDataSyncLoading || rawDataSyncRefreshing"
            @click="refreshRawDataSync"
            title="手动刷新训练原始数据"
          >
            {{ rawDataSyncRefreshing ? '刷新中' : '刷新' }}
          </button>
        </div>
        <p class="value stat-date">{{ formatDate(rawDataSyncState?.synced_to_date || rawDataSyncState?.trade_date) }}</p>
        <p class="stat-label">
          <span :class="['sync-status', rawDataSyncState?.status]">{{ rawDataSyncStatusText(rawDataSyncState?.status) }}</span>
          <span v-if="rawDataSyncState?.finished_at">更新 {{ formatDateTime(rawDataSyncState.finished_at) }}</span>
          <span v-else-if="rawDataSyncLoading || rawDataSyncRefreshing">加载中</span>
          <span v-else-if="rawDataSyncError" class="sync-error">{{ rawDataSyncError }}</span>
        </p>
      </div>
      <div class="stat-card">
        <h3>选股模型</h3>
        <p :class="['stat-value', stats.modelEnabled ? 'ok' : 'err']">{{ stats.modelEnabled ? '已启用' : '未启用' }}</p>
      </div>
      <div class="stat-card">
        <h3>高风险股票</h3>
        <p :class="['stat-value', stats.highRiskCount > 0 ? 'err' : 'ok']">{{ stats.highRiskCount }}</p>
        <p class="stat-label">只股票</p>
      </div>
    </div>

    <div v-if="!loaded" class="loading">加载中...</div>

    <div class="actions">
      <button @click="openStrategySelector" :disabled="selecting" class="btn-primary">
        {{ selecting ? '执行中...' : '立即执行选股' }}
      </button>
      <button @click="$router.push('/strategy-manage')" class="btn-secondary">策略管理</button>
      <button @click="testNotification" class="btn-secondary">测试飞书通知</button>
    </div>

    <!-- 执行中提示 -->
    <div v-if="selecting" class="alert info" style="border: 2px solid #1890ff; font-weight: bold;">
      ⏳ 正在执行选股，请稍候... [新版]
    </div>

    <div v-if="message" :class="['alert', message.type]">{{ message.text }}</div>

    <!-- 最新选股结果预览 -->
    <div v-if="latestStocks.length > 0" class="section preview-section">
      <div class="section-header">
        <h3>最新选股预览 ({{ latestDate }})</h3>
        <span class="stock-count">共 {{ latestStocks.length }} 只股票</span>
      </div>

      <div class="model-guide">
        <div class="model-guide-item">
          <strong>当日涨停</strong>
          <span>目标一，衡量竞价后当天继续冲击涨停的概率。</span>
        </div>
        <div class="model-guide-item">
          <strong>次日溢价</strong>
          <span>目标二，衡量次日高开、冲高或收盘溢价的概率。</span>
        </div>
        <div class="model-guide-item">
          <strong>次日连板</strong>
          <span>目标三，衡量次日继续涨停或连板的概率。</span>
        </div>
        <div class="model-guide-item">
          <strong>接力分</strong>
          <span>三目标加权排序分，不是单一概率，越高越优先观察。</span>
        </div>
      </div>

      <!-- 增强型表格 -->
      <div class="table-wrapper">
        <table class="enhanced-table">
          <thead>
            <tr>
              <th>代码</th>
              <th>名称</th>
              <th @click="sortBy('close_price')" class="sortable">
                收盘价
                <span v-if="sortField === 'close_price'" class="sort-icon">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th @click="sortBy('change_pct')" class="sortable quote-refresh-col">
                <span class="th-inline">
                  <span>涨跌幅</span>
                  <button
                    class="quote-refresh-btn"
                    type="button"
                    :disabled="realtimeRefreshing || latestStocks.length === 0"
                    title="刷新当前选股列表实时股价"
                    @click.stop="refreshRealtimeQuotes"
                  >
                    {{ realtimeRefreshing ? '刷新中' : '刷新' }}
                  </button>
                  <span v-if="sortField === 'change_pct'" class="sort-icon">
                    {{ sortOrder === 'asc' ? '↑' : '↓' }}
                  </span>
                </span>
              </th>
              <th>昨涨幅</th>
              <th>开涨幅</th>
              <th @click="sortBy('auction_ratio')" class="sortable">
                竞昨比
                <span v-if="sortField === 'auction_ratio'" class="sort-icon">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th>竞价换手率</th>
              <th>100天内涨停次数</th>
              <th>100天内封成比</th>
              <th>10日涨幅</th>
              <th @click="sortBy('health_score')" class="sortable">
                龙头评级
                <span v-if="sortField === 'health_score'" class="sort-icon">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th @click="sortBy('default_t0_limit_prob')" class="sortable relay-prob-col">
                当日涨停
                <span v-if="sortField === 'default_t0_limit_prob'" class="sort-icon">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th @click="sortBy('default_t1_premium_prob')" class="sortable relay-prob-col">
                次日溢价
                <span v-if="sortField === 'default_t1_premium_prob'" class="sort-icon">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th @click="sortBy('default_t1_continue_prob')" class="sortable relay-prob-col">
                次日连板
                <span v-if="sortField === 'default_t1_continue_prob'" class="sort-icon">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th @click="sortBy('default_relay_score')" class="sortable relay-score-col">
                接力分
                <span v-if="sortField === 'default_relay_score'" class="sort-icon">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <template
              v-for="(stock, index) in sortedStocks"
              :key="stock.ts_code"
            >
            <tr>
              <!-- 基本信息 -->
              <td class="code-cell"><code>{{ stock.ts_code }}</code></td>
              <td class="name-cell">
                <a class="stock-link" href="#" @click.prevent="openDetail(stock)">{{ stock.name }}</a>
              </td>

              <!-- 行情数据 -->
              <td class="num-cell">{{ fmt(stock.close_price) }}</td>
              <td :class="['num-cell', getPctClass(stock.change_pct)]">
                {{ fmtPct(stock.change_pct) }}
              </td>
              <td :class="['num-cell', getPctClass(stock.pre_change_pct)]">
                {{ fmtPct(stock.pre_change_pct) }}
              </td>
              <td :class="['num-cell', getPctClass(stock.open_change_pct)]">
                {{ fmtPct(stock.open_change_pct) }}
              </td>

              <!-- 市场指标 -->
              <td class="num-cell">{{ fmtPct(stock.auction_ratio) }}</td>
              <td class="num-cell">{{ fmtPct(stock.auction_turnover_rate) }}</td>

              <!-- 趋势强度 -->
              <td class="num-cell highlight">{{ stock.limit_up_count || '--' }}<span class="unit">次</span></td>
              <td class="num-cell">{{ fmtPct(stock.seal_rate) }}</td>
              <td :class="['num-cell', getPctClass(stock.rise_10d_pct)]">
                {{ fmtPct(stock.rise_10d_pct) }}
              </td>
              <td class="score-cell">
                <span v-if="stock.leader_level" class="score-wrap">
                  <span :class="['score-level-tag', leaderLevelClass(stock)]">{{ stock.leader_level }}</span>
                  <span class="score-health">健{{ stock.health_score }}</span>
                </span>
                <span v-else-if="displayScore(stock) !== null" class="score-wrap">
                  <span class="score-num">{{ displayScore(stock) }}</span>
                  <span :class="['score-level-tag', scoreLevelClass(stock)]">{{ scoreLevelText(stock) }}</span>
                </span>
                <span v-else class="muted">--</span>
              </td>
              <td class="num-cell model-prob relay-prob" :title="defaultRelayTitle(stock, 't0')">
                {{ fmtPct1(stock.default_t0_limit_prob) }}
              </td>
              <td class="num-cell model-prob relay-prob" :title="defaultRelayTitle(stock, 'premium')">
                {{ fmtPct1(stock.default_t1_premium_prob) }}
              </td>
              <td class="num-cell model-prob relay-prob" :title="defaultRelayTitle(stock, 'continue')">
                {{ fmtPct1(stock.default_t1_continue_prob) }}
              </td>
              <td class="num-cell relay-score" :title="defaultRelayTitle(stock, 'relay')">
                {{ fmtScore(stock.default_relay_score) }}
              </td>
            </tr>
            <!-- 涨停/换手率标签行 -->
            <tr v-if="hasEnrichData(stock)" class="enrich-row">
              <td colspan="5" class="enrich-cell"><span class="enrich-tag lu-desc">{{ stock.lu_desc || '--' }}</span></td>
              <td colspan="3" class="enrich-cell"><span v-if="isLimitUp(stock)" class="enrich-tag lu-tag">{{ stock.lu_tag || '--' }}</span></td>
              <td colspan="3" class="enrich-cell"><span v-if="isLimitUp(stock)" class="enrich-tag lu-status">{{ stock.lu_status || '--' }}</span></td>
              <td colspan="2" class="enrich-cell"><span v-if="isLimitUp(stock)" class="enrich-tag open-num">炸板{{ stock.lu_open_num != null ? stock.lu_open_num : 0 }}次</span></td>
              <td colspan="2" class="enrich-cell"><span class="enrich-tag suc-rate">近一年封板率{{ fmtRate(stock.limit_up_suc_rate) }}</span></td>
              <td colspan="2" class="enrich-cell"><span class="enrich-tag turnover">昨日换手{{ fmtPct(stock.prev_turnover_rate) }}</span></td>
            </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 策略选择弹窗 -->
    <StrategySelectorModal
      :visible="showStrategyModal"
      :tradeDate="stats.tradeDate"
      @close="showStrategyModal = false"
      @manage="goToStrategyManage"
      @success="onSelectionSuccess"
      @error="onSelectionError"
      @loading="selecting = $event"
    />

    <!-- 个股详情抽屉 -->
    <StockDetailDrawer
      :visible="showDrawer"
      :ts-code="drawerTsCode"
      :stock-name="drawerStockName"
      :trade-date="drawerTradeDate"
      :record-id="drawerRecordId"
      @close="showDrawer = false"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import StrategySelectorModal from '../components/StrategySelectorModal.vue'
import StockDetailDrawer from '../components/StockDetailDrawer.vue'

const router = useRouter()

const stats = ref({ latestCount: 0, totalRecords: 0, healthy: false, tradeDate: '', modelEnabled: false, highRiskCount: 0 })
const loaded = ref(false)
const selecting = ref(false)
const message = ref(null)
const latestStocks = ref([])
const realtimeRefreshing = ref(false)
const rawDataSyncState = ref(null)
const rawDataSyncLoading = ref(false)
const rawDataSyncRefreshing = ref(false)
const rawDataSyncError = ref('')
const latestDate = ref('')
const showStrategyModal = ref(false)
const sortField = ref('health_score')
const sortOrder = ref('desc')

const showDrawer = ref(false)
const drawerTsCode = ref('')
const drawerStockName = ref('')
const drawerTradeDate = ref('')
const drawerRecordId = ref(null)

const sortedStocks = computed(() => {
  if (!latestStocks.value.length) return []

  const sorted = [...latestStocks.value].sort((a, b) => {
    const aVal = a[sortField.value] || 0
    const bVal = b[sortField.value] || 0

    if (sortOrder.value === 'asc') {
      return aVal - bVal
    } else {
      return bVal - aVal
    }
  })

  return sorted
})

onMounted(async () => { await loadStats(); await Promise.all([loadLatest(), loadRawDataSyncState()]) })

async function loadStats() {
  try {
    const [h, r, d] = await Promise.all([
      axios.get('/api/v1/health'),
      axios.get('/api/v1/stock/results', { params: { page: 1, page_size: 1 } }),
      axios.get('/api/v1/stock/trading-date')
    ])
    stats.value.healthy = h.data.code === 200
    const rd = r.data?.data || {}
    stats.value.totalRecords = rd.total || 0
    if (rd.records?.length > 0) {
      const rec = rd.records[0]
      stats.value.latestCount = rec.total_count || 0
      latestDate.value = rec.trade_date
    }
    if (d.data?.code === 200) stats.value.tradeDate = d.data.data?.trading_date || ''
    loaded.value = true
  } catch (e) { console.error('加载统计失败:', e); loaded.value = true }
}

async function loadLatest() {
  try {
    const r = await axios.get('/api/v1/stock/results', { params: { page: 1, page_size: 1 } })
    const rd = r.data?.data || {}
    const rec = (rd.records || []).find(x => x.total_count > 0)
    if (rec) {
      const detail = await axios.get(`/api/v1/stock/results/${rec.id}`)
      const stocks = detail.data?.data?.stocks || []
      latestStocks.value = stocks
      // 计算高风险股票数量（risk_tags 不为空）
      stats.value.highRiskCount = stocks.filter(s => (s.risk_tags || []).length > 0).length
    }
    // 检测 LightGBM 模型状态
    try {
      const modelRes = await axios.get('/api/v1/model/status')
      stats.value.modelEnabled = modelRes.data?.data?.enabled || false
    } catch (e) {
      stats.value.modelEnabled = false
    }
  } catch (e) { console.error('加载最新失败:', e) }
}

async function loadRawDataSyncState() {
  rawDataSyncLoading.value = true
  rawDataSyncError.value = ''
  try {
    const res = await axios.get('/api/v1/models/default-auction-relay/raw-data-sync-state')
    rawDataSyncState.value = res.data?.data || null
  } catch (e) {
    rawDataSyncError.value = e.response?.data?.detail || e.message || '加载失败'
  } finally {
    rawDataSyncLoading.value = false
  }
}

async function refreshRawDataSync() {
  if (rawDataSyncRefreshing.value) return
  rawDataSyncRefreshing.value = true
  rawDataSyncError.value = ''
  try {
    const res = await axios.post('/api/v1/models/default-auction-relay/raw-data-sync')
    rawDataSyncState.value = res.data?.data || rawDataSyncState.value
    await loadRawDataSyncState()
  } catch (e) {
    rawDataSyncError.value = e.response?.data?.detail || e.message || '刷新失败'
  } finally {
    rawDataSyncRefreshing.value = false
  }
}

async function refreshRealtimeQuotes() {
  if (realtimeRefreshing.value || latestStocks.value.length === 0) return

  const tsCodes = latestStocks.value
    .map(stock => stock.ts_code)
    .filter(Boolean)

  if (tsCodes.length === 0) {
    message.value = { type: 'warning', text: '当前选股列表没有可刷新的股票代码' }
    return
  }

  realtimeRefreshing.value = true
  try {
    const res = await axios.post('/api/v1/stock/realtime-quotes', { ts_codes: tsCodes })
    const quotes = res.data?.data?.quotes || {}
    let updated = 0

    latestStocks.value = latestStocks.value.map(stock => {
      const quote = quotes[stock.ts_code]
      if (!quote) return stock

      updated += 1
      const next = { ...stock }
      if (quote.close_price != null) {
        next.close_price = quote.close_price
        next.close = quote.close_price
      }
      if (quote.change_pct != null) next.change_pct = quote.change_pct
      if (quote.open_change_pct != null) next.open_change_pct = quote.open_change_pct
      return next
    })

    message.value = {
      type: updated > 0 ? 'success' : 'warning',
      text: updated > 0 ? `已刷新 ${updated} 只股票实时股价` : '实时行情接口未返回当前列表数据'
    }
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '刷新失败'
    message.value = { type: 'error', text: '实时股价刷新失败：' + errorMsg }
  } finally {
    realtimeRefreshing.value = false
  }
}

function sortBy(field) {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortOrder.value = 'desc'
  }
}

function openDetail(stock) {
  drawerTsCode.value = stock.ts_code
  drawerStockName.value = stock.name
  drawerTradeDate.value = latestDate.value
  drawerRecordId.value = stock.record_id || null
  showDrawer.value = true
}

function displayScore(stock) {
  const s = stock.final_score != null ? stock.final_score : stock.rule_score
  return s != null ? Number(s).toFixed(1) : null
}

function scoreLevelText(stock) {
  const s = stock.final_score != null ? stock.final_score : stock.rule_score
  if (s == null) return ''
  if (s >= 90) return 'S'
  if (s >= 80) return 'A'
  if (s >= 70) return 'B'
  if (s >= 60) return 'C'
  return 'D'
}

function scoreLevelClass(stock) {
  const txt = scoreLevelText(stock)
  if (txt === 'S' || txt === 'A') return 'level-high'
  if (txt === 'B') return 'level-mid'
  return 'level-low'
}

function leaderLevelClass(stock) {
  const lvl = stock.leader_level || ''
  if (lvl === '极强龙头' || lvl === '强势龙头') return 'level-high'
  if (lvl === '疑似龙头' || lvl === '跟风强势股') return 'level-mid'
  return 'level-low'
}

function defaultRelayTitle(stock, target) {
  const version = stock.default_relay_model_version || '未启用默认接力组合模型'
  const titleMap = {
    t0: '当日涨停模型：预测入选后当天继续冲击涨停的概率。',
    premium: '次日溢价模型：预测次日高开、冲高或收盘溢价的概率。',
    continue: '次日连板模型：预测次日继续涨停或连板的概率。',
    relay: '竞价接力综合分：当日涨停、次日溢价、次日连板三目标加权后的排序分，不是单一概率。',
  }
  return `${titleMap[target] || '默认竞价接力V2：三目标综合判断。'}版本：${version}`
}

function openStrategySelector() {
  showStrategyModal.value = true
}

function goToStrategyManage() {
  showStrategyModal.value = false
  router.push('/strategy-manage')
}

async function onSelectionSuccess(data) {
  console.log('=== onSelectionSuccess ===', data)
  // 先清空旧消息
  message.value = null

  console.log('开始加载统计数据...')
  // 加载数据
  await loadStats()
  console.log('开始加载最新股票...')
  await loadLatest()
  console.log('数据加载完成，显示消息')

  // 等数据加载完再显示新消息
  message.value = {
    type: data.passed_count > 0 ? 'success' : 'warning',
    text: data.passed_count > 0
      ? `✅ [新版] 使用「${data.strategy_name}」策略选中 ${data.passed_count} 只股票`
      : `⚠️ [新版] 本次未筛选到符合条件的股票`
  }
}

function onSelectionError(errorMsg) {
  message.value = { type: 'error', text: '❌ 选股失败：' + errorMsg }
}

async function testNotification() {
  try {
    await axios.post('/api/v1/config/test-notification')
    message.value = { type: 'success', text: '✅ 通知发送成功！' }
  } catch (e) {
    message.value = { type: 'error', text: '❌ 发送失败：' + (e.response?.data?.detail || e.message) }
  }
  setTimeout(() => message.value = null, 3000)
}

function fmtRate(v) {
  if (v == null) return '--'
  const pct = v * 100
  return pct.toFixed(1) + '%'
}

function hasEnrichData(stock) {
  return stock.lu_desc || stock.lu_tag || stock.lu_status || stock.lu_open_num != null || stock.limit_up_suc_rate != null || stock.prev_turnover_rate != null
}

function isLimitUp(stock) {
  return stock.pre_change_pct != null && stock.pre_change_pct >= 9.8
}

function fmt(v) { return v != null ? Number(v).toFixed(2) : '--' }
function fmtPct(v) { return v != null ? Number(v).toFixed(2) + '%' : '--' }
function fmtPct1(v) { return v != null ? Number(v).toFixed(1) + '%' : '--' }
function fmtScore(v) { return v != null ? Number(v).toFixed(1) : '--' }

function formatDate(value) {
  if (!value) return '--'
  const text = String(value)
  if (text.length === 8) return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`
  return text
}

function formatDateTime(value) {
  if (!value) return '--'
  const text = String(value).replace('T', ' ')
  return text.slice(0, 19)
}

function rawDataSyncStatusText(status) {
  return {
    success: '成功',
    running: '同步中',
    failed: '失败',
    not_synced: '未同步',
  }[status] || '未知'
}

function getPctClass(v) {
  if (v == null) return ''
  if (v > 0) return 'positive'
  if (v < 0) return 'negative'
  return ''
}
</script>

<style scoped>
.dashboard { padding: 15px 25px; width: 100%; box-sizing: border-box; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(155px, 1fr)); gap: 10px; margin: 12px 0; }
.stat-card { background: white; padding: 18px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }
.stat-card h3 { margin: 0 0 8px; color: #666; font-size: 13px; font-weight: normal; }
.stat-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.stat-card-head h3 { margin: 0; }
.stat-value { margin: 0; font-size: 30px; font-weight: bold; color: #333; }
.stat-value.ok { color: #52c41a; }
.stat-value.err { color: #ff4d4f; }
.stat-label { margin: 4px 0 0; color: #999; font-size: 12px; }
.stat-date { font-size: 22px !important; }
.sync-status { display: inline-block; margin-right: 6px; border-radius: 999px; padding: 2px 8px; background: #f3f4f6; color: #4b5563; font-size: 12px; }
.sync-status.success { background: #ecfdf5; color: #047857; }
.sync-status.running { background: #e6f4ff; color: #1677ff; }
.sync-status.failed { background: #fef2f2; color: #b91c1c; }
.sync-status.not_synced { background: #fff7ed; color: #c2410c; }
.sync-error { color: #b91c1c; }
.sync-refresh-btn {
  flex: 0 0 auto;
  min-width: 48px;
  height: 26px;
  padding: 0 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  color: #555;
  cursor: pointer;
  font-size: 12px;
  line-height: 24px;
}
.sync-refresh-btn:hover:not(:disabled) { color: #1677ff; border-color: #1677ff; }
.sync-refresh-btn:disabled { opacity: .55; cursor: not-allowed; }
.actions { display: flex; gap: 10px; margin: 16px 0; flex-wrap: wrap; }
.btn-primary { padding: 10px 20px; border: none; border-radius: 4px; background: #1890ff; color: white; cursor: pointer; font-size: 14px; transition: all 0.25s; }
.btn-primary:hover:not(:disabled) { background: #096dd9; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(24,144,255,0.35); }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.btn-secondary { padding: 10px 20px; border: none; border-radius: 4px; background: #f0f0f0; color: #333; cursor: pointer; font-size: 14px; transition: all 0.25s; }
.btn-secondary:hover { background: #e0e0e0; }
.alert { padding: 12px 16px; border-radius: 4px; margin-top: 12px; animation: slideDown 0.3s ease-out; }
.alert.success { background: #f6ffed; border: 1px solid #b7eb8f; color: #52c41a; }
.alert.warning { background: #fffbe6; border: 1px solid #ffe58f; color: #faad14; }
.alert.error { background: #fff2f0; border: 1px solid #ffccc7; color: #ff4d4f; }
.alert.info { background: #e6f7ff; border: 1px solid #91d5ff; color: #1890ff; }

/* Section 样式 */
.section { margin-top: 24px; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 2px solid #f0f0f0; }
.section-header h3 { margin: 0; font-size: 16px; color: #262626; font-weight: 600; }
.stock-count { font-size: 13px; color: #999; background: #fafafa; padding: 4px 12px; border-radius: 12px; }
.model-guide {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 8px;
  margin: 10px 0 12px;
}
.model-guide-item {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 9px 10px;
  background: #f9fafb;
  display: grid;
  gap: 4px;
}
.model-guide-item strong { color: #1f2937; font-size: 13px; }
.model-guide-item span { color: #6b7280; font-size: 12px; line-height: 1.45; }

/* 表格容器 */
.table-wrapper { overflow-x: auto; border-radius: 8px; border: 1px solid #f0f0f0; }

/* 增强型表格 */
.enhanced-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
  white-space: nowrap;
}
.enhanced-table th {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 10px 8px;
  text-align: center;
  font-weight: 600;
  font-size: 11.5px;
  letter-spacing: 0.5px;
  position: sticky;
  top: 0;
  z-index: 10;
}
.enhanced-table td {
  padding: 8px 6px;
  text-align: center;
  border-bottom: 1px solid #f5f5f5;
  vertical-align: middle;
}
.enhanced-table tbody tr:hover { background: #fafafa; }

/* 可排序列 */
.sortable {
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}
.sortable:hover {
  background: linear-gradient(135deg, #5a6fd8 0%, #6a4190 100%);
}
.sort-icon {
  margin-left: 4px;
  font-weight: bold;
  font-size: 14px;
}
.quote-refresh-col { min-width: 92px; }
.th-inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.quote-refresh-btn {
  height: 22px;
  padding: 0 6px;
  border: 1px solid rgba(255, 255, 255, 0.62);
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.16);
  color: #ffffff;
  font-size: 11px;
  line-height: 20px;
  cursor: pointer;
}
.quote-refresh-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.26);
  border-color: #ffffff;
}
.quote-refresh-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

/* 单元格样式 */
.index-col {
  width: 60px;
  text-align: center;
  color: #999;
  font-size: 12px;
}
.code-cell code {
  background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
  padding: 3px 8px;
  border-radius: 4px;
  font-family: 'SF Mono', Monaco, monospace;
  font-size: 11.5px;
  color: #667eea;
  font-weight: 600;
}
.name-cell strong { color: #262626; font-weight: 600; }
.stock-link { color: #667eea; font-weight: 600; text-decoration: none; cursor: pointer; }
.stock-link:hover { text-decoration: underline; color: #764ba2; }
.num-cell { font-family: 'SF Mono', -apple-system, sans-serif; font-variant-numeric: tabular-nums; }
.num-cell.muted { color: #bbb; }
.num-cell.highlight { color: #ff4d4f; font-weight: 700; }
.num-cell .unit { font-size: 10px; color: #999; margin-left: 2px; font-family: -apple-system, sans-serif; }

/* 涨跌幅颜色 - 中国股市习惯：涨红跌绿 */
.positive {
  color: #cf1322;
  font-weight: 700;
  background: #fff1f0;
  padding: 2px 6px;
  border-radius: 4px;
}
.negative {
  color: #389e0d;
  font-weight: 700;
  background: #f6ffed;
  padding: 2px 6px;
  border-radius: 4px;
}

/* 标签样式 */
.tag-cell { max-width: 120px; overflow: hidden; text-overflow: ellipsis; }
.score-cell { min-width: 80px; text-align: center; }
.score-wrap { display: inline-flex; align-items: center; gap: 6px; }
.score-num { font-family: 'SF Mono', monospace; font-size: 14px; font-weight: 700; color: #667eea; }
.score-health { font-size: 10px; color: #1890ff; font-weight: 600; margin-left: 2px; }
.score-level-tag { display: inline-block; padding: 1px 8px; border-radius: 8px; font-size: 11px; font-weight: 700; }
.score-level-tag.level-high { background: #f6ffed; color: #52c41a; }
.score-level-tag.level-mid { background: #fff7e6; color: #fa8c16; }
.score-level-tag.level-low { background: #fff2f0; color: #ff4d4f; }
.relay-prob-col { min-width: 96px; }
.relay-score-col { min-width: 76px; }
.relay-prob { color: #1d4ed8; font-weight: 700; }
.relay-score { color: #b45309; font-weight: 800; }
.model-label {
  display: inline-block;
  margin-right: 4px;
  padding: 1px 4px;
  border-radius: 4px;
  background: #e6fffb;
  color: #08979c;
  font-size: 10px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  vertical-align: 1px;
}
.industry-tag {
  background: linear-gradient(135deg, #e6f7ff 0%, #bae7ff 100%);
  color: #1890ff;
  padding: 3px 8px;
  border-radius: 10px;
  font-size: 11px;
  display: inline-block;
  max-width: 110px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sector-tag {
  background: linear-gradient(135deg, #fff7e6 0%, #ffe7ba 100%);
  color: #fa8c16;
  padding: 3px 8px;
  border-radius: 10px;
  font-size: 11px;
  display: inline-block;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.muted { color: #ccc; }

/* 涨停/换手率标签行 */
.enrich-row { background: #fafbfc; }
.enrich-row:hover { background: #f0f5ff; }
.enrich-cell {
  padding: 6px 4px !important;
  text-align: center !important;
}
.enrich-tag {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.6;
  white-space: nowrap;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}
.enrich-tag.lu-desc {
  background: #E3F2FD;
  color: #1565C0;
}
.enrich-tag.lu-tag {
  background: #FFF3E0;
  color: #E65100;
}
.enrich-tag.lu-status {
  background: #FFF3E0;
  color: #E65100;
}
.enrich-tag.open-num {
  background: #FFEBEE;
  color: #C62828;
}
.enrich-tag.suc-rate {
  background: #F5F5F5;
  color: #333333;
}
.enrich-tag.turnover {
  background: #F5F5F5;
  color: #333333;
}

.loading { text-align: center; color: #1890ff; padding: 40px; }

/* 动画 */
@keyframes slideDown { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }

/* 响应式设计 */
@media (max-width: 1400px) {
  .enhanced-table { font-size: 11.5px; }
  .enhanced-table th, .enhanced-table td { padding: 6px 4px; }
}
</style>
