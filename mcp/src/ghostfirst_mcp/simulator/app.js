'use strict';

// A minimal MCP client (Streamable HTTP, protocol 2025-11-25) wrapped in a
// voice-assistant screen. The page decides nothing: verdicts and sentences
// come from the GhostFirst MCP server; the page only chooses how to say them.

const PROTOCOL = '2025-11-25';
const ENDPOINT = '/mcp';
const LOG_LIMIT = 40;

const $ = (id) => document.getElementById(id);

class McpClient {
  constructor(endpoint, { onLog, onElicit }) {
    this.endpoint = endpoint;
    this.onLog = onLog;
    this.onElicit = onElicit;
    this.nextId = 1;
    this.session = null;
  }

  headers() {
    const h = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' };
    if (this.session) {
      h['Mcp-Session-Id'] = this.session;
      h['MCP-Protocol-Version'] = PROTOCOL;
    }
    return h;
  }

  async connect() {
    const init = await this.request('initialize', {
      protocolVersion: PROTOCOL,
      capabilities: { elicitation: { form: {} }, extensions: { "io.modelcontextprotocol/ui": { mimeTypes: ["text/html;profile=mcp-app"] } } },
      clientInfo: { name: 'ghostfirst-voice-simulator', version: '0.1.0' },
    });
    await this.post({ jsonrpc: '2.0', method: 'notifications/initialized' });
    return init;
  }

  request(method, params) {
    const id = this.nextId++;
    return this.exchange({ jsonrpc: '2.0', id, method, params }, id);
  }

  async post(message) {
    this.onLog('out', message);
    const response = await fetch(this.endpoint, {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify(message),
    });
    const session = response.headers.get('Mcp-Session-Id');
    if (session) this.session = session;
    if (!response.ok) throw new Error(`MCP server answered HTTP ${response.status}`);
    return response;
  }

  async exchange(message, id) {
    const response = await this.post(message);
    const type = response.headers.get('Content-Type') || '';
    if (type.includes('application/json')) {
      const reply = await this.handle(await response.json(), id);
      if (reply) return reply.result;
      throw new Error('No reply from the MCP server');
    }
    // Server-sent events: the server may ask the human (elicitation) on this
    // same stream before it sends the final result.
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop();
      for (const event of events) {
        const data = event.split(/\r?\n/).filter((l) => l.startsWith('data:')).map((l) => l.slice(5).trim()).join('\n');
        if (!data) continue;
        const reply = await this.handle(JSON.parse(data), id);
        if (reply) {
          reader.cancel().catch(() => {});
          return reply.result;
        }
      }
    }
    throw new Error('The MCP stream closed without a result');
  }

  async handle(message, id) {
    this.onLog('in', message);
    if (message.method && message.id !== undefined) {
      await this.post({ jsonrpc: '2.0', id: message.id, ...(await this.answer(message)) });
      return null;
    }
    if (message.method) return null; // notification
    if (message.id !== id) return null;
    if (message.error) throw new Error(message.error.message || 'MCP error');
    return { result: message.result };
  }

  async answer(request) {
    if (request.method === 'elicitation/create') return { result: await this.onElicit(request.params) };
    if (request.method === 'ping') return { result: {} };
    return { error: { code: -32601, message: 'Method not found' } };
  }

  async callTool(name, args) {
    const result = await this.request('tools/call', { name, arguments: args });
    if (result.isError || !result.structuredContent) throw new Error('The tool call failed');
    return result.structuredContent;
  }
}

// ---------- speech ----------

