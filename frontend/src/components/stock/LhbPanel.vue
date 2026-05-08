<template>
  <div class="lhb-panel">
    <div v-if="loading" class="state-msg">加载龙虎榜数据中...</div>

    <div v-else-if="error" class="state-card error-card">
      <div class="error-text">龙虎榜加载失败</div>
      <p>{{ error }}</p>
      <button class="btn-retry" @click="$emit('reload')">重新加载</button>
    </div>

    <div v-else-if="!lhb || lhb.data_status === 'not_on_list' || lhb.data_status === 'not_integrated'" class="state-card empty-card">
      <div class="status-icon">📋</div>
      <div class="status-text">{{ statusText }}</div>
    </div>

    <div v-else class="lhb-content">
      <!-- 头部信息 -->
      <div class="lhb-header">
        <div class="header-title">龙虎榜</div>
        <div class="header-date">{{ lhb.trade_date || '' }}</div>
      </div>

      <!-- 上榜原因 -->
      <div class="reason-bar">
        <span class="reason-label">上榜原因：</span>
        <span>{{ lhb.reason || '--' }}</span>
        <span class="reason-sep">|</span>
        <span :class="'change-pct ' + (lhb.change_pct >= 0 ? 'up' : 'down')">{{ fmtPct(lhb.change_pct) }}</span>
        <span class="reason-sep">|</span>
        <span>成交额{{ fmtAmount(lhb.amount) }}</span>
        <span class="reason-sep">|</span>
        <span>换手率{{ fmtPct(lhb.turnover_rate) }}</span>
      </div>

      <!-- 资金汇总 + 进度条 -->
      <div class="fund-summary">
        <div class="fund-row">
          <div class="fund-item">
            <span class="fund-label">总买</span>
            <span class="fund-value up">{{ fmtAmount(lhb.buy_amount) }}</span>
          </div>
          <div class="fund-item net">
            <span class="fund-label">净买</span>
            <span :class="'fund-value ' + (lhb.net_amount >= 0 ? 'up' : 'down')">
              {{ lhb.net_amount >= 0 ? '+' : '' }}{{ fmtAmount(lhb.net_amount) }}
            </span>
          </div>
          <div class="fund-item">
            <span class="fund-label">总卖</span>
            <span class="fund-value down">{{ fmtAmount(lhb.sell_amount) }}</span>
          </div>
        </div>
        <!-- 红绿进度条 -->
        <div class="bar-track">
          <div class="bar-buy" :style="{ width: buyRatio + '%' }"></div>
          <div class="bar-sell" :style="{ width: sellRatio + '%' }"></div>
        </div>
        <div class="bar-labels">
          <span class="bar-label up">{{ buyRatio.toFixed(0) }}%</span>
          <span class="bar-label down">{{ sellRatio.toFixed(0) }}%</span>
        </div>
      </div>

      <!-- 资金结论 + 行为标签 -->
      <div :class="'conclusion-bar ' + conclusionCls">
        <div class="conclusion-left">
          <span class="conclusion-tag">{{ lhb.action_tag || '--' }}</span>
          <span class="conclusion-type">| {{ lhb.main_type || '--' }}</span>
        </div>
        <div class="conclusion-tags">
          <span v-for="(t, i) in lhb.tags || []" :key="i" :class="'ctag ' + ctagCls(t)">{{ t }}</span>
        </div>
      </div>

      <!-- 合并席位列表 -->
      <div class="detail-grid">
        <!-- 买入前五 -->
        <div class="side-panel buy-panel">
          <div class="side-title">买入 TOP5</div>
          <div v-if="lhb.buy_top5 && lhb.buy_top5.length" class="seat-list">
            <div v-for="(s, i) in lhb.buy_top5" :key="'buy-' + i" class="seat-row">
              <span class="seat-idx">{{ i + 1 }}</span>
              <div class="seat-body">
                <div class="seat-name-row">
                  <span class="seat-name">{{ shortenName(s.exalter) }}</span>
                  <span :class="'seat-tag tag-' + tagCls(s.tag)">{{ s.tag || '普通' }}</span>
                </div>
                <span v-if="s.trader" class="seat-trader">👤 {{ s.trader }}</span>
                <div class="seat-amt-row">
                  <span class="seat-buy">买 {{ fmtAmount(s.buy) }}</span>
                  <span v-if="s.sell > 0" class="seat-sell">卖 {{ fmtAmount(s.sell) }}</span>
                  <span :class="'seat-net ' + (s.net_buy >= 0 ? 'up' : 'down')">
                    净{{ s.net_buy >= 0 ? '+' : '' }}{{ fmtAmount(s.net_buy) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="no-data">无买入席位数据</div>
          <div class="side-total">买入合计：<span class="up">{{ fmtAmount(lhb.buy_amount) }}</span></div>
        </div>

        <!-- 卖出前五 -->
        <div class="side-panel sell-panel">
          <div class="side-title">卖出 TOP5</div>
          <div v-if="lhb.sell_top5 && lhb.sell_top5.length" class="seat-list">
            <div v-for="(s, i) in lhb.sell_top5" :key="'sell-' + i" class="seat-row">
              <span class="seat-idx">{{ i + 1 }}</span>
              <div class="seat-body">
                <div class="seat-name-row">
                  <span class="seat-name">{{ shortenName(s.exalter) }}</span>
                  <span :class="'seat-tag tag-' + tagCls(s.tag)">{{ s.tag || '普通' }}</span>
                </div>
                <span v-if="s.trader" class="seat-trader">👤 {{ s.trader }}</span>
                <div class="seat-amt-row">
                  <span v-if="s.buy > 0" class="seat-buy">买 {{ fmtAmount(s.buy) }}</span>
                  <span class="seat-sell">卖 {{ fmtAmount(s.sell) }}</span>
                  <span :class="'seat-net ' + (s.net_buy >= 0 ? 'up' : 'down')">
                    净{{ s.net_buy >= 0 ? '+' : '' }}{{ fmtAmount(s.net_buy) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="no-data">无卖出席位数据</div>
          <div class="side-total">卖出合计：<span class="down">{{ fmtAmount(lhb.sell_amount) }}</span></div>
        </div>
      </div>

      <!-- 历史上榜 -->
      <div v-if="lhb.history && lhb.history.length" class="history-section">
        <div class="history-title">历史上榜</div>
        <div v-for="(h, i) in lhb.history" :key="i" class="history-row">
          <span class="history-date">{{ h.trade_date }}</span>
          <span :class="'history-net ' + (h.net_amount >= 0 ? 'up' : 'down')">
            净{{ h.net_amount >= 0 ? '+' : '' }}{{ fmtAmount(h.net_amount) }}
          </span>
          <span class="history-tag">{{ h.action_tag || '--' }}</span>
        </div>
      </div>

      <!-- 风险提示 -->
      <div v-if="lhb.risk_tips && lhb.risk_tips.length" class="risk-section">
        <div class="risk-title">风险提示</div>
        <div v-for="(tip, i) in lhb.risk_tips" :key="i" class="risk-item">
          <span v-if="tip.includes('核按钮')" class="risk-icon">🔴</span>
          <span v-else class="risk-icon">⚠️</span>
          {{ tip }}
        </div>
      </div>

      <div class="disclaimer">数据来源：Tushare 龙虎榜 | 仅供参考，不构成投资建议</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  lhb: Object,
  loading: Boolean,
  error: [String, null],
})
defineEmits(['reload'])

const statusText = computed(() => {
  if (!props.lhb) return '暂无龙虎榜数据'
  const map = {
    not_on_list: '该股当日未上榜',
    not_integrated: '龙虎榜数据源未配置，需接入 Tushare top_list 接口',
    fetch_failed: '龙虎榜数据拉取失败，请稍后重试',
    timeout: '获取龙虎榜数据超时，请稍后重试',
  }
  return map[props.lhb.data_status] || '暂无龙虎榜数据'
})

const total = computed(() => {
  const b = props.lhb?.buy_amount || 0
  const s = props.lhb?.sell_amount || 0
  return b + s
})

const buyRatio = computed(() => {
  const t = total.value
  return t > 0 ? (props.lhb.buy_amount / t) * 100 : 50
})

const sellRatio = computed(() => {
  const t = total.value
  return t > 0 ? (props.lhb.sell_amount / t) * 100 : 50
})

const conclusionCls = computed(() => {
  if (!props.lhb) return ''
  const a = props.lhb.action_tag || ''
  if (a.includes('抢筹')) return 'conclusion-positive'
  if (a.includes('砸盘')) return 'conclusion-negative'
  if (a === '主力分歧') return 'conclusion-neutral'
  return ''
})

function tagCls(tag) {
  if (!tag) return 'normal'
  const map = { '机构': 'inst', '北向': 'north', '一线游资': 'top', '核按钮': 'knife', '量化': 'quant', '散户': 'retail', '普通': 'normal' }
  return map[tag] || 'normal'
}

function ctagCls(t) {
  if (!t) return ''
  if (t.includes('抢筹') || t.includes('净买') || t.includes('加仓')) return 'ctag-red'
  if (t.includes('砸盘') || t.includes('卖出') || t.includes('核按钮')) return 'ctag-green'
  return 'ctag-orange'
}

function fmtPct(v) {
  if (v == null) return '--'
  return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'
}

function fmtAmount(v) {
  if (v == null) return '--'
  const absVal = Math.abs(v)
  if (absVal >= 100000000) return (v / 100000000).toFixed(2) + '亿'
  if (absVal >= 10000) return (v / 10000).toFixed(0) + '万'
  return v.toFixed(0)
}

function shortenName(name) {
  if (!name) return '--'
  return name
    .replace('股份有限公司', '')
    .replace('有限责任公司', '')
    .replace('有限公司', '')
    .replace('证券营业部', '')
    .replace('营业部', '')
}
</script>

<style scoped>
.lhb-panel {
  width: 100%;
  max-width: 520px;
  background: #fff;
  border-radius: 8px;
  padding: 14px;
  font-size: 13px;
  color: #333;
}

.state-msg { color: #667eea; text-align: center; padding: 40px; }
.state-card { text-align: center; padding: 40px 20px; border-radius: 10px; }
.error-card { background: #fff2f0; }
.error-text { color: #ff4d4f; font-size: 15px; font-weight: 600; margin-bottom: 8px; }
.btn-retry { margin-top: 12px; padding: 6px 18px; border: 1px solid #667eea; border-radius: 4px; background: white; color: #667eea; cursor: pointer; }
.empty-card { background: #fafafa; }
.status-icon { font-size: 32px; margin-bottom: 10px; }
.status-text { color: #666; font-size: 13px; }

/* 头部 */
.lhb-header { display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }
.header-title { font-size: 16px; font-weight: 700; color: #333; }
.header-date { font-size: 13px; color: #999; }

/* 上榜原因 */
.reason-bar { background: #f8f9ff; padding: 6px 10px; border-radius: 6px; font-size: 12px; color: #555; margin-bottom: 10px; display: flex; flex-wrap: wrap; gap: 2px; }
.reason-label { color: #888; }
.reason-sep { color: #ddd; margin: 0 4px; }
.change-pct { font-weight: 600; }
.change-pct.up { color: #ff4d4f; }
.change-pct.down { color: #52c41a; }

/* 资金汇总 + 进度条 */
.fund-summary { margin-bottom: 10px; }
.fund-row { display: flex; justify-content: space-between; margin-bottom: 6px; }
.fund-item { text-align: center; flex: 1; }
.fund-item.net { border-left: 1px solid #f0f0f0; border-right: 1px solid #f0f0f0; }
.fund-label { font-size: 11px; color: #999; display: block; margin-bottom: 2px; }
.fund-value { font-size: 15px; font-weight: 700; }
.fund-value.up { color: #ff4d4f; }
.fund-value.down { color: #52c41a; }

.bar-track { display: flex; height: 8px; border-radius: 4px; overflow: hidden; background: #f0f0f0; }
.bar-buy { background: #ff4d4f; transition: width 0.3s; }
.bar-sell { background: #52c41a; transition: width 0.3s; }
.bar-labels { display: flex; justify-content: space-between; margin-top: 2px; }
.bar-label { font-size: 10px; }
.bar-label.up { color: #ff4d4f; }
.bar-label.down { color: #52c41a; }

/* 结论 */
.conclusion-bar { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; border-radius: 8px; margin-bottom: 10px; }
.conclusion-positive { background: linear-gradient(135deg, #f6ffed, #e6fffb); }
.conclusion-negative { background: linear-gradient(135deg, #fff2f0, #fff7e6); }
.conclusion-neutral { background: #fafafa; }
.conclusion-tag { font-size: 14px; font-weight: 700; }
.conclusion-positive .conclusion-tag { color: #52c41a; }
.conclusion-negative .conclusion-tag { color: #ff4d4f; }
.conclusion-neutral .conclusion-tag { color: #fa8c16; }
.conclusion-type { font-size: 11px; color: #888; margin-left: 4px; }
.conclusion-tags { display: flex; gap: 4px; flex-wrap: wrap; }
.ctag { font-size: 10px; padding: 1px 8px; border-radius: 8px; font-weight: 500; }
.ctag-green { background: #f6ffed; color: #52c41a; }
.ctag-red { background: #fff2f0; color: #ff4d4f; }
.ctag-orange { background: #fff7e6; color: #fa8c16; }

/* 席位明细 - 双栏买入/卖出 */
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
.side-panel { border-radius: 8px; overflow: hidden; }
.buy-panel { border: 1px solid #ffecec; }
.sell-panel { border: 1px solid #ecf5ff; }
.side-title { padding: 8px 12px; font-size: 13px; font-weight: 600; }
.buy-panel .side-title { background: #fff5f5; color: #ff4d4f; }
.sell-panel .side-title { background: #f0f8ff; color: #1890ff; }
.seat-list { padding: 0; border: 1px solid #f0f0f0; border-radius: 8px; overflow: hidden; }
.seat-row { display: flex; align-items: flex-start; padding: 8px 10px; border-bottom: 1px solid #f5f5f5; gap: 8px; }
.seat-row:last-child { border-bottom: none; }
.seat-idx { color: #ccc; font-size: 11px; width: 16px; flex-shrink: 0; margin-top: 2px; }
.seat-body { flex: 1; min-width: 0; }
.seat-name-row { display: flex; align-items: center; gap: 6px; }
.seat-name { font-size: 12px; color: #333; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.seat-trader { font-size: 11px; color: #fa8c16; display: block; margin: 1px 0 2px; }
.seat-amt-row { display: flex; gap: 10px; font-size: 11px; margin-top: 2px; }
.seat-buy { color: #ff4d4f; font-weight: 600; }
.seat-sell { color: #52c41a; font-weight: 600; }
.seat-net { font-weight: 600; }
.seat-net.up { color: #ff4d4f; }
.seat-net.down { color: #52c41a; }
.seat-tag { font-size: 10px; padding: 1px 6px; border-radius: 8px; flex-shrink: 0; }
.tag-inst { background: #f6ffed; color: #52c41a; }
.tag-north { background: #e6f7ff; color: #1890ff; }
.tag-top { background: #fff7e6; color: #fa8c16; }
.tag-knife { background: #fff2f0; color: #ff4d4f; }
.tag-quant { background: #f0f5ff; color: #2f54eb; }
.tag-retail { background: #f5f5f5; color: #999; }
.tag-normal { background: #fafafa; color: #666; }
.no-data { color: #ccc; text-align: center; padding: 12px; font-size: 12px; }
.side-total { padding: 8px 12px; font-size: 12px; font-weight: 600; border-top: 1px solid #f0f0f0; }
.side-total .up { color: #ff4d4f; }
.side-total .down { color: #52c41a; }

/* 历史上榜 */
.history-section { background: #fafafa; padding: 10px 12px; border-radius: 8px; margin-bottom: 10px; }
.history-title { font-weight: 600; font-size: 13px; margin-bottom: 6px; color: #333; }
.history-row { display: flex; gap: 12px; font-size: 12px; padding: 3px 0; }
.history-date { color: #666; width: 80px; }
.history-net { font-weight: 600; }
.history-net.up { color: #ff4d4f; }
.history-net.down { color: #52c41a; }
.history-tag { color: #999; }

/* 风险提示 */
.risk-section { background: #fffbe6; border: 1px solid #ffe58f; padding: 10px 14px; border-radius: 8px; margin-bottom: 10px; }
.risk-title { font-weight: 600; font-size: 13px; color: #d46b08; margin-bottom: 6px; }
.risk-item { font-size: 12px; color: #666; padding: 2px 0; display: flex; align-items: center; gap: 4px; }
.risk-icon { font-size: 10px; }

.disclaimer { font-size: 11px; color: #bbb; text-align: center; margin-top: 12px; }
</style>
