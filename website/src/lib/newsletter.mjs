// @ts-check
/**
 * The launch-updates newsletter sign-up for genome-os.org, sent to a Mailchimp audience held by
 * the genomeOS Foundation.
 *
 * A build shows the form only when its environment sets PUBLIC_MAILCHIMP_FORM_ACTION, and only
 * the production Pages build does, from the repository variable MAILCHIMP_FORM_ACTION. Local dev,
 * the unit-test build, the /genomeOS/ fallback, pull requests and forks render no form.
 *
 * The form is plain HTML that posts straight to Mailchimp's hosted sign-up endpoint, so the site
 * loads no Mailchimp script and sets no cookie; nothing reaches Mailchimp until a visitor submits.
 * The audience must use double opt-in, so an address is added only after its owner confirms it.
 * What is collected and why is on the privacy page.
 */

/**
 * A Mailchimp embedded-form action: a list-manage host, the account `u` and audience `id`, and
 * optionally the form `f_id`, in that order and nothing else.
 */
const FORM_ACTION =
  /^https:\/\/(?:[a-z0-9-]+\.)+list-manage\.com\/subscribe\/post\?u=([0-9a-f]{8,40})&id=([0-9a-f]{6,20})(?:&f_id=[0-9a-f]{6,20})?$/;

/**
 * The Mailchimp form action this build posts to, or null when it shows no form. A value that is
 * not a Mailchimp embedded-form action fails the build rather than shipping a form that posts
 * somewhere unexpected.
 *
 * @param {Readonly<Record<string, string | undefined>>} [env]
 * @returns {string | null}
 */
export function newsletterFormAction(env = process.env) {
  const action = (env.PUBLIC_MAILCHIMP_FORM_ACTION ?? '').trim();
  if (action === '') return null;
  if (!FORM_ACTION.test(action))
    throw new Error(
      'PUBLIC_MAILCHIMP_FORM_ACTION must be a Mailchimp embedded-form action such as ' +
        `https://example.us1.list-manage.com/subscribe/post?u=0123456789abcdef&id=abcdef1234, got "${action}".`,
    );
  return action;
}

/**
 * The name of Mailchimp's bot trap for a form action: a text field people never see and bots
 * fill in. Mailchimp rejects a sign-up whose trap is not empty.
 *
 * @param {string} action a value accepted by `newsletterFormAction`
 * @returns {string}
 */
export function newsletterTrapName(action) {
  const match = FORM_ACTION.exec(action);
  if (!match)
    throw new Error(`Not a Mailchimp embedded-form action: "${action}".`);
  return `b_${match[1]}_${match[2]}`;
}
