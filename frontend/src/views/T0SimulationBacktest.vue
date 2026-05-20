<template>
  <div class="sim-page">
    <div class="page-title">
      <div>
        <h2>日线模拟回测</h2>
        <p>当日涨停模型按每日概率前 2 买入，最多持仓 4 只，按日线收盘条件卖出。</p>
      </div>
      <button class="btn-secondary" :disabled="loadingRuns" @click="loadRuns">
        {{ loadingRuns ? '刷新中' : '刷新历史' }}
      </button>
    </div>

    <section class="panel">
      <div class="form-grid">
        <label>
          起始日期
          <input v-model="form.start_date" type="text" maxlength="8" />
        </label>
        <label>
          结束日期
          <input v-model="form.end_date" type="text" maxlength="8" />
        </label>
        <label>
          初始资金
          <input v-model.number="form.initial_cash" type="number" min="1" />
        </label>
        <label>
          样本来源
          <select v-model="form.sample_source">
            <option value="replay_backtest">历史回放</option>
            <option value="real_selected">真实选股</option>
            <option value="all">全部样本</option>
          </select>
          <small class="field-hint">历史回放用于完整区间回测；真实选股只复盘已实际运行过的选股日。</small>
        </label>
        <label>
          每日买入
          <input v-model.number="form.buy_top_n" type="number" min="1" :max="form.max_positions" />
        </label>
        <label>
          最大持仓
          <input v-model.number="form.max_positions" type="number" min="1" />
        </label>
        <label>
          最低买入概率 %
          <input v-model.number="form.min_buy_prob_pct" type="number" min="0" max="100" step="0.1" />
        </label>
        <label>
          最低开盘涨幅 %
          <input v-model.number="form.min_open_change_pct" type="number" step="0.1" />
        </label>
        <label>
          最高开盘涨幅 %
          <input v-model.number="form.max_open_change_pct" type="number" step="0.1" />
        </label>
        <label>
          高盈利阈值 %
          <input v-model.number="form.high_profit_hold_pct" type="number" min="0.1" step="0.1" />
          <small class="field-hint">达到最长持仓日时，收盘收益高于该值继续持有。</small>
        </label>
        <label>
          回撤卖出 %
          <input v-model.number="form.profit_pullback_pct" type="number" min="0.1" step="0.1" />
          <small class="field-hint">按日线收盘收益率计算最高盈利回落幅度。</small>
        </label>
        <label>
          止损 %
          <input v-model.number="form.stop_loss_pct" type="number" step="0.1" />
        </label>
        <label>
          最长持仓日
          <input v-model.number="form.max_holding_days" type="number" min="1" />
        </label>
        <label>
          模型版本
          <input v-model="form.model_version" type="text" placeholder="留空使用 active" />
        </label>
        <label class="check-row">
          <input v-model="form.force_close_on_end" type="checkbox" />
          结束日强制平仓
        </label>
      </div>
      <div class="actions">
        <button class="btn-primary" :disabled="creating" @click="createRun">
          {{ creating ? '创建中' : '开始回测' }}
        </button>
        <span v-if="error" class="error-text">{{ error }}</span>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h3>历史回测</h3>
        <select v-model="selectedRunId" @change="loadDetail(selectedRunId)">
          <option value="">选择历史回测</option>
          <option v-for="run in runs" :key="run.id" :value="run.id">
            #{{ run.id }} {{ run.start_date }}-{{ run.end_date }} {{ statusText(run.status) }}
          </option>
        </select>
      </div>
      <div v-if="loadingRuns" class="state-panel">加载历史中</div>
      <div v-else-if="runs.length === 0" class="state-panel empty">暂无历史回测</div>
    </section>

    <section v-if="detail" class="panel result-panel">
      <div class="panel-head">
        <div>
          <h3>回测结果 #{{ detail.id }}</h3>
          <p>{{ detail.start_date }} - {{ detail.end_date }} | {{ statusText(detail.status) }}</p>
        </div>
        <div class="head-actions">
          <button v-if="canCancel" class="btn-danger" :disabled="canceling" @click="cancelRun(detail.id)">
            {{ canceling ? '停止中' : '停止回测' }}
          </button>
          <button class="btn-secondary" :disabled="loadingDetail" @click="loadDetail(detail.id)">
            {{ loadingDetail ? '加载中' : '刷新详情' }}
          </button>
        </div>
      </div>

      <div v-if="detail.error_message" class="state-panel error">{{ detail.error_message }}</div>

      <div class="progress-panel">
        <div class="progress-info">
          <span>回测进度</span>
          <strong>{{ progressText }}</strong>
          <em v-if="detail.processed_trade_date">已处理到 {{ detail.processed_trade_date }}</em>
        </div>
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: `${progressPercent}%` }"></div>
        </div>
      </div>

      <div class="summary-grid">
        <div class="summary-card">
          <span>初始资金</span>
          <strong>{{ money(summary.initial_cash) }}</strong>
        </div>
        <div class="summary-card">
          <span>最终权益</span>
          <strong>{{ money(summary.final_equity) }}</strong>
        </div>
        <div class="summary-card">
          <span>总盈亏</span>
          <strong :class="profitClass(summary.total_profit_amount)">{{ money(summary.total_profit_amount) }}</strong>
        </div>
        <div class="summary-card">
          <span>总收益率</span>
          <strong :class="profitClass(summary.total_return_pct)">{{ pct(summary.total_return_pct) }}</strong>
        </div>
        <div class="summary-card">
          <span>最大回撤</span>
          <strong class="loss">{{ pct(summary.max_drawdown_pct) }}</strong>
        </div>
        <div class="summary-card">
          <span>胜率</span>
          <strong>{{ pct01(summary.win_rate) }}</strong>
        </div>
        <div class="summary-card">
          <span>已完成交易</span>
          <strong>{{ summary.trade_count || 0 }}</strong>
        </div>
        <div class="summary-card">
          <span>未平仓</span>
          <strong>{{ summary.open_position_count || 0 }}</strong>
        </div>
      </div>

      <div class="chart-box">
        <svg v-if="equityPoints.length" viewBox="0 0 100 36" preserveAspectRatio="none">
          <polyline :points="equityPoints" fill="none" stroke="#1677ff" stroke-width="1.8" />
        </svg>
        <div v-else class="state-panel empty">暂无权益曲线</div>
      </div>

      <div class="table-section">
        <div class="table-title">
          <h3>每日资产</h3>
          <label class="inline-check">
            <input v-model="showChangedDailyOnly" type="checkbox" />
            仅显示有资产变化日期
          </label>
          <span class="table-count">{{ displayDailyRows.length }} / {{ detail.daily?.length || 0 }}</span>
        </div>
        <div class="table-wrap asset-table-wrap">
          <table>
            <thead>
              <tr>
                <th>交易日</th>
                <th>现金</th>
                <th>持仓市值</th>
                <th>权益</th>
                <th>当日收益</th>
                <th>回撤</th>
                <th>持仓数</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in displayDailyRows" :key="row.trade_date">
                <td>{{ row.trade_date }}</td>
                <td>{{ money(row.cash) }}</td>
                <td>{{ money(row.market_value) }}</td>
                <td>{{ money(row.equity) }}</td>
                <td :class="profitClass(row.daily_return_pct)">{{ pct(row.daily_return_pct) }}</td>
                <td class="loss">{{ pct(row.drawdown_pct) }}</td>
                <td>{{ row.position_count }}</td>
              </tr>
              <tr v-if="!displayDailyRows.length">
                <td colspan="7" class="empty-cell">暂无每日资产</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="table-section">
        <div class="table-title">
          <h3>交易明细</h3>
          <span class="table-count">{{ detail.trades?.length || 0 }} 笔</span>
        </div>
        <div class="table-wrap trade-table-wrap">
          <table>
            <thead>
              <tr>
                <th>股票</th>
                <th>概率</th>
                <th>买入时间</th>
                <th>买入价</th>
                <th>买入金额</th>
                <th>卖出时间</th>
                <th>卖出价</th>
                <th>盈亏率</th>
                <th>盈亏金额</th>
                <th>原因</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="trade in detail.trades" :key="trade.trade_id">
                <td>{{ trade.ts_code }} {{ trade.name || '' }}</td>
                <td>{{ pct(trade.model_prob) }}</td>
                <td>{{ dateTime(trade.buy_date, trade.buy_time) }}</td>
                <td>{{ price(trade.buy_price) }}</td>
                <td>{{ money(trade.buy_amount) }}</td>
                <td>{{ dateTime(trade.sell_date, trade.sell_time) }}</td>
                <td>{{ price(trade.sell_price) }}</td>
                <td :class="profitClass(trade.return_pct)">{{ pct(trade.return_pct) }}</td>
                <td :class="profitClass(trade.profit_amount)">{{ money(trade.profit_amount) }}</td>
                <td>{{ reasonText(trade.sell_reason) }}</td>
                <td>{{ trade.status === 'closed' ? '已平仓' : '持仓中' }}</td>
              </tr>
              <tr v-if="!detail.trades?.length">
                <td colspan="11" class="empty-cell">暂无交易明细</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section v-else class="panel">
      <div class="state-panel empty">创建一次回测或从历史中选择记录</div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import axios from 'axios'

