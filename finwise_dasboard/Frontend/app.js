/* Finwise — browser UI for the local Python budgeting REST API.
 * No client-side financial authority: all budgets and purchase checks come from Python.
 */
'use strict';
const $ = (id) => document.getElementById(id);
const state = {
  data:null, month:localMonth(), chartMode:'cumulative',
  search:'', kind:'all', editingTx:null, editingBill:null,
  settingsDirty:false, loadingSeq:0, lastPrice:null, toastTimer:null,
};
const COLORS=['#b3d944','#0c3022','#86aa1f','#d4e7a2','#537962','#a7bca2','#d9dec7','#73962b'];
const num=(v)=>{const n=Number(v);return Number.isFinite(n)?n:0};
const fmt=(v,decimals=0)=>`HK$${num(v).toLocaleString('en-HK',{minimumFractionDigits:decimals,maximumFractionDigits:decimals})}`;
const esc=(s)=>String(s??'').replace(/[&<>"']/g,(m)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const monthName=(s)=>new Date(`${s}-01T12:00:00`).toLocaleDateString('en-HK',{month:'long',year:'numeric'});
function localDate(d=new Date()){return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
function localMonth(){return localDate().slice(0,7);}
function dateLabel(s){return new Date(`${s}T12:00:00`).toLocaleDateString('en-HK',{day:'numeric',month:'short',year:'numeric'});}
function notice(message,isError=false){const el=$('toast');el.textContent=message;el.className=`toast ${isError?'error':''}`;el.hidden=false;clearTimeout(state.toastTimer);state.toastTimer=setTimeout(()=>el.hidden=true,4200);}
async function api(path,options={}){
  const r=await fetch(path,{...options,headers:{...(options.body?{'Content-Type':'application/json'}:{}),...(options.headers||{})},cache:'no-store'});
  const json=await r.json().catch(()=>({error:'Invalid response from local server'}));
  if(!r.ok)throw new Error(json.error||`Server error (${r.status})`);
  return json;
}
function setText(id,value){$(id).textContent=value;}
function updateIntro(){
  const hr=new Date().getHours();
  setText('greeting',`${hr<12?'Good morning':hr<17?'Good afternoon':'Good evening'}!`);
  setText('todayText',`Today is ${new Date().toLocaleDateString('en-HK',{weekday:'long',month:'long',day:'numeric',year:'numeric'})}`);
  $('monthPicker').max=localMonth();$('monthPicker').value=state.month;
}
async function refresh(silent=false){
  const seq=++state.loadingSeq;
  try{
    const data=await api(`/api/bootstrap?month=${encodeURIComponent(state.month)}`);
    if(seq!==state.loadingSeq)return;
    state.data=data;
    render(data);
    if(!silent)notice(`Dashboard updated for ${monthName(data.month)}`);
    if(state.lastPrice!==null)runPurchase(state.lastPrice,true).catch(()=>{});
    const h=new Date().toLocaleTimeString('en-HK',{hour:'2-digit',minute:'2-digit'});
    setText('refreshNote',`● Updated ${h}`);
  }catch(err){if(seq!==state.loadingSeq)return;notice(err.message,true);setText('refreshNote','● Unable to refresh');}
}
function render(d){
  const a=d.analysis,p=a.budget_plan,f=a.forecast,s=a.current_month;
  setText('incomeValue',fmt(s.income));
  setText('spendingValue',fmt(s.net_spending));
  setText('safeValue',fmt(p.safe_discretionary_purchase_limit));
  setText('forecastValue',fmt(f.projected_month_end));
  setText('incomeSub','Posted income this month');
  const budget=num(p.budget),spent=num(s.net_spending);
  setText('spendingSub',budget>0?`${Math.round(spent/budget*100)}% of ${fmt(budget)} monthly limit`:'Set your monthly budget below');
  setText('safeSub',p.cash_headroom===null?`Budget-based · ${fmt(p.auto_confirmed_bill_total||0)} in upcoming bills protected`:`${fmt(p.auto_confirmed_bill_total||0)} in upcoming bills protected · limited by ${p.binding_constraint==='cash'?'cash':'budget'}`);
  setText('forecastSub',f.over_budget_risk?`Estimated ${fmt(-num(f.projected_variance))} over budget`:'Expected total expenses');
  setText('dailyAllowance',fmt(p.safe_daily_allowance,2));
  setText('remainingValue',fmt(p.nominal_remaining));
  setText('cashValue',p.cash_headroom===null?'Not entered':fmt(p.cash_headroom));
  setText('cashCaption',p.cash_headroom===null?'Add a cash balance in settings':'After unpaid obligations and cash buffer');
  setText('chartSpent',fmt(s.net_spending));setText('chartBudget',fmt(p.budget));
  setText('chartSubtitle',`${monthName(d.month)} · as of ${dateLabel(d.as_of)}`);
  $('demoTag').hidden=!d.demo;
  $('demoBanner').hidden=Boolean(d.transactions.length || num(s.income) || num(s.gross_expenses) || d.demo || num(p.budget));
  renderLineChart(d);renderDonut(s.category_net);renderTransactions(d.transactions);
  renderBills(d.bills);renderRecurring(a.recurring_candidates);renderAlerts(d);
  if(!state.settingsDirty)renderSettings(d.settings);
  renderAllocations(p.dynamic_category_allowances);
  renderWeekdays(a.weekday_spending_patterns);
  document.dispatchEvent(new CustomEvent('finwise:updated'));
}
function renderLineChart(d){
  const pts=d.chart,mode=state.chartMode==='daily'?'daily_net':'cumulative_net';
  const a=d.analysis,actual=pts.filter(x=>x[mode]!==null);
  const yActual=actual.map(x=>num(x[mode]));
  const budget=mode==='cumulative'?num(a.budget_plan.budget):null;
  const future=mode==='cumulative'&&actual.length&&actual.length<pts.length?num(a.forecast.projected_month_end):null;
  const all=[0,...yActual,...(future!==null?[future]:[]),...(budget!==null?[budget]:[])];
  let min=Math.min(...all),max=Math.max(...all);
  if(max===min)max=min+1;
  if(min>=0){min=0;max*=1.12;}else{min*=1.1;max*=1.12;}
  const W=830,H=245,L=63,R=17,T=15,B=31,plotW=W-L-R,plotH=H-T-B;
  const x=(day)=>L+(day-1)/(Math.max(2,pts.length)-1)*plotW;
  const y=(value)=>T+(max-value)/(max-min)*plotH;
  const path=(points)=>points.map((p,i)=>`${i?'L':'M'}${x(p.day).toFixed(1)} ${y(num(p[mode])).toFixed(1)}`).join(' ');
  const grid=[0,1,2,3,4].map(i=>{
    const v=min+(max-min)*i/4,yy=y(v);
    return `<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}" stroke="#e6eae3" stroke-width="1"/><text x="${L-12}" y="${yy+4}" fill="#93a092" font-size="11" text-anchor="end">${esc(shortNum(v))}</text>`;
  }).join('');
  const xMarks=[1,Math.ceil(pts.length/4),Math.ceil(pts.length/2),Math.ceil(pts.length*3/4),pts.length];
  const xlabels=[...new Set(xMarks)].map(day=>`<text x="${x(day)}" y="${H-5}" text-anchor="middle" font-size="11" fill="#93a092">${day}</text>`).join('');
  const budgetLine=budget!==null?`<line x1="${L}" y1="${y(budget)}" x2="${W-R}" y2="${y(budget)}" stroke="#b1b9ad" stroke-dasharray="7 7" stroke-width="1.5"/>`:'';
  const actualPath=actual.length?`<path d="${path(actual)}" stroke="#9ac72c" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`:'';
  const futureLine=future!==null?`<path d="M${x(actual[actual.length-1].day).toFixed(1)} ${y(num(actual[actual.length-1][mode])).toFixed(1)}L${x(pts.length).toFixed(1)} ${y(future).toFixed(1)}" stroke="#6d9626" stroke-width="2.4" stroke-dasharray="7 6" fill="none"/>`:'';
  const circles=actual.filter((_,i)=>i===actual.length-1||i%Math.max(1,Math.floor(actual.length/14))===0).map(p=>`<circle cx="${x(p.day)}" cy="${y(num(p[mode]))}" r="3.5" fill="#aad038" stroke="white" stroke-width="1.3"><title>${esc(`${p.date}: ${fmt(p[mode],2)}`)}</title></circle>`).join('');
  const projectedPoint=future!==null?`<circle cx="${x(pts.length)}" cy="${y(future)}" r="4" fill="#668e25" stroke="white" stroke-width="2"><title>${esc(`Month-end estimate: ${fmt(future)}`)}</title></circle>`:'';
  $('lineChart').innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`Monthly ${state.chartMode} net expenses in HKD`)}">${grid}${budgetLine}${futureLine}${actualPath}${circles}${projectedPoint}${xlabels}</svg>`;
}
function shortNum(v){if(Math.abs(v)>=1000)return `${Math.round(v/100)/10}k`;return String(Math.round(v));}
function renderDonut(category){
  const rows=Object.entries(category||{}).map(([name,value])=>({name,value:Math.max(0,num(value))})).filter(x=>x.value>0).sort((a,b)=>b.value-a.value);
  const sum=rows.reduce((acc,v)=>acc+v.value,0);
  setText('donutTotal',fmt(sum));
  if(!sum){$('expenseDonut').style.background='#edf1e9';$('expenseLegend').innerHTML='<div class="muted tiny">No posted expenses in this month.</div>';return;}
  let start=0;
  const slices=rows.map((r,i)=>{const end=start+r.value/sum*100;const part=`${COLORS[i%COLORS.length]} ${start.toFixed(3)}% ${end.toFixed(3)}%`;start=end;return part;});
  $('expenseDonut').style.background=`conic-gradient(${slices.join(',')})`;
  $('expenseLegend').innerHTML=rows.slice(0,8).map((r,i)=>`<div class="legend-item" title="${esc(r.name)}: ${esc(fmt(r.value,2))}"><span class="legend-color" style="background:${COLORS[i%COLORS.length]}"></span><span class="legend-text">${esc(r.name)}</span><span class="legend-percent">${Math.round(r.value/sum*100)}%</span></div>`).join('');
}
function iconFor(cat){const c=cat.toLowerCase();if(c.includes('food')||c.includes('groc'))return '◉';if(c.includes('trans'))return '↗';if(c.includes('rent'))return '⌂';if(c.includes('shop'))return '▣';if(c.includes('entert'))return '✦';if(c.includes('salary')||c.includes('income'))return '↙';return '▦';}
function renderTransactions(rows){
  const filtered=rows.filter(t=>{
    const q=state.search.toLowerCase();
    return (state.kind==='all'||t.kind===state.kind)&&(!q||[t.merchant,t.category,t.account,t.id].some(v=>String(v||'').toLowerCase().includes(q)));
  });
  setText('transactionCount',`${filtered.length} transaction${filtered.length!==1?'s':''}`);
  if(!filtered.length){$('txTableBody').innerHTML='<tr><td colspan="6" class="empty-cell">No matching transactions for this month. Add one to get started.</td></tr>';return;}
  $('txTableBody').innerHTML=filtered.map(t=>{
    const sign=t.kind==='expense'?'-':t.kind==='income'||t.kind==='refund'?'+':'';
    const tone=t.kind==='income'?'positive':t.kind==='refund'?'refund':'';
    return `<tr><td><div class="transaction-name"><span class="merchant-icon">${iconFor(t.category)}</span><div><strong>${esc(t.merchant||t.kind)}</strong><small>${esc(t.account||'Checking')} · ${esc(t.kind)}</small></div></div></td>
      <td><span class="tag outline">${esc(t.category)}</span></td><td>${esc(dateLabel(t.date))}</td><td><span class="tag ${esc(t.status)}">${esc(t.status)}</span></td>
      <td class="align-right amount-cell ${tone}">${sign}${esc(fmt(t.amount,2))}</td>
      <td><div class="action-row"><button class="icon-button" type="button" data-tx-edit="${esc(t.id)}" title="Edit transaction" aria-label="Edit transaction">✎</button><button class="icon-button danger" type="button" data-tx-delete="${esc(t.id)}" title="Delete transaction" aria-label="Delete transaction">×</button></div></td></tr>`;
  }).join('');
}
function renderBills(bills){
  if(!bills.length){$('billsList').innerHTML='<div class="empty-state"><span class="empty-icon">▦</span>No confirmed bills yet. Add one to include it in your forecast.</div>';return;}
  const recent=bills.slice().sort((a,b)=>a.due.localeCompare(b.due));
  $('billsList').innerHTML=recent.map(b=>`<div class="bill-item"><span class="bill-icon">◫</span><div class="bill-main"><strong>${esc(b.name)}</strong><small>${esc(b.category)} · Due ${esc(dateLabel(b.due))}</small></div><div class="bill-amount">${esc(fmt(b.amount,2))}</div><div class="bill-actions"><button class="icon-button" data-bill-edit="${esc(b.id)}" title="Edit bill" aria-label="Edit bill">✎</button><button class="icon-button danger" data-bill-delete="${esc(b.id)}" title="Delete bill" aria-label="Delete bill">×</button></div></div>`).join('');
}
function renderRecurring(rows){
  if(!rows.length){$('recurringList').innerHTML='<div class="empty-state"><span class="empty-icon">↻</span>No strong recurring pattern found yet. Three or more regularly spaced payments are needed.</div>';return;}
  $('recurringList').innerHTML=rows.slice(0,6).map(r=>`<div class="recurring-item"><span class="bill-icon">↻</span><div class="recurring-info"><strong>${esc(r.merchant)}</strong><small>${esc(r.cadence)} · Next ${esc(dateLabel(r.next_expected))} · ${esc(r.confidence)} confidence</small></div><span class="bill-amount">${esc(fmt(r.typical_amount))}</span></div>`).join('');
}
function renderAlerts(d){
  const a=d.analysis,p=a.budget_plan,items=[];
  if(a.forecast.over_budget_risk)items.push({tone:'warn',text:`Projected spending exceeds your monthly budget by ${fmt(-num(a.forecast.projected_variance))}.`});
  if(num(p.budget_shortfall)>0)items.push({tone:'danger',text:`Future reserves and spending leave a budget shortfall of ${fmt(p.budget_shortfall)}.`});
  if(p.cash_headroom===null)items.push({tone:'warn',text:'No spendable cash balance entered; affordability is budget-based only.'});
  if(a.quality.possible_duplicates.length)items.push({tone:'warn',text:`${a.quality.possible_duplicates.length} group(s) of possible duplicate transactions found.`});
  if(a.quality.pending_count)items.push({tone:'',text:`${a.quality.pending_count} pending transaction(s) are excluded from posted spending.`});
  if(a.unusual_transactions_today.length)items.push({tone:'warn',text:`${a.unusual_transactions_today.length} unusually large transaction(s) flagged today.`});
  if(!items.length)items.push({tone:'',text:'Your recorded spending is within the calculated limits. Forecasts remain estimates.'});
  $('alertsList').innerHTML=items.map(item=>`<div class="alert-item ${item.tone}">${esc(item.text)}</div>`).join('');
}
function renderAllocations(a){
  const entries=Object.entries(a||{}).map(([name,v])=>({name,...v,remaining:Math.max(0,num(v.recommended_remaining))})).sort((x,y)=>y.remaining-x.remaining);
  if(!entries.length){$('allocationList').innerHTML='<div class="empty-state">Add historical transactions and optional category caps to see suggested allowances.</div>';return;}
  const max=Math.max(1,...entries.map(r=>r.remaining));
  $('allocationList').innerHTML=entries.map(r=>`<div class="allocation-row"><div class="allocation-head"><strong>${esc(r.name)}</strong><span>${esc(fmt(r.remaining,2))} remaining</span></div><div class="allocation-track"><div class="allocation-fill" style="width:${Math.min(100,r.remaining/max*100).toFixed(1)}%"></div></div><div class="allocation-foot">Spent ${esc(fmt(r.spent,2))}${r.monthly_cap!==null?` · Monthly cap ${esc(fmt(r.monthly_cap,2))}`:''}</div></div>`).join('');
}
function renderWeekdays(p){
  const names=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
  const vals=names.map(n=>num(p[n]?.average_per_calendar_day));const max=Math.max(1,...vals);
  $('weekdayChart').innerHTML=names.map((n,i)=>`<div class="weekday-col" title="${esc(`${n}: ${fmt(vals[i],2)} on average`)}"><div class="weekday-bar-area"><div class="weekday-bar" style="height:${Math.max(2,vals[i]/max*75)}px"></div></div><span class="weekday-label">${n.slice(0,3)}</span></div>`).join('');
}
function mappingRows(container,entries){
  $(container).innerHTML='';
  for(const [name,value] of Object.entries(entries||{}))addMapRow(container,name,value);
}
function addMapRow(container,name='',value=''){
  const row=document.createElement('div');row.className='mapping-row';
  row.innerHTML=`<input type="text" aria-label="Name" placeholder="Category / name" maxlength="80" value="${esc(name)}"><input type="number" aria-label="Amount" min="0" step="0.01" placeholder="0.00" value="${esc(value)}"><button type="button" class="remove-row" aria-label="Remove row" title="Remove">×</button>`;
  $(container).append(row);state.settingsDirty=true;
}
function renderSettings(settings){
  const cfg=settings.config;
  $('settingBudget').value=settings.monthly_budget;
  $('settingCash').value=cfg.spendable_cash??'';
  $('settingFuture').value=cfg.expected_other_spending;
  $('settingBudgetBuffer').value=cfg.safety_buffer;
  $('settingCashDue').value=cfg.unpaid_cash_obligations;
  $('settingCashBuffer').value=cfg.cash_buffer;
  $('settingLookback').value=cfg.lookback_months;
  mappingRows('reservesRows',cfg.essential_reserves);
  mappingRows('capsRows',cfg.category_caps);
  state.settingsDirty=false;
}
function readRows(container){
  const result={};
  for(const row of $(container).querySelectorAll('.mapping-row')){
    const [name,amt]=[...row.querySelectorAll('input')].map(x=>x.value.trim());
    if(!name&&!amt)continue;
    if(!name||amt==='')throw new Error('Each reserve or category limit needs both a name and amount.');
    if(Object.prototype.hasOwnProperty.call(result,name))throw new Error(`Duplicate label: ${name}`);
    if(num(amt)<0||!Number.isFinite(Number(amt)))throw new Error('Amounts must be finite and nonnegative.');
    result[name]=amt;
  }
  return result;
}
async function saveSettings(){
  try{
    const settings={monthly_budget:$('settingBudget').value,config:{currency:'HKD',lookback_months:$('settingLookback').value,
      spendable_cash:$('settingCash').value||null,
      expected_other_spending:$('settingFuture').value,
      safety_buffer:$('settingBudgetBuffer').value,
      unpaid_cash_obligations:$('settingCashDue').value,
      cash_buffer:$('settingCashBuffer').value,
      essential_reserves:readRows('reservesRows'),category_caps:readRows('capsRows')}};
    await api('/api/settings',{method:'PUT',body:JSON.stringify(settings)});
    state.settingsDirty=false;await refresh(true);notice('Budget settings saved and analysis updated.');
  }catch(err){notice(err.message,true);}
}
function modalShow(id){$(id).hidden=false;document.body.style.overflow='hidden';setTimeout(()=>$(id).querySelector('input')?.focus(),30);}
function modalClose(id){$(id).hidden=true;document.body.style.overflow='';}
function openTransaction(item=null){
  state.editingTx=item?item.id:null;
  $('txModalTitle').textContent=item?'Edit transaction':'Add transaction';
  $('txSaveBtn').textContent=item?'Save changes':'Save transaction';
  $('txAmount').value=item?.amount||'';
  $('txType').value=item?.kind||'expense';
  $('txStatus').value=item?.status||'posted';
  $('txDate').value=item?.date||(state.month===localMonth()?localDate():`${state.month}-01`);
  $('txCategory').value=item?.category||'';$('txMerchant').value=item?.merchant||'';
  $('txAccount').value=item?.account||'Checking';
  modalShow('txModal');
}
async function saveTransaction(event){
  event.preventDefault();const btn=$('txSaveBtn');btn.disabled=true;
  try{
    const row={amount:$('txAmount').value,kind:$('txType').value,date:$('txDate').value,
      status:$('txStatus').value,category:$('txCategory').value.trim(),
      merchant:$('txMerchant').value.trim(),account:$('txAccount').value.trim(),currency:'HKD'};
    if(!row.category)throw new Error('Please enter a transaction category.');
    const edit=state.editingTx;
    await api(edit?`/api/transactions/${encodeURIComponent(edit)}`:'/api/transactions',
      {method:edit?'PUT':'POST',body:JSON.stringify(row)});
    modalClose('txModal');
    const savedMonth=row.date.slice(0,7);
    if(savedMonth<=localMonth()&&savedMonth!==state.month){state.month=savedMonth;$('monthPicker').value=savedMonth;}
    await refresh(true);notice(edit?'Transaction updated.':'Transaction added via the CLI.');
  }catch(err){notice(err.message,true);}finally{btn.disabled=false;}
}
async function removeTransaction(id){
  if(!window.confirm('Delete this transaction permanently from the local database?'))return;
  try{await api(`/api/transactions/${encodeURIComponent(id)}`,{method:'DELETE'});await refresh(true);notice('Transaction deleted.');}
  catch(err){notice(err.message,true);}
}
function openBill(item=null){
  state.editingBill=item?.id||null;$('billModalTitle').textContent=item?'Edit confirmed bill':'Add confirmed bill';
  $('billSaveBtn').textContent=item?'Save changes':'Save bill';
  $('billName').value=item?.name||'';$('billCategory').value=item?.category||'';
  $('billAmount').value=item?.amount||'';
  const tomorrow=new Date();tomorrow.setDate(tomorrow.getDate()+1);
  $('billDue').value=item?.due||localDate(tomorrow);modalShow('billModal');
}
async function saveBill(event){
  event.preventDefault();const btn=$('billSaveBtn');btn.disabled=true;
  try{
    const row={name:$('billName').value.trim(),category:$('billCategory').value.trim(),
      due:$('billDue').value,amount:$('billAmount').value,currency:'HKD'};
    if(!row.category)throw new Error('Please enter the bill category.');
    const id=state.editingBill;
    await api(id?`/api/bills/${encodeURIComponent(id)}`:'/api/bills',
      {method:id?'PUT':'POST',body:JSON.stringify(row)});
    modalClose('billModal');await refresh(true);notice(id?'Confirmed bill updated.':'Confirmed bill added.');
  }catch(err){notice(err.message,true);}finally{btn.disabled=false;}
}
async function removeBill(id){
  if(!window.confirm('Delete this confirmed bill?'))return;
  try{await api(`/api/bills/${encodeURIComponent(id)}`,{method:'DELETE'});await refresh(true);notice('Bill removed.');}
  catch(err){notice(err.message,true);}
}
async function runPurchase(price,silent=false){
  const result=await api('/api/purchase',{method:'POST',body:JSON.stringify({month:state.month,price})});
  const el=$('purchaseResult');
  const headroom=num(result.headroom_after_purchase);
  el.className=`purchase-result ${result.affordable?'good':'bad'}`;
  el.textContent=result.affordable
    ?`✓ Within the calculated limit. ${fmt(headroom,2)} would remain after this purchase (safe limit: ${fmt(result.safe_limit,2)}).`
    :`! Exceeds the calculated limit by ${fmt(-headroom,2)} (safe limit: ${fmt(result.safe_limit,2)}).`;
  if(!silent)notice('Affordability checked using the Python engine.');
}
function wireEvents(){
  $('monthPicker').addEventListener('change',async e=>{
    const newMonth=e.target.value;
    if(!newMonth||newMonth>localMonth()){notice('Select this month or an earlier month.',true);e.target.value=state.month;return;}
    state.month=newMonth;state.lastPrice=null;
    $('purchaseResult').textContent='Enter a price to check against your selected month.';
    $('purchaseResult').className='purchase-result';
    await refresh(true);
  });
  document.querySelectorAll('[data-chart-mode]').forEach(el=>el.addEventListener('click',()=>{
    state.chartMode=el.dataset.chartMode;
    document.querySelectorAll('[data-chart-mode]').forEach(b=>b.classList.toggle('active',b===el));
    if(state.data)renderLineChart(state.data);
  }));
  $('txSearch').addEventListener('input',e=>{state.search=e.target.value;if(state.data)renderTransactions(state.data.transactions);});
  $('txKind').addEventListener('change',e=>{state.kind=e.target.value;if(state.data)renderTransactions(state.data.transactions);});
  $('addTransactionBtn').addEventListener('click',()=>openTransaction());
  $('txForm').addEventListener('submit',saveTransaction);
  $('addBillBtn').addEventListener('click',()=>openBill());
  $('billForm').addEventListener('submit',saveBill);
  $('saveSettingsBtn').addEventListener('click',saveSettings);
  $('addReserveBtn').addEventListener('click',()=>addMapRow('reservesRows'));
  $('addCapBtn').addEventListener('click',()=>addMapRow('capsRows'));
  $('purchaseForm').addEventListener('submit',async e=>{
    e.preventDefault();try{state.lastPrice=$('purchasePrice').value;await runPurchase(state.lastPrice);}catch(err){notice(err.message,true);}
  });
  $('loadDemoBtn').addEventListener('click',async()=>{
    try{await api('/api/demo/seed',{method:'POST',body:'{}'});await refresh(true);notice('Synthetic demonstration data loaded.');}
    catch(err){notice(err.message,true);}
  });
  for(const id of ['reservesRows','capsRows']){
    $(id).addEventListener('click',e=>{if(e.target.closest('.remove-row')){e.target.closest('.mapping-row').remove();state.settingsDirty=true;}});
    $(id).addEventListener('input',()=>state.settingsDirty=true);
  }
  document.querySelectorAll('#settings input').forEach(el=>el.addEventListener('input',()=>state.settingsDirty=true));
  document.addEventListener('click',e=>{
    const edit=e.target.closest('[data-tx-edit]');const remove=e.target.closest('[data-tx-delete]');
    const billEdit=e.target.closest('[data-bill-edit]');const billRemove=e.target.closest('[data-bill-delete]');
    const close=e.target.closest('[data-close]');
    if(edit){const t=state.data?.transactions.find(r=>r.id===edit.dataset.txEdit);if(t)openTransaction(t);}
    else if(remove)removeTransaction(remove.dataset.txDelete);
    else if(billEdit){const b=state.data?.bills.find(r=>r.id===billEdit.dataset.billEdit);if(b)openBill(b);}
    else if(billRemove)removeBill(billRemove.dataset.billDelete);
    else if(close)modalClose(close.dataset.close);
    else if(e.target.classList.contains('modal-backdrop'))modalClose(e.target.id);
  });
  document.addEventListener('keydown',e=>{if(e.key==='Escape')for(const id of ['txModal','billModal'])if(!$(id).hidden)modalClose(id);});
  document.querySelectorAll('.main-nav a').forEach(a=>a.addEventListener('click',()=>{
    document.querySelectorAll('.main-nav a').forEach(x=>x.classList.remove('active'));a.classList.add('active');
  }));
}
document.addEventListener('DOMContentLoaded',async()=>{
  updateIntro();wireEvents();await refresh(true);
  setInterval(()=>{if(document.visibilityState==='visible'&&$('txModal').hidden&&$('billModal').hidden)refresh(true);},15000);
});
