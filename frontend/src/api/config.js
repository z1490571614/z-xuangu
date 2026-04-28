import api from './index'

export const getConfig = () => {
  return api.get('/config')
}

export const updateConfig = (key, data) => {
  return api.put(`/config/${key}`, data)
}

export const testNotificationSend = () => {
  return api.post('/config/test-notification')
}

export const initDefaultConfigApi = () => {
  return api.post('/config/init-default')
}