const today = new Date()
const endDate = `${today.getFullYear()}${String(today.getMonth() + 1).padStart(2, '0')}${String(today.getDate()).padStart(2, '0')}`

const form = reactive({
  start_date: '20250101',
  end_date: endDate,
  model_version: '',
  sample_source: 'replay_backtest',
  initial_cash: 100000,
  buy_top_n: 2,
  max_positions: 4,
  min_buy_prob_pct: 50,
  min_open_change_pct: -3,
  max_open_change_pct: 7,
  high_profit_hold_pct: 13,
  profit_pullback_pct: 5,
  stop_loss_pct: -5,
  max_holding_days: 3,
  force_close_on_end: false,
})

const runs = ref([])
const detail = ref(null)
const selectedRunId = ref('')
const loadingRuns = ref(false)
const loadingDetail = ref(false)
const creating = ref(false)
const canceling = ref(false)
const error = ref('')
const showChangedDailyOnly = ref(true)
let pollTimer = null

const summary = computed(() => detail.value?.summary || {})
const canCancel = computed(() => ['pending', 'running', 'cancel_requested'].includes(detail.value?.status))
const progressPercent = computed(() => {
  const value = Number(detail.value?.progress || 0)
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, value))
})
const progressText = computed(() => {
  const processed = Number(detail.value?.processed_trade_days || 0)
  const total = Number(detail.value?.total_trade_days || 0)
  return `${progressPercent.value.toFixed(2)}% (${processed}/${total})`
})
const displayDailyRows = computed(() => {
  const rows = detail.value?.daily || []
  if (!showChangedDailyOnly.value) return rows
  const initialCash = Number(summary.value.initial_cash || detail.value?.initial_cash || 0)
  const filtered = rows.filter((row) => {
    const equity = Number(row.equity || 0)
    const marketValue = Number(row.market_value || 0)
    const dailyReturn = Number(row.daily_return_pct || 0)
    const drawdown = Number(row.drawdown_pct || 0)
    const positionCount = Number(row.position_count || 0)
    return positionCount > 0 || marketValue > 0 || dailyReturn !== 0 || drawdown !== 0 || Math.abs(equity - initialCash) >= 0.01
  })
  return filtered.length ? filtered : rows
})

