(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const header = $('.site-header');
  if (header) {
    const sectionLinks = [...header.querySelectorAll('[data-header-section]')]
      .map(link => ({ link, section: document.querySelector(link.getAttribute('href')) }))
      .filter(item => item.section);
    let headerFrame = null;
    const updateHeader = () => {
      headerFrame = null;
      const height = header.getBoundingClientRect().height;
      document.documentElement.style.setProperty('--header-offset', `${height + 16}px`);
      const readingLine = height + Math.min(120, Math.max(24, (window.innerHeight - height) * .2));
      const current = sectionLinks.find(({ section }) => {
        const bounds = section.getBoundingClientRect();
        return bounds.top <= readingLine && bounds.bottom > readingLine;
      });
      sectionLinks.forEach(item => {
        if (item === current) item.link.setAttribute('aria-current', 'location');
        else item.link.removeAttribute('aria-current');
      });
    };
    const scheduleHeader = () => {
      if (headerFrame === null) headerFrame = requestAnimationFrame(updateHeader);
    };
    window.addEventListener('scroll', scheduleHeader, { passive: true });
    window.addEventListener('resize', scheduleHeader);
    window.addEventListener('pageshow', scheduleHeader);
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(scheduleHeader).observe(header);
    updateHeader();
  }
  const carousel = $('.fleet-carousel');
  if (carousel) {
    const track = carousel.querySelector('.fleet-track');
    const slides = [...track.querySelectorAll('figure')];
    const dots = [...carousel.querySelectorAll('[data-fleet-slide]')];
    const count = carousel.querySelector('.fleet-count');
    let activeSlide = 0;
    let scrollFrame = null;
    slides.forEach((slide, index) => {
      slide.setAttribute('role', 'group');
      slide.setAttribute('aria-roledescription', 'diapositiva');
      slide.setAttribute('aria-label', `${index + 1} de ${slides.length}`);
    });
    const showSlide = index => {
      activeSlide = (index + slides.length) % slides.length;
      track.scrollTo({
        left: slides[activeSlide].offsetLeft - slides[0].offsetLeft,
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'
      });
    };
    const updatePosition = () => {
      scrollFrame = null;
      const nearest = slides.reduce((best, slide, index) =>
        Math.abs(slide.offsetLeft - slides[0].offsetLeft - track.scrollLeft) <
        Math.abs(slides[best].offsetLeft - slides[0].offsetLeft - track.scrollLeft) ? index : best, 0);
      activeSlide = nearest;
      dots.forEach((dot, index) => {
        if (index === nearest) dot.setAttribute('aria-current', 'true');
        else dot.removeAttribute('aria-current');
      });
      const label = `${nearest + 1} / ${slides.length}`;
      if (count.textContent !== label) count.textContent = label;
    };
    carousel.querySelector('[data-fleet-prev]').addEventListener('click', () => showSlide(activeSlide - 1));
    carousel.querySelector('[data-fleet-next]').addEventListener('click', () => showSlide(activeSlide + 1));
    dots.forEach((dot, index) => dot.addEventListener('click', () => showSlide(index)));
    track.addEventListener('keydown', event => {
      const targets = { ArrowLeft: activeSlide - 1, ArrowRight: activeSlide + 1, Home: 0, End: slides.length - 1 };
      if (!(event.key in targets)) return;
      event.preventDefault();
      showSlide(targets[event.key]);
    });
    track.addEventListener('scroll', () => {
      if (scrollFrame === null) scrollFrame = requestAnimationFrame(updatePosition);
    }, { passive: true });
    window.addEventListener('resize', updatePosition);
    carousel.querySelector('.fleet-controls').hidden = false;
    updatePosition();
  }
  const form = $('#quote-form');
  let whatsappNumber = '';
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Mexico_City', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const events = (event, properties = {}) => {
    // Consent-gated analytics consumes only the explicit fields allowed by analytics.js.
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({ event, ...properties });
    window.dispatchEvent(new CustomEvent('renpat:event', { detail: { event, ...properties } }));
  };
  if ($('#year')) $('#year').textContent = new Date().getFullYear();
  if ($('#date')) {
    $('#date').min = today;
    $('#date').max = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Mexico_City', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(Date.now() + 365 * 86400000));
  }

  let attribution = {};
  try {
    attribution = JSON.parse(sessionStorage.getItem('renpat_attribution') || 'null') || {};
    if (!Object.keys(attribution).length) {
      const params = new URLSearchParams(location.search);
      for (const key of ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']) {
        if (params.has(key)) attribution[key] = params.get(key).slice(0, 200);
      }
      if (document.referrer) attribution.referrer = new URL(document.referrer).hostname;
      if (!attribution.utm_source) attribution.utm_source = document.referrer ? 'referencia' : 'directo';
      sessionStorage.setItem('renpat_attribution', JSON.stringify(attribution));
    }
  } catch { attribution = {}; }

  fetch('/api/config').then(response => {
    if (!response.ok) throw new Error('Configuración no disponible');
    return response.json();
  }).then(config => {
    if (!config.prelaunch) {
      if ($('#launch-strip')) $('#launch-strip').hidden = true;
      // This first release uses a manual inbox; do not promise automatic delivery.
      if ($('#preview-notice')) $('#preview-notice').textContent = 'Tu solicitud se guarda para revisión manual. La tarifa y la disponibilidad se confirman antes de contratar.';
    }
    if (typeof config.whatsapp === 'string' && /^[1-9]\d{7,14}$/.test(config.whatsapp)) {
      whatsappNumber = config.whatsapp;
      document.querySelectorAll('[data-whatsapp-contact]').forEach(link => {
        link.href = `https://wa.me/${whatsappNumber}?text=${encodeURIComponent(link.dataset.contactMessage)}`;
        link.hidden = false;
        link.addEventListener('click', () => events('whatsapp_click', { section: 'header' }));
      });
      if ($('#contact-method-whatsapp')) $('#contact-method-whatsapp').disabled = false;
      document.querySelectorAll('.whatsapp-link').forEach(link => {
        link.href = '#quote-form'; link.hidden = false;
        link.addEventListener('click', () => {
          $('#contact-method-whatsapp').checked = true;
          updateContactMethod();
          $('#contact-method-whatsapp').focus();
        });
      });
    }
    if (form) updateContactMethod();
    if (config.contactEmail && $('#contact-email')) {
      const anchor = document.createElement('a');
      anchor.href = `mailto:${config.contactEmail}`; anchor.textContent = config.contactEmail;
      $('#contact-email').replaceChildren(anchor); $('#contact-email').hidden = false;
      anchor.addEventListener('click', () => events('email_click'));
    }
    if (config.privacyEmail && $('#privacy-contact')) {
      const anchor = document.createElement('a'); anchor.href = `mailto:${config.privacyEmail}`; anchor.textContent = config.privacyEmail;
      $('#privacy-contact').textContent = 'Para solicitar acceso, corrección, cancelación u oposición al tratamiento de tus datos, escribe a ';
      $('#privacy-contact').append(anchor, '. Incluye el folio de tu solicitud cuando lo tengas.');
    }
  }).catch(() => { if (form) updateContactMethod(); });

  document.querySelectorAll('[data-destination]').forEach(link => link.addEventListener('click', () => {
    $('#origin').value = 'Guadalajara';
    $('#destination').value = link.dataset.destination;
    events('route_interest', { route: link.dataset.destination });
  }));
  if (!form) return;
  let submissionId = crypto.randomUUID();
  let lastPayload = null;
  let sending = false;
  const status = $('#form-status');
  const button = form.querySelector('button[type=submit]');
  const whatsappChoice = $('#contact-method-whatsapp');
  const whatsappLink = $('#form-whatsapp-link');
  const updateContactMethod = () => {
    const useWhatsapp = whatsappChoice.checked && !!whatsappNumber;
    button.firstElementChild.textContent = sending ? 'Enviando…' : useWhatsapp ? 'Enviar y abrir WhatsApp' : 'Enviar solicitud';
    $('#contact-method-help').textContent = useWhatsapp
      ? 'También enviaremos tu solicitud y confirmación por correo. Se abrirá WhatsApp con tus datos; sólo tendrás que pulsar Enviar.'
      : whatsappNumber ? 'Enviaremos tu solicitud y confirmación por correo.' : 'Enviaremos tu solicitud y confirmación por correo. WhatsApp no está disponible en este momento.';
  };
  form.querySelectorAll('[name=contactMethod]').forEach(choice => choice.addEventListener('change', updateContactMethod));
  whatsappLink.addEventListener('click', () => events('whatsapp_click', { section: 'quote' }));
  const whatsappUrl = (data, reference) => {
    const message = [
      'Hola, me gustaría cotizar un envío con RENPAT Logistics.',
      `Folio: ${reference}`, `Nombre: ${data.name.trim()}`, `Empresa: ${data.company.trim()}`,
      `Teléfono: ${data.phone.trim()}`, `Correo: ${data.email.trim()}`,
      `Origen: ${data.origin}`, `Destino: ${data.destination}`, `Peso estimado: ${data.weight} kg`,
      `Fecha de recolección: ${data.date}`, ...(data.notes.trim() ? [`Detalles de la carga: ${data.notes.trim()}`] : [])
    ].join('\n');
    return `https://wa.me/${whatsappNumber}?text=${encodeURIComponent(message)}`;
  };
  const displayErrors = errors => {
    form.querySelectorAll('[aria-invalid]').forEach(field => field.removeAttribute('aria-invalid'));
    form.querySelectorAll('.field-error').forEach(field => { field.textContent = ''; });
    for (const [key, value] of Object.entries(errors)) {
      const field = form.elements.namedItem(key);
      const message = document.getElementById(`error-${key}`);
      if (field && message) { field.setAttribute('aria-invalid', 'true'); field.setAttribute('aria-describedby', `error-${key}`); message.textContent = value; }
    }
  };
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (sending) return;
    displayErrors({});
    status.textContent = ''; status.className = 'form-status';
    const data = Object.fromEntries(new FormData(form));
    const useWhatsapp = data.contactMethod === 'whatsapp';
    // The contact choice does not change the email payload or its retry key.
    delete data.contactMethod;
    data.weight = Number(data.weight);
    data.consent = $('#consent').checked;
    data.attribution = attribution;
    const errors = {};
    for (const field of form.querySelectorAll('[required]')) {
      if (!field.checkValidity()) errors[field.name] = field.type === 'checkbox' ? 'Autoriza el uso de tus datos para continuar.' : 'Completa este campo con un valor válido.';
    }
    if (!data.email?.trim() || !$('#email').checkValidity()) errors.email = 'Ingresa un correo válido para recibir la confirmación.';
    if (data.origin === data.destination && data.origin !== 'Otra ciudad') errors.destination = 'El destino debe ser diferente al origen.';
    if ((data.origin === 'Otra ciudad' || data.destination === 'Otra ciudad') && !data.notes.trim()) errors.notes = 'Indica la ciudad y los detalles de tu ruta.';
    if (useWhatsapp && !whatsappNumber) errors.contactMethod = 'WhatsApp no está disponible. Selecciona contacto por correo.';
    if (Object.keys(errors).length) {
      displayErrors(errors);
      status.className = 'form-status error'; status.textContent = errors.contactMethod || 'Revisa los campos indicados antes de enviar.';
      form.querySelector('[aria-invalid=true]')?.focus(); return;
    }
    // An unchanged retry keeps its key after a timeout; edited submissions get a fresh key.
    const payload = JSON.stringify(data);
    if (lastPayload && payload !== lastPayload) submissionId = crypto.randomUUID();
    lastPayload = payload;
    data.submissionId = submissionId;
    whatsappLink.hidden = true; whatsappLink.removeAttribute('href');
    // Reserve the tab during the user gesture, before waiting for the email API.
    let whatsappTab = null;
    if (useWhatsapp) {
      try {
        whatsappTab = window.open('about:blank', '_blank');
        if (whatsappTab) {
          whatsappTab.opener = null;
          whatsappTab.document.title = 'Preparando tu solicitud | RENPAT';
          whatsappTab.document.body.textContent = 'Estamos enviando tu solicitud por correo. WhatsApp se abrirá al terminar.';
        }
      } catch { /* The saved-request link also works when new tabs are blocked. */ }
    }
    sending = true; button.disabled = true; button.firstElementChild.textContent = 'Enviando…';
    try {
      const response = await fetch('/api/leads', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data), signal: AbortSignal.timeout(15000) });
      const result = await response.json();
      if (!response.ok) {
        displayErrors(result.errors || {});
        throw new Error(result.message || 'No pudimos guardar tu solicitud. Intenta de nuevo.');
      }
      status.className = 'form-status success';
      status.textContent = `Solicitud guardada. Tu folio es ${result.reference}. La tarifa y la disponibilidad todavía deben confirmarse.`;
      if (result.confirmationStatus === 'accepted') status.textContent += ' Enviamos la confirmación a tu correo; revisa también la carpeta de spam.';
      else if (result.confirmationStatus === 'pending' || result.confirmationStatus === 'sending') status.textContent += ' La confirmación por correo está pendiente de envío. Conserva tu folio para dar seguimiento.';
      if (response.status === 201 && result.reference !== 'RECIBIDO') events('quote_submitted', { eventId: data.submissionId });
      if (useWhatsapp && result.reference !== 'RECIBIDO') {
        const url = whatsappUrl(data, result.reference);
        whatsappLink.href = url; whatsappLink.hidden = false;
        let opened = false;
        try {
          if (whatsappTab && !whatsappTab.closed) {
            whatsappTab.location.replace(url); opened = true;
            events('whatsapp_click', { section: 'quote' });
          }
        } catch { /* Keep the email success and the manual WhatsApp link. */ }
        status.textContent += opened
          ? ' Abrimos WhatsApp con tu solicitud preparada. Pulsa Enviar para compartirla.'
          : ' Pulsa «Abrir WhatsApp con mi solicitud» para abrir el mensaje preparado y enviarlo.';
      } else if (whatsappTab && !whatsappTab.closed) whatsappTab.close();
      form.reset(); $('#origin').value = 'Guadalajara';
      submissionId = crypto.randomUUID(); lastPayload = null;
      status.focus();
    } catch (error) {
      try { if (whatsappTab && !whatsappTab.closed) whatsappTab.close(); } catch { /* The visitor may have closed the tab. */ }
      status.className = 'form-status error';
      status.textContent = error.name === 'TimeoutError' || error instanceof TypeError ? 'No pudimos confirmar el envío. Tus datos siguen en el formulario. Reintenta; evitaremos duplicar una solicitud ya guardada.' : error.message;
      status.focus();
    } finally {
      sending = false; button.disabled = false; updateContactMethod();
    }
  });
})();
