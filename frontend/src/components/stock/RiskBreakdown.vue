<template>
  <div class="risk-panel">
    <div v-if="loading" class="state-msg">加载风险拆解中...</div>

    <div v-else-if="error" class="state-card error-card">
      <div class="error-text">风险拆解加载失败</div>
      <p>{{ error }}</p>
      <button class="btn-retry" @click="$emit('reload')">重新加载</button>
    </div>

    <div v-else-if="!riskData || (riskData.data_status !== 'available' && !riskData.strategy_type)" class="state-card empty-card">
      <div class="status-icon">🛡️</div>
      <div class="status-text">{{ statusText }}</div>
    </div>

    <!-- 龙头战法模式 -->
    <div v-else-if="riskData.strategy_type === 'dragon_leader'" class="risk-content dragon-leader">
      <!-- 简化说明卡片 -->
      <div v-if="riskData.simplified_summary" class="summary-card">
        <div class="summary-text">{{ riskData.simplified_summary }}</div>
      </div>

      <!-- 顶部分数三栏 -->
      <div class="dl-header">
        <div class="header-title">
          <span>龙头战法评分</span>
          <span class="header-date">{{ riskData.trade_date }}</span>
          <span class="dl-badge">龙</span>
        </div>
        <div class="score-row">
          <div class="score-box strength">
            <div class="score-label">龙头强度</div>
            <div class="score-value">{{ riskData.leader_strength_score }}</div>
            <div class="score-sub">{{ riskData.leader_level }}</div>
          </div>
          <div class="score-box retreat">
            <div class="score-label">退潮风险</div>
            <div class="score-value">{{ riskData.retreat_risk_score }}</div>
            <div class="score-sub">{{ riskData.risk_level }}</div>
          </div>
          <div class="score-box health">
            <div class="score-label">综合健康度</div>
            <div class="score-value">{{ riskData.health_score }}</div>
            <div class="score-sub">{{ riskData.health_level }}</div>
          </div>
        </div>
        <div class="cycle-stage">当前阶段：{{ riskData.cycle_stage || '--' }}</div>
      </div>

      <!-- 强势依据 -->
      <div v-if="riskData.positive_tips?.length" class="dl-section">
        <div class="section-title positive">强势依据</div>
        <div class="section-body">
          <div v-for="(t, i) in riskData.positive_tips" :key="i" class="tip-item positive">● {{ t }}</div>
        </div>
      </div>

      <!-- 风险依据 -->
      <div v-if="riskData.negative_tips?.length" class="dl-section">
        <div class="section-title negative">风险依据</div>
        <div class="section-body">
          <div v-for="(t, i) in riskData.negative_tips" :key="i" class="tip-item negative">● {{ t }}</div>
        </div>
      </div>

      <!-- 消息面 -->
      <div v-if="riskData.score_detail?.alpha_adjustment" class="dl-section">
        <div class="section-title news">消息面</div>
        <div class="section-body">
          <div v-if="riskData.announcement_alpha_score > 0" class="tip-item positive">利好加分 +{{ riskData.announcement_alpha_score }}</div>
          <div v-else-if="riskData.announcement_alpha_score < 0" class="tip-item negative">利空扣分 {{ riskData.announcement_alpha_score }}</div>
          <div v-else class="tip-item neutral">无重大消息</div>
          <div v-for="(t, i) in riskData.score_detail.alpha_adjustment.announcement_tips" :key="'a'+i" class="tip-item detail">{{ t }}</div>
        </div>
      </div>

      <!-- 龙虎榜 -->
      <div v-if="riskData.score_detail?.alpha_adjustment" class="dl-section">
        <div class="section-title lhb">龙虎榜</div>
        <div class="section-body">
          <div v-if="riskData.score_detail.alpha_adjustment.lhb_bonus_score > 0" class="tip-item positive">席位加分 +{{ riskData.score_detail.alpha_adjustment.lhb_bonus_score }}</div>
          <div v-if="riskData.score_detail.alpha_adjustment.lhb_penalty_score < 0" class="tip-item negative">席位扣分 {{ riskData.score_detail.alpha_adjustment.lhb_penalty_score }}</div>
          <div v-else-if="riskData.score_detail.alpha_adjustment.lhb_bonus_score === 0 && riskData.score_detail.alpha_adjustment.lhb_penalty_score === 0" class="tip-item neutral">暂无龙虎榜数据</div>
          <div v-if="riskData.lhb_alpha_score !== 0" class="tip-item detail">龙虎榜净分 {{ riskData.lhb_alpha_score }}</div>
          <div v-for="(t, i) in riskData.score_detail.alpha_adjustment.lhb_tips" :key="'l'+i" class="tip-item detail">{{ t }}</div>
        </div>
      </div>

      <!-- 明日观察 -->
      <div v-if="riskData.watch_tips?.length" class="dl-section">
        <div class="section-title watch">明日观察</div>
        <div class="section-body">
          <div v-for="(t, i) in riskData.watch_tips" :key="i" class="tip-item watch">● {{ t }}</div>
        </div>
      </div>

      <!-- 详细评分分项（始终可见） -->
      <div class="dl-section">
        <div class="section-title detail-title">详细评分分项</div>
        <div class="detail-grid">
          <div class="detail-col">
            <div class="detail-col-title positive">龙头强度</div>
            <div v-for="(v, k) in riskData.score_detail?.leader_strength" :key="k" class="detail-item detail-row">
              <span class="detail-name">{{ getScoreLabel(k, 'leader_strength') }}</span>
              <span class="detail-score">{{ v.score || 0 }}</span>
              <span class="detail-tip">{{ formatDetailTips(v.tips) }}</span>
            </div>
            <div class="detail-total positive-total">总分 {{ riskData.leader_strength_score }}</div>
          </div>
          <div class="detail-col">
            <div class="detail-col-title negative">退潮风险</div>
            <div v-for="(v, k) in riskData.score_detail?.retreat_risk" :key="k" class="detail-item detail-row">
              <span class="detail-name">{{ getScoreLabel(k, 'retreat_risk') }}</span>
              <span class="detail-score">{{ v.score || 0 }}</span>
              <span class="detail-tip">{{ formatDetailTips(v.tips) }}</span>
            </div>
            <div class="detail-total negative-total">总分 {{ riskData.retreat_risk_score }}</div>
          </div>
        </div>
      </div>

      <div class="disclaimer">评分基于公开数据纯规则计算，仅供参考</div>
    </div>

    <!-- 普通风险模型 -->
    <div v-else class="risk-content">
      <div class="risk-header">
        <div class="header-title">
          <span>风险拆解</span>
          <span class="header-date">{{ riskData.trade_date }}</span>
        </div>
        <div class="total-row">
          <span class="total-score">总风险：<strong>{{ riskData.total_score }}</strong>分</span>
          <span :class="'level-tag ' + riskData.risk_level">{{ riskData.risk_level }}</span>
        </div>
        <div class="risk-summary">{{ riskData.risk_summary || '--' }}</div>
        <div class="risk-bar-track">
          <div class="risk-bar" :style="{ width: riskData.total_score + '%' }" :class="riskData.risk_level"></div>
        </div>
      </div>

      <div class="risk-items">
        <div v-for="(item, idx) in riskItems" :key="idx" class="risk-item">
          <div class="item-head">
            <span class="item-name">{{ item.name }}</span>
            <span :class="'item-score ' + getScoreCls(item.score, item.max)">{{ item.score }}/{{ item.max }}</span>
          </div>
          <div v-if="item.tips && item.tips.length" class="item-tips">
            <div v-for="(tip, i) in item.tips" :key="i" class="tip">● {{ tip }}</div>
          </div>
          <div v-else class="item-tips no-risk">无风险项</div>
        </div>
      </div>

      <div v-if="sectorContext.primary_board" class="context-section">
        <div class="context-title">主线板块</div>
        <div class="context-grid">
          <span>{{ sectorContext.primary_board.name }}</span>
          <span v-if="sectorContext.board_pct_chg !== undefined">涨跌 {{ formatPct(sectorContext.board_pct_chg) }}</span>
          <span v-if="sectorContext.money_net_amount_yi !== undefined">资金 {{ formatMoney(sectorContext.money_net_amount_yi) }}</span>
          <span v-if="sectorContext.limit_up_count !== undefined">涨停 {{ sectorContext.limit_up_count }} 家</span>
          <span v-if="sectorContext.strength_score !== undefined">强度 {{ formatNumber(sectorContext.strength_score) }}</span>
        </div>
      </div>

      <div v-if="strengthEvidence.length" class="evidence-section">
        <div class="section-title positive">强势依据</div>
        <div class="section-body">
          <div v-for="(t, i) in strengthEvidence" :key="'s'+i" class="tip-item positive">● {{ t }}</div>
        </div>
      </div>

      <div v-if="riskEvidence.length" class="evidence-section">
        <div class="section-title negative">风险依据</div>
        <div class="section-body">
          <div v-for="(t, i) in riskEvidence" :key="'r'+i" class="tip-item negative">● {{ t }}</div>
        </div>
      </div>

      <div v-if="riskData.warning_tip" class="warning-bar">
        ⚠️ 高危预警：{{ riskData.warning_tip }}
      </div>

      <div v-if="riskData.history && riskData.history.length" class="history-section">
        <div class="history-title">历史风险走势</div>
        <div v-for="(h, i) in riskData.history" :key="i" class="history-row">
          <span class="history-date">{{ h.trade_date }}</span>
          <span :class="'history-score ' + h.risk_level">{{ h.total_score }}分</span>
          <span :class="'history-level ' + h.risk_level">{{ h.risk_level }}</span>
        </div>
      </div>

      <div class="disclaimer">风险评分基于公开数据纯规则计算，仅供参考</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  riskData: Object,
  loading: Boolean,
  error: [String, null],
})
defineEmits(['reload'])

