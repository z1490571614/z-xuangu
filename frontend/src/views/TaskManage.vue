<template>
  <div class="task-manage">
    <h2>任务管理</h2>

    <!-- WebSocket连接状态 -->
    <div class="ws-status-bar">
      <div :class="['status-indicator', wsStatus]">
        <span class="dot"></span>
        {{ wsStatusText }}
      </div>
      <div class="ws-info" v-if="wsStatus === 'connected'">
        <span v-if="lastMessageTime">最后更新: {{ formatTime(lastMessageTime) }}</span>
        <button @click="disconnectWS" class="btn-ws-action">断开</button>
      </div>
      <div class="ws-info" v-else-if="wsStatus === 'disconnected' || wsStatus === 'error'">
        <button @click="connectWS" class="btn-ws-action btn-reconnect">重新连接</button>
      </div>
    </div>

    <!-- 创建任务表单 -->
    <div class="section create-section">
      <h3 class="section-title">创建新任务</h3>
      <form class="task-form" @submit.prevent="createTask">
        <div class="form-row">
          <input type="text" placeholder="任务名称" v-model="newTask.name" required />
          <input type="text" placeholder="Cron 表达式 (如: 30 9 * * 1-5)" v-model="newTask.cron" required />
        </div>
        <textarea placeholder="任务描述" v-model="newTask.description"></textarea>
        <button type="submit" class="btn-primary" :disabled="creating">
          {{ creating ? '创建中...' : '创建任务' }}
        </button>
      </form>
    </div>

    <!-- 任务列表 -->
    <div class="section task-list-section">
      <div class="section-header">
        <h3 class="section-title">
          任务列表
          <span class="live-badge" v-if="wsStatus === 'connected'">
            <span class="pulse-dot"></span>
            WebSocket实时
          </span>
          <span class="poll-badge" v-else-if="autoRefresh">
            轮询模式 ({{ refreshInterval }}s)
          </span>
        </h3>
        <div class="header-actions" v-if="wsStatus !== 'connected'">
          <button
            @click="toggleAutoRefresh"
            :class="['btn-toggle', { active: autoRefresh }]"
          >
            {{ autoRefresh ? '停止刷新' : '开启轮询' }}
          </button>
          <button @click="loadTasks" class="btn-refresh" :disabled="loading">
            {{ loading ? '加载中...' : '手动刷新' }}
          </button>
        </div>
      </div>

      <!-- 定时任务表格 -->
      <div v-if="tasks.length > 0" class="task-group">
        <h4 class="group-title">📋 定时任务 ({{ tasks.length }}个)</h4>
        <table class="data-table task-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>任务名称</th>
              <th>Cron表达式</th>
              <th>状态</th>
              <th>上次执行</th>
              <th>下次执行</th>
              <th>执行结果</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="task in tasks" :key="task.id" :class="{ disabled: !task.enabled }">
              <td><code>#{{ task.id }}</code></td>
              <td><strong>{{ task.name }}</strong></td>
              <td><code>{{ task.cron_expression }}</code></td>
              <td>
                <span :class="['status-badge', task.enabled ? 'enabled' : 'disabled']">
                  {{ task.enabled ? '已启用' : '已禁用' }}
                </span>
              </td>
              <td>{{ formatTime(task.last_run_time) }}</td>
              <td>{{ formatTime(task.next_run_time) || '--' }}</td>
              <td>
                <span v-if="task.last_run_status"
                      :class="['run-status', task.last_run_status]">
                  {{ runStatusText(task.last_run_status) }}
                </span>
                <span v-else class="no-run">暂无记录</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 最近选股记录 -->
      <div v-if="recentSelections.length > 0" class="task-group">
        <h4 class="group-title">📊 最近选股记录 ({{ recentSelections.length }}条)</h4>
        <table class="data-table selection-table">
          <thead>
            <tr>
              <th>记录ID</th>
              <th>交易日</th>
              <th>选中数量</th>
              <th>状态</th>
              <th>执行时间</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="sel in recentSelections" :key="sel.id">
              <td><code>#{{ sel.id }}</code></td>
              <td><strong>{{ sel.trade_date }}</strong></td>
              <td>
                <span :class="['count-badge', sel.total_count > 0 ? 'has-data' : 'empty']">
                  {{ sel.total_count }} 只
                </span>
              </td>
              <td>
                <span :class="['status-badge', sel.status]">
                  {{ selectionStatusText(sel.status) }}
                </span>
              </td>
              <td>{{ formatTime(sel.execute_time) }}</td>
              <td>{{ formatTime(sel.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 空状态 -->
      <div v-if="tasks.length === 0 && recentSelections.length === 0 && !loading" class="empty-state">
        <p>暂无任务数据</p>
        <p class="empty-hint">您可以创建定时任务或手动触发选股</p>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="loading-state">
        <p>⏳ 正在加载任务数据...</p>
      </div>

      <!-- 错误提示 -->
      <div v-if="error" class="error-toast">
        ❌ {{ error }}
      </div>

      <!-- 实时消息提示 -->
      <transition name="fade">
        <div v-if="realtimeMessage" :class="['realtime-msg', realtimeMessage.type]">
          📡 {{ realtimeMessage.text }}
        </div>
      </transition>
    </div>

    <!-- 刷新设置（非WebSocket模式） -->
    <div class="section refresh-settings" v-if="wsStatus !== 'connected'">
      <h3 class="section-title">刷新设置</h3>
      <div class="refresh-controls">
        <label>刷新间隔：</label>
        <select v-model.number="refreshInterval" :disabled="autoRefresh">
          <option :value="5">5 秒</option>
          <option :value="10">10 秒</option>
          <option :value="30">30 秒</option>
          <option :value="60">60 秒</option>
        </select>
        <span class="interval-hint">{{ autoRefresh ? `下次刷新: ${nextRefresh}s` : '已暂停' }}</span>
      </div>
    </div>

    <!-- WebSocket调试信息（开发环境） -->
    <div class="section debug-section" v-if="showDebug">
      <h3 class="section-title">🔧 WebSocket 调试</h3>
      <pre class="debug-log">{{ JSON.stringify(debugInfo, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import axios from 'axios'

const newTask = ref({ name: '', cron: '', description: '' })
const tasks = ref([])
const recentSelections = ref([])
const loading = ref(false)
const creating = ref(false)
const error = ref(null)

const autoRefresh = ref(false)
const refreshInterval = ref(10)
let refreshTimer = null
let countdownTimer = null
const nextRefresh = ref(refreshInterval.value)

const ws = ref(null)
const wsStatus = ref('disconnected')
const lastMessageTime = ref(null)
const realtimeMessage = ref(null)
const showDebug = ref(false)
const debugInfo = ref({})

onMounted(() => {
  connectWS()
})

onUnmounted(() => {
  disconnectWS()
  stopAutoRefresh()
})

function getWebSocketURL() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.hostname
  const port = window.location.port

  if (port && (port === '8080' || port === '8081')) {
    return `${protocol}//${host}:${port}/ws`
  }

  const apiPort = import.meta.env.VITE_API_PORT || '9999'
  if (apiPort && apiPort !== port) {
    return `${protocol}//${host}:${apiPort}/ws`
  }

  return `${protocol}//${host}:${port || '80'}/ws`
}

function connectWS() {
  if (ws.value && (ws.value.readyState === WebSocket.OPEN || ws.value.readyState === WebSocket.CONNECTING)) {
    return
  }

  try {
    const url = getWebSocketURL()
    wsStatus.value = 'connecting'
    ws.value = new WebSocket(url)

    ws.value.onopen = () => {
      wsStatus.value = 'connected'
      console.log('✅ WebSocket已连接')

      subscribeToChannel('tasks')
      loadTasks()

      startHeartbeat()
    }

    ws.value.onmessage = (event) => {
      handleWSMessage(event.data)
    }

    ws.value.onerror = (err) => {
      console.error('❌ WebSocket错误:', err)
      wsStatus.value = 'error'
      showRealtimeMessage('error', 'WebSocket连接错误')
    }

    ws.value.onclose = () => {
      console.log('🔌 WebSocket已断开')
      wsStatus.value = 'disconnected'
      stopHeartbeat()

      if (!error.value) {
        showRealtimeMessage('warning', 'WebSocket已断开，切换到轮询模式')
        startAutoRefreshFallback()
      }
    }

  } catch (e) {
    console.error('❌ WebSocket连接失败:', e)
    wsStatus.value = 'error'
    startAutoRefreshFallback()
  }
}

function disconnectWS() {
  stopHeartbeat()
  if (ws.value) {
    if (ws.value.readyState === WebSocket.OPEN) {
      ws.value.close(1000, '用户主动断开')
    }
    ws.value = null
  }
  wsStatus.value = 'disconnected'
}

function subscribeToChannel(channel) {
  if (ws.value && ws.value.readyState === WebSocket.OPEN) {
    ws.value.send(JSON.stringify({
      type: 'subscribe',
      channel: channel
    }))
    console.log(`📢 已订阅频道: ${channel}`)
  }
}

function handleWSMessage(data) {
  try {
    const message = typeof data === 'string' ? JSON.parse(data) : data
    lastMessageTime.value = new Date()

    debugInfo.value = {
      ...message,
      received_at: lastMessageTime.value.toISOString(),
      connection_status: wsStatus.value
    }

    switch (message.type) {
      case 'subscribed':
        showRealtimeMessage('success', `已订阅 ${message.channel} 频道`)
        break

      case 'pong':
        break

      case 'task_update':
      case 'selection_update':
      case 'system_notification':
        handleDataUpdate(message)
        break

      default:
        if (message.event) {
          handleDataUpdate(message)
        }
    }

  } catch (e) {
    console.error('解析WebSocket消息失败:', e, data)
  }
}

function handleDataUpdate(message) {
  if (message.source === 'task_manager') {
    showRealtimeMessage('info', `📋 ${message.task_name || ''}: ${message.message || message.event}`)

    if (message.event === 'task_completed' || message.event === 'task_failed') {
      loadTasks()
    }
  } else if (message.source === 'stock_selector') {
    showRealtimeMessage('info', `📊 选股更新: ${message.event}`)

    if (message.event === 'selection_completed') {
      loadTasks()
    }
  } else if (message.source === 'system') {
    showRealtimeMessage(
      message.level === 'error' ? 'error' : (message.level === 'warning' ? 'warning' : 'info'),
      `${message.title}: ${message.message}`
    )
  }
}

let heartbeatTimer = null

function startHeartbeat() {
  stopHeartbeat()
  heartbeatTimer = setInterval(() => {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify({ type: 'ping' }))
    }
  }, 30000)
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

function showRealtimeMessage(type, text) {
  realtimeMessage.value = { type, text }
  setTimeout(() => {
    realtimeMessage.value = null
  }, 5000)
}

async function loadTasks() {
  loading.value = true
  error.value = null
  try {
    const res = await axios.get('/api/v1/tasks')
    const data = res.data?.data || {}
    tasks.value = data.tasks || []
    recentSelections.value = data.recent_selections || []
  } catch (e) {
    console.error('加载任务失败:', e)
    error.value = '加载失败：' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

async function createTask() {
  if (!newTask.value.name || !newTask.value.cron) return

  creating.value = true
  try {
    await axios.post('/api/v1/tasks', {
      name: newTask.value.name,
      cron_expression: newTask.value.cron,
      description: newTask.value.description
    })

    showToast('success', '✅ 任务创建成功！')
    newTask.value = { name: '', cron: '', description: '' }

    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      pushTaskUpdateViaAPI(newTask.value.name, 'created')
    }

    await loadTasks()
  } catch (e) {
    showToast('error', '❌ 创建失败：' + (e.response?.data?.detail || e.message))
  } finally {
    creating.value = false
  }
}

function pushTaskUpdateViaAPI(taskName, event) {
  if (ws.value && ws.value.readyState === WebSocket.OPEN) {
    ws.value.send(JSON.stringify({
      type: 'client_event',
      source: 'frontend',
      event: event,
      task_name: taskName,
      timestamp: new Date().toISOString()
    }))
  }
}

function toggleAutoRefresh() {
  if (autoRefresh.value) {
    stopAutoRefresh()
  } else {
    startAutoRefresh()
  }
}

function startAutoRefresh() {
  autoRefresh.value = true
  nextRefresh.value = refreshInterval.value

  refreshTimer = setInterval(() => {
    loadTasks()
    nextRefresh.value = refreshInterval.value
  }, refreshInterval.value * 1000)

  countdownTimer = setInterval(() => {
    if (nextRefresh.value > 0) {
      nextRefresh.value--
    }
  }, 1000)
}

function startAutoRefreshFallback() {
  if (!autoRefresh.value) {
    autoRefresh.value = true
    refreshInterval.value = 10
    startAutoRefresh()
  }
}

function stopAutoRefresh() {
  autoRefresh.value = false
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
  nextRefresh.value = 0
}

const wsStatusText = computed(() => {
  const statusMap = {
    connected: '已连接',
    connecting: '连接中...',
    disconnected: '未连接',
    error: '连接错误'
  }
  return statusMap[wsStatus.value] || '未知'
})

function runStatusText(status) {
  const map = { success: '✅ 成功', failed: '❌ 失败', running: '⏳ 运行中', partial: '⚠️ 部分' }
  return map[status] || status
}

function selectionStatusText(status) {
  const map = { success: '完成', failed: '失败', running: '运行中', partial: '部分' }
  return map[status] || status
}

function formatTime(t) {
  if (!t) return '--'
  return t.replace('T', ' ').substring(0, 19)
}

function showToast(type, text) {
  const toast = document.createElement('div')
  toast.className = `toast ${type}`
  toast.textContent = text
  toast.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 12px 18px;
    border-radius: 8px;
    z-index: 2000;
    box-shadow: 0 4px 16px rgba(0,0,0,.14);
    font-size: 14px;
    animation: fadeIn .25s ease;
    background: ${type === 'success' ? '#f6ffed' : '#fff2f0'};
    border: 1px solid ${type === 'success' ? '#b7eb8f' : '#ffccc7'};
    color: ${type === 'success' ? '#389e0d' : '#cf1322'};
  `
  document.body.appendChild(toast)
  setTimeout(() => {
    toast.style.animation = 'fadeOut .25s ease'
    setTimeout(() => toast.remove(), 250)
  }, 3000)
}
</script>

<style scoped>
.task-manage { padding: 20px; max-width: 1200px; margin: 0 auto; }

.section {
  background: white;
  padding: 24px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  margin-bottom: 24px;
}

.section-title {
  font-size: 16px;
  color: #333;
  margin: 0 0 16px 0;
  font-weight: 600;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.header-actions { display: flex; gap: 10px; }

.ws-status-bar {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 12px 20px;
  border-radius: 8px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  animation: pulse 1.5s infinite;
}

.status-indicator.connected .dot { background: #52c41a; }
.status-indicator.connecting .dot { background: #faad14; }
.status-indicator.disconnected .dot { background: #999; }
.status-indicator.error .dot { background: #ff4d4f; }

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.8); }
}

.ws-info {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  opacity: 0.9;
}

.btn-ws-action {
  padding: 4px 14px;
  background: rgba(255,255,255,0.2);
  border: 1px solid rgba(255,255,255,0.3);
  border-radius: 4px;
  color: white;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.3s;
}

.btn-ws-action:hover { background: rgba(255,255,255,0.3); }
.btn-reconnect { background: rgba(82,196,26,0.3); border-color: rgba(82,196,26,0.5); }

.create-section { border-left: 4px solid #1890ff; }
.task-form { max-width: 700px; }

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}

.task-form input,
.task-form textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  box-sizing: border-box;
  transition: border-color 0.3s;
}

.task-form input:focus,
.task-form textarea:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24,144,255,0.1);
}

.task-form textarea {
  min-height: 80px;
  resize: vertical;
  margin-bottom: 12px;
}

.btn-primary {
  padding: 10px 24px;
  background: #1890ff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
}

.btn-primary:hover:not(:disabled) {
  background: #40a9ff;
  transform: translateY(-1px);
}

.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

.btn-toggle,
.btn-refresh {
  padding: 6px 16px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.3s;
}

.btn-toggle.active {
  background: #e6f7ff;
  border-color: #1890ff;
  color: #1890ff;
}

.btn-refresh:hover:not(:disabled) { border-color: #1890ff; color: #1890ff; }
.btn-refresh:disabled { opacity: 0.6; cursor: not-allowed; }

.live-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 12px;
  font-size: 12px;
  color: #52c41a;
  margin-left: 8px;
  font-weight: normal;
}

.poll-badge {
  display: inline-block;
  padding: 3px 10px;
  background: #fffbe6;
  border: 1px solid #ffe58f;
  border-radius: 12px;
  font-size: 12px;
  color: #faad14;
  margin-left: 8px;
  font-weight: normal;
}

.pulse-dot {
  width: 8px;
  height: 8px;
  background: #52c41a;
  border-radius: 50%;
  animation: pulse 1.5s infinite;
}

.task-group { margin-bottom: 24px; }

.group-title {
  font-size: 15px;
  color: #555;
  margin: 0 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 2px solid #f0f0f0;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th,
.data-table td {
  padding: 11px 14px;
  text-align: left;
  border-bottom: 1px solid #f0f0f0;
}

.data-table th {
  background: #fafafa;
  font-weight: 600;
  color: #666;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.data-table tr:hover { background: #fafafa; }
.data-table tr.disabled { opacity: 0.6; }

.status-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.status-badge.enabled { background: #e6f7ff; color: #1890ff; border: 1px solid #91d5ff; }
.status-badge.disabled { background: #f5f5f5; color: #999; border: 1px solid #d9d9d9; }
.status-badge.success { background: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }
.status-badge.failed { background: #fff2f0; color: #ff4d4f; border: 1px solid #ffccc7; }
.status-badge.running { background: #e6f7ff; color: #1890ff; border: 1px solid #91d5ff; }
.status-badge.partial { background: #fffbe6; color: #faad14; border: 1px solid #ffe58f; }

.run-status { font-weight: 500; font-size: 12px; }
.run-status.success { color: #52c41a; }
.run-status.failed { color: #ff4d4f; }
.run-status.running { color: #1890ff; }
.run-status.partial { color: #faad14; }

.no-run { color: #999; font-size: 12px; }

.count-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
}

.count-badge.has-data { background: #e6f7ff; color: #1890ff; border: 1px solid #91d5ff; }
.count-badge.empty { background: #f5f5f5; color: #999; border: 1px solid #d9d9d9; }

code {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Monaco', 'Consolas', monospace;
  font-size: 12px;
  color: #d63384;
}

.empty-state,
.loading-state {
  text-align: center;
  padding: 50px 20px;
  color: #999;
  background: #fafafa;
  border-radius: 8px;
  border: 2px dashed #d9d9d9;
}

.empty-state p { margin: 6px 0; font-size: 14px; }
.empty-hint { font-size: 13px !important; color: #bbb !important; }
.loading-state p { color: #1890ff; font-size: 14px; animation: pulse 1.5s infinite; }

.error-toast {
  background: #fff2f0;
  border: 1px solid #ffccc7;
  color: #cf1322;
  padding: 12px 18px;
  border-radius: 6px;
  margin-top: 16px;
  font-size: 14px;
}

.realtime-msg {
  position: relative;
  padding: 10px 16px;
  border-radius: 6px;
  margin-top: 12px;
  font-size: 13px;
  animation: slideIn .3s ease;
}

.realtime-msg.info { background: #e6f7ff; border: 1px solid #91d5ff; color: #0050b3; }
.realtime-msg.success { background: #f6ffed; border: 1px solid #b7eb8f; color: #389e0d; }
.realtime-msg.warning { background: #fffbe6; border: 1px solid #ffe58f; color: #d48806; }
.realtime-msg.error { background: #fff2f0; border: 1px solid #ffccc7; color: #cf1322; }

.fade-enter-active, .fade-leave-active { transition: all 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(-10px); }

.refresh-settings {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.refresh-settings .section-title { color: white; }

.refresh-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.refresh-controls label { font-size: 14px; font-weight: 500; }

.refresh-controls select {
  padding: 8px 12px;
  border: 1px solid rgba(255,255,255,0.3);
  border-radius: 4px;
  background: rgba(255,255,255,0.9);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s;
}

.refresh-controls select:focus {
  outline: none;
  box-shadow: 0 0 0 2px rgba(255,255,255,0.5);
}

.interval-hint { font-size: 13px; opacity: 0.9; font-family: monospace; }

.debug-section { background: #1e1e1e; color: #d4d4d4; }
.debug-section .section-title { color: #4ec9b0; }
.debug-log {
  background: #252526;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 6px;
  font-size: 12px;
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
}

@media (max-width: 768px) {
  .form-row { grid-template-columns: 1fr; }
  .header-actions { width: 100%; }
  .data-table { font-size: 12px; }
  .data-table th, .data-table td { padding: 8px 10px; }
  .section-header { flex-direction: column; align-items: flex-start; }
  .ws-status-bar { flex-direction: column; align-items: stretch; }
}
</style>
