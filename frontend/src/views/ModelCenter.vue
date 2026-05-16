<template>
  <div class="model-center">
    <div class="page-title">
      <h2>模型中心</h2>
      <button class="btn-primary" @click="loadModels" :disabled="loading">
        {{ loading ? '刷新中' : '刷新模型状态' }}
      </button>
    </div>

    <div v-if="loading" class="state-panel">加载模型中</div>
    <div v-else-if="error" class="state-panel error">
      {{ error }}
      <button class="btn-secondary" @click="loadModels">重试</button>
    </div>
    <div v-else-if="modelNames.length === 0" class="state-panel empty">暂无可用模型</div>

    <template v-else>
      <section class="panel">
        <h3>模型概览</h3>
        <div class="model-grid">
          <div v-for="name in modelNames" :key="name" class="model-card">
            <div class="model-title">{{ name }}</div>
            <div class="metric-row">
              <span>Active</span>
              <strong>{{ models[name].active_version?.version || '--' }}</strong>
            </div>
            <div class="metric-row">
              <span>AUC</span>
              <strong>{{ fmtMetric(models[name].active_version?.metrics?.auc) }}</strong>
            </div>
            <div class="metric-row">
              <span>胜率</span>
              <strong>{{ fmtPct01(models[name].active_version?.metrics?.precision) }}</strong>
            </div>
            <div class="version-list">
              <button
                v-for="version in models[name].versions"
                :key="version.version"
                class="version-chip"
                :class="{ active: version.is_active, unavailable: !version.available }"
                :disabled="activating || version.is_active || !version.available"
                @click="activateVersion(name, version.version)"
              >
                {{ version.version }}{{ version.is_active ? ' active' : '' }}
              </button>
            </div>
          </div>
        </div>
        <p v-if="activateStatus" class="status-line">{{ activateStatus }}</p>
      </section>

      <section class="panel">
        <h3>预测刷新</h3>
        <div class="form-grid compact">
          <label>
            模型
            <select v-model="selectedModel">
              <option v-for="name in modelNames" :key="name" :value="name">{{ name }}</option>
            </select>
          </label>
          <label>
            版本
            <select v-model="selectedVersion">
              <option value="">active</option>
              <option v-for="version in models[selectedModel]?.versions || []" :key="version.version" :value="version.version">
                {{ version.version }}{{ version.is_active ? ' active' : '' }}
              </option>
            </select>
          </label>
          <label for="refresh-record-id">
            选股记录 ID
            <input id="refresh-record-id" v-model="refreshRecordId" placeholder="例如 46" />
          </label>
          <button class="btn-primary" :disabled="refreshing || !refreshRecordId" @click="refreshPredictions">
            {{ refreshing ? '刷新中' : '刷新预测' }}
          </button>
        </div>
        <p v-if="refreshStatus" class="status-line">{{ refreshStatus }}</p>
      </section>

      <section class="panel">
        <h3>训练控制台</h3>
        <div class="form-grid">
          <label for="train-start">
            训练开始日期
            <input id="train-start" v-model="trainingForm.start_date" />
          </label>
          <label for="train-end">
            训练结束日期
            <input id="train-end" v-model="trainingForm.end_date" />
          </label>
          <label>
            学习率
            <input v-model.number="trainingForm.learning_rate" type="number" step="0.01" />
          </label>
          <label>
            树数量
            <input v-model.number="trainingForm.n_estimators" type="number" />
          </label>
          <label>
            叶子数
            <input v-model.number="trainingForm.num_leaves" type="number" />
          </label>
          <label>
            胜率门槛
            <input v-model.number="trainingForm.min_precision" type="number" step="0.01" />
          </label>
          <label>
            最小命中数
            <input v-model.number="trainingForm.min_hit_count" type="number" />
          </label>
          <label>
            最大重训次数
            <input v-model.number="trainingForm.max_retrain_attempts" type="number" />
          </label>
        </div>
        <details class="advanced">
          <summary>高级参数</summary>
          <div class="form-grid">
            <label>
              最大深度
              <input v-model.number="trainingForm.max_depth" type="number" />
            </label>
            <label>
              行采样
              <input v-model.number="trainingForm.subsample" type="number" step="0.05" />
            </label>
            <label>
              列采样
              <input v-model.number="trainingForm.colsample_bytree" type="number" step="0.05" />
            </label>
            <label>
              早停轮数
              <input v-model.number="trainingForm.early_stopping_rounds" type="number" />
            </label>
            <label>
              随机种子
              <input v-model.number="trainingForm.random_seed" type="number" />
            </label>
            <label class="check-row">
              <input v-model="trainingForm.is_unbalance" type="checkbox" />
              类别不平衡修正
            </label>
          </div>
        </details>
        <div class="button-row">
          <button class="btn-secondary" :disabled="training" @click="startTraining('test')">测试训练</button>
          <button class="btn-primary" :disabled="training" @click="startTraining('formal')">正式训练</button>
        </div>
      </section>

      <section class="panel">
        <h3>训练任务与日志</h3>
        <div v-if="!currentJob" class="empty-inline">暂无训练任务</div>
        <div v-else class="job-panel">
          <div class="job-head">
            <h4>任务 #{{ currentJob.id || '--' }}</h4>
            <span :class="['status-badge', currentJob.status]">{{ currentJob.status || '--' }}</span>
          </div>
          <div class="progress">
            <div class="progress-bar" :style="{ width: `${currentJob.progress || 0}%` }"></div>
          </div>
          <div class="progress-text">{{ currentJob.progress || 0 }}%</div>
          <div v-if="currentJob.attempts?.length" class="attempt-list">
            <div v-for="attempt in currentJob.attempts" :key="attempt.attempt" class="attempt-row">
              第 {{ attempt.attempt }} 次
              <strong>{{ attempt.accepted ? '通过' : '未通过' }}</strong>
              <span>胜率 {{ fmtPct01(attempt.precision) }}</span>
              <span>命中 {{ attempt.hit_count || 0 }}</span>
            </div>
          </div>
          <div class="log-list">
            <div v-for="(log, idx) in currentJob.logs || []" :key="idx">{{ log.message }}</div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'