const DEFAULT_LABELS = {
  leader_strength: {
    leader_status: '龙头地位',
    theme_strength: '题材强度',
    emotion_cycle: '情绪周期',
    sector_ladder: '板块梯队',
    acceptance_strength: '承接强度',
    auction_intraday: '竞价分时',
    lhb_bonus: '龙虎榜加成',
  },
  retreat_risk: {
    leader_position_loss: '龙头地位动摇',
    emotion_retreat: '情绪退潮',
    ladder_break: '板块梯队断裂',
    acceptance_failure: '承接失败',
    chip_cashout: '筹码兑现',
    auction_miss: '竞价低预期',
    announcement_regulatory: '公告监管风险',
    financial_risk: '业绩风险',
    shareholder_risk: '减持解禁',
    st_risk: 'ST退市风险',
  },
}

function getScoreLabel(key, group) {
  const labels = props.riskData?.score_labels?.[group] || DEFAULT_LABELS[group] || {}
  return labels[key] || key
}

function formatDetailTips(tips) {
  return (tips || [])
    .filter(Boolean)
    .slice(0, 3)
    .join('；')
}

const statusText = computed(() => {
  if (!props.riskData) return '暂无风险拆解数据'
  const map = {
    source_not_configured: '风险数据源未配置，需接入 Tushare 接口',
    timeout: '获取风险数据超时，请稍后重试',
    fetch_failed: '风险数据获取失败',
  }
  return map[props.riskData?.data_status] || '暂无风险拆解数据'
})

