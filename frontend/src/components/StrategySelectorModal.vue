<template>
  <div v-if="visible" class="modal-overlay" @click.self="handleClose">
    <div class="modal-container">
      <div class="modal-header">
        <h3>选择选股策略</h3>
        <button class="close-btn" @click="handleClose">×</button>
      </div>

      <div class="modal-body">
        <!-- 策略卡片列表 -->
        <div class="strategy-cards">
          <div
            v-for="strategy in strategies"
            :key="strategy.id"
            :class="['strategy-card', { selected: selectedId === strategy.id, disabled: !strategy.is_enabled }]"
            @click="selectStrategy(strategy)"
          >
            <div class="card-header">
              <div class="card-title">
                <span class="strategy-name">{{ strategy.name }}</span>
                <span v-if="strategy.is_system" class="badge system">系统</span>
                <span v-else class="badge custom">自定义</span>
              </div>
              <div
                :class="['status-indicator', { active: strategy.is_enabled }]"
              ></div>
            </div>

            <p class="card-description">{{ strategy.description }}</p>

            <!-- 关键参数预览 -->
            <div class="params-preview">
                <div class="param-item" v-if="strategy.conditions_config?.market_cap">
                    <span class="param-label">市值上限:</span>
                    <span class="param-value">{{ strategy.conditions_config.market_cap.max_market_cap }}亿</span>
                </div>
                <div class="param-item" v-if="strategy.conditions_config?.price">
                    <span class="param-label">价格上限:</span>
                    <span class="param-value">{{ strategy.conditions_config.price.max_close_price }}元</span>
                </div>
                <div class="param-item" v-if="strategy.conditions_config?.limit_up">
                    <span class="param-label">涨停要求:</span>
                    <span class="param-value">
                        ≥{{ strategy.conditions_config.limit_up.min_limit_up_count }}次
                        <span v-if="strategy.conditions_config.limit_up.min_seal_rate">
                            ，封板率≥{{ strategy.conditions_config.limit_up.min_seal_rate }}%
                        </span>
                    </span>
                </div>
                <div class="param-item" v-if="strategy.conditions_config?.call_auction">
                    <span class="param-label">竞价活跃度:</span>
                    <span class="param-value">{{ strategy.conditions_config.call_auction.call_auction_ratio_min }}%-{{ strategy.conditions_config.call_auction.call_auction_ratio_max }}%</span>
                </div>
                <div class="param-item" v-if="strategy.conditions_config?.open_change">
                    <span class="param-label">开盘涨幅:</span>
                    <span class="param-value">≥{{ strategy.conditions_config.open_change.min_open_change_pct }}%</span>
                </div>
            </div>

            <!-- 选中标记 -->
            <div v-if="selectedId === strategy.id" class="selected-checkmark">✓</div>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="action-buttons">
          <button class="btn-secondary" @click="goToManagePage">
            ⚙️ 管理策略
          </button>
          <button
            class="btn-primary"
            :disabled="!selectedId || executing"
            @click="executeWithStrategy"
          >
            {{ executing ? '执行中...' : '开始选股' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  tradeDate: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['close', 'select', 'execute', 'manage', 'success', 'error', 'loading'])

const strategies = ref([])
const selectedId = ref(null)
const executing = ref(false)

onMounted(() => {
  if (props.visible) {
    loadStrategies()
  }
})

watch(() => props.visible, (newVal) => {
  if (newVal) {
    loadStrategies()
  }
})

async function loadStrategies() {
  try {
    const res = await axios.get('/api/v1/stock/strategies')
    strategies.value = res.data?.data?.strategies || []

    // 默认选中第一个启用的策略
    const firstEnabled = strategies.value.find(s => s.is_enabled)
    if (firstEnabled) {
      selectedId.value = firstEnabled.id
    }
  } catch (e) {
    console.error('加载策略列表失败:', e)
  }
}

function selectStrategy(strategy) {
  if (!strategy.is_enabled) return

  selectedId.value = strategy.id
  emit('select', strategy)
}

async function executeWithStrategy() {
  console.log('=== executeWithStrategy ===')
  if (!selectedId.value || executing.value) return

  executing.value = true
  emit('loading', true)

  try {
    const selectedStrategy = strategies.value.find(s => s.id === selectedId.value)

    emit('execute', {
      trade_date: props.tradeDate,
      strategy_id: selectedId.value,
      task_template: selectedStrategy?.task_template,
      notify: false
    })

    console.log('准备调用API...')
    // 调用API执行选股
    const res = await axios.post('/api/v1/stock/select', {
      trade_date: props.tradeDate,
      strategy_id: selectedId.value,
      min_seal_rate: selectedStrategy?.conditions_config?.limit_up?.min_seal_rate,
      min_open_change_pct: selectedStrategy?.conditions_config?.open_change?.min_open_change_pct,
      notify: false
    })

    const data = res.data?.data || {}
    console.log('API返回:', data)

    // 先重置状态再关闭
    executing.value = false
    emit('loading', false)

    console.log('先关闭弹窗...')
    // 关闭弹窗
    handleClose()

    // 小延迟确保关闭完成
    await new Promise(r => setTimeout(r, 100))

    console.log('发送success事件...')
    // 发送成功事件
    emit('success', {
      passed_count: data.passed_count,
      total_count: data.total_count,
      strategy_name: selectedStrategy?.name
    })
  } catch (e) {
    console.error('执行选股失败:', e)
    // 出错也重置状态
    executing.value = false
    emit('loading', false)
    emit('error', e.message)
  }
}

function goToManagePage() {
  emit('manage')
  handleClose()
}

function handleClose() {
  emit('close')
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease-in-out;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-container {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 900px;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  animation: slideUp 0.3s ease-out;
}

@keyframes slideUp {
  from {
    transform: translateY(30px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #f0f0f0;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 28px;
  cursor: pointer;
  color: #999;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #f5f5f5;
  color: #333;
}

.modal-body {
  padding: 24px;
}

.strategy-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.strategy-card {
  position: relative;
  border: 2px solid #e8e8e8;
  border-radius: 10px;
  padding: 18px;
  cursor: pointer;
  transition: all 0.25s ease;
  background: #fafafa;
}

.strategy-card:hover:not(.disabled) {
  border-color: #1890ff;
  box-shadow: 0 4px 12px rgba(24, 144, 255, 0.15);
  transform: translateY(-2px);
}

.strategy-card.selected {
  border-color: #1890ff;
  background: #e6f7ff;
  box-shadow: 0 4px 16px rgba(24, 144, 255, 0.2);
}

.strategy-card.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.strategy-name {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.badge {
  padding: 2px 8px;
  border-radius: 10px;
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

.status-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #d9d9d9;
}

.status-indicator.active {
  background: #52c41a;
  box-shadow: 0 0 6px rgba(82, 196, 26, 0.5);
}

.card-description {
  margin: 0 0 14px 0;
  font-size: 13px;
  color: #666;
  line-height: 1.5;
  min-height: 40px;
}

.params-preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.param-item {
  display: flex;
  font-size: 12px;
  line-height: 1.6;
}

.param-label {
  color: #999;
  min-width: 80px;
}

.param-value {
  color: #333;
  font-weight: 500;
}

.selected-checkmark {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 24px;
  height: 24px;
  background: #1890ff;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: bold;
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.3);
}

.action-buttons {
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
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.25);
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(24, 144, 255, 0.35);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
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
</style>
