'use strict';
const el = (id) => document.getElementById(id);
const labels = {do_not_continue: '⛔ Do not continue', caution: '⚠ Caution', no_obvious_danger: '✓ No suspicious behavior observed'};
const esLabels = {do_not_continue:'⛔ No continúes', caution:'⚠ Ten cuidado', no_obvious_danger:'✓ No se observó comportamiento sospechoso'};
let nextId = 2;
let ready = false;
function send(message) { window.parent.postMessage({jsonrpc:'2.0', ...message}, '*'); }
function adapt(context = {}) {
  document.documentElement.dataset.theme = context.theme === 'dark' ? 'dark' : 'light';
  document.body.className = context.deviceClass === 'mobile' || context.isMobile ? 'mobile' : 'block';
}
window.addEventListener('message', (event) => {
  if (event.source !== window.parent || event.data?.jsonrpc !== '2.0') return;
  const message = event.data;
  if (message.id === 1 && message.result && !ready) {
    ready = true; adapt(message.result.hostContext);
    send({method:'ui/notifications/initialized'});
  } else if (ready && message.method === 'ui/notifications/host-context-changed') {
    adapt(message.params);
  } else if (ready && message.method === 'ui/notifications/tool-result') {
    const out = message.params?.structuredContent || {};
    const spanish = out.locale === 'es-US';
    document.documentElement.lang = spanish ? 'es-US' : 'en-US';
    el('yes').textContent = spanish ? 'Sí' : 'Yes';
    const host = out.final_host || out.visitors?.find((v) => v.final_host)?.final_host || '';
    el('host').textContent = host;
    el('card').dataset.verdict = out.verdict || '';
    el('verdict').textContent = (spanish ? esLabels : labels)[out.verdict] || 'GhostFirst';
    el('summary').textContent = out.summary || out.comparison_detail || out.agent_guidance || '';
    el('notice').textContent = out.not_a_guarantee || '';
    el('chips').replaceChildren();
    for (const reason of (out.reasons || []).slice(0, 4)) {
      const chip = document.createElement('li'); chip.textContent = reason.text; el('chips').append(chip);
    }
    el('visitors').hidden = out.status !== 'checked' || !Array.isArray(out.visitors);
    el('visitor-tiles').replaceChildren();
    if (!el('visitors').hidden) {
      el('visitors-title').textContent = spanish ? 'Tres visitantes' : 'Three visitors';
      el('comparison').textContent = out.comparison || out.differences?.[0] || '';
      for (const row of VisitorView.rows(out, spanish)) {
        const tile = document.createElement('article');
        tile.className = 'visitor';
        tile.dataset.differs = String(row.differs);
        const heading = document.createElement('h3'); heading.textContent = `${row.icon} ${row.label}`;
        tile.append(heading);
        for (const text of [row.host, row.status, row.differs ? (spanish ? '≠ Observaciones diferentes' : '≠ Observations differ') : ''].filter(Boolean)) {
          const line = document.createElement('p'); line.textContent = text; tile.append(line);
        }
        const chips = document.createElement('ul'); chips.className = 'field-chips';
        for (const field of row.fields) { const chip = document.createElement('li'); chip.textContent = field; chips.append(chip); }
        tile.append(chips); el('visitor-tiles').append(tile);
      }
    }
    const question = out.human_question || (out.recommended_next_step === 'deep_check' ? (spanish ? '¿Quieres una revisión profunda?' : 'Would you like a Deep Check?') : '');
    el('question').textContent = question; el('question').hidden = !question;
    el('actions').hidden = !question;
  }
});
for (const [id, text] of [['yes','Yes'],['no','No']]) {
  el(id).addEventListener('click', () => {
    el('actions').hidden = true;
    send({id:nextId++, method:'ui/message', params:{role:'user',content:{type:'text',text}}});
  });
}
send({id:1,method:'ui/initialize',params:{protocolVersion:'2026-01-26',appInfo:{name:'ghostfirst-verdict',version:'1'},appCapabilities:{availableDisplayModes:['inline']}}});

new ResizeObserver(() => send({method:'ui/notifications/size-changed',params:{height:el('card').offsetHeight + 32}})).observe(el('card'));
