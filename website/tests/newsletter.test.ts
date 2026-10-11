/**
 * The launch-updates newsletter sign-up: the build-time gate on PUBLIC_MAILCHIMP_FORM_ACTION, the
 * bot-trap name, and a build without the variable (tests/setup/build.ts clears it) rendering no
 * form and naming Mailchimp's sign-up host nowhere.
 */
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  newsletterFormAction,
  newsletterTrapName,
} from '../src/lib/newsletter.mjs';

const ACTION =
  'https://example.us1.list-manage.com/subscribe/post?u=0123456789abcdef&id=abcdef1234';
const dist = path.resolve(import.meta.dirname, '../dist');

describe('newsletterFormAction', () => {
  it('is null when the variable is unset or blank', () => {
    expect(newsletterFormAction({})).toBeNull();
    expect(
      newsletterFormAction({ PUBLIC_MAILCHIMP_FORM_ACTION: '  ' }),
    ).toBeNull();
  });

  it('accepts a Mailchimp embedded-form action, with or without a form id', () => {
    expect(newsletterFormAction({ PUBLIC_MAILCHIMP_FORM_ACTION: ACTION })).toBe(
      ACTION,
    );
    const withForm = `${ACTION}&f_id=00a1b2c3d4`;
    expect(
      newsletterFormAction({ PUBLIC_MAILCHIMP_FORM_ACTION: ` ${withForm} ` }),
    ).toBe(withForm);
  });

  it.each([
    'http://example.us1.list-manage.com/subscribe/post?u=0123456789abcdef&id=abcdef1234',
    'https://example.us1.list-manage.com.evil.test/subscribe/post?u=0123456789abcdef&id=abcdef1234',
    'https://evil.test/subscribe/post?u=0123456789abcdef&id=abcdef1234',
    'https://example.us1.list-manage.com/subscribe/post?id=abcdef1234&u=0123456789abcdef',
    `${ACTION}&tags=launch`,
    'https://example.us1.list-manage.com/subscribe/post?u=ZZZZ&id=abcdef1234',
  ])('fails the build on anything else: %s', (value) => {
    expect(() =>
      newsletterFormAction({ PUBLIC_MAILCHIMP_FORM_ACTION: value }),
    ).toThrow(/PUBLIC_MAILCHIMP_FORM_ACTION must be a Mailchimp/);
  });
});

describe('newsletterTrapName', () => {
  it('names the bot trap after the account and audience', () => {
    expect(newsletterTrapName(ACTION)).toBe('b_0123456789abcdef_abcdef1234');
  });

  it('refuses a value that is not a form action', () => {
    expect(() => newsletterTrapName('https://evil.test/')).toThrow();
  });
});

function htmlFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return htmlFiles(target);
    return entry.name.endsWith('.html') ? [target] : [];
  });
}

describe('a build without PUBLIC_MAILCHIMP_FORM_ACTION', () => {
  it('renders no sign-up form and never names list-manage.com', () => {
    const offenders = htmlFiles(dist)
      .filter((file) =>
        /data-newsletter\b|list-manage\.com/.test(readFileSync(file, 'utf8')),
      )
      .map((file) => path.relative(dist, file));
    expect(offenders).toEqual([]);
  });

  it('still publishes the newsletter notice on the privacy page', () => {
    const privacy = readFileSync(path.join(dist, 'privacy/index.html'), 'utf8');
    expect(privacy).toContain('id="newsletter"');
    expect(privacy).toContain('mailto:info@genome-os.org');
  });
});
