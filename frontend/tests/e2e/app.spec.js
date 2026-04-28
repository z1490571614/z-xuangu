import { test, expect } from '@playwright/test';

test.describe('Dashboard 页面测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.app-header', { timeout: 10000 });
  });

  test('应该显示页面标题', async ({ page }) => {
    const header = page.locator('.app-header h1');
    await expect(header).toContainText('选股通知系统');
  });

  test('应该显示统计卡片', async ({ page }) => {
    const statCards = page.locator('.stat-card');
    await expect(statCards).toHaveCount(4, { timeout: 5000 });
  });

  test('应该显示快速操作按钮', async ({ page }) => {
    await expect(page.locator('button:has-text("立即执行选股")')).toBeVisible();
    await expect(page.locator('button:has-text("测试飞书通知")')).toBeVisible();
  });

  test('点击立即执行应该触发选股', async ({ page }) => {
    await page.click('button:has-text("立即执行选股")');
    await page.waitForTimeout(2000);
    const alert = page.locator('.alert');
    await expect(alert.first()).toBeVisible({ timeout: 5000 });
  });
});

test.describe('选股结果页面测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/stock-results');
    await page.waitForSelector('.app-header', { timeout: 10000 });
  });

  test('应该显示日期选择器', async ({ page }) => {
    await expect(page.locator('.date-picker input[type="date"]')).toBeVisible();
  });

  test('应该显示股票列表表格或暂无数据提示', async ({ page }) => {
    const table = page.locator('.data-table');
    const noData = page.locator('.no-data');
    const isTableVisible = await table.count() > 0;
    const isNoDataVisible = await noData.count() > 0;
    expect(isTableVisible || isNoDataVisible).toBe(true);
  });

  test('页面标题正确', async ({ page }) => {
    await expect(page.locator('h2:has-text("选股结果")')).toBeVisible();
  });
});

test.describe('任务管理页面测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/tasks');
    await page.waitForSelector('.app-header', { timeout: 10000 });
  });

  test('应该显示任务配置表单', async ({ page }) => {
    await expect(page.locator('.task-form')).toBeVisible();
  });

  test('应该显示输入字段', async ({ page }) => {
    await expect(page.locator('input[placeholder="任务名称"]')).toBeVisible();
    await expect(page.locator('input[placeholder*="Cron"]')).toBeVisible();
  });

  test('页面标题正确', async ({ page }) => {
    await expect(page.locator('h2:has-text("任务管理")')).toBeVisible();
  });
});

test.describe('系统设置页面测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings');
    await page.waitForSelector('.app-header', { timeout: 10000 });
  });

  test('应该显示配置表单', async ({ page }) => {
    await expect(page.locator('.config-form')).toBeVisible();
  });

  test('应该显示配置字段', async ({ page }) => {
    await expect(page.locator('label:has-text("Tushare Token")')).toBeVisible();
    await expect(page.locator('label:has-text("飞书 Webhook URL")')).toBeVisible();
  });

  test('应该显示测试通知按钮', async ({ page }) => {
    await expect(page.locator('button:has-text("测试通知")')).toBeVisible();
  });

  test('页面标题正确', async ({ page }) => {
    await expect(page.locator('h2:has-text("系统设置")')).toBeVisible();
  });
});

test.describe('导航功能测试', () => {
  test('导航链接可点击', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('.app-header', { timeout: 10000 });

    await page.click('a:has-text("选股结果")');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/stock-results/);

    await page.click('a:has-text("任务管理")');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/tasks/);

    await page.click('a:has-text("系统设置")');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/settings/);

    await page.click('a:has-text("首页")');
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\//);
  });
});

test.describe('响应式布局测试', () => {
  test('桌面端布局正确', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto('/');
    await page.waitForSelector('.app-header', { timeout: 10000 });

    const header = page.locator('.app-header');
    await expect(header).toBeVisible();

    const navLinks = page.locator('.nav-links a');
    await expect(navLinks).toHaveCount(4);
  });

  test('移动端布局适配', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    await page.waitForSelector('.app-header', { timeout: 10000 });

    const header = page.locator('.app-header');
    await expect(header).toBeVisible();
  });
});
