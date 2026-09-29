# Every power throws a visible burst in its own colour when it is let off, and asks for its own
# sound. Placed powers (wall, dome, black hole) burst where they land as well as at the tank.
import asyncio, os, subprocess, time, sys, tempfile
from playwright.async_api import async_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8820; MOCK = os.path.join(ROOT, 'tools', 'mock-three.js')
DATA = tempfile.mkdtemp(prefix='kt-b19-')
# tank → its power, and the sound it should ask for
POWERS = [('zagros','wall','abWall'), ('baz','drone','abDrone'), ('halgurd','dome','dome'),
          ('rashaba','cloak','cloak'), ('safeen','homing','abMissile'), ('bradost','freeze','abFreezeCast'),
          ('korek','heal','abHeal'), ('newroz','hole','blackhole')]
PLACED = {'wall', 'dome', 'hole'}

async def main():
    srv = subprocess.Popen(['node', 'server/index.js'], cwd=ROOT,
        env={**os.environ, 'PORT': str(PORT), 'DATA_DIR': DATA, 'REG_LIMIT': '100'}, stdout=subprocess.PIPE)
    time.sleep(0.9)
    errs = []; fails = []
    def ok(c, m):
        print(('  ok   ' if c else '  FAIL ') + m)
        if not c: fails.append(m)
    try:
        async with async_playwright() as pw:
            br = await pw.chromium.launch()
            ctx = await br.new_context(viewport={'width': 900, 'height': 420}, service_workers='block')
            p = await ctx.new_page()
            p.on('pageerror', lambda e: errs.append(f'PAGEERROR {e}'))
            await p.route('https://cdn.jsdelivr.net/**', lambda r: r.fulfill(path=MOCK, content_type='text/javascript'))
            await p.route('https://fonts.googleapis.com/**', lambda r: r.fulfill(body='', content_type='text/css'))
            await p.goto(f'http://localhost:{PORT}/'); await p.wait_for_selector('#scr-menu:not([hidden])')
            await p.wait_for_function('window.__tf'); await p.evaluate("__tf.setName('Hemin')")
            await p.click('#btnPractice'); await p.wait_for_selector('#scr-lobby:not([hidden])')
            await p.wait_for_function("__tf.room && __tf.room.players.length>=4", timeout=15000)
            await p.click('#btnStart'); await p.wait_for_selector('#hud:not([hidden])', timeout=15000)
            await p.wait_for_timeout(1200)
            # record every sound the game asks for, without making any noise
            await p.evaluate("""() => { window.__snd = []; window.__cast = [];
              const a = __tf.game.audio, real = a.play.bind(a);
              a.play = (n, pos, v) => { window.__snd.push(n); try { return real(n, pos, v); } catch (e) {} };
              const fx = __tf.game.W.abfx, rc = fx.cast.bind(fx);
              fx.cast = (ab, x, y, z, sc) => { window.__cast.push({ ab, x, z, sc: sc || 1 }); return rc(ab, x, y, z, sc); };
            }""")

            for tank, ab, snd in POWERS:
                await p.evaluate("__tf.tryTank(arguments[0], 5)", tank) if False else await p.evaluate(f"__tf.tryTank('{tank}', 5)")
                await p.wait_for_timeout(700)
                await p.evaluate("window.__snd = []; window.__cast = [];")
                await p.evaluate("""() => {
                  const n = __tf.net; n.ab.chg = n.ab.need; n.armAbility();
                  __tf.game.input.aimWorld = { x: n.me.x + 18, z: n.me.z + 16 };
                  __tf.game.input.firePulse = true;
                }""")
                await p.wait_for_timeout(900)
                got = await p.evaluate("""() => ({ casts: window.__cast.length, cast: window.__cast.slice(),
                    snd: window.__snd.slice() })""")
                ok(got['casts'] >= 1, f'{tank}: {ab} throws a burst when let off ({got["casts"]})')
                ok(all(c['ab'] == ab for c in got['cast']), f'{tank}: the burst is coloured for {ab}')
                ok(snd in got['snd'], f'{tank}: it makes its own sound ({snd})' + ('' if snd in got['snd'] else f' — heard {got["snd"]}'))
                if ab in PLACED:
                    ok(got['casts'] >= 2, f'{tank}: and a second burst where it lands ({got["casts"]})')
                    if got['casts'] >= 2:
                        ok(any(c['sc'] < 1 for c in got['cast']), f'{tank}: the landing burst is the smaller of the two')

            # the bursts clear themselves away rather than piling up
            await p.wait_for_timeout(1200)
            ok(await p.evaluate("__tf.game.W.abfx.casts.length === 0"), 'bursts clear themselves once they finish')
            await br.close()
    finally:
        srv.terminate()
    for e in errs: print('  ' + e)
    bad = fails + errs
    print(('FAILED: %d' % len(bad)) if bad else 'browser-test19: all good')
    sys.exit(1 if bad else 0)

asyncio.run(main())
