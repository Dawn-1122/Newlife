/**
 * 名堂 · 预览自检探针（开发用）
 *
 * 干什么：用本机 Chrome 的无头模式打开 tools/preview/，逐页巡检，
 * 把页面自己产出的自检报告（<script id="wb-report">）+ 控制台报错 + 截图抓出来。
 * 于是「预览到底有没有真的跑起来」可以**不靠肉眼**判定。
 *
 * 两个坑，已在实现里绕开（改代码时别踩回去）：
 *   1) 不能「一页起一次 Chrome」—— 这台机器上沙箱会拦截 Chrome 的签名克隆，
 *      冷启动要 ~36s，8 页就是十分钟。所以**一个 Chrome 实例巡检到底**。
 *   2) 不能用固定调试端口 + 复用 profile —— 上一次没退干净的实例会占着端口，
 *      表现为「WebSocket 连上了但 Runtime.enable 永远不返回」。
 *      改用 --remote-debugging-port=0（系统分配）+ 每次独立的 profile 目录，
 *      端口从 profile 里的 DevToolsActivePort 文件读。
 *
 * 只依赖 Node 内置能力（Node 22 自带 WebSocket / fetch），不装任何包。
 *
 * 用法：
 *   node tools/preview/probe.js                        # 巡检常用页面
 *   node tools/preview/probe.js --all                  # 连冷门页一起巡检
 *   node tools/preview/probe.js pages/bazi/bazi        # 只看一页
 *   node tools/preview/probe.js --flow                 # 跑通真实起名流程，再看结果页/详情页
 *   node tools/preview/probe.js --out /tmp/shots
 *
 * 前置：后端 :8000 与预览服务 :8899 都要在跑（起名、测评要真后端）。
 */

import { spawn } from 'node:child_process'
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { setTimeout as sleep } from 'node:timers/promises'

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const BASE = process.env.PREVIEW_BASE || 'http://127.0.0.1:8899'

const argv = process.argv.slice(2)
const outIdx = argv.indexOf('--out')
const OUT_DIR = outIdx === -1 ? '/tmp/mingtang-shots' : argv[outIdx + 1]
const WITH_FLOW = argv.includes('--flow')
const ALL = argv.includes('--all')
const PAGES = argv.filter((a) => a.startsWith('pages/'))

const COMMON_PAGES = [
  'pages/home/home',
  'pages/name/name',
  'pages/wizard/wizard',
  'pages/more/more',
  'pages/analyze/analyze',
  'pages/bazi/bazi'
]
const EXTRA_PAGES = ['index/index', 'prenatal-result/prenatal-result', 'analyze-result/analyze-result'].map(
  (p) => 'pages/' + p
)

// 直接跳过去没有上下文的页面：靠 --flow 或前置动作喂数据后才看
const CONTEXT_PAGES = ['pages/result/result', 'pages/detail/detail']

mkdirSync(OUT_DIR, { recursive: true })

// ══════════════════════════════════════════════════════════════
// Chrome 启动与 CDP 连接
// ══════════════════════════════════════════════════════════════

/**
 * 起一个可用的 Chrome 并返回 CDP 会话。
 *
 * 为什么要写成「失败就整只重来」的循环：本机沙箱下 Chrome 的 GPU 子进程
 * 会间歇性起不来（日志里是 `GPU process isn't usable. Goodbye.`），
 * 表现是 DevToolsActivePort 已经写出来了、但调试端点马上消失。
 * 同一组参数这一分钟 3/3 成功、下一分钟必然失败，纯属抖动。
 * 因此不押注单次启动，而是最多重试若干次，失败就把进程杀了换 profile 重开。
 */
const CHROME_FLAGS = [
  '--headless=new',
  '--remote-debugging-port=0',
  '--remote-allow-origins=*',
  '--no-first-run',
  '--no-default-browser-check',
  '--no-sandbox',
  '--disable-gpu',
  '--disable-gpu-sandbox',
  '--use-angle=swiftshader',
  '--disable-dev-shm-usage',
  '--hide-scrollbars',
  '--force-device-scale-factor=2',
  '--window-size=560,1150'
]

const consoleLines = []
let label = 'boot'

