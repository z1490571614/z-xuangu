<template>
  <div class="strategy-manage">
    <div class="page-header">
      <h2>选股策略管理</h2>
      <button class="btn-primary" @click="openCreateModal">
        + 新建策略
      </button>
    </div>

    <!-- 策略列表 -->
    <div class="strategy-list" v-if="!loading">
      <div v-if="strategies.length === 0" class="empty-state">
        <p>暂无策略模板</p>
        <button class="btn-primary" @click="openCreateModal">创建第一个策略</button>
      </div>

      <div
        v-for="strategy in strategies"
        :key="strategy.id"
        :class="['strategy-item', { disabled: !strategy.is_enabled }]"
      >
        <div class="strategy-info">
          <div class="strategy-title-row">
            <h3>{{ strategy.name }}</h3>
            <div class="badges">
              <span v-if="strategy.is_system" class="badge system">系统预置</span>
              <span v-else class="badge custom">自定义</span>
              <span :class="['badge', strategy.is_enabled ? 'enabled' : 'disabled']">
                {{ strategy.is_enabled ? '已启用' : '已禁用' }}
              </span>
            </div>
          </div>

          <p class="description">{{ strategy.description || '暂无描述' }}</p>

          <!-- 关键参数摘要 -->
          <div class="params-summary">
            <span v-if="getConfigValue(strategy, 'market_cap', 'max_market_cap')">
              市值≤{{ getConfigValue(strategy, 'market_cap', 'max_market_cap') }}亿
            </span>
            <span v-if="getConfigValue(strategy, 'price', 'max_close_price')">
              价格≤{{ getConfigValue(strategy, 'price', 'max_close_price') }}元
            </span>
            <span v-if="getConfigValue(strategy, 'limit_up', 'min_limit_up_count')">
              涨停≥{{ getConfigValue(strategy, 'limit_up', 'min_limit_up_count') }}次
            </span>
          </div>
        </div>

        <div class="strategy-actions">
          <button
            class="btn-sm btn-outline"
            @click="previewQuery(strategy)"
            title="预览查询语句"
          >
            👁️ 预览
          </button>
          <button
            class="btn-sm btn-outline"
            @click="editStrategy(strategy)"
            :disabled="strategy.is_system"
            title="编辑参数"
          >
            ✏️ 编辑
          </button>
          <button
            :class="['btn-sm', strategy.is_enabled ? 'btn-warning' : 'btn-success']"
            @click="toggleStrategy(strategy)"
            :title="strategy.is_enabled ? '禁用' : '启用'"
          >
            {{ strategy.is_enabled ? '⏸ 禁用' : '▶ 启用' }}
          </button>
          <button
            class="btn-sm btn-danger"
            @click="deleteStrategy(strategy)"
            :disabled="strategy.is_system"
            title="删除"
          >
            🗑️ 删除
          </button>
        </div>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-else class="loading-state">
      <p>加载中...</p>
    </div>

    <!-- 创建/编辑弹窗 -->
    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal-container">
        <div class="modal-header">
          <h3>{{ editingStrategy ? '编辑策略' : '新建策略' }}</h3>
          <button class="close-btn" @click="closeModal">×</button>
        </div>

        <div class="modal-body">
          <form @submit.prevent="saveStrategy">
            <!-- 基本信息 -->
            <div class="form-section">
              <h4>基本信息</h4>
              <div class="form-group">
                <label>策略名称 *</label>
                <input
                  v-model="formData.name"
                  type="text"
                  placeholder="输入策略名称"
                  :disabled="editingStrategy?.is_system"
                  required
                />
              </div>
              <div class="form-group">
                <label>策略描述</label>
                <textarea
                  v-model="formData.description"
                  placeholder="简要描述该策略的特点和适用场景"
                  rows="3"
                ></textarea>
              </div>
            </div>

            <!-- 选股条件配置 -->
            <div class="form-section">
              <h4>选股条件参数</h4>

              <!-- 基本过滤 -->
              <div class="condition-group">
                <h5>📋 基本过滤</h5>
                <div class="checkbox-group">
                  <label><input type="checkbox" v-model="formData.conditions_config.basic_filter.exclude_st" /> 排除ST股票</label>
                  <label><input type="checkbox" v-model="formData.conditions_config.basic_filter.exclude_suspended" /> 排除停牌股</label>
                  <label><input type="checkbox" v-model="formData.conditions_config.basic_filter.exclude_bse" /> 排除北交所</label>
                </div>
              </div>

              <!-- 市值过滤 -->
              <div class="condition-group">
                <h5>💰 市值过滤</h5>
                <div class="form-group">
                  <label>最大流通市值 (亿元)</label>
                  <input
                    v-model.number="formData.conditions_config.market_cap.max_market_cap"
                    type="number"
                    min="1"
                    max="10000"
                    step="10"
                  />
                  <small>建议范围: 500-2000亿</small>
                </div>
              </div>

              <!-- 价格过滤 -->
              <div class="condition-group">
                <h5>💵 价格过滤</h5>
                <div class="form-group">
                  <label>最大收盘价 (元)</label>
                  <input
                    v-model.number="formData.conditions_config.price.max_close_price"
                    type="number"
                    min="1"
                    max="2000"
                    step="1"
                  />
                  <small>建议范围: 50-500元</small>
                </div>
              </div>

              <!-- 趋势条件 -->
              <div class="condition-group">
                <h5>📈 趋势条件</h5>
                <div class="form-group">
                  <label>近N日股价上涨 (天)</label>
                  <input
                    v-model.number="formData.conditions_config.trend.min_rise_days"
                    type="number"
                    min="1"
                    max="120"
                    step="1"
                  />
                  <small>建议范围: 5-20天</small>
                </div>
              </div>

              <!-- 涨停强度 -->
            <div class="condition-group">
                <h5>🔥 涨停强度</h5>
                <div class="form-row">
                    <div class="form-group">
                        <label>最小涨停次数</label>
                        <input
                            v-model.number="formData.conditions_config.limit_up.min_limit_up_count"
                            type="number"
                            min="0"
                            max="30"
                            step="1"
                        />
                    </div>
                    <div class="form-group">
                        <label>最小封板成功率 (%)</label>
                        <input
                            v-model.number="formData.conditions_config.limit_up.min_seal_rate"
                            type="number"
                            min="0"
                            max="100"
                            step="1"
                        />
                    </div>
                </div>
                <div class="form-group">
                    <label>统计周期 (交易日)</label>
                    <input
                        v-model.number="formData.conditions_config.limit_up.limit_up_days"
                        type="number"
                        min="30"
                        max="250"
                        step="10"
                    />
                </div>
            </div>

              <!-- 竞价活跃度 -->
              <div class="condition-group">
                <h5>⚡ 竞价活跃度</h5>
                <div class="form-row">
                  <div class="form-group">
                    <label>竞昨比最小值 (%)</label>
                    <input
                      v-model.number="formData.conditions_config.call_auction.call_auction_ratio_min"
                      type="number"
                      min="0"
                      max="100"
                      step="0.5"
                    />
                  </div>
                  <div class="form-group">
                    <label>竞昨比最大值 (%)</label>
                    <input
                      v-model.number="formData.conditions_config.call_auction.call_auction_ratio_max"
                      type="number"
                      min="0"
                      max="100"
                      step="0.5"
                    />
                  </div>
                </div>
                <div class="form-row">
                  <div class="form-group">
                    <label>竞价换手率最小值 (%)</label>
                    <input
                      v-model.number="formData.conditions_config.call_auction.turnover_rate_min"
                      type="number"
                      min="0"
                      max="50"
                      step="0.1"
                    />
                  </div>
                  <div class="form-group">
                    <label>竞价换手率最大值 (%)</label>
                    <input
                      v-model.number="formData.conditions_config.call_auction.turnover_rate_max"
                      type="number"
                      min="0"
                      max="50"
                      step="0.1"
                    />
                  </div>
                </div>
              </div>

              <!-- 开盘涨幅过滤 -->
              <div class="condition-group">
                <h5>📈 开盘涨幅过滤</h5>
                <div class="form-group">
                  <label>最小开盘涨幅 (%)</label>
                  <input
                    v-model.number="formData.conditions_config.open_change.min_open_change_pct"
                    type="number"
                    min="-20"
                    max="20"
                    step="0.5"
                  />
                  <small>负数表示允许低开，如-3表示允许低开不超过3%</small>
                </div>
              </div>
            </div>

            <!-- 实时预览 -->
            <div class="preview-section" v-if="previewText">
              <h4>📝 生成的查询语句预览</h4>
              <pre class="query-preview">{{ previewText }}</pre>
            </div>

            <!-- 操作按钮 -->
            <div class="form-actions">
              <button type="button" class="btn-secondary" @click="closeModal">
                取消
              </button>
              <button
                type="button"
                class="btn-outline"
                @click="generatePreview"
              >
                预览查询
              </button>
              <button type="submit" class="btn-primary" :disabled="saving">
                {{ saving ? '保存中...' : '保存策略' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <!-- 查询预览弹窗 -->
    <div v-if="showPreviewModal" class="modal-overlay" @click.self="showPreviewModal = false">
      <div class="modal-container modal-small">
        <div class="modal-header">
          <h3>查询语句预览 - {{ previewData?.strategy_name }}</h3>
          <button class="close-btn" @click="showPreviewModal = false">×</button>
        </div>
        <div class="modal-body">
          <pre class="query-preview">{{ previewData?.query }}</pre>
          <p class="preview-info">
            包含 {{ previewData?.conditions_count || 0 }} 个筛选条件
          </p>
        </div>
      </div>
    </div>

    <!-- 提示消息 -->
    <div v-if="message" :class="['toast', message.type]">
      {{ message.text }}
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import axios from 'axios'

const strategies = ref([])
const loading = ref(false)
const saving = ref(false)
const showModal = ref(false)
const showPreviewModal = ref(false)
const editingStrategy = ref(null)
const message = ref(null)
const previewData = ref(null)

const formData = ref({
  name: '',
  description: '',
  task_template: 'custom',
  conditions_config: {
    basic_filter: {
      exclude_st: true,
      exclude_suspended: true,
      exclude_bse: true,
    },
    market_cap: {
      max_market_cap: 2000,
    },
    price: {
      max_close_price: 500,
    },
    trend: {
      min_rise_days: 10,
    },
    limit_up: {
      min_limit_up_count: 3,
      min_seal_rate: 80,
      limit_up_days: 100,
    },
    call_auction: {
      call_auction_ratio_min: 4,
      call_auction_ratio_max: 30,
      turnover_rate_min: 0.5,
      turnover_rate_max: 10,
    },
    open_change: {
      min_open_change_pct: -3,
    },
  },
})

const previewText = computed(() => {
  const config = formData.value.conditions_config
  if (!config) return ''

  const parts = []

  if (config.basic_filter) {
    const bf = config.basic_filter
    const conditions = []
    if (bf.exclude_st) conditions.push('非ST')
    if (bf.exclude_suspended) conditions.push('非停牌')
    if (bf.exclude_bse) conditions.push('非北交所')
    if (conditions.length > 0) parts.push(conditions.join('') + '股票')
  }

  if (config.market_cap?.max_market_cap) {
    parts.push(`流通市值小于${config.market_cap.max_market_cap}亿`)
  }

  if (config.price?.max_close_price) {
    parts.push(`昨日收盘价小于${config.price.max_close_price}元`)
  }

  if (config.trend?.min_rise_days) {
    parts.push(`近${config.trend.min_rise_days}日股价上涨`)
  }

  if (config.limit_up) {
    const lu = config.limit_up
    const luParts = []
    if (lu.min_limit_up_count > 0) {
      luParts.push(`近${lu.limit_up_days || 100}个交易日内涨停次数不少于${lu.min_limit_up_count}次`)
    }
    if (lu.min_seal_rate > 0) {
      luParts.push(`封板成功率不低于${lu.min_seal_rate}%`)
    }
    if (luParts.length > 0) parts.push(luParts.join('，'))
  }

  if (config.call_auction) {
    const ca = config.call_auction
    const caParts = []
    if (ca.call_auction_ratio_min > 0 && ca.call_auction_ratio_max > 0) {
      caParts.push(
        `竞价量占昨日成交量比例${ca.call_auction_ratio_min}%到${ca.call_auction_ratio_max}%`
      )
    }
    if (ca.turnover_rate_min > 0 && ca.turnover_rate_max > 0) {
      caParts.push(
        `竞价换手率${ca.turnover_rate_min}%到${ca.turnover_rate_max}%`
      )
    }
    if (caParts.length > 0) parts.push(caParts.join('，'))
  }

  if (config.open_change) {
    const oc = config.open_change
    if (oc.min_open_change_pct !== undefined && oc.min_open_change_pct !== null) {
      parts.push(`开盘涨幅≥${oc.min_open_change_pct}%`)
    }
  }

  return parts.join('，')
})

onMounted(() => {
  loadStrategies()
})

async function loadStrategies() {
  loading.value = true
  try {
    const res = await axios.get('/api/v1/stock/strategies', {
      params: { include_disabled: true }
    })
    strategies.value = res.data?.data?.strategies || []
  } catch (e) {
    console.error('加载策略失败:', e)
    showToast('加载策略列表失败', 'error')
  } finally {
    loading.value = false
  }
}

function getConfigValue(strategy, conditionKey, paramKey) {
  return strategy.conditions_config?.[conditionKey]?.[paramKey]
}

function openCreateModal() {
  editingStrategy.value = null
  resetForm()
  showModal.value = true
}

function editStrategy(strategy) {
  if (strategy.is_system) {
    showToast('系统预置模板不允许编辑', 'warning')
    return
  }

  editingStrategy.value = strategy
  formData.value = {
    name: strategy.name,
    description: strategy.description || '',
    task_template: strategy.task_template,
    conditions_config: JSON.parse(JSON.stringify(strategy.conditions_config || {})),
  }
  showModal.value = true
}

function resetForm() {
  formData.value = {
    name: '',
    description: '',
    task_template: 'custom',
    conditions_config: {
      basic_filter: {
        exclude_st: true,
        exclude_suspended: true,
        exclude_bse: true,
      },
      market_cap: { max_market_cap: 2000 },
      price: { max_close_price: 500 },
      trend: { min_rise_days: 10 },
      limit_up: {
        min_limit_up_count: 3,
        min_seal_rate: 80,
        limit_up_days: 100,
      },
      call_auction: {
        call_auction_ratio_min: 4,
        call_auction_ratio_max: 30,
        turnover_rate_min: 0.5,
        turnover_rate_max: 10,
      },
    },
  }
}

function closeModal() {
  showModal.value = false
  editingStrategy.value = null
}

async function saveStrategy() {
  if (!formData.value.name.trim()) {
    showToast('请输入策略名称', 'warning')
    return
  }

  saving.value = true
  try {
    if (editingStrategy.value) {
      await axios.put(`/api/v1/stock/strategies/${editingStrategy.value.id}`, formData.value)
      showToast('策略更新成功', 'success')
    } else {
      await axios.post('/api/v1/stock/strategies', formData.value)
      showToast('策略创建成功', 'success')
    }

    closeModal()
    await loadStrategies()
  } catch (e) {
    console.error('保存策略失败:', e)
    showToast(e.response?.data?.detail || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

async function deleteStrategy(strategy) {
  if (strategy.is_system) {
    showToast('系统预置模板不允许删除', 'warning')
    return
  }

  if (!confirm(`确定要删除策略"${strategy.name}"吗？此操作不可恢复。`)) {
    return
  }

  try {
    await axios.delete(`/api/v1/stock/strategies/${strategy.id}`)
    showToast('策略删除成功', 'success')
    await loadStrategies()
  } catch (e) {
    console.error('删除策略失败:', e)
    showToast(e.response?.data?.detail || '删除失败', 'error')
  }
}

async function toggleStrategy(strategy) {
  try {
    await axios.patch(`/api/v1/stock/strategies/${strategy.id}/toggle`)
    const status = strategy.is_enabled ? '禁用' : '启用'
    showToast(`策略已${status}`, 'success')
    await loadStrategies()
  } catch (e) {
    console.error('切换状态失败:', e)
    showToast('操作失败', 'error')
  }
}

async function previewQuery(strategy) {
  try {
    const res = await axios.post(`/api/v1/stock/strategies/${strategy.id}/preview`)
    previewData.value = res.data?.data
    showPreviewModal.value = true
  } catch (e) {
    console.error('预览失败:', e)
    showToast('预览失败', 'error')
  }
}

function generatePreview() {
  // 已通过 computed 属性自动生成
  showToast('查询语句已更新', 'info')
}

function showToast(text, type = 'info') {
  message.value = { text, type }
  setTimeout(() => { message.value = null }, 3000)
}
</script>

<style scoped>
.strategy-manage {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 24px;
  color: #333;
}

.strategy-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.empty-state, .loading-state {
  text-align: center;
  padding: 60px 20px;
  color: #999;
}

.strategy-item {
  background: white;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: all 0.25s;
  border: 2px solid transparent;
}

.strategy-item:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  border-color: #e6f7ff;
}

.strategy-item.disabled {
  opacity: 0.6;
}

.strategy-info {
  flex: 1;
  margin-right: 20px;
}

.strategy-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.strategy-title-row h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
}

.badges {
  display: flex;
  gap: 8px;
}

.badge {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
}

.badge.system {
  background: #e6f7ff;
  color: #1890ff;
}

.badge.custom {
  background: #fff7e6;
  color: #fa8c16;
}

.badge.enabled {
  background: #f6ffed;
  color: #52c41a;
}

.badge.disabled {
  background: #fff2f0;
  color: #ff4d4f;
}

.description {
  margin: 0 0 10px 0;
  color: #666;
  font-size: 14px;
  line-height: 1.5;
}

.params-summary {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #888;
  flex-wrap: wrap;
}

.params-summary span {
  padding: 4px 10px;
  background: #f5f5f5;
  border-radius: 4px;
}

.strategy-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.btn-sm {
  padding: 6px 14px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.btn-outline {
  background: white;
  border: 1px solid #d9d9d9;
  color: #666;
}

.btn-outline:hover:not(:disabled) {
  border-color: #1890ff;
  color: #1890ff;
}

.btn-success {
  background: #f6ffed;
  color: #52c41a;
  border: 1px solid #b7eb8f;
}

.btn-warning {
  background: #fffbe6;
  color: #faad14;
  border: 1px solid #ffe58f;
}

.btn-danger {
  background: #fff2f0;
  color: #ff4d4f;
  border: 1px solid #ffccc7;
}

.btn-sm:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Modal 样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  overflow-y: auto;
  padding: 20px;
}

.modal-container {
  background: white;
  border-radius: 12px;
  width: 100%;
  max-width: 800px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
}

.modal-container.modal-small {
  max-width: 600px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #f0f0f0;
  position: sticky;
  top: 0;
  background: white;
  z-index: 1;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
}

.close-btn {
  background: none;
  border: none;
  font-size: 28px;
  cursor: pointer;
  color: #999;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
}

.close-btn:hover {
  background: #f5f5f5;
  color: #333;
}

.modal-body {
  padding: 24px;
}

.form-section {
  margin-bottom: 28px;
}

.form-section h4 {
  margin: 0 0 16px 0;
  font-size: 16px;
  color: #333;
  padding-bottom: 8px;
  border-bottom: 2px solid #1890ff;
}

.condition-group {
  margin-bottom: 20px;
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
  border-left: 3px solid #1890ff;
}

.condition-group h5 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: #555;
}

.form-group {
  margin-bottom: 14px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: #555;
  font-size: 14px;
}

.form-group input[type="text"],
.form-group input[type="number"],
.form-group textarea {
  width: 100%;
  padding: 9px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.25s;
  box-sizing: border-box;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 3px rgba(24, 144, 255, 0.1);
}

.form-group input:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

.form-group small {
  display: block;
  margin-top: 4px;
  color: #999;
  font-size: 12px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.checkbox-group label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #666;
}

.checkbox-group input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.preview-section {
  margin-bottom: 24px;
  padding: 18px;
  background: #f6f8fa;
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}

.preview-section h4 {
  margin: 0 0 12px 0;
  font-size: 15px;
  color: #333;
}

.query-preview {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 6px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
}

.preview-info {
  text-align: center;
  color: #888;
  font-size: 13px;
  margin: 12px 0 0 0;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 20px;
  border-top: 1px solid #f0f0f0;
}

.btn-primary {
  padding: 10px 24px;
  border: none;
  border-radius: 6px;
  background: linear-gradient(135deg, #1890ff 0%, #096dd9 100%);
  color: white;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.25s;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(24, 144, 255, 0.35);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 10px 24px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: white;
  color: #666;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.25s;
}

.btn-secondary:hover {
  border-color: #1890ff;
  color: #1890ff;
}

.toast {
  position: fixed;
  top: 80px;
  right: 24px;
  padding: 14px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  z-index: 2000;
  animation: slideInRight 0.3s ease-out;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}

@keyframes slideInRight {
  from {
    transform: translateX(400px);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

.toast.success {
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  color: #52c41a;
}

.toast.error {
  background: #fff2f0;
  border: 1px solid #ffccc7;
  color: #ff4d4f;
}

.toast.warning {
  background: #fffbe6;
  border: 1px solid #ffe58f;
  color: #faad14;
}

.toast.info {
  background: #e6f7ff;
  border: 1px solid #91d5ff;
  color: #1890ff;
}

@media (max-width: 768px) {
  .strategy-item {
    flex-direction: column;
    align-items: flex-start;
  }

  .strategy-actions {
    width: 100%;
    margin-top: 16px;
    flex-wrap: wrap;
  }

  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
