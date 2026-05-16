import { test, expect } from '@playwright/test'

test('model center route renders core sections', async ({ page }) => {
  await page.route('**/api/v1/models', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        message: 'success',
        data: {
          models: {
            leader_main_t0_lgbm: {
              model_name: 'leader_main_t0_lgbm',
              active_version: {
                version: 'v1',
                metrics: { precision: 0.5, auc: 0.69 },
                available: true
              },
              versions: [
                { version: 'v1', is_active: true, available: true, metrics: { precision: 0.5 } }
              ]
            }
          }
        }
      })
    })
  })
  await page.goto('http://localhost:8080/models')
  await expect(page.getByRole('heading', { name: '模型中心' })).toBeVisible()
  await expect(page.getByText('模型概览')).toBeVisible()
  await expect(page.getByText('预测刷新')).toBeVisible()
  await expect(page.getByText('训练控制台')).toBeVisible()
  await expect(page.getByText('训练任务与日志')).toBeVisible()
})

test('model center refreshes predictions for a record', async ({ page }) => {
  await page.route('**/api/v1/models', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        data: {
          models: {
            leader_main_t0_lgbm: {
              model_name: 'leader_main_t0_lgbm',
              active_version: { version: 'v1', available: true, metrics: {} },
              versions: [{ version: 'v1', is_active: true, available: true, metrics: {} }]
            }
          }
        }
      })
    })
  })
  await page.route('**/api/v1/models/leader_main_t0_lgbm/refresh-predictions', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { updated_count: 3, failed: [] } })
    })
  })
  await page.goto('http://localhost:8080/models')
  await page.getByLabel('选股记录 ID').fill('46')
  await page.getByRole('button', { name: '刷新预测' }).click()
  await expect(page.getByText('已更新 3 只股票')).toBeVisible()
})

test('model center starts a test training job and shows progress', async ({ page }) => {
  await page.route('**/api/v1/models', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        data: {
          models: {
            leader_main_t0_lgbm: {
              model_name: 'leader_main_t0_lgbm',
              active_version: null,
              versions: []
            }
          }
        }
      })
    })
  })
  await page.route('**/api/v1/models/leader_main_t0_lgbm/training-jobs', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { job_id: 12 } })
    })
  })
  await page.route('**/api/v1/models/training-jobs/12', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        data: {
          id: 12,
          status: 'running',
          phase: 'train',
          progress: 55,
          logs: [{ message: '开始第 1 次训练' }],
          attempts: []
        }
      })
    })
  })
  await page.goto('http://localhost:8080/models')
  await page.getByLabel('训练开始日期').fill('20250101')
  await page.getByLabel('训练结束日期').fill('20260508')
  await page.getByRole('button', { name: '测试训练' }).click()
  await expect(page.getByText('任务 #12')).toBeVisible()
  await expect(page.getByText('55%')).toBeVisible()
})
