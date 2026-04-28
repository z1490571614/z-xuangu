<template>
  <div class="stock-result">
    <h2 class="page-title">选股结果</h2>
    
    <el-card class="filter-card">
      <el-form :inline="true">
        <el-form-item label="交易日期">
          <el-date-picker
            v-model="filterDate"
            type="date"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYYMMDD"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadResults">查询</el-button>
          <el-button @click="executeSelection">立即选股</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="result-card">
      <el-table :data="stockList" style="width: 100%" v-loading="loading">
        <el-table-column prop="ts_code" label="股票代码" width="120" />
        <el-table-column prop="name" label="股票名称" width="120" />
        <el-table-column prop="close_price" label="收盘价" width="100">
          <template #default="{ row }">
            {{ row.close_price ? row.close_price.toFixed(2) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="change_pct" label="涨跌幅" width="100">
          <template #default="{ row }">
            <span :class="row.change_pct >= 0 ? 'positive' : 'negative'">
              {{ row.change_pct ? row.change_pct.toFixed(2) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="circ_mv" label="流通市值(亿)" width="120">
          <template #default="{ row }">
            {{ row.circ_mv ? row.circ_mv.toFixed(2) : '-' }}
          </template>
        </el-table-column>
      </el-table>
      
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="handlePageChange"
        class="pagination"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getSelectionResults, getSelectionDetail, executeStockSelection } from '../api/stock'

const loading = ref(false)
const filterDate = ref(null)
const stockList = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)
const currentRecordId = ref(null)

const loadResults = async () => {
  loading.value = true
  try {
    const response = await getSelectionResults(currentPage.value, pageSize.value)
    if (response.code === 200 && response.data.length > 0) {
      const latestRecord = response.data[0]
      currentRecordId.value = latestRecord.id
      
      const detailResponse = await getSelectionDetail(currentRecordId.value)
      if (detailResponse.code === 200) {
        stockList.value = detailResponse.data.stocks || []
        total.value = detailResponse.data.total_count || 0
      }
    }
  } catch (error) {
    ElMessage.error('加载选股结果失败')
  } finally {
    loading.value = false
  }
}

const executeSelection = async () => {
  try {
    ElMessage.info('开始执行选股...')
    const response = await executeStockSelection(filterDate.value, false)
    if (response.code === 200) {
      ElMessage.success(`选股完成，选出 ${response.data.passed_count} 只股票`)
      loadResults()
    }
  } catch (error) {
    ElMessage.error('选股执行失败')
  }
}

const handlePageChange = (page) => {
  currentPage.value = page
  loadResults()
}

onMounted(() => {
  loadResults()
})
</script>

<style scoped>
.stock-result {
  padding: 20px;
}

.page-title {
  margin-bottom: 20px;
  color: #303133;
}

.filter-card {
  margin-bottom: 20px;
}

.result-card {
  margin-bottom: 20px;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.positive {
  color: #f56c6c;
}

.negative {
  color: #67c23a;
}
</style>
