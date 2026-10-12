import asyncio,json,re
from playwright.async_api import async_playwright
# Fixture server uses MockTransport. Speech is captured, never played or sent out.
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch()
  reports=[]
  for theme in ['light','dark']:
   page=await b.new_page(viewport={'width':375,'height':812},color_scheme=theme)
   await page.add_init_script("window.__speech=[];speechSynthesis.speak=(u)=>window.__speech.push({text:u.text,lang:u.lang});window.SpeechRecognition=class{start(){window.__micLanguage=this.lang;this.onend?.();}};")
   errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto('http://127.0.0.1:8799/')
   await page.locator('#status').filter(has_text=re.compile('Connected')).wait_for()
   await page.select_option('#locale','es-US')
   await page.locator('#mic').click()
   assert await page.evaluate('window.__micLanguage')=='es-US'
   await page.locator('#share').click()
   await page.locator('#share-status').filter(has_text=re.compile('Enlace compartido')).wait_for()
   await page.locator('#check-shared').click()
   card=page.frame_locator('#verdict-card')
   await card.locator('#verdict').filter(has_text='Ten cuidado').wait_for()
   assert await card.locator('#host').text_content()=='xn--pple-43d.example'
   assert await card.locator('#yes').text_content()=='Sí'
   card_button = await card.locator('#yes').bounding_box()
   assert card_button['width'] >= 48 and card_button['height'] >= 48
   speech=await page.evaluate('window.__speech')
   assert speech[-1]['lang']=='es-US' and 'contraseña' in speech[-1]['text'] and 'garantiza' in speech[-1]['text']
   await card.locator('#no').focus(); await page.keyboard.press('Enter')
   await page.locator('#talk li').filter(has_text='De acuerdo.').wait_for()
   # Retry host adds fixed memory sentence to both transcript and voice.
   await page.locator('#check-shared').click()
   await page.locator('#talk').filter(has_text='Ya revisaste este sitio hoy.').wait_for()
   await card.locator('#yes').focus()
   assert await card.locator('#yes').evaluate('(el)=>document.activeElement===el')
   await page.fill('#say','sí')
   await page.locator('#ask button[type=submit]').click()
   await page.locator('#talk').filter(has_text='Diferencias menores').wait_for()
   controls=await page.locator('button:visible,select:visible,input[type=url]:visible,input[type=text]:visible').evaluate_all('(els)=>els.map(e=>({id:e.id,w:e.getBoundingClientRect().width,h:e.getBoundingClientRect().height,label:e.getAttribute("aria-label")||e.title||e.textContent||e.labels?.[0]?.textContent}))')
   assert all(v['w']>=48 and v['h']>=48 and v['label'] for v in controls),controls
   # Check contrast of actual rendered text on actual computed backgrounds.
   js='''(el)=>{let s=getComputedStyle(el),bg=s.backgroundColor,p=el;while(bg==='rgba(0, 0, 0, 0)'&&p.parentElement){p=p.parentElement;bg=getComputedStyle(p).backgroundColor;}return {fg:s.color,bg,outline:s.outlineStyle};}'''
   colors=[await page.locator(sel).evaluate(js) for sel in ['.note','.hint','#share','#ask button.primary']]
   for state in ['do_not_continue','caution','no_obvious_danger']:
    await card.locator('#card').evaluate('(el,state)=>el.dataset.verdict=state',state)
    colors.append(await card.locator('#verdict').evaluate(js))
   def lum(rgb):
    nums=[int(x)/255 for x in re.findall(r'\d+',rgb)[:3]]
    nums=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in nums]
    return sum(v*w for v,w in zip(nums,[.2126,.7152,.0722]))
   ratios=[(max(lum(v['fg']),lum(v['bg']))+.05)/(min(lum(v['fg']),lum(v['bg']))+.05) for v in colors]
   assert min(ratios)>=4.5,ratios
   await page.evaluate("document.body.style.zoom='2'")
   overflow=await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
   if overflow: print("OVERFLOW", await page.locator("body *").evaluate_all("els=>els.filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>({tag:e.tagName,id:e.id,cls:e.className,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})).slice(0,20)"))
   assert not overflow
   assert not errors,errors
   reports.append({'theme':theme,'controls':controls,'contrast_min':round(min(ratios),2),'zoom200_overflow':overflow,'speech_locale':speech[-1]['lang'],'page_errors':errors})
   await page.close()
  print(json.dumps(reports,ensure_ascii=False,indent=2));await b.close()
asyncio.run(main())
