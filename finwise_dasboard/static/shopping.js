/* Finwise Shopping: browser-only UI state. Financial authority remains in Python. */
'use strict';
(() => {
  const el = id => document.getElementById(id);
  const money = x => 'HK$' + (Number(x) || 0).toLocaleString('en-HK', {maximumFractionDigits: 2, minimumFractionDigits: 2});
  const escapeHtml = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const safeLink = u => { try { const x = new URL(u); return ['https:', 'http:'].includes(x.protocol) ? x.href : null; } catch { return null; } };
  const state = { coords: null, lastPolicy: null, busy: false };

  async function request(path, opts={}) {
    const response = await fetch(path, { cache:'no-store', ...opts,
      headers: {'Content-Type':'application/json', ...(opts.headers||{})} });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
    return body;
  }
  async function updateStatus() {
    try {
      const s = await request('/api/shopping/status');
      const box = el('shoppingConnection');
      if (s.demo_mode) {
        box.className='shopping-connection';
        box.textContent='Demonstration mode · Results are fictional. Disable SHOPPING_DEMO for live OpenRouter + Tavily results.';
      } else if (s.configured) {
        box.className='shopping-connection';
        box.textContent=`OpenRouter + Tavily ready (${s.model}). Web access required; location is optional.`;
      } else {
        box.className='shopping-connection warning';
        box.textContent='Shopping requires two keys: OPENROUTER_API_KEY and TAVILY_API_KEY. Copy .env.example to .env, add both, and restart.';
      }
    } catch (e) {
      el('shoppingConnection').textContent='Unable to contact the local shopping API: '+e.message;
    }
  }
  async function updatePolicy() {
    try {
      const p=await request('/api/shopping/policy');
      state.lastPolicy=p;
      el('shoppingMaxPrice').textContent=money(p.maximum_total_purchase_hkd);
      el('shoppingSafe').textContent=money(p.safe_discretionary_hkd);
      el('shoppingDaily').textContent=money(p.safe_daily_allowance_hkd);
      el('shoppingForecastHead').textContent=money(p.forecast_headroom_hkd);
      el('shoppingBills').textContent=money(p.protected_confirmed_bills_hkd);
      el('shoppingCapExplanation').textContent = Number(p.maximum_total_purchase_hkd) <= 0
        ? 'No discretionary shopping budget is available right now. Protect your essential expenses first.'
        : `A conservative cap based on your safe limit, three daily allowances, and a 20% margin on projected headroom. ${p.cash_verified?'Cash balance has also been checked.':'Add spendable cash under Budget Settings for a cash-verified limit.'}`;
      el('shoppingSearchBtn').disabled = Number(p.maximum_total_purchase_hkd) <= 0;
    } catch (e) {
      el('shoppingCapExplanation').textContent='Could not calculate the shopping limit: '+e.message;
    }
  }
  function makeProduct(p) {
    const wrap=document.createElement('article');
    wrap.className='shopping-product';
    const href=safeLink(p.url);
    wrap.innerHTML=`<span class="shopping-icon" aria-hidden="true">♧</span>
      <h4>${escapeHtml(p.name)}</h4>
      <div class="shopping-merchant">${escapeHtml(p.store)}</div>
      <div class="shopping-price">${money(p.total_hkd)}</div>
      <div class="shopping-tags"><span>Within calculated cap</span></div>
      <p class="shopping-note">${escapeHtml(p.note || 'Check the current price and availability directly with the seller.')}</p>
      <small class="muted" style="font-size:10px">Search-based listing · Verify seller details</small>
      ${href?`<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">View seller listing ↗</a>`:'<small class="muted">No source link provided</small>'}`;
    return wrap;
  }
  function makeStore(p) {
    const wrap=document.createElement('article');
    wrap.className='shopping-store';
    const href=safeLink(p.url);
    wrap.innerHTML=`<h4>◎ ${escapeHtml(p.name)}</h4>
      <p>${escapeHtml(p.area || 'Area not specified')}</p>
      <p>${escapeHtml(p.note || 'Contact the store before visiting.')}</p>
      ${href?`<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Open store source ↗</a>`:''}`;
    return wrap;
  }
  function renderResults(result) {
    const products=el('shoppingProductGrid'),stores=el('shoppingStoreGrid'),sources=el('shoppingSources');
    products.replaceChildren();stores.replaceChildren();sources.replaceChildren();
    el('shoppingResultsMessage').textContent=result.message||'';
    if (result.status==='demo') {
      el('shoppingResultsMessage').textContent='⚠ FICTIONAL CLASSROOM DEMO — '+(result.message||'');
    }
    for (const p of result.products||[]) products.append(makeProduct(p));
    for (const s of result.stores||[]) stores.append(makeStore(s));
    const actualSources=(result.sources||[]).filter(s=>safeLink(s.url));
    for (const s of actualSources) {
      const a=document.createElement('a');a.href=safeLink(s.url);
      a.target='_blank';a.rel='noopener noreferrer';a.textContent=s.title||'View source';
      sources.append(a);
    }
    const count=(result.products||[]).length;
    el('shoppingResultsCount').textContent=result.status==='wait'?'Not recommended':`${count} within budget`;
    el('shoppingStoreSection').hidden=!(result.stores||[]).length;
    el('shoppingSourcesSection').hidden=!actualSources.length;
    if (result.research_text) {
      const raw=document.createElement('details');raw.className='shopping-result-raw';
      const heading=document.createElement('summary');heading.textContent='Show AI research text (unstructured)';
      const pre=document.createElement('p');pre.textContent=result.research_text;
      raw.append(heading,pre);products.append(raw);
    }
    if (count===0 && result.status==='ok') {
      const msg=document.createElement('p');msg.className='muted';
      msg.textContent='No price-checked listings under your cap were returned. Check the sources or adjust your search terms. Unpriced products are deliberately excluded.';
      products.append(msg);
    }
    el('shoppingDisclaimer').textContent=(result.warnings||[]).join(' ') ||
      'AI suggestions are not verified stock or financial guarantees. No purchase is made through Finwise.';
  }
  async function submitSearch(event) {
    event.preventDefault();
    if(state.busy)return;
    const query=el('shoppingQuery').value.trim();
    const mode=el('shoppingMode').value;
    const location=el('shoppingLocation').value.trim();
    if (mode!=='online' && !location && !state.coords) {
      el('shoppingResultsMessage').textContent='Enter a city/area or click “Use my current location” for nearby searches.';
      el('shoppingLocation').focus();return;
    }
    state.busy=true;
    const button=el('shoppingSearchBtn');button.disabled=true;button.textContent='Researching options…';
    el('shoppingResultsCount').textContent='Searching';
    el('shoppingResultsMessage').textContent='Searching for real listings with Tavily, then evaluating with OpenRouter and your financial limit…';
    el('shoppingProductGrid').replaceChildren();
    try {
      const result=await request('/api/shopping/recommend', {
        method:'POST',body:JSON.stringify({query,mode,location:{label:location,...(state.coords||{})}})});
      renderResults(result);
    } catch (e) {
      el('shoppingResultsCount').textContent='Unavailable';
      el('shoppingResultsMessage').textContent=e.message;
    } finally {
      state.busy=false;button.textContent='✳  Find affordable options';
      button.disabled=Number(state.lastPolicy?.maximum_total_purchase_hkd||0)<=0;
    }
  }
  function useLocation() {
    if (!navigator.geolocation) {
      el('shoppingLocationStatus').textContent='Your browser does not support geolocation. Enter your city manually.';
      return;
    }
    el('shoppingLocationStatus').textContent='Asking for location permission…';
    navigator.geolocation.getCurrentPosition(position=>{
      state.coords={latitude:position.coords.latitude, longitude:position.coords.longitude};
      el('shoppingLocationStatus').textContent='Location ready for this search only (not saved).';
      if (!el('shoppingLocation').value.trim()) el('shoppingLocation').placeholder='Current device location selected';
    }, err=>{
      state.coords=null;
      el('shoppingLocationStatus').textContent='Location unavailable or denied. Enter a city/area manually.';
    },{enableHighAccuracy:false,timeout:12000,maximumAge:30000});
  }
  document.addEventListener('DOMContentLoaded',()=>{
    el('shoppingForm').addEventListener('submit',submitSearch);
    el('shoppingUseLocation').addEventListener('click',useLocation);
    el('shoppingLocation').addEventListener('input',()=>{
      // Manual area takes precedence over previously-granted precise coordinates.
      if (state.coords) {state.coords=null;el('shoppingLocationStatus').textContent='Using manually entered area.';}
    });
    updateStatus();updatePolicy();
    document.addEventListener('finwise:updated',updatePolicy);
  });
})();
