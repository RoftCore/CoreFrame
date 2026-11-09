// ── Demand-driven widget refresh ─────────────────────────────────
// One scheduler for every core-owned widget instead of one setInterval each.
// Rules: only widgets in the viewport are fetched; nothing is fetched while the
// window is hidden; an untouched card decays to a slow lane; a card that scrolls
// back into view refreshes on the spot, so it never shows stale data for long.

const cfPollRegistry = {};   // "ext|widgetId" -> entry
const cfPollExt = {};        // extId -> [key], so a touch/visibility change is O(card)
const cfWidgetEls = {};      // "ext|widgetId" -> element (hot paths never query the DOM)
const cfCardEls = {};        // extId -> card element

let cfPollTimer = null;
let cfPollActive = 0;        // refreshes the scheduler has started and not seen settle
let cfPollIO = null;

const CF_POLL_PARALLEL = 4;          // concurrent fetches from the scheduler
const CF_POLL_MARGIN = '400px';      // prefetch band around the viewport
const CF_POLL_MARGIN_PX = 400;       // same band, for the rect fallback
const CF_POLL_STAGGER_MS = 15;       // spread of a resumed wave
const CF_POLL_STAGGER_MAX_MS = 400;
const CF_POLL_IDLE_AFTER_MS = 60000; // untouched this long on screen -> slow lane
const CF_POLL_IDLE_FACTOR = 4;       // slow lane = cadence * factor...
const CF_POLL_IDLE_MIN_MS = 15000;   // ...never faster than this...
const CF_POLL_IDLE_MAX_MS = 60000;   // ...and never slower than this

// Visibility from geometry, not from the observer.
// An IntersectionObserver only queues an entry when the target's intersection is
// computed, and Chromium skips that computation while the window is occluded or
// before the first render. Connecting an observer and disconnecting it in the same
// task (cfPollReset did exactly that) leaves every later observe() silently dead:
// measured on 2026-11-05 the poller reported hot=0 for twenty cards, including
// seven in plain view, so cfPollGate refused every fetch and the cards sat on "--"
// until the page was forced to re-observe. The rect is authoritative and costs one
// layout for the whole batch; the observer stays as the fast path.
function cfPollVisible(card) {
  if (!card || !card.isConnected) return false;
  const r = card.getBoundingClientRect();
  if (!r.width && !r.height) return false;
  return r.bottom > -CF_POLL_MARGIN_PX && r.top < window.innerHeight + CF_POLL_MARGIN_PX &&
         r.right > -CF_POLL_MARGIN_PX && r.left < window.innerWidth + CF_POLL_MARGIN_PX;
}

function cfPollKey(extId, widgetId) { return extId + '|' + widgetId; }

// ── Element index ────────────────────────────────────────────────

function cfPollElement(extId, widgetId) {
  const key = cfPollKey(extId, widgetId);
  let el = cfWidgetEls[key];
  if (el && el.isConnected) return el;
  el = document.querySelector('[data-widget-id="' + widgetId + '"][data-ext-id="' + extId + '"]');
  if (el) cfWidgetEls[key] = el; else delete cfWidgetEls[key];
  return el;
}

function cfPollIndexCard(card) {
  if (!card) return;
  const extId = card.dataset.extId;
  if (!extId) return;
  cfCardEls[extId] = card;
  const nodes = card.querySelectorAll('[data-widget-id]');
  for (let i = 0; i < nodes.length; i++) {
    const id = nodes[i].dataset.widgetId;
    if (id) cfWidgetEls[cfPollKey(extId, id)] = nodes[i];
  }
}

function cfPollCard(extId) {
  let card = cfCardEls[extId];
  if (card && card.isConnected) return card;
  card = document.querySelector('.widget-extension.ext-' + extId);
  if (card) cfCardEls[extId] = card;
  return card;
}

// ── Registry ─────────────────────────────────────────────────────

function cfPollEffectiveEvery(e) {
  if (e.every <= 0) return 0;
  const idle = (Date.now() - (e.touched || 0)) > CF_POLL_IDLE_AFTER_MS;
  if (!idle) return e.every;
  return Math.min(CF_POLL_IDLE_MAX_MS, Math.max(e.every * CF_POLL_IDLE_FACTOR, CF_POLL_IDLE_MIN_MS));
}

function cfPollAdd(extId, ext, wDef) {
  const key = cfPollKey(extId, wDef.id);
  let e = cfPollRegistry[key];
  if (!e) {
    e = cfPollRegistry[key] = { extId: extId, wDef: wDef, hot: false, nextAt: 0, lastAt: 0, touched: 0, fired: false };
    (cfPollExt[extId] = cfPollExt[extId] || []).push(key);
  }
  e.wDef = wDef;
  // Realtime widgets are pushed by the socket: an HTTP poll on top is pure waste.
  e.every = ext.realtime === true ? 0 : cfRefreshInterval(ext);
  e.once = ext.realtime !== true && e.every <= 0;
  e.fired = false;
  e.nextAt = 0;
  return e;
}