const riskItems = computed(() => {
  const d = props.riskData || {}
  return [
    { name: '市场环境', score: d.market_score || 0, max: 10, tips: d.market_tips || [] },
    { name: '筹码压力', score: d.chip_score || 0, max: 14, tips: d.chip_tips || [] },
    { name: '舆情与公告', score: d.news_score || 0, max: 18, tips: d.news_tips || [] },
    { name: '个股资金', score: d.capital_score || 0, max: 14, tips: d.capital_tips || [] },
    { name: '龙虎风险', score: d.lhb_score || 0, max: 10, tips: d.lhb_tips || [] },
    { name: '板块与题材风险', score: d.sector_score || 0, max: 18, tips: d.sector_tips || [] },
    { name: '技术结构', score: d.technical_score || 0, max: 16, tips: d.technical_tips || [] },
  ]
})

const sectorContext = computed(() => props.riskData?.sector_context || {})
const strengthEvidence = computed(() => props.riskData?.strength_evidence || [])
const riskEvidence = computed(() => props.riskData?.risk_evidence || [])

function formatPct(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '--'
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}%`
}

function formatMoney(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '--'
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}亿`
}

function formatNumber(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '--'
  return n.toFixed(0)
}

function getScoreCls(score, max) {
  const pct = max > 0 ? score / max : 0
  if (pct >= 0.8) return 'high'
  if (pct >= 0.5) return 'mid'
  return 'low'
}
</script>

