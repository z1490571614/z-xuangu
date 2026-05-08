import api from './index'

export const executeStockSelection = (tradeDate, notify) => {
  return api.post('/stock/select', {
    trade_date: tradeDate,
    notify: notify
  })
}

export const getSelectionResults = (page, pageSize) => {
  return api.get('/stock/results', {
    params: { page, page_size: pageSize }
  })
}

export const getSelectionDetail = (recordId) => {
  return api.get(`/stock/results/${recordId}`)
}

export const deleteStockResults = (ids) => {
  return api.post('/stock/results/batch-delete', ids)
}

export const testNotificationSend = () => {
  return api.post('/config/test-notification')
}

export const getStockDetail = (params) => {
  return api.get('/stock/detail', { params })
}

export const getScoreV2Detail = (params) => {
  return api.get('/score-v2/detail', { params })
}

export const getScoreV2List = (params) => {
  return api.get('/score-v2/list', { params })
}

