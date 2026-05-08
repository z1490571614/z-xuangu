import axios from 'axios';

class StockPreloadService {
  constructor() {
    this.cache = new Map();
    this.preloadingTasks = new Map();
    this.maxConcurrent = 5;
    this.currentConcurrent = 0;
    this.queue = [];
    this.cacheTtl = 300000;
    this.stats = {
      totalPreloaded: 0,
      cacheHits: 0,
      cacheMisses: 0,
      preloadSuccess: 0,
      preloadFailed: 0
    };
  }

  getCacheKey(tsCode, type = 'detail') {
    return `${type}_${tsCode}`;
  }

  isCached(tsCode, type = 'detail') {
    const key = this.getCacheKey(tsCode, type);
    const cached = this.cache.get(key);
    if (!cached) return false;
    if (Date.now() - cached.timestamp > this.cacheTtl) {
      this.cache.delete(key);
      return false;
    }
    return true;
  }

  getFromCache(tsCode, type = 'detail') {
    const key = this.getCacheKey(tsCode, type);
    const cached = this.cache.get(key);
    if (cached && Date.now() - cached.timestamp <= this.cacheTtl) {
      this.stats.cacheHits++;
      return cached.data;
    }
    this.stats.cacheMisses++;
    return null;
  }

  setCache(tsCode, data, type = 'detail') {
    const key = this.getCacheKey(tsCode, type);
    this.cache.set(key, { data, timestamp: Date.now() });
  }

  clearCache() {
    this.cache.clear();
    this.stats.cacheHits = 0;
    this.stats.cacheMisses = 0;
  }

  clearStockCache(tsCode) {
    ['detail', 'overview', 'anomaly', 'risk'].forEach(type => {
      this.cache.delete(this.getCacheKey(tsCode, type));
    });
  }

  async preloadStock(tsCode, stockName, recordId = null) {
    const key = this.getCacheKey(tsCode);
    if (this.preloadingTasks.has(key)) {
      return this.preloadingTasks.get(key);
    }
    return new Promise((resolve, reject) => {
      const task = { tsCode, stockName, recordId, resolve, reject };
      this.queue.push(task);
      this.preloadingTasks.set(key, task);
      this.processQueue();
    });
  }

  preloadStocks(stocks) {
    const promises = stocks.slice(0, 10).map(stock =>
      this.preloadStock(stock.ts_code, stock.name, stock.record_id)
    );
    return Promise.allSettled(promises);
  }

  async processQueue() {
    if (this.queue.length === 0 || this.currentConcurrent >= this.maxConcurrent) return;
    const task = this.queue.shift();
    this.currentConcurrent++;
    try {
      // 并行预加载：stock/detail（快速）+ overview-brief（AI，慢但提前预热）
      const [detailRes, overviewRes, anomalyRes, riskRes] = await Promise.allSettled([
        axios.get('/api/v1/stock/detail', {
          params: { ts_code: task.tsCode, stock_name: task.stockName, record_id: task.recordId },
          timeout: 30000
        }),
        axios.get('/api/v1/stock/overview-brief', {
          params: { ts_code: task.tsCode, stock_name: task.stockName, trade_date: null, record_id: task.recordId },
          timeout: 90000
        }),
        axios.get('/api/v1/stock/anomaly-interpretation', {
          params: { ts_code: task.tsCode, stock_name: task.stockName, trade_date: null, force_refresh: false },
          timeout: 90000
        }),
        axios.get('/api/v1/stock/detail/risk', {
          params: { ts_code: task.tsCode, stock_name: task.stockName, strategy_type: 'dragon_leader' },
          timeout: 60000
        }),
      ]);

      const detailData = detailRes.status === 'fulfilled' ? (detailRes.value?.data?.data || {}) : {};
      this.setCache(task.tsCode, detailData, 'detail');

      // 缓存AI预加载结果（用户打开详情时直接读取，不再请求API）
      if (overviewRes.status === 'fulfilled' && overviewRes.value?.data?.data) {
        this.setCache(task.tsCode, overviewRes.value.data.data, 'overview');
      }
      if (anomalyRes.status === 'fulfilled' && anomalyRes.value?.data?.data) {
        this.setCache(task.tsCode, anomalyRes.value.data.data, 'anomaly');
      }
      // 缓存龙头战法风险拆解
      if (riskRes.status === 'fulfilled' && riskRes.value?.data?.data) {
        this.setCache(task.tsCode, riskRes.value.data.data, 'risk');
      }

      this.stats.preloadSuccess++;
      this.stats.totalPreloaded++;
      task.resolve(detailData);
    } catch (error) {
      this.stats.preloadFailed++;
      task.reject(error);
    } finally {
      const key = this.getCacheKey(task.tsCode);
      this.preloadingTasks.delete(key);
      this.currentConcurrent--;
      this.processQueue();
    }
  }

  async getStockDetail(tsCode, stockName, recordId = null) {
    const cached = this.getFromCache(tsCode, 'detail');
    if (cached) return cached;
    const res = await axios.get('/api/v1/stock/detail', {
      params: { ts_code: tsCode, stock_name: stockName, record_id: recordId },
      timeout: 30000
    });
    const data = res.data?.data || {};
    this.setCache(tsCode, data, 'detail');
    return data;
  }

  getStats() {
    return { ...this.stats };
  }

  resetStats() {
    this.stats = { totalPreloaded: 0, cacheHits: 0, cacheMisses: 0, preloadSuccess: 0, preloadFailed: 0 };
  }
}

export const stockPreloadService = new StockPreloadService();
export default stockPreloadService;