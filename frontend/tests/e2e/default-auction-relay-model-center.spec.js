import { test, expect } from '@playwright/test'

test('default auction relay section renders in model center', async ({ page }) => {
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
            },
            default_auction_t0_limit_lgbm: {
              model_name: 'default_auction_t0_limit_lgbm',
              active_version: null,
              versions: []
            },
            default_auction_t1_premium_lgbm: {
              model_name: 'default_auction_t1_premium_lgbm',
              active_version: null,
              versions: []
            },
            default_auction_t1_continue_lgbm: {
              model_name: 'default_auction_t1_continue_lgbm',
              active_version: null,
              versions: []
            },
            default_auction_relay_v2: {
              model_name: 'default_auction_relay_v2',
              active_version: { version: 'composite', status: 'active' },
              target_models: [
                'default_auction_t0_limit_lgbm',
                'default_auction_t1_premium_lgbm',
                'default_auction_t1_continue_lgbm'
              ],
              versions: []
            }
          }
        }
      })
    })
  })

  await page.goto('http://localhost:8080/models')

  await expect(page.getByRole('heading', { name: '默认竞价接力 V2' })).toBeVisible()
  await expect(page.getByText('default_auction_t0_limit_lgbm')).toBeVisible()
  await expect(page.getByText('default_auction_t1_premium_lgbm')).toBeVisible()
  await expect(page.getByText('default_auction_t1_continue_lgbm')).toBeVisible()
  await expect(page.getByText('回放验收')).toBeVisible()
  await expect(page.getByText('样本构建')).toBeVisible()
  await expect(page.getByText('三目标训练')).toBeVisible()
})