/** 极简 CDP 客户端：只用到 send + 事件回调 */
class CDP {
  constructor(ws) {
    this.ws = ws
    this.seq = 0
    this.pending = new Map()
    this.onEvent = () => {}
    ws.addEventListener('message', (ev) => {
      let msg
      try {
        msg = JSON.parse(ev.data)
      } catch {
        return
      }
      if (msg.id !== undefined) {
        const p = this.pending.get(msg.id)
        if (!p) return
        this.pending.delete(msg.id)
        if (msg.error) p.reject(new Error(JSON.stringify(msg.error)))
        else p.resolve(msg.result)
      } else {
        this.onEvent(msg)
      }
    })
  }
  send(method, params = {}, timeoutMs = 120000) {
    const id = ++this.seq
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.ws.send(JSON.stringify({ id, method, params }))
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id)
          reject(new Error('CDP 超时: ' + method))
        }
      }, timeoutMs)
    })
  }
}

async function readDevToolsPort(profile, timeoutMs = 20000) {
  const file = `${profile}/DevToolsActivePort`
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const first = readFileSync(file, 'utf8').split('\n')[0]
      if (first) return parseInt(first, 10)
    } catch {
      /* 还没写出来 */
    }
    await sleep(200)
  }
  throw new Error('等不到 DevToolsActivePort')
}

async function findPageTarget(port, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs
  let last = '（还没试）'
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/list`)
      const list = await res.json()
      const t = list.find((x) => x.type === 'page' && x.webSocketDebuggerUrl)
      if (t) return t
      last = `无 page 目标（${list.map((x) => x.type).join(',')}）`
    } catch (err) {
      last = 'fetch 失败: ' + err.message
    }
    await sleep(250)
  }
  throw new Error('找不到可调试的页面目标：' + last)
}

function attachConsoleTap(client) {
  client.onEvent = (msg) => {
    if (msg.method === 'Runtime.consoleAPICalled') {
      const text = (msg.params.args || [])
        .map((a) => (a.value !== undefined ? a.value : a.description || a.type))
        .join(' ')
      consoleLines.push({ label, level: msg.params.type, text })
    } else if (msg.method === 'Runtime.exceptionThrown') {
      const d = msg.params.exceptionDetails
      const text = (d.exception && (d.exception.description || d.exception.value)) || d.text
      consoleLines.push({ label, level: 'uncaught', text: String(text) })
    } else if (msg.method === 'Log.entryAdded') {
      const e = msg.params.entry
      if (e.level === 'error' || e.level === 'warning') {
        consoleLines.push({ label, level: 'log:' + e.level, text: e.text + (e.url ? ' @' + e.url : '') })
      }
    }
  }
}

async function bringUpChrome(maxAttempts = 8) {
  let lastErr = null
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const profile = `/tmp/mingtang-probe-${process.pid}-${attempt}`
    rmSync(profile, { recursive: true, force: true })
    const child = spawn(CHROME, [...CHROME_FLAGS, `--user-data-dir=${profile}`, 'about:blank'], {
      stdio: 'ignore'
    })
    let sock = null
    try {
      const port = await readDevToolsPort(profile)
      const target = await findPageTarget(port)
      sock = new WebSocket(target.webSocketDebuggerUrl)
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('WebSocket 打开超时')), 8000)
        sock.addEventListener('open', () => { clearTimeout(timer); resolve() })
        sock.addEventListener('error', () => { clearTimeout(timer); reject(new Error('WebSocket 打开失败')) })
      })
      const client = new CDP(sock)
      attachConsoleTap(client)
      await client.send('Browser.getVersion', {}, 8000)
      await client.send('Runtime.enable', {}, 10000)
      await client.send('Log.enable', {}, 10000)
      await client.send('Page.enable', {}, 10000)
      console.log(`[probe] Chrome 就绪（第 ${attempt} 次尝试，端口 ${port}）`)
      return { child, profile, client }
    } catch (err) {
      lastErr = err
      console.log(`[probe] 第 ${attempt} 次启动 Chrome 未就绪（${err.message}），换一只重来…`)
      try { sock && sock.close() } catch { /* ignore */ }
      try { child.kill('SIGKILL') } catch { /* ignore */ }
      rmSync(profile, { recursive: true, force: true })
      await sleep(700)
    }
  }
  throw new Error('多次尝试仍拿不到可用的 Chrome：' + (lastErr && lastErr.message))
}

/** 连一只已经在跑的无头 Chrome（推荐：一次起好，反复巡检，省掉冷启动） */
async function attachChrome(port) {
  let lastErr = null
  for (let attempt = 1; attempt <= 5; attempt++) {
    let sock = null
    try {
      const target = await findPageTarget(port, 5000)
      sock = new WebSocket(target.webSocketDebuggerUrl)
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('WebSocket 打开超时')), 8000)
        sock.addEventListener('open', () => { clearTimeout(timer); resolve() })
        sock.addEventListener('error', () => { clearTimeout(timer); reject(new Error('WebSocket 打开失败')) })
      })
      const client = new CDP(sock)
      attachConsoleTap(client)
      await client.send('Browser.getVersion', {}, 8000)
      await client.send('Runtime.enable', {}, 10000)
      await client.send('Log.enable', {}, 10000)
      await client.send('Page.enable', {}, 10000)
      console.log(`[probe] 已连上常驻 Chrome :${port}`)
      return { child: null, profile: null, client }
    } catch (err) {
      lastErr = err
      try { sock && sock.close() } catch { /* ignore */ }
      await sleep(600)
    }
  }
  throw new Error(
    `连不上常驻 Chrome :${port}（${lastErr && lastErr.message}）。` +
      '先起一只：见 tools/preview/README.md 的「常驻 Chrome」一节。'
  )
}

const startedAt = Date.now()
const attachIdx = argv.indexOf('--attach')
const attachPort =
  attachIdx !== -1
    ? parseInt(argv[attachIdx + 1], 10) || 9222
    : process.env.PREVIEW_CHROME_PORT
      ? parseInt(process.env.PREVIEW_CHROME_PORT, 10)
      : null
const { child: chrome, profile: PROFILE, client: cdp } = attachPort
  ? await attachChrome(attachPort)
  : await bringUpChrome()
console.log(`[probe] 共耗时 ${((Date.now() - startedAt) / 1000).toFixed(1)}s`)

// 视口：预览壳是「手机壳 390px + 日志侧栏 320px」，窗口太窄会把手机裁掉。
// 用 Emulation 覆写而不是依赖 Chrome 启动参数，--attach 连上现成浏览器时也能改。
await cdp.send('Emulation.setDeviceMetricsOverride', {
  width: 1100,
  height: 1200,
  deviceScaleFactor: 2,
  mobile: false
})

async function evaluate(expr) {
  // 注意：CDP.send 返回的已经是 Runtime.evaluate 的 result 对象
  //（形如 { result: {type,value}, exceptionDetails? }），别再往里剥一层。
  const r = await cdp.send('Runtime.evaluate', {
    expression: expr,
    returnByValue: true,
    awaitPromise: true
  })
  if (r.exceptionDetails) {
    const d = r.exceptionDetails
    return { __err: d.text + ' ' + (d.exception?.description || '') }
  }
  return r.result ? r.result.value : undefined
}

async function screenshot(name) {
  // .screen 是内部滚动容器（760px），captureBeyondViewport 只能展开页面本身，
  // 展不开容器 —— 截图前临时把它撑开，才能截到完整页面内容。
  await evaluate(
    '(function(){var s=document.querySelector(".screen");if(s){s.dataset.h=s.style.height;s.style.height="auto"}return 1})()'
  ).catch(() => 1)
  const r = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  const file = `${OUT_DIR}/${name.replace(/\//g, '_')}.png`
  writeFileSync(file, Buffer.from(r.data, 'base64'))
  await evaluate(
    '(function(){var s=document.querySelector(".screen");if(s&&s.dataset.h!==undefined){s.style.height=s.dataset.h}return 1})()'
  ).catch(() => 1)
  return file
}

/** 等某个 JS 条件成立 */
async function waitJs(predicate, timeoutMs = 60000, step = 200) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const v = await evaluate(predicate)
    if (v === true) return true
    await sleep(step)
  }
  return false
}

