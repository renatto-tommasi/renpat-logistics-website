'use strict';
// Run the production route-picker IIFE against a small event-capable DOM.
// No browser, network, backend calls, or copied implementation logic.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup() {
  const timers = [];
  function element(value = '') {
    const handlers = new Map();
    return {
      value, dataset: {}, options: [],
      addEventListener(type, listener) {
        if (!handlers.has(type)) handlers.set(type, []);
        handlers.get(type).push(listener);
      },
      dispatch(type) {
        const event = { target: this, preventDefault() {} };
        for (const listener of handlers.get(type) || []) listener(event);
      },
      focus() {}, scrollIntoView() {}
    };
  }
  const ids = {};
  for (const id of ['origin', 'destination', 'notes', 'date', 'weight', 'name', 'rp-origin', 'rp-destination', 'rp-date', 'quote-form']) ids['#' + id] = element();
  for (const id of ['#origin', '#destination']) {
    ids[id].options = ['', 'Guadalajara', 'León', 'Otra ciudad'].map(value => ({ value, text: value }));
  }
  ids['#origin'].value = ids['#rp-origin'].value = 'Guadalajara';
  const picker = element();
  picker.querySelector = selector => ids[selector] || null;
  const cards = [
    { destination: 'Otra ciudad', destinationNote: 'Morelia, Michoacán' },
    { destination: 'Otra ciudad', destinationNote: 'Querétaro, Querétaro' },
    { destination: 'León' }
  ].map(dataset => Object.assign(element(), { dataset }));
  // app.js's earlier, unchanged handler runs first for every destination card.
  for (const card of cards) card.addEventListener('click', () => {
    ids['#origin'].value = 'Guadalajara';
    ids['#destination'].value = card.dataset.destination;
  });
  const document = {
    querySelector(selector) { return selector === '[data-route-picker]' ? picker : ids[selector] || null; },
    querySelectorAll(selector) {
      if (selector === '[data-destination-note]') return cards.filter(card => card.dataset.destinationNote);
      if (selector === '[data-destination]') return cards;
      return [];
    }
  };
  const source = fs.readFileSync(path.join(__dirname, '../public_html/app.js'), 'utf8');
  const marker = source.indexOf('/* Escena del mapa:');
  assert(marker >= 0, 'Production route-picker IIFE marker must exist');
  vm.runInNewContext(source.slice(marker), {
    document, window: { matchMedia: () => ({ matches: true }) },
    setTimeout: callback => { timers.push(callback); return timers.length; }, clearTimeout() {}
  }, { filename: 'production-route-picker.js' });
  const flush = () => { while (timers.length) timers.shift()(); };
  return {
    ids,
    choose(city) { ids['#rp-destination'].value = city; picker.dispatch('submit'); flush(); },
    card(index) { cards[index].dispatch('click'); flush(); },
    changeDestination(city) { ids['#destination'].value = city; ids['#destination'].dispatch('change'); flush(); },
    reset() {
      ids['#quote-form'].dispatch('reset');
      ids['#notes'].value = ''; ids['#destination'].value = '';
      flush();
    }
  };
}

const cases = {
  existing_cargo() {
    const app = setup();
    const cargo = 'Tres pallets de alimentos\nEntregar por la mañana.';
    app.ids['#notes'].value = cargo;
    app.choose('Morelia');
    assert.equal(app.ids['#destination'].value, 'Otra ciudad');
    assert(app.ids['#notes'].value.startsWith('Destino: Morelia.'), 'Selected unsupported city must precede cargo notes');
    assert(app.ids['#notes'].value.endsWith(cargo), 'Existing cargo notes must remain unchanged');
  },
  replace_city() {
    const app = setup(); const cargo = 'Tres pallets de alimentos';
    app.ids['#notes'].value = cargo;
    app.choose('Morelia'); app.choose('Querétaro');
    assert(app.ids['#notes'].value.startsWith('Destino: Querétaro.'));
    assert(!app.ids['#notes'].value.includes('Morelia'));
    assert(app.ids['#notes'].value.endsWith(cargo));
  },
  supported_city() {
    const app = setup(); const cargo = '  Cajas frágiles\nNo apilar.  ';
    app.ids['#notes'].value = cargo;
    app.choose('Morelia'); app.choose('León');
    assert.equal(app.ids['#destination'].value, 'León');
    assert.equal(app.ids['#notes'].value, cargo, 'Remove only the generated city, preserving user whitespace');
  },
  card_city() {
    const app = setup(); const cargo = 'Dos tarimas';
    app.ids['#notes'].value = cargo;
    app.card(0); app.card(1);
    assert(app.ids['#notes'].value.startsWith('Destino: Querétaro, Querétaro.'));
    assert(!app.ids['#notes'].value.includes('Morelia'));
    assert(app.ids['#notes'].value.endsWith(cargo));
    assert.equal(app.ids['#destination'].value, 'Otra ciudad');
  },
  repeat_card() {
    const app = setup(); app.ids['#notes'].value = 'Dos tarimas';
    app.card(0); const once = app.ids['#notes'].value; app.card(0);
    assert(once.startsWith('Destino: Morelia, Michoacán.'));
    assert.equal(app.ids['#notes'].value, once, 'Repeated clicks must not duplicate city notes');
  },
  supported_card() {
    const app = setup(); const cargo = 'Dos tarimas';
    app.ids['#notes'].value = cargo; app.card(0); app.card(2);
    assert.equal(app.ids['#destination'].value, 'León');
    assert.equal(app.ids['#notes'].value, cargo);
  },
  manual_destination() {
    const app = setup(); const cargo = 'Dos tarimas';
    app.ids['#notes'].value = cargo; app.choose('Morelia'); app.changeDestination('León');
    assert.equal(app.ids['#notes'].value, cargo);
  },
  reset_state() {
    const app = setup(); app.choose('Morelia'); app.reset();
    // A new request may contain user-authored text matching an old generated line.
    const userNotes = 'Destino: Morelia.\nEsta línea fue escrita por el cliente.';
    app.ids['#notes'].value = userNotes; app.choose('Querétaro');
    assert(app.ids['#notes'].value.startsWith('Destino: Querétaro.'));
    assert(app.ids['#notes'].value.endsWith(userNotes), 'Reset must clear prior generated-line tracking');
  },
  edited_generated_note() {
    const app = setup(); app.choose('Morelia');
    const edited = 'Destino: Morelia, almacén norte.\nCajas frágiles.';
    app.ids['#notes'].value = edited; app.choose('Querétaro');
    assert(app.ids['#notes'].value.startsWith('Destino: Querétaro.'));
    assert(app.ids['#notes'].value.endsWith(edited), 'An edited generated note is user content and must be preserved');
  },
  preserve_manual_notes() {
    const app = setup();
    const cargo = 'Destino: almacén del cliente.\nConservar estas instrucciones.';
    app.ids['#notes'].value = cargo; app.choose('Morelia'); app.choose('León');
    assert.equal(app.ids['#notes'].value, cargo, 'User-authored destination lines must never be stripped');
  }
};
const name = process.argv[2];
assert(Object.hasOwn(cases, name), `Unknown case: ${name}`);
cases[name]();
console.log(`PASS ${name}`);