const equityPoints = computed(() => {
  const rows = detail.value?.daily || []
  if (!rows.length) return ''
  const values = rows.map((row) => Number(row.equity || 0))
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  return values.map((value, index) => {
    const x = rows.length === 1 ? 0 : (index / (rows.length - 1)) * 100
    const y = 34 - ((value - min) / span) * 32
    return `${x.toFixed(2)},${y.toFixed(2)}`
  }).join(' ')
})

async function createRun() {
  error.value = ''
  creating.value = true
  try {
    const payload = {
      ...form,
      model_version: form.model_version || null,
      cost: {
        buy_fee_pct: 0,
        sell_fee_pct: 0,
        slippage_pct: 0,
      },
    }
    const res = await axios.post('/api/v1/backtest/t0-simulation/runs', payload)
    const runId = res.data.data.run_id
    selectedRunId.value = runId
    await loadRuns()
    await loadDetail(runId)
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '创建回测失败'
  } finally {
    creating.value = false
  }
}

async function loadRuns() {
  loadingRuns.value = true
  try {
    const res = await axios.get('/api/v1/backtest/t0-simulation/runs?limit=30')
    runs.value = res.data.data || []
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '加载历史失败'
  } finally {
    loadingRuns.value = false
  }
}

async function loadDetail(runId, options = {}) {
  if (!runId) return
  const showLoading = options.showLoading !== false
  if (showLoading) loadingDetail.value = true
  try {
    const res = await axios.get(`/api/v1/backtest/t0-simulation/runs/${runId}`)
    detail.value = res.data.data
    selectedRunId.value = runId
    scheduleDetailPoll(runId, detail.value?.status)
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '加载详情失败'
  } finally {
    if (showLoading) loadingDetail.value = false
  }
}

async function cancelRun(runId) {
  if (!runId) return
  error.value = ''
  canceling.value = true
  try {
    const res = await axios.post(`/api/v1/backtest/t0-simulation/runs/${runId}/cancel`)
    detail.value = { ...(detail.value || {}), ...res.data.data }
    await loadRuns()
    await loadDetail(runId)
  } catch (err) {
    error.value = err.response?.data?.detail || err.message || '停止回测失败'
  } finally {
    canceling.value = false
  }
}

function scheduleDetailPoll(runId, status) {
  clearDetailPoll()
  if (!isActiveRun(status)) {
    loadRuns()
    return
  }
  pollTimer = window.setTimeout(() => {
    loadDetail(runId, { showLoading: false })
  }, 1500)
}