// ── 打开预览页（会顺带等 __wb 就绪）─────────────────────────────
console.log('[probe] 打开预览页 …')
await cdp.send('Page.navigate', { url: `${BASE}/?logs=1` })
const booted = await waitJs('!!(window.__wb && window.__wb.report)', 90000)
if (!booted) {
  console.error('[probe] 预览页 __wb 未就绪，后续结果不可信')
}

async function report() {
  return (await evaluate('window.__wb ? JSON.stringify(window.__wb.report()) : null')) || null
}

// ══════════════════════════════════════════════════════════════
// 巡检
// ══════════════════════════════════════════════════════════════

const results = []

async function inspect(page, note) {
  label = page
  const before = consoleLines.length
  await evaluate(`window.__wb.goto(${JSON.stringify(page)})`)
  const ok = await waitJs(
    `(function(){var r=window.__wb.report();return r && r.page === ${JSON.stringify(page)}})()`,
    20000,
    150
  )
  await sleep(1600) // 等异步请求 / 首屏动画
  const rep = JSON.parse((await report()) || '{}')
  const shot = await screenshot(page)
  const issues = consoleLines.slice(before)
  const text = await evaluate(
    '(function(){var m=document.getElementById("mount");return m?m.innerText.replace(/\\s+/g," ").slice(0,300):""})()'
  )
  const els = await evaluate(
    '(function(){var m=document.getElementById("mount");return m?m.querySelectorAll("[data-wb-h]").length:-1})()'
  )
  results.push({ page, note, reached: ok, rep, issues, shot, text, handlers: els })
}