function say(text) {
  if (!$('speak').checked || !('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'en-US';
  utterance.rate = 0.95;
  window.speechSynthesis.speak(utterance);
}

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

// ---------- understanding what the person said ----------

const TRAILING = /[).,!?;:'"]+$/;

function findUrl(text) {
  const written = text.match(/\bhttps?:\/\/[^\s<>"]+/i);
  if (written) return written[0].replace(TRAILING, '');
  // Spoken form: "paypal dash secure dot example slash login".
  const spoken = ` ${text.toLowerCase()} `
    .replace(/\s+dot\s+/g, '.')
    .replace(/\s+slash\s+/g, '/')
    .replace(/\s+dash\s+/g, '-');
  const domain = spoken.match(/\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:\/[^\s]*)?/);
  return domain ? `https://${domain[0].replace(TRAILING, '')}` : null;
}

const isYes = (t) => /^\s*(yes|yeah|yep|sure|ok(ay)?|please|do it|go ahead)\b/i.test(t);
const isNo = (t) => /^\s*(no|nope|don'?t|stop|cancel|never ?mind)\b/i.test(t);
const wantsDeeper = (t) => /\b(deep|deeper|again|closer|phone|computer)\b/i.test(t);

// ---------- turning tool results into speech ----------

const LEAD = {
  do_not_continue: "Please don't open this link, and don't type anything into it.",
  caution: 'Be careful with this link.',
  no_obvious_danger: "I didn't see obvious danger on this link. That's not a guarantee.",
};

function notVisited(out) {
  return out.status === 'declined_by_human'
    ? "Okay, I didn't open it. One-time links are best checked by you, in the GhostFirst app."
    : "This looks like a one-time link, like a password reset, so I didn't open it. Please check it yourself in the GhostFirst app.";
}

function linkAnswer(out) {
  if (out.status === 'needs_human_confirmation' || out.status === 'declined_by_human') {
    return { text: notVisited(out), details: [] };
  }
  if (out.status === 'error') return { text: out.agent_guidance, details: [] };
  const details = out.reasons.slice(0, 3).map((r) => r.text);
  if (out.final_host) {
    const hops = out.redirects ? ` after ${out.redirects} redirect${out.redirects > 1 ? 's' : ''}` : '';
    details.push(`It ends up at ${out.final_host}${hops}.`);
  }
  let text = `${LEAD[out.verdict] || LEAD.caution} ${out.summary || ''}`.trim();
  const followUp = out.recommended_next_step === 'deep_check';
  if (followUp) text += ' Do you want me to look again, as a phone and as a computer?';
  return { text, details, verdict: out.verdict, followUp };
}

function deepAnswer(out) {
  if (out.status !== 'checked') return linkAnswer(out);
  const text = [LEAD[out.verdict] || LEAD.caution, out.comparison && `${out.comparison}.`, out.comparison_detail]
    .filter(Boolean).join(' ');
  const details = [...new Set([...out.differences, ...out.reasons.slice(0, 2).map((r) => r.text)])];
  return { text, details, verdict: out.verdict };
}

// ---------- screen ----------

function bubble(who, text, details = [], verdict) {
  const li = document.createElement('li');
  li.className = who;
  if (verdict) li.dataset.verdict = verdict;
  li.append(text);
  for (const d of details) {
    const span = document.createElement('span');
    span.className = 'detail';
    span.textContent = d;
    li.append(span);
  }
  $('talk').append(li);
  li.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

function setState(state, status) {
  $('ring').dataset.state = state;
  if (status) $('status').textContent = status;
}

function log(direction, message) {
  const li = document.createElement('li');
  const head = document.createElement('div');
  head.className = 'head';
  const dir = document.createElement('span');
  dir.className = 'dir';
  dir.textContent = direction === 'out' ? 'assistant → server' : 'server → assistant';
  const name = document.createElement('span');
  name.textContent = message.method || (message.error ? 'error' : `result #${message.id}`);
  head.append(name, dir);
  const pre = document.createElement('pre');
  pre.textContent = JSON.stringify(message, null, 2).slice(0, 4000);
  li.append(head, pre);
  const list = $('log');
  list.prepend(li);
  while (list.children.length > LOG_LIMIT) list.lastChild.remove();
}

// ---------- conversation ----------

let cardReady = false;
let cardResult = null;
function renderCard(out) {
  cardResult = out;
  if (cardReady) $('verdict-card').contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{content:[],structuredContent:out}}, '*');
}
window.addEventListener('message', (event) => {
  const frame = $('verdict-card');
  if (event.source !== frame.contentWindow || event.data?.jsonrpc !== '2.0') return;
  const m = event.data;
  if (m.method === 'ui/initialize') {
    frame.contentWindow.postMessage({jsonrpc:'2.0',id:m.id,result:{protocolVersion:'2026-01-26',hostInfo:{name:'ghostfirst-simulator',version:'1'},hostCapabilities:{message:{}},hostContext:{displayMode:'inline',deviceClass:window.innerWidth < 600 ? 'mobile':'echo-show',theme:matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}}}, '*');
  } else if (m.method === 'ui/notifications/initialized') {
    cardReady = true;
    frame.contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-input',params:{arguments:{}}}, '*');
    if (cardResult) renderCard(cardResult);
  } else if (m.method === 'ui/message' && m.params?.role === 'user' && ['Yes','No'].includes(m.params?.content?.text)) {
    frame.contentWindow.postMessage({jsonrpc:'2.0',id:m.id,result:{}}, '*');
    hear(m.params.content.text);
  }
});

const conversation = { lastUrl: null, followUp: null, confirm: null, busy: false };

function askHuman(params) {
  const props = params.requestedSchema?.properties || {};
  const keys = Object.keys(props);
  const field = keys.length === 1 && props[keys[0]].type === 'boolean' ? keys[0] : null;
  if (!field) return Promise.resolve({ action: 'decline' });
  renderCard({human_question:params.message,agent_guidance:params.message});
  bubble('assistant', params.message);
  say(params.message);
  setState('idle', 'Waiting for your answer');
  $('confirm').hidden = false;
  return new Promise((resolve) => {
    conversation.confirm = (yes) => {
      conversation.confirm = null;
      $('confirm').hidden = true;
      setState('thinking', 'Checking…');
      resolve(yes ? { action: 'accept', content: { [field]: true } } : { action: 'decline' });
    };
  });
}

const client = new McpClient(ENDPOINT, { onLog: log, onElicit: askHuman });

async function run(tool, url) {
  conversation.busy = true;
  setState('thinking', tool === 'deep_check' ? 'Visiting as three different visitors…' : 'Sending a disposable browser to the link…');
  try {
    let out = await client.callTool(tool, tool === 'check_shared_link' ? {} : { url });
    const deadline = Date.now() + 70000;
    while (out.status === 'checking' && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      out = await client.callTool('get_check_result', { job_id: out.job_id });
    }
    if (out.status === 'checking') throw new Error('Check timed out');
    const answer = tool === 'deep_check' ? deepAnswer(out) : linkAnswer(out);
    conversation.followUp = answer.followUp ? 'deep_check' : null;
    if (out.history_note) answer.details.unshift(out.history_note);
    bubble('assistant', answer.text, answer.details, answer.verdict);
    renderCard(out);
    say([answer.text, ...answer.details, out.not_a_guarantee].filter(Boolean).join(' '));
    setState(answer.verdict || 'idle', 'Ask me about another link.');
  } catch (error) {
    const text = "I couldn't check that link right now, so please don't open it yet.";
    bubble('assistant', text, [String(error.message || error)]);
    say(text);
    setState('idle', 'Something went wrong.');
  } finally {
    conversation.busy = false;
  }
}

async function hear(text) {
  text = text.trim();
  if (!text) return;
  bubble('you', text);
  if (conversation.confirm) {
    if (isYes(text) || isNo(text)) conversation.confirm(isYes(text));
    else say('Please say yes or no.');
    return;
  }
  if (conversation.busy) return;
  if (/shared|text message|grandson/i.test(text)) {
    conversation.lastUrl = conversation.sharedUrl;
    await run('check_shared_link');
    return;
  }
  const url = findUrl(text);
  if (url) {
    conversation.lastUrl = url;
    await run('check_link', url);
    return;
  }
  if (conversation.followUp && isNo(text)) {
    conversation.followUp = null;
    bubble('assistant', 'Okay.');
    say('Okay.');
    return;
  }
  if (conversation.lastUrl && ((conversation.followUp && isYes(text)) || wantsDeeper(text))) {
    conversation.followUp = null;
    await run('deep_check', conversation.lastUrl);
    return;
  }
  const help = "Tell me the link you want me to check. You can paste it, or read it out, like 'example dot com'.";
  bubble('assistant', help);
  say(help);
}

function setUpMic() {
  const mic = $('mic');
  if (!Recognition) {
    mic.hidden = true;
    return;
  }
  const recognition = new Recognition();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.onresult = (event) => hear(event.results[0][0].transcript);
  recognition.onend = () => {
    mic.setAttribute('aria-pressed', 'false');
    if ($('ring').dataset.state === 'listening') setState('idle');
  };
  mic.addEventListener('click', () => {
    window.speechSynthesis?.cancel();
    mic.setAttribute('aria-pressed', 'true');
    setState('listening', 'Listening…');
    recognition.start();
  });
}

async function start() {
  $('share').addEventListener('click', async () => {
    try {
      const out = await client.callTool('share_link', {url:$('shared-url').value.trim()});
      $('share-status').textContent = out.agent_guidance;
      if (out.status === 'shared') conversation.sharedUrl = $('shared-url').value.trim();
    } catch (_) { $('share-status').textContent = 'The link could not be shared.'; }
  });
  $('check-shared').addEventListener('click', () => {
    if (!conversation.busy) { conversation.lastUrl = conversation.sharedUrl; run('check_shared_link'); }
  });
  $('ask').addEventListener('submit', (event) => {
    event.preventDefault();
    const text = $('say').value;
    $('say').value = '';
    hear(text);
  });
  $('yes').addEventListener('click', () => conversation.confirm?.(true));
  $('no').addEventListener('click', () => conversation.confirm?.(false));
  setUpMic();
  try {
    const init = await client.connect();
    const { tools } = await client.request('tools/list', {});
    const resource = await client.request('resources/read', {uri:'ui://ghostfirst/verdict'});
    const card = resource.contents.find((c) => c.mimeType === 'text/html;profile=mcp-app');
    if (card) { $('verdict-card').srcdoc = card.text; $('verdict-card').hidden = false; }
    setState('idle', `Connected to ${init.serverInfo.title || init.serverInfo.name} · tools: ${tools.map((t) => t.name).join(', ')}`);
  } catch (error) {
    setState('idle', `Could not reach the MCP server: ${error.message}`);
  }
}

start();
