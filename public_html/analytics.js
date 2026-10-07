(() => {
  'use strict';
  const script = document.currentScript;
  const gaId = script?.dataset.gaId || '';
  const metaId = script?.dataset.metaId || '';
  const gaEnabled = /^G-[A-Z0-9]+$/.test(gaId);
  const metaEnabled = /^\d{5,30}$/.test(metaId);
  if (!gaEnabled && !metaEnabled) return;
  const $ = selector => document.querySelector(selector);
  if ($('#analytics-consent')) $('#analytics-consent').closest('label').hidden = !gaEnabled;
  if ($('#marketing-consent')) $('#marketing-consent').closest('label').hidden = !metaEnabled;
  const key = 'renpat_measurement_consent_v1';
  let consent = { analytics: false, marketing: false };
  let gaLoaded = false;
  let metaLoaded = false;
  const pageUrl = () => location.origin + location.pathname;
  const referrer = () => {
    try { return document.referrer ? new URL(document.referrer).origin + '/' : ''; }
    catch { return ''; }
  };
  const addScript = src => {
    const external = document.createElement('script'); external.async = true;
    external.src = src; document.head.append(external);
  };
  function gtag() { window.dataLayer = window.dataLayer || []; window.dataLayer.push(arguments); }
  const apply = () => {
    if (consent.analytics && gaEnabled && !gaLoaded) {
      gaLoaded = true;
      gtag('consent', 'default', { analytics_storage: 'granted', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied' });
      gtag('js', new Date());
      gtag('config', gaId, { send_page_view: false, allow_google_signals: false, allow_ad_personalization_signals: false });
      gtag('event', 'page_view', { send_to: gaId, page_location: pageUrl(), page_referrer: referrer(), page_title: document.title });
      addScript(`https://www.googletagmanager.com/gtag/js?id=${gaId}`);
    }
    if (consent.marketing && metaEnabled && !metaLoaded) {
      metaLoaded = true;
      const fbq = window.fbq = function () { if (fbq.callMethod) fbq.callMethod.apply(fbq, arguments); else fbq.queue.push(arguments); };
      fbq.push = fbq; fbq.loaded = true; fbq.version = '2.0'; fbq.queue = [];
      window._fbq = fbq;
      fbq('set', 'autoConfig', false, metaId);
      fbq('init', metaId);
      fbq('consent', 'grant');
      fbq('track', 'PageView');
      addScript('https://connect.facebook.net/en_US/fbevents.js');
    }
  };
  const removeMeasurementCookies = () => {
    for (const cookie of document.cookie.split(';')) {
      const name = cookie.split('=')[0].trim();
      if (!/^(_ga(?:_|$)|_gid$|_gat(?:_|$)|_fbp$|_fbc$)/.test(name)) continue;
      for (const domain of ['', location.hostname, '.' + location.hostname]) {
        document.cookie = `${name}=; Max-Age=0; Path=/; SameSite=Lax${domain ? '; Domain=' + domain : ''}`;
      }
    }
  };
  const save = next => {
    consent = next;
    try { localStorage.setItem(key, JSON.stringify({ ...consent, savedAt: Date.now() })); } catch { /* This visit still respects the choice. */ }
    if ($('#cookie-panel')) $('#cookie-panel').hidden = true;
    // Reload on withdrawal so scripts already loaded cannot continue collecting.
    if ((gaLoaded && !consent.analytics) || (metaLoaded && !consent.marketing)) {
      removeMeasurementCookies(); location.reload(); return;
    }
    apply();
  };
  try {
    const saved = JSON.parse(localStorage.getItem(key) || 'null');
    if (saved && Date.now() - saved.savedAt < 180 * 86400000) {
      consent = { analytics: saved.analytics === true, marketing: saved.marketing === true }; apply();
    } else if ($('#cookie-panel')) $('#cookie-panel').hidden = false;
  } catch { if ($('#cookie-panel')) $('#cookie-panel').hidden = false; }
  $('#cookies-reject')?.addEventListener('click', () => save({ analytics: false, marketing: false }));
  $('#cookies-accept')?.addEventListener('click', () => save({ analytics: gaEnabled, marketing: metaEnabled }));
  $('#cookies-customize')?.addEventListener('click', () => { $('#cookie-options').hidden = false; $('#cookies-save').hidden = false; $('#cookies-customize').hidden = true; });
  $('#cookies-save')?.addEventListener('click', () => save({ analytics: gaEnabled && $('#analytics-consent').checked, marketing: metaEnabled && $('#marketing-consent').checked }));
  $('#cookie-settings')?.addEventListener('click', () => {
    $('#analytics-consent').checked = consent.analytics; $('#marketing-consent').checked = consent.marketing;
    $('#cookie-panel').hidden = false; $('#cookie-options').hidden = false; $('#cookies-save').hidden = false; $('#cookies-customize').hidden = true;
    $('#cookies-reject').focus();
  });
  window.addEventListener('renpat:event', event => {
    const detail = event.detail || {};
    const names = { quote_submitted: 'generate_lead', route_interest: 'route_interest', email_click: 'email_click' };
    const name = names[detail.event];
    if (!name) return;
    // Explicit fields only: never forward form fields, folios, email addresses or free text.
    const params = { page_location: pageUrl(), page_referrer: referrer() };
    if (detail.event === 'quote_submitted') params.method = 'quote_form';
    if (detail.event === 'route_interest' && ['León', 'San Luis Potosí', 'Aguascalientes'].includes(detail.route)) params.route = detail.route;
    if (consent.analytics && gaLoaded) gtag('event', name, { ...params, send_to: gaId });
    if (detail.event === 'quote_submitted' && consent.marketing && metaLoaded) window.fbq('track', 'Lead', { content_name: 'Solicitud de cotización' }, { eventID: detail.eventId });
  });
})();