const route = useRoute()
const loading = ref(false)
const error = ref('')
const models = ref({})
const selectedModel = ref('leader_main_t0_lgbm')
const selectedVersion = ref('')
const activateStatus = ref('')
const activating = ref(false)
const refreshRecordId = ref('')
const refreshStatus = ref('')
const refreshing = ref(false)
const training = ref(false)
const currentJob = ref(null)
const modelNames = computed(() => Object.keys(models.value))

const trainingForm = ref({
  start_date: '20250101',
  end_date: '',
  learning_rate: 0.05,
  n_estimators: 500,
  num_leaves: 31,
  threshold: 0.5,
  min_precision: 0.5,
  min_hit_count: 30,
  max_retrain_attempts: 3,
  is_unbalance: true,
  max_depth: -1,
  subsample: 0.8,
  colsample_bytree: 0.8,
  early_stopping_rounds: 50,
  random_seed: 42,
})

let ws = null
let pollTimer = null

watch(modelNames, names => {
  if (names.length && !names.includes(selectedModel.value)) selectedModel.value = names[0]
})

onMounted(() => {
  if (route.query.record_id) refreshRecordId.value = String(route.query.record_id)
  const today = new Date()
  trainingForm.value.end_date = `${today.getFullYear()}${String(today.getMonth() + 1).padStart(2, '0')}${String(today.getDate()).padStart(2, '0')}`
  loadModels()
  connectModelWS()
})

onUnmounted(() => {
  if (ws) ws.close()
  if (pollTimer) clearTimeout(pollTimer)
})

