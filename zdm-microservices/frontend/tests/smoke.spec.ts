import { expect, test } from '@playwright/test';

test('settings page renders', async ({ page }) => {
  await page.goto('/settings');
  await expect(page.getByRole('heading', { name: 'ZEUS Settings', exact: true })).toBeVisible();
});

test('navigation reaches core pages', async ({ page }) => {
  await page.goto('/settings');
  await page.getByRole('button', { name: 'Projects' }).click();
  await expect(page).toHaveURL(/\/projects$/);
  await expect(page.getByRole('heading', { name: 'Projects', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'ZDM Response Files' }).click();
  await expect(page).toHaveURL(/\/response-files$/);
  await expect(page.getByRole('heading', { name: 'ZDM Response Files', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Migration Dashboard' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole('heading', { name: 'Migration Dashboard', exact: true })).toBeVisible();
});
