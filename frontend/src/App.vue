<template>
  <div id="app">
    <header class="app-header">
      <h1>📊 选股通知系统</h1>
      <nav class="nav-links">
        <router-link to="/" exact-active-class="active">首页</router-link>
        <router-link to="/stock-results" active-class="active">选股结果</router-link>
        <router-link to="/models" active-class="active">模型中心</router-link>
        <router-link to="/tasks" active-class="active">任务管理</router-link>
        <router-link to="/settings" active-class="active">系统设置</router-link>
      </nav>
    </header>

    <main class="main-content">
      <router-view></router-view>
    </main>
  </div>
</template>

<script setup>
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif;
  background: #f0f2f5;
  color: #333;
}

#app {
  min-height: 100vh;
}

.app-header {
  background: white;
  padding: 16px 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.app-header h1 {
  font-size: 20px;
  font-weight: 600;
  color: #1890ff;
}

.nav-links {
  display: flex;
  gap: 24px;
}

.nav-links a {
  text-decoration: none;
  color: #666;
  font-size: 14px;
  padding: 8px 16px;
  border-radius: 4px;
  transition: all 0.3s;
}

.nav-links a:hover {
  color: #1890ff;
  background: #e6f7ff;
}

.nav-links a.active {
  color: #1890ff;
  background: #e6f7ff;
  font-weight: 600;
}

.main-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}
</style>