<style scoped>
.risk-panel {
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

/* 龙头战法模式 */
.dragon-leader { font-size: 13px; }
.summary-card { background: linear-gradient(135deg, #f0f5ff, #e6f7ff); border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; border-left: 3px solid #1890ff; }
.summary-text { font-size: 13px; line-height: 1.7; color: #333; }
.dl-header { margin-bottom: 14px; }
.header-title { display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 700; margin-bottom: 10px; }
.header-date { font-size: 12px; color: #999; font-weight: 400; }
.dl-badge { display: inline-block; padding: 1px 8px; border-radius: 4px; background: #ff6b00; color: #fff; font-size: 11px; font-weight: 700; }
.score-row { display: flex; gap: 8px; margin-bottom: 8px; }
.score-box { flex: 1; text-align: center; padding: 12px 6px; border-radius: 8px; }
.score-box.strength { background: linear-gradient(135deg, #fff1f0, #ffccc7); }
.score-box.retreat { background: linear-gradient(135deg, #f6ffed, #d9f7be); }
.score-box.health { background: linear-gradient(135deg, #e6f7ff, #bae7ff); }
.score-label { font-size: 11px; color: #666; margin-bottom: 4px; }
.score-value { font-size: 24px; font-weight: 800; }
.score-value { color: #cf1322; }
.score-box.retreat .score-value { color: #389e0d; }
.score-box.health .score-value { color: #1890ff; }
.score-sub { font-size: 11px; color: #888; margin-top: 2px; }
.cycle-stage { text-align: center; font-size: 12px; color: #666; padding: 4px 0; border-top: 1px dashed #f0f0f0; }

.dl-section { margin-bottom: 10px; }
.section-title { font-weight: 700; font-size: 13px; margin-bottom: 4px; padding-left: 8px; border-left: 3px solid; }
.section-title.positive { color: #cf1322; border-color: #cf1322; }
.section-title.negative { color: #389e0d; border-color: #389e0d; }
.section-title.news { color: #722ed1; border-color: #722ed1; }
.section-title.lhb { color: #fa8c16; border-color: #fa8c16; }
.section-title.watch { color: #1890ff; border-color: #1890ff; }
.section-title.detail-title { color: #333; border-color: #667eea; }
.section-body { padding: 4px 0 4px 12px; }
.tip-item { font-size: 12px; line-height: 1.8; color: #555; }
.tip-item.positive { color: #cf1322; }
.tip-item.negative { color: #389e0d; }
.tip-item.detail { color: #888; font-size: 11px; }
.tip-item.neutral { color: #999; }
.tip-item.watch { color: #1890ff; }

.detail-grid { display: flex; gap: 8px; margin-top: 6px; }
.detail-col { flex: 1; background: #fafafa; border-radius: 6px; padding: 8px; }
.detail-col-title { font-size: 11px; font-weight: 600; margin-bottom: 6px; }
.detail-col-title.positive { color: #cf1322; }
.detail-col-title.negative { color: #389e0d; }
.detail-row { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 6px; font-size: 11px; padding: 3px 2px; border-bottom: 1px dashed #f0f0f0; }
.detail-row:last-of-type { border-bottom: none; }
.detail-name { color: #888; min-width: 60px; }
.detail-score { font-weight: 700; min-width: 20px; text-align: right; }
.detail-tip { color: #aaa; font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.detail-total { font-size: 12px; font-weight: 700; text-align: right; padding-top: 4px; border-top: 1px solid #e8e8e8; margin-top: 4px; }
.detail-total.positive-total { color: #cf1322; }
.detail-total.negative-total { color: #389e0d; }

/* 普通风险模型 */
.risk-header { margin-bottom: 14px; }
.risk-header .header-title { font-size: 16px; font-weight: 700; margin-bottom: 8px; }
.total-row { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.total-score { font-size: 15px; }
.total-score strong { font-size: 20px; }
.level-tag { padding: 2px 10px; border-radius: 4px; font-size: 13px; font-weight: 700; }
.level-tag.低 { background: #e6ffeb; color: #009933; }
.level-tag.中 { background: #fff7e6; color: #ff7d00; }
.level-tag.高 { background: #fff2f0; color: #ff4d4f; }
.level-tag.极高 { background: #ff2f2f; color: #fff; }
.risk-summary { color: #666; font-size: 12px; margin-bottom: 8px; }
.risk-bar-track { height: 6px; background: #f0f0f0; border-radius: 3px; }
.risk-bar { height: 100%; border-radius: 3px; transition: width 0.3s; }
.risk-bar.低 { background: #009933; }
.risk-bar.中 { background: #ff7d00; }
.risk-bar.高 { background: #ff4d4f; }
.risk-bar.极高 { background: #ff0000; }

.risk-items { margin-bottom: 12px; }
.risk-item { margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px dashed #f0f0f0; }
.risk-item:last-child { border-bottom: none; }
.item-head { display: flex; justify-content: space-between; font-weight: 600; margin-bottom: 4px; font-size: 13px; }
.item-score.high { color: #ff0000; }
.item-score.mid { color: #ff7d00; }
.item-score.low { color: #009933; }
.item-tips { font-size: 12px; color: #555; line-height: 1.6; }
.tip { margin-bottom: 2px; }
.no-risk { color: #bbb; font-size: 11px; }

.context-section { margin: 10px 0 12px; padding: 10px 12px; background: #f7fbff; border-radius: 8px; border-left: 3px solid #1890ff; }
.context-title { font-size: 12px; color: #1890ff; font-weight: 700; margin-bottom: 6px; }
.context-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.context-grid span { font-size: 11px; color: #4a5a68; background: #fff; border: 1px solid #e6f4ff; border-radius: 4px; padding: 3px 7px; }
.evidence-section { margin: 10px 0; }

.warning-bar { margin-top: 12px; padding: 8px 12px; background: #fff2f0; color: #ff0000; border-radius: 6px; font-size: 12px; font-weight: 600; }

.history-section { background: #fafafa; padding: 10px 12px; border-radius: 8px; margin-top: 12px; }
.history-title { font-weight: 600; font-size: 13px; margin-bottom: 6px; color: #333; }
.history-row { display: flex; gap: 12px; font-size: 12px; padding: 3px 0; }
.history-date { color: #666; width: 80px; }
.history-score { font-weight: 600; }
.history-score.低 { color: #009933; }
.history-score.中 { color: #ff7d00; }
.history-score.高 { color: #ff4d4f; }
.history-score.极高 { color: #ff0000; }
.history-level { color: #999; }

.disclaimer { font-size: 11px; color: #bbb; text-align: center; margin-top: 14px; }
</style>
