<template>
  <div class="settings">
    <h2>系统设置</h2>
    <form class="config-form" @submit.prevent="saveConfig">
      <div class="form-group">
        <label>Tushare Token</label>
        <input type="text" v-model="config.tushareToken" />
      </div>
      <div class="form-group">
        <label>飞书 Webhook URL</label>
        <input type="text" v-model="config.feishuWebhook" />
      </div>
      <button type="button" @click="testNotification" class="btn-primary">测试通知</button>
      <button type="submit" class="btn-secondary">保存配置</button>
    </form>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const config = ref({ tushareToken: '', feishuWebhook: '' })

onMounted(async () => {
  try {
    const response = await axios.get('/api/v1/config')
    if (response.data.data) {
      config.value = response.data.data
    }
  } catch (error) {
    console.error('获取配置失败:', error)
  }
})

async function testNotification() {
  try {
    await axios.post('/api/v1/config/test-notification')
    alert('通知发送成功！')
  } catch (error) {
    alert('通知发送失败：' + (error.response?.data?.message || error.message))
  }
}

async function saveConfig() {
  try {
    await axios.put('/api/v1/config', config.value)
    alert('配置保存成功！')
  } catch (error) {
    alert('配置保存失败：' + (error.response?.data?.message || error.message))
  }
}
</script>

<style scoped>
.settings {
  padding: 20px;
}

.config-form {
  max-width: 600px;
  background: white;
  padding: 24px;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
  color: #333;
}

.form-group input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
}

.btn-primary, .btn-secondary {
  padding: 10px 24px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  margin-right: 10px;
}

.btn-primary {
  background: #1890ff;
  color: white;
}

.btn-secondary {
  background: #f0f0f0;
  color: #333;
}
</style>
