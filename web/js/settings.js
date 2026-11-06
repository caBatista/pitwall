import { esc, prefs, savePrefs } from './util.js';
import { standingsPage } from './set-standings.js';
import { layoutPage } from './set-layout.js';
import { screenPage } from './set-screen.js';
import { generalPage } from './set-general.js';
import { headerPage } from './set-header.js';
import { flagsPage } from './set-flags.js';

// One entry per page, in the order of the menu. To add a setting: give the page a render(root).
const GROUPS = [
  { title: 'App', pages: [
    { id: 'screen', name: 'Screen', info: 'Where Pitwall runs. Layouts follow the shape of this screen.', render: screenPage },
    { id: 'general', name: 'General', info: 'How Pitwall starts and looks.', render: generalPage },
    { id: 'header', name: 'Header', info: 'The bar across the top of the board.', render: headerPage },
    { id: 'layout', name: 'Layout', info: 'The widgets of each session. Drag to move, pull the corner to resize.', render: layoutPage },
  ] },
  { title: 'Widgets', pages: [
    { id: 'standings', name: 'Standings', info: 'Every driver in the session, by class.', render: standingsPage },
    { id: 'relative', name: 'Relative', info: 'The cars around you on track.' },
    { id: 'fuel', name: 'Fuel', info: 'Consumption, pit window and auto fuel.' },
    { id: 'map', name: 'Track map', info: 'The track and every car on it.' },
    { id: 'weather', name: 'Weather', info: 'Conditions and how they are changing.' },
    { id: 'events', name: 'Race events', info: 'What happened in the session.' },
    { id: 'flags', name: 'Race flags', info: 'The flags you get, on the background of the board.', render: flagsPage },
  ] },
];
const PAGES = GROUPS.flatMap((g) => g.pages);

const nav = document.getElementById('st-nav');
const page = document.getElementById('st-page');

function show(id) {
  const p = PAGES.find((x) => x.id === id) ?? PAGES[0];
  prefs.setPage = p.id; savePrefs();
  for (const b of nav.querySelectorAll('button')) b.classList.toggle('on', b.dataset.page === p.id);
  page.dataset.shown = Number(page.dataset.shown || 0) + 1;   // a page that loads slowly sees it changed
  page.innerHTML = `<h1>${esc(p.name)}</h1><p>${esc(p.info)}</p>`;
  if (p.render) p.render(page);
  else page.insertAdjacentHTML('beforeend', '<div class="st-none">No settings yet</div>');
  page.scrollTop = 0;
}

nav.innerHTML = GROUPS.map((g) => `<small>${esc(g.title)}</small>${g.pages.map((p) => `<button data-page="${p.id}">${esc(p.name)}</button>`).join('')}`).join('');
nav.addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (b) show(b.dataset.page);
});
show(prefs.setPage);

const close = () => (window.pywebview?.api ? window.pywebview.api.close_settings() : window.close());
document.getElementById('st-close').addEventListener('click', close);
addEventListener('keydown', (e) => {
  if (e.key === 'Escape') close();
  if (e.key === 'F5' && window.pywebview?.api) { e.preventDefault(); location.reload(); }
});