function clearDetailPoll() {
  if (pollTimer) {
    window.clearTimeout(pollTimer)
    pollTimer = null
  }
}

function isActiveRun(status) {
  return ['pending', 'running', 'cancel_requested'].includes(status)
}

function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function price(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(2)
}

function pct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toFixed(2)}%`
}

function pct01(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${(Number(value) * 100).toFixed(2)}%`
}

function dateTime(date, time) {
  if (!date) return '-'
  const text = String(date)
  return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)} ${time || ''}`.trim()
}

function profitClass(value) {
  const number = Number(value)
  if (!Number.isFinite(number) || number === 0) return ''
  return number > 0 ? 'profit' : 'loss'
}

function statusText(status) {
  return {
    pending: '等待中',
    running: '运行中',
    cancel_requested: '停止中',
    canceled: '已停止',
    passed: '完成',
    failed: '失败',
  }[status] || status || '-'
}

function reasonText(reason) {
  return {
    take_profit: '固定止盈',
    profit_pullback: '高盈回撤',
    stop_loss: '止损',
    stop_loss_next_open: '跌停次日止损',
    max_holding_days: '最长持仓',
    end_of_backtest: '期末平仓',
  }[reason] || '-'
}

onMounted(loadRuns)
onUnmounted(clearDetailPoll)
</script>

<style scoped>
.sim-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-title,
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-title h2,
.panel h3 {
  margin: 0;
}

.page-title p,
.panel-head p {
  margin: 6px 0 0;
  color: #667085;
  font-size: 13px;
}

.panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 18px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #475467;
  font-size: 13px;
}

.field-hint {
  color: #667085;
  font-size: 12px;
  line-height: 1.4;
}

input,
select {
  height: 36px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  padding: 0 10px;
  color: #101828;
  background: #fff;
}

.check-row {
  flex-direction: row;
  align-items: center;
  padding-top: 24px;
}

.check-row input {
  width: 16px;
  height: 16px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
}

.btn-primary,
.btn-secondary,
.btn-danger {
  border: none;
  border-radius: 6px;
  padding: 9px 14px;
  cursor: pointer;
  font-weight: 600;
}

.btn-primary {
  color: #fff;
  background: #1677ff;
}

.btn-secondary {
  color: #1677ff;
  background: #e6f4ff;
}

.btn-danger {
  color: #b42318;
  background: #fff1f0;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-text {
  color: #d92d20;
}

.state-panel {
  padding: 18px;
  text-align: center;
  color: #667085;
  background: #f9fafb;
  border-radius: 8px;
}

.state-panel.error {
  color: #b42318;
  background: #fff1f0;
}

.progress-panel {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f8fafc;
}

.progress-info {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #475467;
  font-size: 13px;
}

.progress-info strong {
  color: #101828;
}

.progress-info em {
  color: #667085;
  font-style: normal;
}

.progress-track {
  height: 8px;
  margin-top: 10px;
  overflow: hidden;
  background: #e5e7eb;
  border-radius: 999px;
}

.progress-fill {
  height: 100%;
  background: #1677ff;
  transition: width 0.25s ease;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.summary-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
}

.summary-card span {
  display: block;
  color: #667085;
  font-size: 12px;
}

.summary-card strong {
  display: block;
  margin-top: 6px;
  font-size: 18px;
}

.profit {
  color: #cf1322;
}

.loss {
  color: #389e0d;
}

.chart-box {
  height: 220px;
  margin-top: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  background: linear-gradient(180deg, #fff, #f8fafc);
}

.chart-box svg {
  width: 100%;
  height: 100%;
}

.table-section {
  margin-top: 18px;
}

.table-title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.table-title h3 {
  margin-right: auto;
}

.inline-check {
  flex-direction: row;
  align-items: center;
  gap: 6px;
  color: #475467;
  font-size: 13px;
}

.inline-check input {
  width: 16px;
  height: 16px;
}

.table-count {
  color: #667085;
  font-size: 12px;
}

.table-wrap {
  max-height: 360px;
  overflow: auto;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.trade-table-wrap {
  max-height: 420px;
}

table {
  width: 100%;
  border-collapse: collapse;
  min-width: 920px;
}

th,
td {
  padding: 10px 12px;
  border-bottom: 1px solid #eef2f6;
  text-align: left;
  white-space: nowrap;
  font-size: 13px;
}

th {
  color: #475467;
  background: #f8fafc;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 1;
}

.empty-cell {
  text-align: center;
  color: #667085;
}

@media (max-width: 720px) {
  .page-title,
  .panel-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .head-actions {
    width: 100%;
    flex-wrap: wrap;
  }
}
</style>