async function runFlow() {
  label = 'flow'
  const before = consoleLines.length
  console.log('[probe] 跑通真实起名流程（资料 → 感觉 → 生成 → 结果）…')
  await evaluate('window.__wb.flow({ surname: "林", birthDate: "1994-05-20" })')
  const done = await waitJs(
    '(function(){var r=window.__wb.report();return r && (r.flowDone === true || r.flowDone === false || r.flowError)})()',
    90000,
    400
  )
  await sleep(2000)
  const rep = JSON.parse((await report()) || '{}')
  const shot = await screenshot('flow-result')
  const issues = consoleLines.slice(before)
  const text = await evaluate(
    '(function(){var m=document.getElementById("mount");return m?m.innerText.replace(/\\s+/g," ").slice(0,300):""})()'
  )
  results.push({
    page: 'flow（资料→感觉→生成）',
    note: '停在 ' + (rep.flowAt || rep.page || '?'),
    reached: done && rep.flowDone === true,
    rep,
    issues,
    shot,
    text,
    handlers: await evaluate(
      '(function(){var m=document.getElementById("mount");return m?m.querySelectorAll("[data-wb-h]").length:-1})()'
    )
  })
}

const pagesToRun = PAGES.length
  ? PAGES
  : ALL
    ? [...COMMON_PAGES, ...EXTRA_PAGES]
    : [...COMMON_PAGES, ...CONTEXT_PAGES]

if (WITH_FLOW) {
  await runFlow()
} else {
  console.log('[probe] 提示：结果页/详情页依赖起名结果，加 --flow 才能看到真实内容')
}

for (const p of pagesToRun) {
  await inspect(p)
}

// ══════════════════════════════════════════════════════════════
// 汇总
// ══════════════════════════════════════════════════════════════

console.log('\n═══════════ 巡检结果 ═══════════')
let hard = 0
for (const r of results) {
  const panelErrs = (r.rep.panel || []).filter((l) => l.level === 'error')
  const runtimeErrs = r.rep.errors || []
  const conErrs = r.issues.filter((l) => l.level.includes('error') || l.level === 'uncaught')
  const conWarns = r.issues.filter((l) => l.level.includes('warn'))
  const bad = panelErrs.length + runtimeErrs.length + conErrs.length + (r.reached ? 0 : 1)
  hard += bad

  console.log(`\n▶ ${r.page}${r.note ? '  · ' + r.note : ''}`)
  console.log(`  到达=${r.reached}  处理器数=${r.handlers}  截图=${r.shot}`)
  if (r.rep.flowDone !== undefined) console.log(`  流程完成=${r.rep.flowDone}${r.rep.flowError ? ' 错误=' + r.rep.flowError : ''}`)
  if (!r.reached) console.log('  [ERR] 未能停在目标页面')
  runtimeErrs.slice(0, 8).forEach((t) => console.log('  [ERR] ' + String(t).slice(0, 240)))
  panelErrs.slice(0, 8).forEach((l) => console.log('  [ERR] ' + String(l.text).slice(0, 240)))
  conErrs.slice(0, 10).forEach((l) => console.log('  [ERR] ' + String(l.text).slice(0, 240)))
  conWarns.slice(0, 8).forEach((l) => console.log('  [WRN] ' + String(l.text).slice(0, 200)))
  // 面板里的非 error 提示也值得看（未实现的 wx.*、表达式求值失败等）
  const soft = (r.rep.panel || []).filter((l) => l.level !== 'info' && l.level !== 'error')
  soft.slice(0, 6).forEach((l) => console.log(`  [${l.level}] ` + String(l.text).slice(0, 200)))
  console.log('  可见文本: ' + (r.text || '（空）').slice(0, 240))
}

console.log(`\n合计硬报错：${hard}`)
console.log(hard === 0 ? '结论：预览各页均无报错。' : '结论：仍有报错，见上。')

try {
  cdp.ws.close()
} catch { /* ignore */ }
try { chrome && chrome.kill() } catch { /* ignore */ }   // --attach 模式下没有自己起的 Chrome
if (PROFILE) rmSync(PROFILE, { recursive: true, force: true })
process.exit(hard === 0 ? 0 : 1)
