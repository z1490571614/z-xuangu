import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import StockResults from '../views/StockResults.vue'
import TaskManage from '../views/TaskManage.vue'
import Settings from '../views/Settings.vue'
import StrategyManage from '../views/StrategyManage.vue'

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: Dashboard
  },
  {
    path: '/stock-results',
    name: 'StockResults',
    component: StockResults
  },
  {
    path: '/tasks',
    name: 'TaskManage',
    component: TaskManage
  },
  {
    path: '/settings',
    name: 'Settings',
    component: Settings
  },
  {
    path: '/strategy-manage',
    name: 'StrategyManage',
    component: StrategyManage
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
