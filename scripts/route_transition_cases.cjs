'use strict';
// Exercise the production map-scene controller, not a copied animation model.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function setup({ reduced = false, width = 1280, height = 900, scrollWidth = 1700, empty = false } = {}) {
  const frames = [], timers = [];
  const listeners = new Map();
  function element({ left = 0, top = 0, width = 236, height = 86 } = {}) {
    const handlers = new Map(), classes = new Set();
    const style = { setProperty(k,v) { this[k] = String(v); }, removeProperty(k) { delete this[k]; }, getPropertyValue(k) { return this[k] || ''; } };
    return { style, dataset: {}, clientWidth: width, clientHeight: height, offsetWidth: width, offsetHeight: height, offsetLeft: left, offsetTop: top,
      classList: { add: k => classes.add(k), remove: k => classes.delete(k), contains: k => classes.has(k), toggle(k,on) { if(on) classes.add(k); else classes.delete(k); } },
      addEventListener(k, fn) { handlers.set(k, fn); }, dispatch(k,event) { handlers.get(k)?.(event); },
      getBoundingClientRect() { return { left, top, width, height, right:left+width,bottom:top+height }; },
      querySelector() { return null; }, querySelectorAll() { return []; },
      setAttribute(k,v) { this[k] = v; }, removeAttribute(k) { delete this[k]; },
      matches() { return true; }, contains(el) { return el === this; }
    };
  }
  const scene = element(), sticky = element({width,height}), stage = element();
  const rail = element({width,height:184}), track = element({width:scrollWidth,height:184});
  track.scrollWidth = scrollWidth;
  const anchor = element(), hero = element({height:360}), heading = element({height:64}), panel = element();
  const cards = empty ? [] : [0,248,496,744,992,124,372,620,868,1240].map((left,i) => {
    const card = element({left}); card.dataset = {routeChapter:`city${i}`,routeState:`state${i}`,routeRegion:`Region ${i}`};
    // Deliberately bogus offsetLeft: nested rows do not share track's offset parent.
    card.offsetLeft = i === 5 ? 0 : left;
    return card;
  });
  track.querySelectorAll = () => cards;
  track.contains = el => cards.includes(el);
  const refs = {'[data-scene-sticky]':sticky,'[data-map-stage]':stage,'.rail':rail,'[data-rail-track]':track,'.scene-anchor':anchor,'.hero-copy':hero,'.routes-head':heading,'.routes-panel':panel};
  scene.querySelector = selector => refs[selector] || null;
  const mediaHandlers=[];
  const media = {matches:reduced, addEventListener(k,fn){mediaHandlers.push(fn);},addListener(fn){mediaHandlers.push(fn);}};
  const scrolls = [];
  const window = {innerWidth:width,innerHeight:height,scrollY:0,matchMedia:()=>media,
    addEventListener(k,fn) { listeners.set(k,fn); },
    scrollTo(options) { scrolls.push(options); window.scrollY=options.top; },
    visualViewport: {height,addEventListener(){}},
    IntersectionObserver: class {observe(){} disconnect(){}}
  };
  scene.getBoundingClientRect = () => ({top:1000-window.scrollY,left:0,width,height});
  const document = {querySelector: selector => selector==='[data-scene]' ? scene : null,querySelectorAll:()=>[],documentElement:element({width,height})};
  const source = fs.readFileSync(path.join(__dirname,'../public_html/app.js'),'utf8');
  const start = source.indexOf('/* Escena del mapa:');
  assert(start>=0,'Production map-scene marker must exist');
  const raf=fn=>{frames.push(fn);return frames.length;};
  vm.runInNewContext(source.slice(start),{window,document,getComputedStyle:el=>({paddingLeft:'36px',paddingRight:'36px',getPropertyValue:k=>k==='--header-offset'?'84px':el.style.getPropertyValue(k)}),
    requestAnimationFrame:raf,cancelAnimationFrame(){},setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout(){},
    IntersectionObserver:window.IntersectionObserver,performance:{now:()=>0},ResizeObserver:class{observe(){}},console
  },{filename:'production-map-scene.js'});
  function flush(){for(let i=0;frames.length && i<20;i++)frames.shift()(2000);assert(frames.length<1,'Animation frame queue must settle');}
  function scroll(y){window.scrollY=y;listeners.get('scroll')?.();flush();}
  return {scene,sticky,rail,track,anchor,hero,heading,panel,cards,scrolls,window,media,scroll,flush,
    focus(i,keyboard=true){const card=cards[i];track.dispatch('focusin',{target:{closest:()=>card,matches:()=>keyboard}});flush();},
    setReduced(matches){media.matches=matches;mediaHandlers.forEach(fn=>fn({matches}));flush();},
    resize(){listeners.get('resize')?.();while(timers.length)timers.shift()();flush();},
    intro(){return parseFloat(anchor.style.top) - 84;},number(k){return parseFloat(sticky.style[k]);}};
}
const cases = {
  motion_change(){const s=setup();s.scroll(1000+s.intro());assert.equal(s.hero.inert,true);s.setReduced(true);assert(!s.scene.classList.contains('is-live'));assert(!s.scene.style.height);assert.equal(s.hero.inert,false);assert.equal(s.panel.inert,false);s.setReduced(false);assert(s.scene.classList.contains('is-live'));assert(s.scene.style.height);},
  interaction_gating(){const s=setup();s.scroll(1000);assert.equal(s.hero.inert,false);assert.equal(s.panel.inert,true);s.scroll(1000+s.intro());assert.equal(s.hero.inert,true);assert.equal(s.panel.inert,false);s.scroll(1000);assert.equal(s.hero.inert,false);assert.equal(s.panel.inert,true);},
  measured_heading(){const s=setup({width:375,height:800});const before=parseFloat(s.sticky.style['--routes-rail-top']);s.heading.offsetHeight+=50;s.resize();assert.equal(parseFloat(s.sticky.style['--routes-rail-top']),before+50,'Rail placement follows rendered heading height');},
  staged_reveal(){const s=setup(), intro=s.intro();s.scroll(1000);assert.equal(s.number('--hero-out'),0);assert.equal(s.number('--routes-in'),0);s.scroll(1000+intro*.3);assert(s.number('--hero-out')>0);assert.equal(s.number('--routes-in'),0);s.scroll(1000+intro*.7);assert.equal(s.number('--hero-out'),1);assert(s.number('--routes-in')>0);assert.equal(s.number('--x'),0);s.scroll(1000+intro*.96);assert.equal(s.number('--routes-in'),1);assert.equal(s.number('--x'),0);s.scroll(1000+intro+100);assert(s.number('--x')>0);},
  scroll_clamps(){const s=setup();s.scroll(-100);assert.equal(s.number('--x'),0);assert.equal(s.number('--hero-out'),0);s.scroll(100000);assert.equal(s.number('--p'),1);const x=s.number('--x');s.scroll(200000);assert.equal(s.number('--x'),x);s.scroll(1000);assert.equal(s.number('--routes-in'),0);assert.equal(s.number('--x'),0);},
  focus_geometry(){const s=setup();s.focus(5);const rowStart=s.scrolls.at(-1).top;s.focus(4);assert(s.scrolls.at(-1).top>rowStart,'Second-row first card precedes first-row last card spatially');assert(rowStart<=1000+s.intro()+10,'Early staggered card must not jump to DOM-index fraction of rail');s.focus(9);assert(s.scrolls.at(-1).top>rowStart);},
  pointer_focus(){const s=setup();s.focus(4,false);assert.equal(s.scrolls.length,0,'Pointer focus must not unexpectedly move the page');},
  reduced_motion(){const s=setup({reduced:true});assert(!s.scene.classList.contains('is-live'));assert(!s.scene.style.height);s.focus(4);assert.equal(s.scrolls.length,0);s.scroll(2000);assert(!s.scene.classList.contains('is-live'));},
  no_overflow(){const s=setup({scrollWidth:500});s.scroll(100000);assert.equal(s.number('--x'),0);assert.equal(s.number('--p'),0);assert(!String(s.scene.style.height).includes('NaN'));},
  empty_cards(){const s=setup({empty:true});s.scroll(100000);s.resize();assert(!String(s.scene.style.height).includes('NaN'));},
  small_viewport(){const s=setup({width:375,height:300});assert(!s.scene.classList.contains('is-live'),'Viewport too small for content should use native stacked layout');assert(!s.scene.style.height);},
  resize(){const s=setup();s.window.innerWidth=375;s.window.innerHeight=750;s.sticky.clientHeight=750;s.rail.clientWidth=375;s.resize();s.scroll(1000+s.intro());assert.equal(s.number('--routes-in'),1);assert(Number.isFinite(s.number('--x')));}
};
const name=process.argv[2];assert(cases[name],`Unknown case: ${name}`);cases[name]();
