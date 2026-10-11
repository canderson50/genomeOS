/**
 * The launch-updates newsletter sign-up in a browser. `npm run test:e2e` builds with a
 * placeholder Mailchimp form action on example.us1.list-manage.com; these tests never submit to
 * it, and check that the page contacts Mailchimp only on submit.
 */
import { expect, test } from '@playwright/test';

import { installAtlasBrowserFixture } from './atlas-browser-fixture';

const ACTION =
  'https://example.us1.list-manage.com/subscribe/post?u=0123456789abcdef&id=abcdef1234';

test.beforeEach(async ({ page }) => installAtlasBrowserFixture(page));
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
});

test('the home page posts the sign-up straight to Mailchimp and loads nothing from it', async ({
  page,
}) => {
  const mailchimp: string[] = [];
  page.on('request', (request) => {
    if (/list-manage\.com|mailchimp|chimpstatic/.test(request.url()))
      mailchimp.push(request.url());
  });

  await page.goto('/');
  const form = page.locator('[data-newsletter] form');
  await form.scrollIntoViewIfNeeded();

  await expect(form).toHaveAttribute('action', ACTION);
  await expect(form).toHaveAttribute('method', 'post');
  await expect(form.getByLabel('Email address')).toHaveAttribute(
    'name',
    'EMAIL',
  );
  await expect(
    form.locator('input[name="b_0123456789abcdef_abcdef1234"]'),
  ).toHaveValue('');
  await expect(form.locator('.newsletter__trap')).not.toBeInViewport();
  await expect(
    form.getByRole('link', { name: 'How my email is used' }),
  ).toHaveAttribute('href', '/privacy/#newsletter');
  expect(mailchimp).toEqual([]);
});

test('consent starts unticked and is required before the form can submit', async ({
  page,
}) => {
  const submitted: string[] = [];
  await page.route(/list-manage\.com/, (route) => {
    submitted.push(route.request().url());
    return route.fulfill({ status: 204 });
  });

  await page.goto('/');
  const form = page.locator('[data-newsletter] form');
  const consent = form.locator('[data-newsletter-consent]');
  await expect(consent).not.toBeChecked();
  await expect(consent).toHaveAttribute('required', '');

  await form.getByLabel('Email address').fill('reader@example.org');
  await form.getByRole('button', { name: 'Sign up' }).click();
  expect(
    await consent.evaluate(
      (input: HTMLInputElement) => input.validity.valueMissing,
    ),
  ).toBe(true);
  expect(submitted).toEqual([]);
});