async function loadModels() {
  loading.value = true
  error.value = ''
  try {
    const res = await axios.get('/api/v1/models')
    models.value = res.data?.data?.models || {}
  } catch (e) {
    error.value = '模型状态加载失败：' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

async function activateVersion(modelName, version) {
  activating.value = true
  activateStatus.value = ''
  try {
    const res = await axios.post(`/api/v1/models/${modelName}/versions/${version}/activate`)
    activateStatus.value = res.data?.message || `已激活 ${version}`
    await loadModels()
  } catch (e) {
    activateStatus.value = '激活失败：' + (e.response?.data?.detail || e.message)
  } finally {
    activating.value = false
  }
}

async function refreshPredictions() {
  refreshing.value = true
  refreshStatus.value = ''
  try {
    const res = await axios.post(`/api/v1/models/${selectedModel.value}/refresh-predictions`, {
      record_id: Number(refreshRecordId.value),
      version: selectedVersion.value || null,
    })
    const data = res.data?.data || {}
    refreshStatus.value = `已更新 ${data.updated_count || 0} 只股票`
  } catch (e) {
    refreshStatus.value = '刷新失败：' + (e.response?.data?.detail || e.message)
  } finally {
    refreshing.value = false
  }
}

async function startTraining(mode) {
  training.value = true
  try {
    const payload = {
      start_date: trainingForm.value.start_date,
      end_date: trainingForm.value.end_date,
      mode,
      auto_activate: mode === 'formal',
      params: {
        learning_rate: Number(trainingForm.value.learning_rate),
        n_estimators: Number(trainingForm.value.n_estimators),
        num_leaves: Number(trainingForm.value.num_leaves),
        is_unbalance: Boolean(trainingForm.value.is_unbalance),
        max_depth: Number(trainingForm.value.max_depth),
        subsample: Number(trainingForm.value.subsample),
        colsample_bytree: Number(trainingForm.value.colsample_bytree),
        early_stopping_rounds: Number(trainingForm.value.early_stopping_rounds),
        random_seed: Number(trainingForm.value.random_seed),
      },
      acceptance: {
        threshold: Number(trainingForm.value.threshold),
        min_precision: Number(trainingForm.value.min_precision),
        min_hit_count: Number(trainingForm.value.min_hit_count),
        max_retrain_attempts: Number(trainingForm.value.max_retrain_attempts),
      },
    }
    const res = await axios.post(`/api/v1/models/${selectedModel.value}/training-jobs`, payload)
    currentJob.value = { id: res.data?.data?.job_id, status: 'pending', progress: 0, logs: [] }
    await pollTrainingJob()
  } catch (e) {
    currentJob.value = { status: 'failed', error_message: e.response?.data?.detail || e.message, progress: 100, logs: [] }
  } finally {
    training.value = false
  }
}

async function pollTrainingJob() {
  if (!currentJob.value?.id) return
  try {
    const res = await axios.get(`/api/v1/models/training-jobs/${currentJob.value.id}`)
    currentJob.value = res.data?.data || currentJob.value
    if (['pending', 'running'].includes(currentJob.value.status)) {
      pollTimer = setTimeout(pollTrainingJob, 3000)
    } else {
      await loadModels()
    }
  } catch (e) {
    currentJob.value = { ...currentJob.value, error_message: e.response?.data?.detail || e.message }
  }
}

function connectModelWS() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.hostname
  const apiPort = import.meta.env.VITE_API_PORT || '9999'
  ws = new WebSocket(`${protocol}//${host}:${apiPort}/ws`)
  ws.onopen = () => ws.send(JSON.stringify({ type: 'subscribe', channel: 'models' }))
  ws.onmessage = event => {
    const message = JSON.parse(event.data)
    const job = message.job
    if (job && currentJob.value?.id === job.id) currentJob.value = job
  }
  ws.onerror = () => {}
}

function fmtMetric(v) {
  return v == null ? '--' : Number(v).toFixed(4)
}

function fmtPct01(v) {
  return v == null ? '--' : `${(Number(v) * 100).toFixed(1)}%`
}
</script>

<style scoped>
.model-center { padding: 4px 0 28px; }
.page-title { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.page-title h2 { font-size: 24px; color: #1f2937; }
.panel, .state-panel { background: #fff; border-radius: 8px; padding: 18px; margin-bottom: 16px; box-shadow: 0 2px 6px rgba(0,0,0,.06); }
.panel h3 { font-size: 17px; margin-bottom: 14px; color: #1f2937; }
.model-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.model-card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; }
.model-title { font-weight: 700; color: #0f766e; margin-bottom: 10px; }
.metric-row { display: flex; justify-content: space-between; font-size: 14px; padding: 4px 0; color: #4b5563; }
.version-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.version-chip { border: 1px solid #d1d5db; background: #fff; border-radius: 6px; padding: 6px 9px; cursor: pointer; font-size: 12px; }
.version-chip.active { border-color: #0f766e; color: #0f766e; background: #ecfdf5; }
.version-chip.unavailable { color: #9ca3af; background: #f9fafb; cursor: not-allowed; }
.form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; align-items: end; }
.form-grid.compact { grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); }
label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: #4b5563; }
input, select { height: 36px; border: 1px solid #d1d5db; border-radius: 6px; padding: 0 10px; font-size: 14px; background: #fff; }
.check-row { flex-direction: row; align-items: center; }
.check-row input { width: 16px; height: 16px; }
.advanced { margin-top: 14px; color: #4b5563; }
.advanced summary { cursor: pointer; margin-bottom: 12px; }
.button-row { display: flex; gap: 10px; margin-top: 14px; }
.btn-primary, .btn-secondary { height: 36px; border: none; border-radius: 6px; padding: 0 14px; cursor: pointer; white-space: nowrap; }
.btn-primary { background: #1677ff; color: #fff; }
.btn-secondary { background: #f3f4f6; color: #374151; border: 1px solid #d1d5db; }
.btn-primary:disabled, .btn-secondary:disabled { opacity: .55; cursor: not-allowed; }
.status-line { margin-top: 10px; color: #0f766e; font-size: 14px; }
.state-panel.error { color: #b91c1c; display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.state-panel.empty, .empty-inline { color: #6b7280; }
.job-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px; }
.status-badge { border-radius: 999px; padding: 4px 10px; background: #f3f4f6; color: #4b5563; font-size: 12px; }
.status-badge.passed { background: #ecfdf5; color: #047857; }
.status-badge.failed, .status-badge.rejected { background: #fef2f2; color: #b91c1c; }
.progress { height: 10px; background: #eef2f7; border-radius: 999px; overflow: hidden; }
.progress-bar { height: 100%; background: #1677ff; transition: width .25s ease; }
.progress-text { margin-top: 6px; font-size: 13px; color: #4b5563; }
.attempt-list { margin-top: 12px; display: grid; gap: 8px; }
.attempt-row { display: flex; flex-wrap: wrap; gap: 10px; font-size: 13px; color: #4b5563; background: #f9fafb; padding: 8px; border-radius: 6px; }
.log-list { margin-top: 12px; max-height: 180px; overflow: auto; border-top: 1px solid #e5e7eb; padding-top: 10px; font-size: 13px; color: #374151; display: grid; gap: 6px; }
</style>
