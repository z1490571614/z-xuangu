<template>
  <div class="stock-results">
    <h2>选股结果</h2>

    <!-- 选股记录列表 -->
    <div v-if="records.length > 0" class="section">
      <div class="section-header">
        <h3>历史选股记录 (共{{ totalRecords }}条)</h3>
        <div class="batch-actions">
          <button
            class="btn-delete-batch"
            :disabled="selectedIds.length === 0"
            @click="confirmBatchDelete"
          >批量删除 ({{ selectedIds.length }})</button>
        </div>
      </div>

      <table class="data-table records-table">
        <thead>
          <tr>
            <th class="col-check">
              <input
                type="checkbox"
                :checked="isAllSelected"
                :indeterminate="isIndeterminate"
                @change="toggleSelectAll"
              />
            </th>
            <th>记录ID</th>
            <th>交易日</th>
            <th>选中数量</th>
            <th>状态</th>
            <th>执行时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="record in records" :key="record.id">
            <td class="col-check">
              <input
                type="checkbox"
                :checked="selectedIds.includes(record.id)"
                @change="toggleSelect(record.id)"
              />
            </td>
            <td>{{ record.id }}</td>
            <td>{{ record.trade_date }}</td>
            <td><strong>{{ record.total_count }}</strong></td>
            <td><span :class="['badge', record.status]">{{ statusText(record.status) }}</span></td>
            <td>{{ formatTime(record.execute_time) }}</td>
            <td class="actions-cell">
              <button @click="loadStocks(record.id)" :disabled="record.total_count === 0"
                      class="btn-detail">详情</button>
              <button @click="confirmDelete(record.id)" class="btn-delete">删除</button>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 分页 -->
      <div v-if="totalPages > 1" class="pagination">
        <button @click="prevPage" :disabled="currentPage <= 1">上一页</button>
        <span>{{ currentPage }} / {{ totalPages }}</span>
        <button @click="nextPage" :disabled="currentPage >= totalPages">下一页</button>
      </div>
    </div>

    <!-- 股票详情 -->
    <div v-if="stocks.length > 0" class="section stock-section">
      <div class="section-header">
        <h3>股票明细 <small>(记录 #{{ currentRecordId }})</small></h3>
        <div class="header-actions">
          <div class="stock-count-bar">
            共 <strong>{{ stocks.length }}</strong> 只股票
          </div>
          <div v-if="preloading" class="preload-status">
            <span class="preload-spinner"></span>
            预加载中 {{ preloadCount }}/{{ stocks.length }}
          </div>
          <button v-if="!preloading" class="btn-clear-cache" @click="clearAllCache">
            清空缓存
          </button>
        </div>
      </div>

      <div class="table-wrapper">
        <table class="data-table stock-table">
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
              <th @click="sortBy('change_pct')" class="sortable">
                涨跌幅
                <span v-if="sortField === 'change_pct'" class="sort-icon">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th>昨涨幅</th>
              <th>开涨幅</th>
              <th @click="sortBy('health_score')" class="sortable">
                龙头评级
                <span v-if="sortField === 'health_score'" class="sort-icon">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th @click="sortBy('leader_strength_score')" class="sortable">
                强度
                <span v-if="sortField === 'leader_strength_score'" class="sort-icon">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th>风险</th>
              <th>入选原因</th>
              <th>竞昨比</th>
              <th>竞价换手率</th>
              <th @click="sortBy('t0_limit_success_prob')" class="sortable">
                T+0成功率
                <span v-if="sortField === 't0_limit_success_prob'" class="sort-icon">
                  {{ sortOrder === 'asc' ? '↑' : '↓' }}
                </span>
              </th>
              <th>触板</th>
              <th>封板</th>
              <th>封成比</th>
              <th>10日涨幅</th>
            </tr>
          </thead>
          <tbody>
            <template
              v-for="(stock, index) in sortedStocks"
              :key="stock.ts_code"
            >
            <tr>
              <td><code>{{ stock.ts_code }}</code></td>
              <td><a class="stock-name-link" href="#" @click.prevent="showDetail(stock)">{{ stock.name }}</a></td>
              <td class="num-cell">{{ formatNum(stock.close_price) }}</td>
              <td :class="['num-cell', getChangeClass(stock.change_pct)]">
                {{ formatPct(stock.change_pct) }}
              </td>
              <td :class="['num-cell', getChangeClass(stock.pre_change_pct)]">
                {{ formatPct(stock.pre_change_pct) }}
              </td>
              <td :class="['num-cell', getChangeClass(stock.open_change_pct)]">
                {{ formatPct(stock.open_change_pct) }}
              </td>
              <td class="num-cell score-cell">
                <span v-if="stock.leader_level" :class="'level-tag ' + stock.leader_level">{{ stock.leader_level }}</span>
                <span v-else class="muted">{{ stock.final_score != null ? stock.final_score.toFixed(1) : '--' }}</span>
              </td>
              <td class="num-cell">{{ stock.leader_strength_score ?? '--' }}</td>
              <td class="num-cell">{{ stock.retreat_risk_score ?? '--' }}</td>
              <td class="reasons-cell">
                <span v-if="stock.reasons?.length" class="reasons-text" :title="stock.reasons.join('; ')">{{ stock.reasons[0] }}{{ stock.reasons.length > 1 ? '等' : '' }}</span>
                <span v-else class="muted">--</span>
              </td>
              <td class="num-cell">{{ formatPct(stock.auction_ratio) }}</td>
              <td class="num-cell">{{ formatPct(stock.auction_turnover_rate) }}</td>
              <td class="num-cell model-prob" :title="stock.t0_limit_success_model_version || '未启用模型'">
                {{ formatPct(stock.t0_limit_success_prob) }}
              </td>
              <td class="num-cell">{{ stock.touch_days || '--' }}</td>
              <td class="num-cell highlight">{{ stock.limit_up_days || stock.limit_up_count || '--' }}</td>
              <td class="num-cell">{{ formatPct(stock.seal_rate) }}</td>
              <td :class="['num-cell', getChangeClass(stock.rise_10d_pct)]">
                {{ formatPct(stock.rise_10d_pct) }}
              </td>
            </tr>
            <!-- 涨停/换手率标签行 -->
              <tr v-if="hasEnrichData(stock)" class="enrich-row">
                <td colspan="5" class="enrich-cell"><span class="enrich-tag lu-desc">{{ stock.lu_desc || '--' }}</span></td>
                <td colspan="3" class="enrich-cell"><span v-if="isLimitUp(stock)" class="enrich-tag lu-tag">{{ stock.lu_tag || '--' }}</span></td>
                <td colspan="2" class="enrich-cell"><span v-if="isLimitUp(stock)" class="enrich-tag lu-status">{{ stock.lu_status || '--' }}</span></td>
                <td colspan="2" class="enrich-cell"><span v-if="isLimitUp(stock)" class="enrich-tag open-num">炸板{{ stock.lu_open_num != null ? stock.lu_open_num : 0 }}次</span></td>
                <td colspan="3" class="enrich-cell"><span class="enrich-tag suc-rate">近一年封板率{{ fmtRate(stock.limit_up_suc_rate) }}</span></td>
                <td colspan="2" class="enrich-cell"><span class="enrich-tag turnover">昨日换手{{ formatPct(stock.prev_turnover_rate) }}</span></td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <p v-if="t0ModelDisclaimer" class="model-disclaimer">{{ t0ModelDisclaimer }}</p>
    </div>

    <!-- 个股详情弹窗 -->
    <StockDetailModal
      :visible="showDetailModal"
      :ts-code="detailTsCode"
      :stock-name="detailStockName"
      :record-id="currentRecordId"
      @close="showDetailModal = false"
    />

    <!-- 确认删除弹窗 -->
    <div v-if="showConfirm" class="modal-overlay" @click.self="showConfirm = false">
      <div class="modal-box">
        <h3>确认删除</h3>
        <p>{{ confirmMessage }}</p>
        <div class="modal-actions">
          <button class="btn-cancel" @click="showConfirm = false">取消</button>
          <button class="btn-confirm" @click="executeDelete" :disabled="deleting">
            {{ deleting ? '删除中...' : '确定删除' }}
          </button>
        </div>
      </div>
    </div>

    <p v-if="records.length === 0 && !loading" class="no-data">暂无选股记录</p>
    <p v-if="loading" class="loading">加载中...</p>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'
import StockDetailModal from './StockDetailModal.vue'
import { stockPreloadService } from '../services/StockPreloadService'

const records = ref([])
const stocks = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = 10
const totalRecords = ref(0)
const currentRecordId = ref(null)
const t0ModelDisclaimer = ref('')

const sortField = ref('health_score')
const sortOrder = ref('desc')

const showDetailModal = ref(false)
const detailTsCode = ref('')
const detailStockName = ref('')

const selectedIds = ref([])
const showConfirm = ref(false)
const deleting = ref(false)
const confirmMode = ref('batch')
const confirmTarget = ref(null)
const confirmMessage = ref('')

const preloading = ref(false)
const preloadProgress = ref(0)
const preloadCount = ref(0)

const totalPages = computed(() => Math.max(1, Math.ceil(totalRecords.value / pageSize)))

const isAllSelected = computed(() =>
  records.value.length > 0 && selectedIds.value.length === records.value.length
)

const isIndeterminate = computed(() =>
  selectedIds.value.length > 0 && selectedIds.value.length < records.value.length
)

const sortedStocks = computed(() => {
  if (!stocks.value.length) return []

  const sorted = [...stocks.value].sort((a, b) => {
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

onMounted(() => loadRecords())

async function loadRecords() {
  loading.value = true
  try {
    const res = await axios.get('/api/v1/stock/results', {
      params: { page: currentPage.value, page_size: pageSize }
    })
    const data = res.data?.data || {}
    records.value = data.records || []
    totalRecords.value = data.total || 0
    selectedIds.value = []

    if (records.value.length > 0 && currentRecordId.value === null) {
      const firstWithData = records.value.find(r => r.total_count > 0)
      if (firstWithData) loadStocks(firstWithData.id)
    }
  } catch (e) {
    console.error('加载记录失败:', e)
  } finally {
    loading.value = false
  }
}

async function loadStocks(recordId) {
  currentRecordId.value = recordId
  try {
    const res = await axios.get(`/api/v1/stock/results/${recordId}`)
    const data = res.data?.data || {}
    stocks.value = data.stocks || []
    t0ModelDisclaimer.value = data.t0_model_disclaimer || ''
    
    if (stocks.value.length > 0) {
      startPreload(stocks.value)
    }
  } catch (e) {
    console.error('加载股票失败:', e)
    stocks.value = []
    t0ModelDisclaimer.value = ''
  }
}

async function startPreload(stocksList) {
  preloading.value = true
  preloadProgress.value = 0
  preloadCount.value = 0
  
  try {
    const preloadStocks = stocksList.map(stock => ({
      ts_code: stock.ts_code,
      name: stock.name,
      record_id: currentRecordId.value
    }))
    
    const results = await stockPreloadService.preloadStocks(preloadStocks)
    
    let successCount = 0
    results.forEach(result => {
      if (result.status === 'fulfilled') successCount++
    })
    
    preloadCount.value = successCount
    preloadProgress.value = 100
    
    console.log(`预加载完成: ${successCount}/${results.length} 只股票`)

    // 第二步：后台批量预热AI数据（概览+异动解读），不阻塞响应
    axios.post('/api/v1/stock/detail/preload-ai', preloadStocks, { timeout: 5000 }).catch(() => {})
  } catch (e) {
    console.error('预加载失败:', e)
  } finally {
    setTimeout(() => {
      preloading.value = false
    }, 2000)
  }
}

function clearAllCache() {
  stockPreloadService.clearCache()
  alert('缓存已清空')
}

function showDetail(stock) {
  detailTsCode.value = stock.ts_code
  detailStockName.value = stock.name
  showDetailModal.value = true
}

function toggleSelect(id) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) {
    selectedIds.value.splice(idx, 1)
  } else {
    selectedIds.value.push(id)
  }
}

function toggleSelectAll() {
  if (isAllSelected.value) {
    selectedIds.value = []
  } else {
    selectedIds.value = records.value.map(r => r.id)
  }
}

function confirmDelete(id) {
  confirmMode.value = 'single'
  confirmTarget.value = id
  confirmMessage.value = `确定要删除选股记录 #${id} 吗？该操作不可撤销。`
  showConfirm.value = true
}

function confirmBatchDelete() {
  if (selectedIds.value.length === 0) return
  confirmMode.value = 'batch'
  confirmTarget.value = [...selectedIds.value]
  confirmMessage.value = `确定要删除 ${selectedIds.value.length} 条选股记录吗？该操作不可撤销。`
  showConfirm.value = true
}

async function executeDelete() {
  deleting.value = true
  try {
    if (confirmMode.value === 'single') {
      await axios.delete(`/api/v1/stock/results/${confirmTarget.value}`)
    } else {
      await axios.post('/api/v1/stock/results/batch-delete', confirmTarget.value)
    }
    showConfirm.value = false
    selectedIds.value = []
    await loadRecords()
  } catch (e) {
    console.error('删除失败:', e)
    alert('删除失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    deleting.value = false
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

function getChangeClass(change) {
  if (change === null || change === undefined) return ''
  if (change > 0) return 'positive'
  if (change < 0) return 'negative'
  return ''
}

function prevPage() {
  if (currentPage.value > 1) {
    currentPage.value--
    loadRecords()
  }
}

function nextPage() {
  if (currentPage.value < totalPages.value) {
    currentPage.value++
    loadRecords()
  }
}

function statusText(s) {
  return { success: '成功', partial: '部分', failed: '失败', running: '运行中' }[s] || s
}

function formatNum(v) { return v != null ? Number(v).toFixed(2) : '--' }
function formatPct(v) { return v != null ? Number(v).toFixed(2) + '%' : '--' }
function formatTime(t) { if (!t) return '--'; return t.replace('T', ' ').substring(0, 19) }

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
</script>

<style scoped>
.stock-results { padding: 20px; max-width: 1800px; margin: 0 auto; }
.section { margin-bottom: 24px; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 12px;
}

.section-header h3 { margin: 0; font-size: 16px; color: #333; }
.section-header h3 small { color: #999; font-weight: normal; font-size: 13px; }
.stock-count-bar { background: #f6ffed; padding: 8px 14px; border-radius: 4px; color: #52c41a; font-size: 13px; }

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.preload-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #e6f7ff;
  border-radius: 4px;
  color: #1890ff;
  font-size: 12px;
}

.preload-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #91d5ff;
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.btn-clear-cache {
  padding: 6px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 12px;
  color: #999;
}

.btn-clear-cache:hover {
  border-color: #ff4d4f;
  color: #ff4d4f;
}

.batch-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-delete-batch {
  padding: 6px 16px;
  border: 1px solid #ff4d4f;
  border-radius: 4px;
  background: #fff;
  color: #ff4d4f;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}
.btn-delete-batch:hover:not(:disabled) {
  background: #ff4d4f;
  color: #fff;
}
.btn-delete-batch:disabled {
  opacity: .4;
  cursor: not-allowed;
  border-color: #d9d9d9;
  color: #d9d9d9;
}

/* 表格容器 */
.table-wrapper { overflow-x: auto; border-radius: 8px; border: 1px solid #f0f0f0; }

.model-disclaimer {
  margin: 10px 0 0;
  color: #8c8c8c;
  font-size: 12px;
  line-height: 1.6;
}

.data-table { width: 100%; border-collapse: collapse; margin-top: 12px; white-space: nowrap; }
.data-table th,
.data-table td {
  padding: 10px 8px;
  text-align: center;
  border-bottom: 1px solid #f0f0f0;
  font-size: 12.5px;
}
.data-table th {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-weight: 600;
  font-size: 11.5px;
  letter-spacing: 0.5px;
}
.data-table tr:hover { background: #fafafa; }

.col-check {
  width: 40px;
}
.col-check input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: #1890ff;
}

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

.index-col {
  width: 60px;
  text-align: center;
  color: #999;
  font-size: 12px;
}

.num-cell { font-family: 'SF Mono', -apple-system, sans-serif; font-variant-numeric: tabular-nums; }
.num-cell.muted { color: #bbb; }
.num-cell.highlight { color: #ff4d4f; font-weight: 700; }
.num-cell.score-cell { color: #667eea; font-weight: 700; }

.level-badge {
  display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: 700;
}
.level-badge.A\+ { background: linear-gradient(135deg, #667eea20, #764ba220); color: #667eea; }
.level-badge.A { background: #f6ffed; color: #52c41a; }
.level-badge.B\+ { background: #fff7e6; color: #fa8c16; }
.level-badge.B { background: #fffbe6; color: #faad14; }
.level-badge.C { background: #fff2f0; color: #ff4d4f; }
.level-badge.D { background: #f5f5f5; color: #999; }

.reasons-cell { max-width: 180px; }
.reasons-text { font-size: 11px; color: #666; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.stock-name-link { color: #667eea; font-weight: 600; text-decoration: none; cursor: pointer; }
.stock-name-link:hover { text-decoration: underline; color: #764ba2; }

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

.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
}
.badge.success { background: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }
.badge.partial { background: #fffbe6; color: #faad14; border: 1px solid #ffe58f; }
.badge.failed { background: #fff2f0; color: #ff4d4f; border: 1px solid #ffccc7; }
.badge.running { background: #e6f7ff; color: #1890ff; border: 1px solid #91d5ff; }

.actions-cell { white-space: nowrap; }
.btn-detail {
  padding: 5px 14px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  cursor: pointer;
  background: white;
  font-size: 13px;
  margin-right: 6px;
}
.btn-detail:hover:not(:disabled) { border-color: #1890ff; color: #1890ff; }
.btn-detail:disabled { opacity: .4; cursor: not-allowed; }

.btn-delete {
  padding: 5px 14px;
  border: 1px solid #ffccc7;
  border-radius: 4px;
  cursor: pointer;
  background: white;
  color: #ff4d4f;
  font-size: 13px;
}
.btn-delete:hover { background: #fff2f0; }

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  margin-top: 16px;
}
.pagination button {
  padding: 5px 14px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: white;
  cursor: pointer;
}
.pagination button:disabled { opacity: .4; cursor: not-allowed; }

code {
  background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
  padding: 3px 8px;
  border-radius: 4px;
  font-family: 'SF Mono', Monaco, monospace;
  font-size: 11.5px;
  color: #667eea;
  font-weight: 600;
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

.no-data, .loading {
  text-align: center;
  padding: 50px;
  color: #999;
  background: white;
  border-radius: 8px;
}
.loading { color: #1890ff; }

/* 确认弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}
.modal-box {
  background: white;
  border-radius: 8px;
  padding: 24px;
  min-width: 380px;
  max-width: 480px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
.modal-box h3 {
  margin: 0 0 12px;
  font-size: 16px;
  color: #333;
}
.modal-box p {
  margin: 0 0 20px;
  color: #666;
  font-size: 14px;
  line-height: 1.6;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.btn-cancel {
  padding: 8px 20px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 13px;
}
.btn-cancel:hover { border-color: #1890ff; color: #1890ff; }
.btn-confirm {
  padding: 8px 20px;
  border: none;
  border-radius: 4px;
  background: #ff4d4f;
  color: white;
  cursor: pointer;
  font-size: 13px;
}
.btn-confirm:hover:not(:disabled) { background: #ff7875; }
.btn-confirm:disabled { opacity: .5; cursor: not-allowed; }

@media (max-width: 1400px) {
  .data-table { font-size: 11.5px; }
  .data-table th, .data-table td { padding: 6px 4px; }
}
</style>
