'use strict';
const el = (id) => document.getElementById(id);
const labels = {do_not_continue: '⛔ Do not continue', caution: '⚠ Caution', no_obvious_danger: '✓ No suspicious behavior observed'};
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
    const host = out.final_host || out.visitors?.find((v) => v.final_host)?.final_host || '';
    el('host').textContent = host;
    el('card').dataset.verdict = out.verdict || '';
    el('verdict').textContent = labels[out.verdict] || 'GhostFirst';
    el('summary').textContent = out.summary || out.comparison_detail || out.agent_guidance || '';
    el('notice').textContent = out.not_a_guarantee || '';
    el('chips').replaceChildren();
    for (const reason of (out.reasons || []).slice(0, 4)) {
      const chip = document.createElement('li'); chip.textContent = reason.text; el('chips').append(chip);
    }
    const question = out.human_question || (out.recommended_next_step === 'deep_check' ? 'Would you like a Deep Check?' : '');
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
