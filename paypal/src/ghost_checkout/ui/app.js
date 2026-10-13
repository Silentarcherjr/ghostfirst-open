'use strict';
const $=id=>document.getElementById(id);
let csrf='',order=null,latest=null;
async function api(path,data){
  const r=await fetch(path,{method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:data===undefined?undefined:JSON.stringify(data)});
  const result=await r.json();if(!r.ok)throw new Error(result.error_code||'operation_failed');return result;
}
function say(text){const p=document.createElement('p');p.textContent=text;$('chat').append(p);}
function show(result){
  latest=result;$('traffic').textContent=JSON.stringify(result.traffic||[],null,2);say(result.answer||'Review the result.');
  if(result.evidence){const ev=result.evidence;const labels={no_obvious_danger:'No suspicious behavior observed',caution:'Caution',do_not_continue:'Do not continue'};
    $('verdict').textContent=labels[ev.verdict]||'Check did not complete';$('merchant').textContent='Observed merchant: '+(ev.observed_merchant||[]).join(', ');
    $('reasons').replaceChildren();for(const reason of ev.reasons||[]){const li=document.createElement('li');li.textContent=reason.text;$('reasons').append(li);} $('why').open=true;}
  if(result.status==='buyer_approval_required'){order=result.order;$('pay').hidden=false;}
  if(result.status==='captured'){$('pay').hidden=true;$('payment-state').textContent='Mock capture verified. No real payment.';}
  if(result.error)say(result.error.message||'Checkout stopped.');
}
async function poll(){
  try{const state=await api('/api/state');
    if(state.confirmation){$('confirmation').hidden=false;$('confirm-message').textContent=state.confirmation.message;
      const choice=$('merchant-choice');if(!choice.options.length){for(const id of state.confirmation.merchants){const opt=document.createElement('option');opt.value=id;opt.textContent=id;choice.append(opt);} $('confirm-yes').focus();}}
    else $('confirmation').hidden=true;
    if(state.result && !latest){show(state.result);return;}
    if(state.running)setTimeout(poll,250);
  }catch(error){say('The operation stopped. Start a fresh session.');}
}
$('purchase').addEventListener('submit',async event=>{event.preventDefault();$('purchase').querySelector('button').disabled=true;latest=null;
  say('Checking the store through Ghost Checkout…');
  try{await api('/api/chat',{store:$('store').value,item:$('item').value,amount:$('amount').value,currency:'USD'});poll();}
  catch(error){say('The operation stopped: '+error.message);$('purchase').querySelector('button').disabled=false;}
});
for(const [id,proceed] of [['confirm-yes',true],['confirm-no',false]])$(id).addEventListener('click',async()=>{
  try{await api('/api/confirm',{proceed,merchant_id:$('merchant-choice').value});$('confirmation').hidden=true;poll();}catch(error){say('Confirmation did not complete.');}
});
$('pay').addEventListener('click',async()=>{
  if(!order)return;$('pay').disabled=true;
  try{const sdk=await window.paypal.createInstance({clientId:'MOCK_CLIENT',components:['paypal-payments']});
    const methods=await sdk.findEligibleMethods({currencyCode:'USD'});if(!methods.isEligible('paypal'))throw new Error('unavailable');
    const session=sdk.createPayPalOneTimePaymentSession({onApprove:async data=>{
      const result=await api('/api/mock-approve',{order_id:data.orderId});show(result);$('pay').disabled=false;
    },onCancel:()=>{$('pay').disabled=false;say('Mock payment cancelled.');}});
    await session.start({presentationMode:'auto'},Promise.resolve({orderId:order.order_id}));
  }catch(error){say('Payment step stopped. Do not retry automatically.');}
});
(async()=>{const config=await api('/api/session');csrf=config.csrf;$('purchase').querySelector('button').disabled=false;})().catch(()=>say('Session could not start.'));
