const $ = id => document.getElementById(id);
let key = '', thread = null;
async function api(path, options = {}) {
  if (!key) throw new Error('Connect with your API key first.');
  const response = await fetch(path, {...options, headers: {'X-API-Key': key, ...options.headers}});
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
async function action(button, fn) {
  button.disabled = true; $('status').textContent = 'Working…';
  try { await fn(); $('status').textContent = ''; }
  catch (error) { $('status').textContent = error.message; }
  finally { button.disabled = false; }
}
async function listDocuments() {
  const docs = await api('/v1/documents'); $('documents').replaceChildren();
  for (const doc of docs) {
    const li = document.createElement('li');
    li.textContent = `${doc.filename} · ${doc.chunks} chunks · ${doc.status}`;
    const button = document.createElement('button'); button.textContent = 'Delete'; button.className = 'secondary';
    button.onclick = () => { if (confirm('Delete this document and all saved conversations for this customer?')) action(button, async () => {
      await api(`/v1/documents/${doc.document_id}`, {method:'DELETE'}); thread = null;
      $('answer').textContent = ''; $('sources').replaceChildren(); await listDocuments();
    }); }; li.append(button); $('documents').append(li);
  }
  if (!docs.length) $('documents').textContent = 'No documents yet. Try examples/refund-policy.md.';
}
$('connect').onclick = () => action($('connect'), async () => {
  key = $('key').value.trim(); thread = null; $('answer').textContent = ''; $('sources').replaceChildren();
  await listDocuments(); const health = await fetch('/health/ready').then(r => r.json());
  $('connection').textContent = `Connected · ${health.mode === 'fake' ? 'FREE DEMO — excerpt matching, no AI model' : 'LIVE AI — provider charges apply'}`;
});
$('refresh').onclick = () => action($('refresh'), listDocuments);
$('upload').onclick = () => action($('upload'), async () => {
  const file = $('file').files[0]; if (!file) throw new Error('Choose a document first.');
  const body = new FormData(); body.append('file', file); await api('/v1/documents', {method:'POST', body}); await listDocuments();
});
$('ask').onclick = () => action($('ask'), async () => {
  const question = $('question').value.trim(); if (!question) throw new Error('Enter a question.');
  const data = await api('/v1/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question,thread_id:thread})});
  thread = data.thread_id; $('answer').textContent = data.answer; $('sources').replaceChildren();
  for (const source of data.sources) {
    const details = document.createElement('details'), summary = document.createElement('summary'), text = document.createElement('p');
    summary.textContent = `[${source.citation}] ${source.filename}${source.page ? ` · page ${source.page}` : ''} · score ${source.score}`;
    text.textContent = source.excerpt; details.append(summary,text); $('sources').append(details);
  }
});
$('new').onclick = () => { thread = null; $('answer').textContent = ''; $('sources').replaceChildren(); $('status').textContent = 'New conversation. Previous conversation remains saved until deleted or expired.'; };
$('forget').onclick = () => action($('forget'), async () => {
  if (thread) await api(`/v1/threads/${thread}`, {method:'DELETE'});
  thread = null; $('answer').textContent = ''; $('sources').replaceChildren();
});
