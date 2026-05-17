import { test, expect } from '@playwright/test';

test('选股结果在评分旁显示 LightGBM 概率', async ({ page }) => {
  await page.route('**/api/v1/stock/results?page=*', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          records: [{ id: 41, trade_date: '20260508', total_count: 1, status: 'success', execute_time: '2026-05-09T10:00:00' }],
          total: 1,
        },
      }),
    });
  });

  await page.route('**/api/v1/stock/results/41', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          t0_model_disclaimer: 'LightGBM 模型仅供参考',
          stocks: [{
            ts_code: '000889.SZ',
            name: '中嘉博创',
            close_price: 5.41,
            change_pct: 1.12,
            open_change_pct: 5.79,
            final_score: 57,
            t0_limit_success_prob: 41.72,
            t0_limit_success_model_version: '20260509_172312',
            default_t0_limit_prob: 40.0,
            default_t1_premium_prob: 31.5,
            default_t1_continue_prob: 18.25,
            default_relay_score: 66.6,
            reasons: ['涨停基因强'],
          }],
        },
      }),
    });
  });

  await page.route('**/api/v1/stock/**', async route => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: {} }) });
  });

  await page.goto('http://localhost:8080/stock-results');

  await expect(page.locator('.stock-table thead')).toContainText('LightGBM');
  await expect(page.locator('.stock-table thead')).toContainText('T+0涨停概率');
  await expect(page.locator('.stock-table thead')).toContainText('T+1高溢价概率');
  await expect(page.locator('.stock-table thead')).toContainText('T+1连板概率');
  await expect(page.locator('.stock-table thead')).toContainText('接力分');
  await expect(page.locator('.stock-table tbody')).toContainText('41.72%');
  await expect(page.locator('.stock-table tbody')).toContainText('40.0%');
  await expect(page.locator('.stock-table tbody')).toContainText('31.5%');
  await expect(page.locator('.stock-table tbody')).toContainText('18.3%');
  await expect(page.locator('.stock-table tbody')).toContainText('66.6');
  await expect(page.locator('.stock-table tbody')).toContainText('57.0');
});