function cfPollDropExtension(extId) {
  const keys = cfPollExt[extId] || [];
  for (let i = 0; i < keys.length; i++) {
    delete cfPollRegistry[keys[i]];
    delete cfWidgetEls[keys[i]];
  }
  delete cfPollExt[extId];
  delete cfCardEls[extId];
}

function cfPollObserve(extId) {
  const io = cfPollObserver();
  const card = cfPollCard(extId);
  if (card) {
    if (io) { try { io.observe(card); } catch (e) {} }
    // Never wait for the observer's first entry: it may never come (see cfPollVisible).
    cfPollSetHot(extId, cfPollVisible(card));
  }
}

function cfPollAddExtension(extId, ext) {
  if (!ext || ext.disabled) return;
  if (!cfCoreOwnsWidgets(ext, extId)) { cfPollDropExtension(extId); return; }
  cfPollDropExtension(extId);
  for (const wDef of (ext.widgets || [])) cfPollAdd(extId, ext, wDef);
  cfPollIndexCard(cfPollCard(extId));
  cfPollObserve(extId);
  cfPollArm();
}

function cfPollRegisterAll(data) {
  cfPollReset();
  for (const [extId, ext] of Object.entries(data || {})) {
    if (ext.disabled) continue;
    if (!cfCoreOwnsWidgets(ext, extId)) continue;
    for (const wDef of (ext.widgets || [])) cfPollAdd(extId, ext, wDef);
    cfPollIndexCard(cfPollCard(extId));
    cfPollObserve(extId);
  }
  cfPollArm();
}

function cfPollReset() {
  for (const k in cfPollRegistry) delete cfPollRegistry[k];
  for (const k in cfPollExt) delete cfPollExt[k];
  for (const k in cfWidgetEls) delete cfWidgetEls[k];
  for (const k in cfCardEls) delete cfCardEls[k];
  if (cfPollTimer) { clearTimeout(cfPollTimer); cfPollTimer = null; }
  // Drop the reference as well as the targets. A disconnected observer that is
  // kept alive and re-observed never delivers again, and cfPollObserver() would
  // hand that corpse to every later caller.
  if (cfPollIO) { try { cfPollIO.disconnect(); } catch (e) {} cfPollIO = null; }
}

// ── Viewport tracking ────────────────────────────────────────────

function cfPollSetHot(extId, hot) {
  const keys = cfPollExt[extId] || [];
  let now = 0;
  for (let i = 0; i < keys.length; i++) {
    const e = cfPollRegistry[keys[i]];
    if (!e) continue;
    const was = e.hot;
    e.hot = !!hot;
    if (hot && !was) {
      now = now || Date.now();
      // Entering the viewport is the moment to be correct, not five seconds later.
      e.nextAt = now;
      cfPollFlushPending(e);
    }
  }
}

// A realtime value that arrived while the card was off screen is applied on arrival,
// instead of being written into an unseen DOM a thousand times.
// Returns true when the poller took the value, false when the caller should apply it now.
function cfPollStore(extId, widgetId, value) {
  const e = cfPollRegistry[cfPollKey(extId, widgetId)];
  if (!e) return false;
  if (e.hot) return false;
  e.pendingValue = value;
  return true;
}

function cfPollFlushPending(e) {
  if (e.pendingValue === undefined) return;
  const value = e.pendingValue;
  e.pendingValue = undefined;
  const el = cfPollElement(e.extId, e.wDef.id);
  if (!el) return;
  try { updateWidgetValue(el, { value: value }); } catch (err) {}
}

function cfPollObserver() {
  if (cfPollIO || typeof IntersectionObserver === 'undefined') return cfPollIO;
  cfPollIO = new IntersectionObserver(function (entries) {
    let woke = false;
    for (let i = 0; i < entries.length; i++) {
      const extId = entries[i].target.dataset.extId;
      if (!extId) continue;
      cfPollSetHot(extId, entries[i].isIntersecting);
      if (entries[i].isIntersecting) woke = true;
    }
    if (woke) cfPollArm();
  }, { rootMargin: CF_POLL_MARGIN, threshold: 0 });
  return cfPollIO;
}

// ── Idle freeze ──────────────────────────────────────────────────
// A card out of view keeps its box tree (so decoded images survive) but has no
// reason to keep its CSS animations ticking: the compositor still advances them
// for a subtree nobody can see. Removing the class resumes from the same frame,
// so waking costs nothing and nothing jumps.
let cfIdleIO = null;

