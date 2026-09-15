import json, time, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORK = ROOT / "video" / ".work"
CARDS_DIR = pathlib.Path(__file__).resolve().parent / "cards"
BROWSER_DIR = WORK / "browser"
BROWSER_DIR.mkdir(parents=True, exist_ok=True)
(WORK / "cards").mkdir(parents=True, exist_ok=True)

events = [json.loads(l) for l in (ROOT / "samples/pgbackrest-disk-full/run.ndjson").read_text().splitlines() if l.strip()]
EVENTS_JSON = json.dumps(events)

T1, T2, T3 = 16.651791, 34.870929, 54.994104
O1, O2 = 15.401, 27.899

DRIVER_JS = f"""
async () => {{
  const events = {EVENTS_JSON};
  function targetTime(t) {{
    const T1={T1}, T2={T2}, T3={T3}, O1={O1}, O2={O2};
    if (t <= O1) return t * (T1 / O1);
    if (t <= O2) return T1 + (t - O1) * ((T2 - T1) / (O2 - O1));
    return T2 + (t - O2) * ((T3 - T2) / (35.307 - O2));
  }}
  reset();
  state.running = true;
  document.getElementById('runLive').disabled = true;
  document.getElementById('runReplay').disabled = true;
  state.started = performance.now();
  state.timer = setInterval(tick, 100);
  let prev = 0;
  for (const e of events) {{
    const tt = targetTime(e.t ?? prev);
    const delay = Math.max(0, tt - prev);
    prev = tt;
    if (delay > 0) await new Promise(r => setTimeout(r, delay * 1000));
    e.replay = true;
    handle(e);
    if (e.type === 'analysis') {{
      document.getElementById('results').scrollIntoView({{behavior: 'smooth', block: 'start'}});
    }}
  }}
  clearInterval(state.timer); tick();
  state.running = false;
}}
"""

with sync_playwright() as p:
    browser = p.chromium.launch()

    card_page = browser.new_page(viewport={"width": 1920, "height": 1080})
    card_page.goto((CARDS_DIR / "title.html").as_uri())
    card_page.wait_for_timeout(150)
    card_page.screenshot(path=str(WORK / "cards" / "title.png"))
    card_page.goto((CARDS_DIR / "end.html").as_uri())
    card_page.wait_for_timeout(150)
    card_page.screenshot(path=str(WORK / "cards" / "end.png"))
    card_page.close()

    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        record_video_dir=str(BROWSER_DIR),
        record_video_size={"width": 1920, "height": 1080},
        accept_downloads=True,
    )
    page = context.new_page()
    page.on("download", lambda d: None)
    page.goto("http://127.0.0.1:8080/")
    page.wait_for_selector(".sample")
    page.wait_for_selector(".tab")
    page.click('.sample[data-id="pgbackrest-disk-full"]')
    page.wait_for_timeout(300)

    time.sleep(14.875465)

    time.sleep(3.0)
    page.click('.tab[data-i="1"]'); time.sleep(4.0)
    page.click('.tab[data-i="2"]'); time.sleep(3.5)
    page.click('.tab[data-i="3"]'); time.sleep(3.5)
    page.click('.tab[data-i="4"]'); time.sleep(3.96)

    page.click("#runReplay")
    page.evaluate(DRIVER_JS)

    page.click('[data-claim="root_cause"] .ref')
    time.sleep(3.0)
    page.eval_on_selector('[data-claim="causal_chain-2"]', "el => el.scrollIntoView({behavior:'smooth', block:'center'})")
    time.sleep(1.2)
    page.click('[data-claim="causal_chain-2"] .ref')
    time.sleep(4.0)
    page.eval_on_selector("#actionsBody", "el => el.scrollIntoView({behavior:'smooth', block:'center'})")
    time.sleep(1.2)
    time.sleep(5.0)
    time.sleep(3.749478)

    page.eval_on_selector("#usage", "el => el.scrollIntoView({behavior:'smooth', block:'center'})")
    time.sleep(1.0)
    time.sleep(5.0)
    page.click("#downloadMd")
    time.sleep(2.5)
    page.eval_on_selector("footer", "el => el.scrollIntoView({behavior:'smooth', block:'center'})")
    time.sleep(2.0)
    time.sleep(7.02254)

    video_path = page.video.path()
    context.close()
    browser.close()
    print("VIDEO_PATH", video_path)
