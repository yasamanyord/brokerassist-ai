'use strict';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let tickets=[],selected=null,filter='All',query='',currentView='inbox';
let detailToken=0,noticeTimer,session={pilot:false,role:"operator"};
async function api(path,options={}){
 const res=await fetch('/api'+path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
 if(!res.ok){const body=await res.json().catch(()=>({}));throw new Error(typeof body.detail==='string'?body.detail:'Request failed ('+res.status+')');}
 return res.json();
}
function statusBadge(status){return '<span class="badge '+({'In review':'review','Escalated':'escalated','Approved':'approved'}[status]||'')+'">'+esc(status)+'</span>'}
function notice(message,error=false){clearTimeout(noticeTimer);$('notice').textContent=message;$('notice').className=error?'error':'';$('notice').hidden=false;noticeTimer=setTimeout(()=>$('notice').hidden=true,5000)}
function statsHTML(m){return [['Total tickets',m.total,'▤','All incoming requests'],['In review',m.review,'✦','Awaiting operator action'],['Approved',m.approved,'✓','Local approval only'],['Escalated',m.escalated,'↗','Local escalation records']].map(([label,val,icon,caption])=>'<div class="stat"><span class="stat-icon">'+icon+'</span><label>'+label+'</label><div class="value">'+val+'</div><small>'+caption+'</small></div>').join('')}
async function refresh(keep=true){
 tickets=await api('/tickets');
 const m=await api('/metrics');
 $('stats').innerHTML=statsHTML(m);$('analytics-stats').innerHTML=statsHTML(m);$('nav-count').textContent=m.new;
 const bars=[['New',m.new],['In review',m.review],['Approved',m.approved],['Escalated',m.escalated]];
 $('bars').innerHTML=bars.map(([label,v])=>'<div class="barrow"><span>'+label+'</span><div class="bartrack"><div class="barfill" style="width:'+(m.total?100*v/m.total:0)+'%"></div></div><b>'+v+'</b></div>').join('');
 if(!keep||!tickets.find(t=>t.id===selected)) selected=tickets[0]?.id??null;
 renderList();await renderDetail();
}
function renderList(){
 const visible=tickets.filter(t=>(filter==='All'||t.status===filter)&&(!query||(t.id+' '+t.customer+' '+t.subject+' '+t.message).toLowerCase().includes(query)));
 $('ticket-count').textContent=visible.length;
 $('ticket-list').innerHTML=visible.length?visible.map(t=>'<button class="ticket-row '+(t.id===selected?'selected':'')+'" data-ticket="'+esc(t.id)+'"><div class="ticket-meta"><span>'+esc(t.id)+' · '+esc(t.channel)+'</span>'+statusBadge(t.status)+'</div><b>'+esc(t.subject)+'</b><p>'+esc(t.customer)+' · '+esc(t.message)+'</p></button>').join(''):'<div class="empty-state">No matching tickets.</div>';
 document.querySelectorAll('[data-ticket]').forEach(btn=>btn.onclick=()=>{selected=btn.dataset.ticket;renderList();renderDetail().catch(e=>notice(e.message,true));});
}
function analysisHTML(t){
 const a=t.analysis,closed=['Approved','Escalated'].includes(t.status),readOnly=session.role==='viewer';
 if(!a&&readOnly)return '<div class="placeholder">Awaiting operator analysis.</div>';
 if(!a)return '<div class="placeholder"><div class="spark" style="margin:auto">✦</div><h3>Ready to analyze</h3><p>Retrieve relevant policy, identify risk and create a reviewable response draft.</p><button class="primary" id="analyze-btn">✦ Analyze ticket</button></div>';
 const refs=a.citations.map(c=>'<details class="source"><summary>'+esc(c.id)+' · '+esc(c.title)+'</summary><p>'+esc(c.excerpt)+'</p></details>').join('');
 const calls=a.tool_calls.map(c=>'<div class="source"><b>Tool: '+esc(c.tool)+'</b> '+statusBadge(c.status==='ok'?'Authorized':'Blocked')+'<p>'+esc(c.status==='ok'?c.reference+' · '+c.state+(c.simulated?' (demo data)':''):c.reason)+'</p></div>').join('');
 const decision=a.mandatory_escalation?'Specialist review required':'Operator review required';
 const signals=(a.risk_signals||[]).map(r=>esc(r.code.replaceAll('_',' '))).join(' · ');
 return '<div class="analysis-grid"><div class="analysis-field"><span class="label">Category</span><b>'+esc(a.category)+'</b></div><div class="analysis-field"><span class="label">Priority</span><span class="badge '+esc(a.priority.toLowerCase())+'">'+esc(a.priority)+'</span></div><div class="analysis-field"><span class="label">Assigned team</span><b>'+esc(a.team)+'</b></div></div>'+
 '<div class="alert '+(a.mandatory_escalation?'':'safe')+'"><b>'+decision+'</b> — '+esc(a.reason)+(signals?'<br><span class="muted">Risk flags: '+signals+'</span>':'')+'</div><div class="sources"><span class="label">Retrieved evidence</span>'+refs+calls+'</div>'+
 '<div class="draft"><span class="label">'+(t.status==='Approved'?'Approved local draft':'Suggested response')+' · '+esc(a.mode)+'</span><textarea id="draft" aria-label="Suggested response" '+(closed||readOnly?'readonly':'')+'>'+esc(t.final_reply||a.draft)+'</textarea></div>'+
 (closed?'<div class="alert safe">Finalized locally: '+esc(t.status)+'. No message was sent externally.</div>':readOnly?'<div class="alert safe">Read-only viewer access.</div>':
 '<div class="actions"><button id="approve-btn" class="primary" '+(a.mandatory_escalation?'disabled title="Mandatory specialist escalation"':'')+'>✓ Approve local draft</button><button id="escalate-btn" class="danger-btn">↗ Escalate to '+esc(a.team)+'</button><button id="analyze-btn" class="secondary">↻ Re-analyze</button></div>');
}
async function renderDetail(){
 const token=++detailToken,t=tickets.find(t=>t.id===selected);
 if(!t){$('detail').innerHTML='<div class="empty-state">Select a ticket to get started.</div>';return;}
 const initials=t.customer.split(' ').slice(0,2).map(x=>x[0]).join('');
 $('detail').innerHTML='<div class="ticket-top"><div><span class="ticket-id">'+esc(t.id)+' · '+esc(t.channel)+'</span><h2>'+esc(t.subject)+'</h2></div>'+statusBadge(t.status)+'</div><div class="customerline"><div class="avatar">'+esc(initials)+'</div><b>'+esc(t.customer)+'</b><span>·</span><span>'+esc(new Date(t.created_at).toLocaleString())+'</span></div><div class="message"><span class="label">Customer message</span><p>'+esc(t.message)+'</p></div><div class="ai-title"><div class="spark">✦</div><div><h3>Support copilot</h3><small>Policy-grounded assistance</small></div></div>'+analysisHTML(t)+'<div class="audit"><h3 style="font-size:13px;margin:0 0 8px">Audit history</h3><div id="audit-rows" class="muted">Loading…</div></div>';
 const bind=(id,fn)=>{const btn=$(id);if(btn)btn.onclick=async()=>{btn.disabled=true;const old=btn.textContent;btn.textContent='Working…';try{await fn()}catch(e){notice(e.message,true)}finally{if(btn.isConnected){btn.disabled=false;btn.textContent=old}}}};
 bind('analyze-btn',async()=>{await api('/tickets/'+t.id+'/analyze',{method:'POST'});await refresh();notice('Ticket analyzed. Review the retrieved policy and recommended action.')});
 bind('approve-btn',async()=>{await api('/tickets/'+t.id+'/decision',{method:'POST',body:JSON.stringify({action:'approve',reply:$('draft').value,analysis_revision:t.analysis_revision})});await refresh();notice('Draft approved locally. No external message sent.')});
 bind('escalate-btn',async()=>{await api('/tickets/'+t.id+'/decision',{method:'POST',body:JSON.stringify({action:'escalate',analysis_revision:t.analysis_revision})});await refresh();notice('Local escalation recorded for '+t.analysis.team+'. No message was sent.')});
 if(t.status==='Escalated'){
  const h=await api('/tickets/'+t.id+'/handoff');
  if(token===detailToken){
   const lines=[
    'Ticket: '+h.ticket_id,
    'Issue: '+h.issue,
    'Impact: '+h.customer_impact,
    'Priority: '+h.priority+' · Recommended team: '+h.recommended_team,
    'Reason: '+h.reason,
    'Evidence: '+h.policy_ids.join(', '),
    'Risk flags: '+(h.risk_flags.join(', ')||'None detected'),
    'Tool attempts: '+(h.tool_attempts.map(x=>x.tool+' — '+x.status+(x.simulated?' (simulation)':'')).join(', ')||'None'),
    'Next step: '+h.next_step,
    'Recorded by: '+h.recorded_by+' · '+h.recorded_at,
    'Delivery: Local record only. Not sent to a specialist.'
   ];
   const section=document.createElement('div');section.className='draft';
   section.innerHTML='<span class="label">Specialist handoff · local only</span><textarea aria-label="Specialist handoff" readonly rows="10">'+esc(lines.join('\n'))+'</textarea>';
   $('audit-rows').parentElement.before(section);
  }
 }
 const audit=await api('/tickets/'+t.id+'/audit');
 if(token===detailToken&&$('audit-rows'))$('audit-rows').innerHTML=audit.length?audit.map(a=>'<div class="audit-row"><b>'+esc(a.action)+'</b> · '+esc(a.detail)+'<br>'+esc(a.actor||'legacy-demo')+' · '+esc(new Date(a.created_at).toLocaleString())+'</div>').join(''):'<div class="audit-row">No actions recorded yet.</div>';
}
async function showView(view){
 currentView=view;document.querySelectorAll('.view').forEach(v=>v.hidden=v.id!==view);
 document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
 $('breadcrumb').textContent={inbox:'Ticket inbox',knowledge:'Knowledge base',analytics:'Operations'}[view];
 if(view==='knowledge'){
  const policies=await api('/knowledge');
  $('policy-list').innerHTML=policies.map(p=>'<div class="policy-card"><div class="eyebrow">'+esc(p.id)+' · '+esc(p.category)+'</div><h2>'+esc(p.title)+'</h2><p>'+esc(p.policy)+'</p><details class="source"><summary>Approved draft</summary><p>'+esc(p.reply)+'</p></details></div>').join('');
 }
 if(view==='analytics')await refresh();
}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>showView(b.dataset.view).catch(e=>notice(e.message,true)));
document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('selected',x===b));renderList()});
$('search').oninput=e=>{query=e.target.value.toLowerCase();renderList()};
$('create-ticket').onclick=()=>$('ticket-dialog').showModal();
$('close-dialog').onclick=()=>$('ticket-dialog').close();
$('intake-form').onsubmit=async e=>{
 e.preventDefault();const button=e.target.querySelector('[type=submit]');button.disabled=true;
 try{const t=await api('/tickets',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});selected=t.id;filter='All';query='';$('search').value='';document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('selected',x.dataset.filter==='All'));$('ticket-dialog').close();e.target.reset();await refresh();notice(session.pilot?'Ticket received.':'Synthetic ticket created.')}
 catch(err){notice(err.message,true)}finally{button.disabled=false}
};
(async()=>{try{const health=await api('/health');session=await api('/session');$('mode').innerHTML='<span class="dot"></span>'+ (session.pilot?'Restricted company pilot':health.mode==='llm-enabled'?'LLM enabled':'Offline demo');if(session.pilot){$('org-name').textContent=session.client;$('org-description').textContent='Dedicated company workspace';$('workspace-label').textContent='Restricted pilot · local approval';$('profile-name').textContent=session.name;$('profile-avatar').textContent=session.name.slice(0,2).toUpperCase();$('profile-role').textContent=session.role;$('policy-description').textContent='Client-approved policies used to ground response drafts.';$('intake-title').textContent='Receive a ticket';$('intake-note').textContent='Enter only company-authorized, minimum necessary data.';const customer=document.querySelector('[name=customer]');customer.defaultValue='';customer.value='';document.querySelector('[name=message]').placeholder='Enter an authorized support request';}if(session.role==='viewer')$('create-ticket').hidden=true;await refresh(false)}catch(e){notice('Unable to load workspace: '+e.message,true)}})();