function cfIdleObserver() {
  if (cfIdleIO || typeof IntersectionObserver === 'undefined') return cfIdleIO;
  cfIdleIO = new IntersectionObserver(function (entries) {
    for (let i = 0; i < entries.length; i++) {
      const card = entries[i].target;
      if (!card) continue;
      if (entries[i].isIntersecting) card.classList.remove('cf-idle');
      else card.classList.add('cf-idle');
    }
  }, { rootMargin: '100% 0px 100% 0px', threshold: 0 });
  return cfIdleIO;
}

// Watches every card, not only the ones the scheduler owns: the heavy
// JS-painted extensions are exactly the ones with animations worth freezing.
// Same trap as the poller: apply the class from geometry at once, because an
// observer whose first entry never arrives would leave a visible card paused.
function cfIdleApply(card) {
  if (!card || !card.isConnected) return;
  const r = card.getBoundingClientRect();
  if (!r.width && !r.height) return;
  const m = window.innerHeight;   // matches the observer's 100% vertical margin
  const near = r.bottom > -m && r.top < window.innerHeight + m &&
               r.right > 0 && r.left < window.innerWidth;
  if (near) card.classList.remove('cf-idle');
  else card.classList.add('cf-idle');
}

function cfIdleObserve(card) {
  if (!card) return;
  const io = cfIdleObserver();
  if (io) { try { io.observe(card); } catch (e) {} }
  cfIdleApply(card);
}

// ── Scheduler ────────────────────────────────────────────────────

function cfPollArm() {
  if (cfPollTimer) { clearTimeout(cfPollTimer); cfPollTimer = null; }
  if (document.hidden) return;
  const now = Date.now();
  let next = Infinity;
  let due = false;
  for (const key in cfPollRegistry) {
    const e = cfPollRegistry[key];
    if (!e.hot) continue;
    if (e.once && e.fired) continue;
    if (e.nextAt <= now || (e.once && !e.fired)) { due = true; continue; }
    if (e.nextAt < next) next = e.nextAt;
  }
  if (due && cfPollActive < CF_POLL_PARALLEL) { cfPollTimer = setTimeout(cfPollRun, 16); return; }
  if (next < Infinity) cfPollTimer = setTimeout(cfPollRun, Math.max(16, Math.min(next - now, 5000)));
}

function cfPollRun() {
  cfPollTimer = null;
  if (document.hidden) return;
  const now = Date.now();
  for (const key in cfPollRegistry) {
    if (cfPollActive >= CF_POLL_PARALLEL) break;
    const e = cfPollRegistry[key];
    if (!e.hot) continue;
    if (e.nextAt > now && !(e.once && !e.fired)) continue;
    if (e.once && e.fired) continue;
    cfPollFire(e);
  }
  cfPollArm();
}

function cfPollFire(e) {
  const started = Date.now();
  e.lastAt = started;
  if (e.once) e.fired = true;
  const cadence = e.once ? 0 : cfPollEffectiveEvery(e);
  // Jitter keeps a resumed wave from landing on the same millisecond.
  e.nextAt = cadence > 0 ? started + cadence + Math.floor(Math.random() * 120) : Infinity;
  cfPollActive++;
  Promise.resolve()
    .then(function () { return refreshWidget(e.extId, e.wDef); })
    .catch(function () {})
    .then(function () {
      cfPollActive = Math.max(0, cfPollActive - 1);
      cfPollArm();
    });
}

// ── Entry points used by the rest of the app ─────────────────────

// Called after the grid is rebuilt.
function cfPollRebuild(data) {
  // cfPollRegisterAll resets (and drops) the current observer, so creating one
  // here would only be disconnected in the same task - the exact poison.
  cfPollRegisterAll(data);
}

// First fetch for an extension, at the cadence its manifest asks for.
function cfPollPrime(extId, ext) {
  if (ext) cfPollAddExtension(extId, ext);
  const keys = cfPollExt[extId] || [];
  const now = Date.now();
  for (let i = 0; i < keys.length; i++) {
    const e = cfPollRegistry[keys[i]];
    if (!e) continue;
    e.nextAt = now;
    e.touched = now;
  }
  cfPollArm();
}

// Scene switch: everything in the new scene is stale, but only what is on
// screen actually fires. Replaces the old per-widget loop that fired N fetches.
function cfPollInvalidateScene(ids) {
  const now = Date.now();
  for (let i = 0; i < (ids || []).length; i++) {
    const extId = ids[i];
    // The cards were just revealed: settle their visibility from geometry before
    // deciding, so a dead observer cannot leave a visible card cold on a switch.
    const card = cfPollCard(extId);
    if (card) cfPollSetHot(extId, cfPollVisible(card));
    const keys = cfPollExt[extId] || [];
    for (let j = 0; j < keys.length; j++) {
      const e = cfPollRegistry[keys[j]];
      if (!e) continue;
      e.touched = 0;            // back to full cadence
      if (e.hot) e.nextAt = 0;
      else if (e.once) { /* one-shot cards refresh when they scroll in */ }
    }
  }
  cfPollArm();
}

