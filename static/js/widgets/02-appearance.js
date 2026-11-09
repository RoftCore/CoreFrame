const EXT_DEFAULT_GRID = { w: 4, h: 2 };

/* Appearance animations, owned by the host: an extension may name one in
   extension.json ("appear_animation") but cannot add its own, so the grid stays
   consistent. */
const CF_APPEAR_DEFAULT = 'fill-center';
// Per-card offset so a full dashboard cascades instead of landing in one frame.
const CF_APPEAR_STAGGER_MS = 32;
// Cards past this point of a grid build do not animate: they are off screen.
const CF_APPEAR_MAX_ANIMATED = 48;
// A skeleton must be readable; extensions that finish in ~150ms would otherwise replace it in a frame.
const CF_PLACEHOLDER_MIN_MS = 450;
const CF_APPEAR_ANIMATIONS = {
  fill: 'cf-anim-fill',
  'fill-center': 'cf-anim-fill-center',
  rise: 'cf-anim-rise',
  unfold: 'cf-anim-unfold',
  fade: 'cf-anim-fade',
  none: 'cf-anim-none',
};

// Entrance budget: how many cards of a grid build may animate. Reset before the
// build, released afterwards so a card that arrives later still animates.
let cfAppearBudget = -1;
function cfAppearReset() { cfAppearBudget = CF_APPEAR_MAX_ANIMATED; }
function cfAppearEnd() { cfAppearBudget = -1; }

function cfApplyAppearAnimation(el, ext) {
  if (!el || el.dataset.cfAppeared === '1') return;
  // Marked before the animation: this flag stops a re-render replaying the entrance.
  el.dataset.cfAppeared = '1';
  // Only the first screens animate. A card below the fold is not visible while
  // its entrance plays, so the class, the stagger and the 900 ms failsafe timer
  // are pure cost. Late arrivals (budget = -1) keep their animation.
  if (cfAppearBudget === 0) return;
  if (cfAppearBudget > 0) cfAppearBudget--;
  const requested = (ext && ext.appear_animation) || CF_APPEAR_DEFAULT;
  const cls = CF_APPEAR_ANIMATIONS[requested] || CF_APPEAR_ANIMATIONS[CF_APPEAR_DEFAULT];
  // Staggered by grid position, so the cascade follows the reading order.
  const order = Array.prototype.indexOf.call(
    el.parentNode ? el.parentNode.querySelectorAll('.widget-extension') : [], el);
  const delay = Math.max(0, order < 0 ? 0 : order) * CF_APPEAR_STAGGER_MS;
  el.style.setProperty('--cf-appear-delay', delay + 'ms');
  el.classList.add('cf-appearing', cls);
  const done = () => {
    el.classList.remove('cf-appearing', cls);
    el.style.removeProperty('--cf-appear-delay');
    el.removeEventListener('animationend', done);
  };
  el.addEventListener('animationend', done);
  // Failsafe: a never-fired animation would pin pointer-events:none forever.
  setTimeout(done, 900 + delay);
}

/* Skeleton for an installed extension not loaded yet; holds its real grid slot. */
function createPlaceholderCard(ext) {
  const gs = ext.grid_size || EXT_DEFAULT_GRID;
  const el = document.createElement('div');
  el.className = `widget widget-extension cf-placeholder ext-${ext.id}`;
  el.dataset.extId = ext.id;
  el.dataset.placeholder = '1';
  // Stamped so the swap can honour CF_PLACEHOLDER_MIN_MS below.
  el.dataset.cfPhAt = String(Date.now());
  el.style.gridColumn = `span ${gs.w}`;
  el.style.gridRow = `span ${gs.h}`;
  el.style.minWidth = '0';
  el.style.minHeight = '0';
  el.style.overflow = 'hidden';
  el.style.pointerEvents = 'none';

  const header = document.createElement('div');
  header.className = 'widget-header';
  const label = document.createElement('span');
  label.textContent = ext.name || ext.id;
  header.appendChild(label);
  el.appendChild(header);

  const body = document.createElement('div');
  body.className = 'widget-body';
  // One bar per declared widget: the placeholder reads as the shape of what is coming.
  const count = Math.max(1, Math.min((ext.widgets || []).length || 1, 6));
  for (let i = 0; i < count; i++) {
    const bar = document.createElement('div');
    bar.className = 'cf-placeholder-bar';
    bar.style.width = i === count - 1 && count > 1 ? '62%' : '100%';
    body.appendChild(bar);
  }
  el.appendChild(body);
  return el;
}

