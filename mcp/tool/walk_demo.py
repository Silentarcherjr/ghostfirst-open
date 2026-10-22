"""Offline Task G browser walk. Start fake_ui_server.py first; requires Playwright.

Recognised voice input and speech output are mocked; no microphone/provider use.
Screenshots go to /tmp/ghostfirst-task-g by default, never into the repository.
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, expect

SCRATCH = Path('/tmp/ghostfirst-task-g')

async def main():
    SCRATCH.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        reports = []
        for locale in ['en-US', 'es-US']:
            es = locale == 'es-US'
            for theme in ['light', 'dark']:
                page = await browser.new_page(viewport={'width':375,'height':812}, color_scheme=theme, reduced_motion='reduce')
                page.set_default_timeout(10000)
                await page.route('**/*', lambda route: route.continue_() if route.request.url.startswith('http://127.0.0.1:8799/') else route.abort())
                await page.add_init_script("""window.__speech=[];speechSynthesis.speak=u=>window.__speech.push({text:u.text,lang:u.lang});
                    window.SpeechRecognition=class{start(){this.onresult({results:[[{transcript:window.__voice}]]});this.onend?.();}};""")
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                requests = []
                page.on('request', lambda r: requests.append(r.url))
                await page.goto('http://127.0.0.1:8799/')
                await page.wait_for_function("() => document.querySelector('#status').textContent.startsWith('Connected')")
                await page.select_option('#locale', locale)
                async def ask(text):
                    await page.fill('#say',text)
                    await page.locator('#ask button[type=submit]').click()
                await ask('¿por qué?' if es else 'why?')
                assert ('Todavía' if es else 'Nothing') in await page.locator('#talk li').last.text_content()
                await page.locator('#share').click()
                await page.wait_for_function("() => document.querySelector('#share-status').textContent.includes('compartido') || document.querySelector('#share-status').textContent.includes('shared.')")
                await page.locator('#check-shared').click()
                card = page.frame_locator('#verdict-card')
                await card.locator('#yes').wait_for()
                assert await card.locator('#visitors').is_hidden()  # Single visit is not a comparison.
                await card.locator('#yes').click()
                await card.locator('.visitor').nth(2).wait_for()
                assert await card.locator('.visitor').count() == 3
                tiles = await card.locator('.visitor').all_text_contents()
                assert ('Teléfono' if es else 'Phone') in tiles[0]
                assert 'xn--pple-43d.example' in tiles[0]
                assert ('Contraseña' if es else 'Password') in tiles[0]
                assert ('Código' if es else 'Code') in tiles[0]
                assert ('Inicio de sesión' if es else 'Sign-in') in tiles[1]
                assert ('Otro navegador' if es else 'Another browser') in tiles[2]
                assert ('No se pudo acceder' if es else "Couldn't reach") in tiles[2]
                assert await card.locator('[data-differs=true]').count() == 3
                before = len(requests)
                for question, expected in [
                    ('¿por qué?' if es else 'why?', 'direcciones' if es else 'addresses'),
                    ('¿qué hago?' if es else 'what should I do?', 'otro medio' if es else 'another channel'),
                    ('¿qué vio cada visitante?' if es else 'what did each visitor see?', 'Otro navegador' if es else 'Another browser'),
                    ('xyz unrecognised', 'Comparte el enlace' if es else 'Tell me the link')]:
                    await ask(question)
                    assert expected in await page.locator('#talk li').last.text_content()
                # Mocked recognition traverses the actual mic handler, then the same hear().
                await page.evaluate('(text)=>window.__voice=text', '¿qué vio cada visitante?' if es else 'what did each visitor see?')
                await page.locator('#mic').click()
                speech = await page.evaluate('window.__speech.at(-1)')
                assert speech['lang'] == locale and ('Otro navegador' if es else 'Another browser') in speech['text']
                assert len(requests) == before, 'Follow-ups must make zero network requests'
                assert 'safe' not in speech['text'].lower()
                # Shared renderer: majority highlights only the differing tile; absent and
                # unknown profiles never borrow another visitor's evidence.
                rows = await page.evaluate("""() => VisitorView.rows({visitors:[
                    {profile:'android_mobile',final_host:'same.example',reached_page:true,requested:['payment']},
                    {profile:'desktop_chrome',final_host:'same.example',reached_page:true,requested:['payment']},
                    {profile:'unknown',final_host:'invented.example',reached_page:true,requested:['password']}]},false)""")
                assert [r['differs'] for r in rows] == [False,False,True]
                assert rows[2]['host'] == '' and not rows[2]['reached'] and rows[2]['fields'] == []
                for zoom in [1,2]:
                    await page.evaluate('(z)=>document.body.style.zoom=z', str(zoom))
                    assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                    metrics = await card.locator('body').evaluate('()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,items:[...document.querySelectorAll("body *")].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>({id:e.id,width:e.clientWidth,scroll:e.scrollWidth}))})')
                    assert metrics['scroll'] <= metrics['width']+1, (locale,theme,zoom,metrics)
                    await page.locator('#verdict-card').evaluate('(e)=>window.scrollTo(0,scrollY+e.getBoundingClientRect().top)')
                    await page.screenshot(path=str(SCRATCH/f'{locale}-{theme}-{zoom}x.png'))
                    await card.locator('.visitor').nth(2).scroll_into_view_if_needed()
                    await page.screenshot(path=str(SCRATCH/f'{locale}-{theme}-{zoom}x-last-visitor.png'))
                await page.evaluate("document.body.style.zoom='1'")
                await page.set_viewport_size({'width':1600,'height':1000})
                boxes = [await card.locator('.visitor').nth(i).bounding_box() for i in range(3)]
                assert max(b['y'] for b in boxes)-min(b['y'] for b in boxes) < 2, boxes
                await page.locator('#verdict-card').evaluate('(e)=>window.scrollTo(0,scrollY+e.getBoundingClientRect().top)')
                await page.screenshot(path=str(SCRATCH/f'{locale}-{theme}-desktop.png'))
                # Additional structured-result mocks cover every guidance branch.
                for state in ['do_not_continue','caution','no_obvious_danger']:
                    await page.evaluate('(state)=>conversation.lastResult={status:"checked",verdict:state,reasons:[],differences:[]}', state)
                    await ask('¿qué hago?' if es else 'what should I do?')
                    answer = await page.locator('#talk li').last.text_content()
                    assert ('garantía' if es else 'guarantee') in answer if state == 'no_obvious_danger' else ('No ingreses' if es else "Don't enter") in answer
                    assert 'safe' not in answer.lower()
                # Empty deep evidence produces three unavailable tiles, with no host/fields.
                await page.evaluate('()=>renderCard({locale,status:"checked",visitors:[]})')
                await card.locator('.visitor').nth(2).wait_for()
                await expect(card.locator('.field-chips li')).to_have_count(0)
                assert await card.locator('.visitor').filter(has_text='No se pudo acceder' if es else "Couldn't reach").count() == 3
                assert not errors, errors
                reports.append({'locale':locale,'theme':theme,'tiles':tiles,'follow_up_network_requests':len(requests)-before,'voice':'mocked recognition and synthesis','errors':errors})
                await page.close()
        await browser.close()
        (SCRATCH/'walk.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2))
        print(json.dumps(reports,ensure_ascii=False,indent=2))

asyncio.run(main())