// Socket came back: the push gap is invisible only if we ask once.
function cfPollRefreshHot() {
  const now = Date.now();
  for (const key in cfPollRegistry) {
    const e = cfPollRegistry[key];
    if (e.hot && !(e.once && e.fired)) e.nextAt = now;
  }
  cfPollArm();
}

// Gate used by refreshWidget: an off-screen card must not cost a request.
function cfPollGate(extId, widgetId) {
  const e = cfPollRegistry[cfPollKey(extId, widgetId)];
  if (!e) return true;            // not scheduler-owned: never block a direct caller
  if (document.hidden) return false;
  return !!e.hot;
}

function cfPollNoteFetched(extId, widgetId) {
  const e = cfPollRegistry[cfPollKey(extId, widgetId)];
  if (e) e.lastAt = Date.now();
}

// Interaction restores the full cadence, and refreshes a card that had gone quiet.
function cfPollTouch(extId) {
  if (!extId) return;
  const keys = cfPollExt[extId] || [];
  const now = Date.now();
  let stale = false;
  for (let i = 0; i < keys.length; i++) {
    const e = cfPollRegistry[keys[i]];
    if (!e) continue;
    e.touched = now;
    if (!e.hot || (e.once && e.fired)) continue;
    if (now - e.lastAt >= cfPollEffectiveEvery(e)) { e.nextAt = 0; stale = true; }
  }
  if (stale) cfPollArm();
}

function cfPollTouchFrom(target) {
  const card = target && target.closest ? target.closest('.widget-extension') : null;
  if (card) cfPollTouch(card.dataset.extId);
}

document.addEventListener('pointerover', function (ev) { cfPollTouchFrom(ev.target); }, { passive: true });
document.addEventListener('pointerdown', function (ev) { cfPollTouchFrom(ev.target); }, { passive: true });
document.addEventListener('focusin', function (ev) { cfPollTouchFrom(ev.target); }, { passive: true });

// A hidden window runs no JS and paints nothing: stop the clock entirely.
document.addEventListener('visibilitychange', function () {
  if (document.hidden) {
    if (cfPollTimer) { clearTimeout(cfPollTimer); cfPollTimer = null; }
    return;
  }
  let i = 0;
  const now = Date.now();
  for (const key in cfPollRegistry) {
    const e = cfPollRegistry[key];
    if (!e.hot || (e.once && e.fired)) continue;
    e.nextAt = now + Math.min(i++ * CF_POLL_STAGGER_MS, CF_POLL_STAGGER_MAX_MS);
  }
  cfPollArm();
  cfPollRecheck();
});

// Re-settle visibility from geometry. A resize, a restore or a scene switch can
// change what is on screen while the observers stay silent; this is the path that
// does not depend on them. Debounced: a drag-resize fires dozens of times.
let cfPollRecheckTimer = null;
function cfPollRecheck() {
  if (cfPollRecheckTimer) clearTimeout(cfPollRecheckTimer);
  cfPollRecheckTimer = setTimeout(function () {
    cfPollRecheckTimer = null;
    // Read every rect before writing anything: cfPollSetHot may flush a pending
    // socket value into the DOM, and interleaving writes with reads would force a
    // reflow per card.
    const plan = [];
    for (const extId in cfPollExt) {
      const card = cfPollCard(extId);
      if (card) plan.push([extId, cfPollVisible(card)]);
    }
    for (let i = 0; i < plan.length; i++) cfPollSetHot(plan[i][0], plan[i][1]);
    const cards = document.querySelectorAll('.widget-extension');
    const near = [];
    for (let i = 0; i < cards.length; i++) {
      const r = cards[i].getBoundingClientRect();
      const m = window.innerHeight;
      near.push(!!r.width && r.bottom > -m && r.top < window.innerHeight + m && r.right > 0 && r.left < window.innerWidth);
    }
    for (let i = 0; i < cards.length; i++) {
      if (near[i]) cards[i].classList.remove('cf-idle');
      else cards[i].classList.add('cf-idle');
    }
    cfPollArm();
  }, 200);
}

window.addEventListener('resize', cfPollRecheck, { passive: true });

// Diagnostics: /api/debug/pollers is server side; this is the client mirror.
window.cfPollStats = function () {
  const out = { widgets: 0, hot: 0, active: cfPollActive, timers: cfPollTimer ? 1 : 0 };
  for (const key in cfPollRegistry) {
    out.widgets++;
    if (cfPollRegistry[key].hot) out.hot++;
  }
  return out;
};
