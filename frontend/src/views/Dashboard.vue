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

      <!-- 增强型表格 -->
      <div class="table-wrapper">
        <table class="enhanced-table">
          <thead>
            <tr>
              <th>序号</th>
              <th>代码</th>
              <th>名称</th>
              <th @click="sortBy('close_price')" class="sortable">
                收盘价
                <span v-if="sortField === 'close_price'" class="sort-icon">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th @click="sortBy('change_pct')" class="sortable">
                涨跌幅
                <span v-if="sortField === 'change_pct'" class="sort-icon">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th>昨涨幅</th>
              <th>开涨幅</th>
              <th>竞昨比</th>
              <th>竞价换手率</th>
              <th>100天内涨停次数</th>
              <th>100天内封成比</th>
              <th>10日涨幅</th>
              <th>行业概念</th>
              <th>板块</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(stock, index) in sortedStocks"
              :key="stock.ts_code"
            >
              <!-- 基本信息 -->
              <td class="index-col">{{ index + 1 }}</td>
              <td class="code-cell"><code>{{ stock.ts_code }}</code></td>
              <td class="name-cell"><strong>{{ stock.name }}</strong></td>

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

              <!-- 分类信息 -->
              <td class="tag-cell">
                <span v-if="stock.industry" class="industry-tag">{{ stock.industry }}</span>
                <span v-else class="muted">--</span>
              </td>
              <td class="tag-cell">
                <span v-if="stock.board_type" class="sector-tag">{{ stock.board_type }}</span>
                <span v-else class="muted">--</span>
              </td>
            </tr>
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
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import StrategySelectorModal from '../components/StrategySelectorModal.vue'

const router = useRouter()

const stats = ref({ latestCount: 0, totalRecords: 0, healthy: false, tradeDate: '' })
const loaded = ref(false)
const selecting = ref(false)
const message = ref(null)
const latestStocks = ref([])
const latestDate = ref('')
const showStrategyModal = ref(false)
const sortField = ref('change_pct')
const sortOrder = ref('desc')

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

onMounted(async () => { await loadStats(); await loadLatest() })

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
      latestStocks.value = detail.data?.data?.stocks || []
    }
  } catch (e) { console.error('加载最新失败:', e) }
}

function sortBy(field) {
  if (sortField.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortOrder.value = 'desc'
  }
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

function fmt(v) { return v != null ? Number(v).toFixed(2) : '--' }
function fmtPct(v) { return v != null ? Number(v).toFixed(2) + '%' : '--' }

function getPctClass(v) {
  if (v == null) return ''
  if (v > 0) return 'positive'
  if (v < 0) return 'negative'
  return ''
}
</script>

<style scoped>
.dashboard { padding: 20px; max-width: 1800px; margin: 0 auto; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin: 16px 0; }
.stat-card { background: white; padding: 18px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }
.stat-card h3 { margin: 0 0 8px; color: #666; font-size: 13px; font-weight: normal; }
.stat-value { margin: 0; font-size: 30px; font-weight: bold; color: #333; }
.stat-value.ok { color: #52c41a; }
.stat-value.err { color: #ff4d4f; }
.stat-label { margin: 4px 0 0; color: #999; font-size: 12px; }
.stat-date { font-size: 22px !important; }
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

.loading { text-align: center; color: #1890ff; padding: 40px; }

/* 动画 */
@keyframes slideDown { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }

/* 响应式设计 */
@media (max-width: 1400px) {
  .enhanced-table { font-size: 11.5px; }
  .enhanced-table th, .enhanced-table td { padding: 6px 4px; }
}
</style>
