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
 *   node tools/preview/probe.js --flow                 # 跑通起名流程（直接推荐 + 从字出发），再看结果页/详情页
 *   node tools/preview/probe.js --flow --flowall       # 再加一条「从出处出发」
 *   node tools/preview/probe.js --book                 # 验证名字本：起名落盘→收藏→记录恢复→删除→清空
 *   node tools/preview/probe.js --picker               # 验证 picker / switch 替身的命中区与回填
 *   node tools/preview/probe.js --out /tmp/shots
 *
 * 前置：后端 :8000 与预览服务 :8899 都要在跑（起名、测评要真后端）。
 */

import { spawn } from 'node:child_process'
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { setTimeout as sleep } from 'node:timers/promises'

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
// 默认用 localhost：这台机器上 127.0.0.1 会被代理策略拦成空响应（curl 返回 000）
const BASE = process.env.PREVIEW_BASE || 'http://localhost:8899'

const argv = process.argv.slice(2)
const outIdx = argv.indexOf('--out')
const OUT_DIR = outIdx === -1 ? '/tmp/mingtang-shots' : argv[outIdx + 1]
const WITH_FLOW = argv.includes('--flow')
const WITH_FLOW_ALL = argv.includes('--flowall')
const WITH_BOOK = argv.includes('--book')
const WITH_PICKER = argv.includes('--picker')
const WITH_INPUT = argv.includes('--input')
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
  //
  // 必须自带超时：awaitPromise 遇到「页面 JS 卡在死循环 / 弹层把线程占住」时
  // 协议层不会回包，整条巡检会静默挂死 —— 之前排查一次就耗在这上面。
  const r = await Promise.race([
    cdp.send('Runtime.evaluate', {
      expression: expr,
      returnByValue: true,
      awaitPromise: true
    }),
    new Promise((resolve) => {
      setTimeout(() => resolve({ evaluateTimeout: true }), 30000)
    })
  ])
  if (r && r.evaluateTimeout) {
    return { __err: 'evaluate 超时（30s）：页面可能卡死或弹层阻塞' }
  }
  if (r.exceptionDetails) {
    const d = r.exceptionDetails
    return { __err: d.text + ' ' + (d.exception?.description || '') }
  }
  return r.result ? r.result.value : undefined
}

async function screenshot(name, opts) {
  // 手机壳里有两层会截断内容：.screen（760px，且是 fixed 的包含块）与里面的
  // .wb-page-root（滚动视口）。截图前把两层都撑开，才能截到整页内容。
  //
  // 但撑开 .screen 会把 fixed 弹层一起「带到」长页面的底部 —— 那是截图假象，
  // 会让人误判成「弹层掉回文档流」。要看浮层真实位置时传 { raw: true }，
  // 按屏幕原样截，不撑高、也不截视口外的内容。
  const raw = !!(opts && opts.raw)
  if (!raw) {
    await evaluate(
      '(function(){' +
        'var s=document.querySelector(".screen"),m=document.querySelector(".wb-page-root");' +
        'if(s){s.dataset.h=s.style.height;s.style.height="auto"}' +
        'if(m){m.dataset.h=m.style.height;m.style.height="auto"' +
        ';m.dataset.o=m.style.overflow;m.style.overflow="visible"}' +
        'return 1})()'
    ).catch(() => 1)
  }
  // raw：按手机壳的真实几何裁剪，不受外层视口高度影响，也不改 .screen 高度
  const clip = raw
    ? await evaluate(
        '(function(){var p=document.querySelector(".phone");if(!p)return null;' +
          'var r=p.getBoundingClientRect();' +
          'return {x:r.x+window.scrollX,y:r.y+window.scrollY,width:r.width,height:r.height,scale:1}})()'
      ).catch(() => null)
    : null
  // 截图也要有上限：页面主线程一旦被卡住，Page.captureScreenshot 不会回包，
  // 整条巡检会静默挂死（比报错更难查）。
  const shotParams = clip
    ? { format: 'png', captureBeyondViewport: true, clip }
    : { format: 'png', captureBeyondViewport: true }
  const r = await Promise.race([
    cdp.send('Page.captureScreenshot', shotParams),
    new Promise((resolve) => setTimeout(() => resolve({ captureTimeout: true }), 20000))
  ])
  if (r.captureTimeout) {
    console.log('[probe] 截图超时：页面主线程可能被卡住')
    return ''
  }
  const file = `${OUT_DIR}/${name.replace(/\//g, '_')}.png`
  writeFileSync(file, Buffer.from(r.data, 'base64'))
  if (!raw) {
    await evaluate(
      '(function(){' +
        'var s=document.querySelector(".screen"),m=document.querySelector(".wb-page-root");' +
        'if(s&&s.dataset.h!==undefined){s.style.height=s.dataset.h}' +
        'if(m&&m.dataset.h!==undefined){m.style.height=m.dataset.h;m.style.overflow=m.dataset.o}' +
        'return 1})()'
    ).catch(() => 1)
  }
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

async function runFlow(path = 'direct') {
  label = path === 'direct' ? 'flow' : 'flow-' + path
  const before = consoleLines.length
  const NAMES = {
    direct: '资料 → 定偏好 → 生成',
    chars: '资料 → 定偏好 → 先字后典（点字）→ 生成',
    sources: '资料 → 定偏好 → 先典后字（限定诗经）→ 生成'
  }
  console.log(`[probe] 跑通起名流程 · ${path}（${NAMES[path]}）…`)
  await evaluate(
    `window.__wb.flow({ surname: "林", birthDate: "1994-05-20", path: ${JSON.stringify(path)} })`
  )
  // 先字/先出处两条要真的向后端算一遍字表，给久一点
  const done = await waitJs(
    '(function(){var r=window.__wb.report();return r && (r.flowDone === true || r.flowDone === false || r.flowError)})()',
    path === 'direct' ? 90000 : 150000,
    400
  )
  await sleep(2000)
  const rep = JSON.parse((await report()) || '{}')
  const shot = await screenshot('flow-' + path)
  const issues = consoleLines.slice(before)
  const text = await evaluate(
    '(function(){var m=document.getElementById("mount");return m?m.innerText.replace(/\\s+/g," ").slice(0,300):""})()'
  )
  // 硬约束违约（flowViolations / flowSources）由 harness 写进报告，这里并成一条判定
  const violated =
    (rep.flowViolations || 0) > 0 || (rep.flowSources || []).length > 0
  results.push({
    page: `flow·${path}（${NAMES[path]}）`,
    note: '停在 ' + (rep.flowAt || rep.page || '?') +
      (rep.flowPicked ? ' · 点选 ' + rep.flowPicked.join('/') + ' · 违约 ' + (rep.flowViolations || 0) : '') +
      (rep.flowSources ? ' · 出典越界 ' + rep.flowSources.length : ''),
    reached: done && rep.flowDone === true && !violated,
    rep,
    issues,
    shot,
    text,
    handlers: await evaluate(
      '(function(){var m=document.getElementById("mount");return m?m.querySelectorAll("[data-wb-h]").length:-1})()'
    )
  })
}

/**
 * 验证「名字本」这条链路（本机存储）：
 * 起名落盘 → 收藏 → 名字本两个分段 → 从收藏进详情 → 从记录恢复结果 → 删除 → 清空。
 *
 * 为什么值得单独跑：这条链路全靠 wx.setStorageSync 落盘，
 * 「存上了没有」「恢复得回来没有」都只能在跑起来之后才看得见。
 */
async function runBook() {
  label = 'book'
  const before = consoleLines.length
  console.log('[probe] 验证名字本：起名落盘 → 收藏 → 记录恢复 → 删除 → 清空 …')

  const script = `(async () => {
    var wb = window.__wb
    var out = {}
    var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms) }) }
    var text = function () {
      var m = document.getElementById('mount')
      return m ? m.innerText.replace(/\\s+/g, ' ').slice(0, 400) : ''
    }
    var at = function () { return wb.runtime.current ? wb.runtime.current.path : '' }
    var countOf = function (sel) {
      var m = document.getElementById('mount')
      return m ? m.querySelectorAll(sel).length : -1
    }
    // 删除/清空都要过 wx.showModal，预设成「确定」，否则脚本会停在弹窗上
    wb.setModalAnswer(true)

    // 1) 跑通一次起名：结果应自动落盘成一条记录
    out.flow = await wb.flow({ surname: '林', birthDate: '1994-05-20' })
    await wait(800)
    var recs = wb.storage('mt_records_v1') || []
    out.records = recs.length
    out.recKind = recs[0] && recs[0].kind
    out.recTitle = recs[0] && recs[0].title
    out.recSubtitle = recs[0] && recs[0].subtitle
    out.recChips = recs[0] ? recs[0].chips.length : -1
    out.recHasPayload = !!(recs[0] && recs[0].payload && recs[0].payload.names)

    // 2) 结果页收藏第一个名字
    out.favClicked = await wb.clickHandler('onFavTap')
    await wait(500)
    var favs = wb.storage('mt_favs_v1') || []
    out.favs = favs.length
    out.favName = favs[0] && favs[0].full_name
    // 收藏要存下整份候选名对象，详情页才渲染得出来
    out.favHasChars = !!(favs[0] && favs[0].data && favs[0].data.chars_info)
    out.favHasPoetry = !!(favs[0] && favs[0].data && favs[0].data.poetry)
    out.cardSaysFaved = text().indexOf('已收藏') !== -1

    // 3) 名字本 · 起名记录
    await wb.goto('pages/history/history')
    await wait(800)
    out.historyPath = at()
    out.recRows = countOf('.rec')
    out.recChipEls = countOf('.rec .chip')
    out.historyText = text()

    // 4) 切到收藏分段
    await wb.clickText('收藏')
    await wait(400)
    out.favRows = countOf('.fav')
    out.favText = text()

    // 5) 从收藏点进详情：与从结果页点名字是同一条路径
    await wb.clickHandler('onFavTap')
    await wait(1200)
    out.detailPath = at()
    out.detailText = text()
    out.detailFavBtn = countOf('.actions .btn-secondary')

    // 6) 回名字本，点那条记录 → 应恢复该批结果并回到结果页
    await wb.goto('pages/history/history')
    await wait(700)
    out.backToBook = at()
    await wb.clickText('起名记录')
    await wait(300)
    await wb.clickHandler('onRecordTap')
    await wait(1200)
    out.restoredPath = at()
    out.restoredText = text()
    out.restoredCards = countOf('.name-card')

    // 7) 删除单条记录
    await wb.goto('pages/history/history')
    await wait(700)
    await wb.clickHandler('onRecordDelete')
    await wait(500)
    out.recordsAfterDelete = (wb.storage('mt_records_v1') || []).length
    out.emptyAfterDelete = text()

    // 8) 取消单个收藏
    await wb.clickText('收藏')
    await wait(300)
    await wb.clickHandler('onFavDelete')
    await wait(500)
    out.favsAfterDelete = (wb.storage('mt_favs_v1') || []).length

    // 9) 再起一批，然后整批清空
    out.flow2 = await wb.flow({ surname: '沈', birthDate: '1992-03-08' })
    await wait(800)
    out.recordsBeforeClear = (wb.storage('mt_records_v1') || []).length
    await wb.goto('pages/history/history')
    await wait(700)
    await wb.clickHandler('onClearTap')
    await wait(500)
    out.recordsAfterClear = (wb.storage('mt_records_v1') || []).length

    wb.setModalAnswer(null)
    return out
  })()`

  const res = await evaluate(script)
  await sleep(600)
  const shot = await screenshot('book')
  const issues = consoleLines.slice(before)
  results.push({
    page: '名字本（记录 + 收藏）',
    note: '起名→收藏→名字本→恢复→删除→清空',
    reached: !!(res && res.flow === true && res.restoredPath === 'pages/result/result'),
    rep: {},
    issues,
    shot,
    text: '',
    handlers: -1,
    book: res
  })
  return res
}

/**
 * 验证自绘日期弹层与十二时辰格真的能点、能选、能回填。
 *
 * 以前这一项守的是原生 `<picker>` 替身的命中区 —— 但原生 picker 在预览里点不开，
 * 用户根本选不了日期，所以页面已改成自绘三列 scroll-view + 12 格时辰。
 * 现在要守的是：
 *   1. 页面上**不再有** `<picker>`（有就说明改动被回退了）
 *   2. 点「出生日期」整行能打开弹层，弹层是三列
 *   3. 点年/月/日能选中，点确定能回填成 YYYY-MM-DD 并关掉弹层
 *   4. 点时辰格能高亮，且第 4 格是卯
 */
async function runPicker() {
  label = 'date'
  const before = consoleLines.length
  console.log('[probe] 验证自绘弹层：日期三列 / 时辰单列，点击 → 弹层 → 选中 → 确定回填 …')

  // 每一步都是一次独立、同步的 evaluate，等待放在 Node 侧（sleep）。
  // 早先写成「一个 async IIFE 里连做十几步」，会把整串动作压进一次
  // Runtime.evaluate(awaitPromise)，任何一步抛错都表现为整条巡检静默挂死，
  // 也定位不到卡在哪一步。
  const CLICK = `function clickEl(el) {
    if (!el) return false
    try { el.scrollIntoView({ block: 'center' }) } catch (e) {}
    var r = el.getBoundingClientRect()
    var x = r.left + r.width / 2
    var y = r.top + r.height / 2
    var t = document.elementFromPoint(x, y) || el
    ;['mousedown', 'mouseup', 'click'].forEach(function (type) {
      t.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y }))
    })
    return true
  }`

  const pickInCol = (colIdx, text) =>
    evaluate(`(function () {
      ${CLICK}
      var col = document.querySelectorAll('.sheet-col')[${colIdx}]
      if (!col) return 'NO_COL_${colIdx}'
      var kids = col.children
      for (var i = 0; i < kids.length; i++) {
        if (kids[i].innerText.trim() === '${text}') return clickEl(kids[i])
      }
      return 'NOT_FOUND_${text}_N' + kids.length
    })()`)

  const out = {}

  console.log('[probe]   · goto name 页')
  await evaluate("window.__wb.goto('pages/name/name')")
  await sleep(900)

  out.nativePickers = await evaluate("document.querySelectorAll('picker').length")
  console.log('[probe]   · 原生 picker 个数 = ' + out.nativePickers)

  // 0) 八字默认是关的：先确认此时没有日期行，再打开开关
  out.dateRowHiddenByDefault =
    (await evaluate("document.querySelectorAll('[data-wb-h=\"onOpenBirthDate\"]').length")) === 0
  await evaluate(`(function () { ${CLICK}; return clickEl(document.querySelector('[data-wb-h="onBaziToggle"]')) })()`)
  await sleep(700)
  out.baziOnAfterClick = await evaluate(
    "(function(){var s=document.querySelector('[data-wb-h=\"onBaziToggle\"]');return s? s.classList.contains('on'): null})()"
  )
  console.log('[probe]   · 八字默认关 = ' + out.dateRowHiddenByDefault + '，开关后 = ' + out.baziOnAfterClick)
  out.switchBox = await evaluate(
    "(function(){var s=document.querySelector('[data-wb-h=\"onBaziToggle\"]');" +
      "if(!s)return null;var r=s.getBoundingClientRect();" +
      "return {w:Math.round(r.width),h:Math.round(r.height),cls:s.className}})()"
  )
  await screenshot('bazi-on')

  // 1) 打开日期弹层
  out.dateRowFound = (await evaluate("document.querySelectorAll('[data-wb-h=\"onOpenBirthDate\"]').length")) === 1
  console.log('[probe]   · 日期行找到 = ' + out.dateRowFound)
  await evaluate(`(function () { ${CLICK}; return clickEl(document.querySelector('[data-wb-h="onOpenBirthDate"]')) })()`)
  await sleep(600)
  console.log('[probe]   · 弹层已打开')
  out.sheetOpen = (await evaluate("document.querySelectorAll('.sheet-mask').length")) === 1
  out.colCount = await evaluate("document.querySelectorAll('.sheet-col').length")
  // 数列里的 .sheet-item，不是 children（首尾各有一块 .sheet-pad 衬垫）
  out.dayCountBefore = await evaluate(
    "(function(){var c=document.querySelectorAll('.sheet-col')[2];return c?c.querySelectorAll('.sheet-item').length:0})()"
  )
  // 弹层开着的样子要留档：这一屏出过「弹层掉回文档流」的事故，肉眼可查最省事。
  // 用 raw 模式：撑高 .screen 会把 fixed 弹层带到长页面底部，那是假象。
  await screenshot('date-sheet-open', { raw: true })

  // 1.5) 打开时选中项应落在列正中 —— 首尾衬垫就是为了让「今年」「今天」
  //      这种端点项也能居中，而不是贴在最底边
  out.centerOffset = await evaluate(
    "(function(){var c=document.querySelectorAll('.sheet-col');" +
      "return Array.prototype.map.call(c,function(col){" +
      "var on=col.querySelector('.sheet-item.on'); if(!on) return null;" +
      "var rc=col.getBoundingClientRect(), ro=on.getBoundingClientRect();" +
      "return Math.round(((ro.top+ro.bottom)/2)-((rc.top+rc.bottom)/2))})})()"
  )
  console.log('[probe]   · 选中项偏离列中心 = ' + JSON.stringify(out.centerOffset))

  // 2) 选 1994-05-20（先换年，大小月天数会跟着重算）
  out.pickYear = await pickInCol(0, 1994)
  await sleep(500)
  out.pickMonth = await pickInCol(1, 5)
  await sleep(500)
  out.pickDay = await pickInCol(2, 20)
  await sleep(500)
  console.log('[probe]   · 选年月日 = ' + out.pickYear + '/' + out.pickMonth + '/' + out.pickDay)
  out.dayCountAfter = await evaluate(
    "(function(){var c=document.querySelectorAll('.sheet-col')[2];return c?c.querySelectorAll('.sheet-item').length:0})()"
  )
  out.onCount = await evaluate("document.querySelectorAll('.sheet-item.on').length")
  out.onText = await evaluate(
    "Array.prototype.map.call(document.querySelectorAll('.sheet-item.on'),function(n){return n.innerText.trim()}).join('/')"
  )

  // 3) 确定 → 回填
  await evaluate(`(function () { ${CLICK}; return clickEl(document.querySelector('[data-wb-h="onSheetConfirm"]')) })()`)
  await sleep(700)
  out.sheetClosed = (await evaluate("document.querySelectorAll('.sheet-mask').length")) === 0
  out.dateAfterPick = await evaluate(
    "(function(){var r=document.querySelector('[data-wb-h=\"onOpenBirthDate\"]');var v=r&&r.querySelector('.picker-value');return v?v.innerText.trim():''})()"
  )
  console.log('[probe]   · 回填 = ' + out.dateAfterPick + '（弹层已关=' + out.sheetClosed + '）')

  // 4) 时辰：与日期同一个弹层。点行 → 弹层 → 选第 4 项（卯时）→ 确定 → 回填
  out.hourLegacyGone =
    (await evaluate("document.querySelectorAll('.hour-cell, .select-panel').length")) === 0
  out.hourRowFound = (await evaluate("document.querySelectorAll('[data-wb-h=\"onOpenHour\"]').length")) === 1
  console.log('[probe]   · 时辰行找到 = ' + out.hourRowFound)
  await evaluate(`(function () { ${CLICK}; return clickEl(document.querySelector('[data-wb-h="onOpenHour"]')) })()`)
  await sleep(700)
  out.hourSheetOpen = (await evaluate("document.querySelectorAll('.sheet-mask').length")) === 1
  out.hourSheetOneCol = (await evaluate("document.querySelectorAll('.sheet-cols-hour').length")) === 1
  out.hourOptionCount = await evaluate("document.querySelectorAll('.sheet-item-hour').length")
  out.hourTitle = await evaluate(
    "(function(){var t=document.querySelector('.sheet-title');return t?t.innerText.trim():''})()"
  )
  console.log('[probe]   · 弹层已开 = ' + out.hourSheetOpen + '，单列 = ' + out.hourSheetOneCol +
    '，选项数 = ' + out.hourOptionCount + '，标题 = ' + out.hourTitle)
  const hourShot = await screenshot('hour-sheet', { raw: true })
  await evaluate(`(function () { ${CLICK}; return clickEl(document.querySelectorAll('.sheet-item-hour')[3]) })()`)
  await sleep(500)
  await evaluate(`(function () { ${CLICK}; return clickEl(document.querySelector('[data-wb-h="onSheetConfirm"]')) })()`)
  await sleep(700)
  out.hourText = await evaluate(
    "(function(){var rows=document.querySelectorAll('[data-wb-h=\"onOpenHour\"]');" +
      "var v=rows[0]&&rows[0].querySelector('.picker-value');return v?v.innerText.trim():''})()"
  )
  out.hourSheetClosed = (await evaluate("document.querySelectorAll('.sheet-mask').length")) === 0
  console.log('[probe]   · 选后时辰 = ' + out.hourText + '（弹层已关=' + out.hourSheetClosed + '）')

  // 5) 关掉八字 → 日期行应消失
  //    找挂了 onBaziToggle 的元素，而不是 .wb-switch —— 那个类名是 runner 给
  //    原生 <switch> 生成的替身，本页用的是自绘 <view>，没有这个类。
  out.switchFound = (await evaluate("document.querySelectorAll('[data-wb-h=\"onBaziToggle\"]').length")) === 1
  out.switchBefore = await evaluate(
    "(function(){var s=document.querySelector('[data-wb-h=\"onBaziToggle\"]');return s?s.classList.contains('on'):null})()"
  )
  console.log('[probe]   · 开关找到 = ' + out.switchFound + '，点前 = ' + out.switchBefore)
  await evaluate(`(function () { ${CLICK}; return clickEl(document.querySelector('[data-wb-h="onBaziToggle"]')) })()`)
  await sleep(700)
  console.log('[probe]   · 已点开关')
  out.switchAfter = await evaluate(
    "(function(){var s=document.querySelector('[data-wb-h=\"onBaziToggle\"]');return s?s.classList.contains('on'):null})()"
  )
  out.dateRowHidden = (await evaluate("document.querySelectorAll('[data-wb-h=\"onOpenBirthDate\"]').length")) === 0
  console.log('[probe]   · 点后 = ' + out.switchAfter + '，日期行已收起 = ' + out.dateRowHidden)

  const res = out
  await sleep(300)
  await screenshot('date-sheet')
  const issues = consoleLines.slice(before)
  const pass =
    res.nativePickers === 0 &&
    res.dateRowHiddenByDefault === true &&
    res.baziOnAfterClick === true &&
    res.dateRowFound &&
    res.sheetOpen &&
    res.colCount === 3 &&
    res.centerOffset.length === 3 &&
    res.centerOffset.every((v) => v !== null && Math.abs(v) <= 3) &&
    res.pickYear === true &&
    res.pickMonth === true &&
    res.pickDay === true &&
    res.sheetClosed &&
    res.dateAfterPick === '1994-05-20' &&
    res.hourLegacyGone === true &&
    res.hourRowFound === true &&
    res.hourSheetOpen === true &&
    res.hourSheetOneCol === true &&
    res.hourOptionCount === 12 &&
    res.hourTitle === '出生时辰' &&
    res.hourText === '卯时' &&
    res.hourSheetClosed === true &&
    res.switchAfter === false &&
    res.dateRowHidden === true
  results.push({
    page: '自绘弹层（日期 / 时辰）',
    note: '日期行 → 三列弹层 → 回填；时辰行 → 单列弹层 → 选卯时；八字开关联动',
    reached: !!pass,
    rep: {},
    issues,
    shot: hourShot,
    text: '',
    handlers: -1,
    picker: res
  })
  return res
}

async function runInput() {
  label = 'input'
  const before = consoleLines.length
  console.log('[probe] 验证输入框：点击不误派发 → 真实键入 → 焦点与数据都对 …')

  await evaluate("window.__wb.goto('pages/name/name')")
  const ok = await waitJs("!!document.querySelector('[data-wb-h=\"onSurnameInput\"]')", 20000)
  if (!ok) {
    results.push({ page: '输入框', note: '找不到姓氏输入框', reached: false, rep: {}, issues: [], shot: '', text: '', handlers: -1 })
    return null
  }

  // 1) 点击输入框：旧缺陷下这里会把 bindinput 当 tap 派发，
  //    detail={} → setData({surname: undefined}) → 整页重绘 → 输入框被换掉 → 永远打不进字。
  const clickRes = await evaluate(`(function(){
    var el = document.querySelector('[data-wb-h="onSurnameInput"]')
    var r = el.getBoundingClientRect()
    var x = r.x + r.width / 2, y = r.y + r.height / 2
    var t = document.elementFromPoint(x, y)
    ;['mousedown','mouseup','click'].forEach(function(k){
      t.dispatchEvent(new MouseEvent(k, { bubbles: true, cancelable: true, clientX: x, clientY: y }))
    })
    var d = window.__wb.runtime.current.instance.data
    return { 命中: t === el, 点击后值: String(d.surname), 有该字段: 'surname' in d }
  })()`)

  // 2) 真实键入（不是直接赋 value）：走浏览器默认行为，会触发 input 事件
  const focusOk = await evaluate(`(function(){
    var el = document.querySelector('[data-wb-h="onSurnameInput"]')
    el.focus()
    return document.activeElement === el
  })()`)
  await cdp.send('Input.insertText', { text: '林' })
  await sleep(350)

  const typed = await evaluate(`(function(){
    var el = document.querySelector('[data-wb-h="onSurnameInput"]')
    var d = window.__wb.runtime.current.instance.data
    return {
      焦点还在: document.activeElement === el,
      输入框值: el.value,
      数据值: String(d.surname),
      节点还在页面里: document.body.contains(el)
    }
  })()`)

  // 3) 再补一个字，确认连续输入不被重绘打断
  await cdp.send('Input.insertText', { text: '溪' })
  await sleep(350)
  const typed2 = await evaluate(`(function(){
    var el = document.querySelector('[data-wb-h="onSurnameInput"]')
    var d = window.__wb.runtime.current.instance.data
    return { 焦点还在: document.activeElement === el, 输入框值: el.value, 数据值: String(d.surname) }
  })()`)

  const shot = await screenshot('input')
  const issues = consoleLines.slice(before)
  const reached =
    clickRes && clickRes.命中 && clickRes['点击后值'] === '' &&
    focusOk === true &&
    typed && typed['焦点还在'] && typed['节点还在页面里'] &&
    typed2 && typed2['焦点还在'] && typed2['数据值'] === '林溪'

  results.push({
    page: '输入框（姓氏）',
    note: `点击不误派发=${clickRes && clickRes['点击后值'] === ''} · 键入=${JSON.stringify(typed2 && typed2['数据值'])} · 焦点保持=${!!(typed2 && typed2['焦点还在'])}`,
    reached: !!reached,
    rep: {},
    issues,
    shot,
    text: `姓氏输入框 = ${JSON.stringify(typed2 && typed2['输入框值'])}（data 同步=${typed2 && typed2['数据值']}）`,
    handlers: -1,
    input: { clickRes, typed, typed2 }
  })
  return { clickRes, typed, typed2 }
}

const pagesToRun = PAGES.length
  ? PAGES
  : ALL
    ? [...COMMON_PAGES, ...EXTRA_PAGES]
    : [...COMMON_PAGES, ...CONTEXT_PAGES]

if (WITH_FLOW) {
  // 直接推荐 + 从字出发：后者会把「载入可选字表 → 点字 → 硬约束生效」整条链路验掉
  await runFlow('direct')
  await runFlow('chars')
  if (WITH_FLOW_ALL) await runFlow('sources')
} else if (!WITH_BOOK && !WITH_PICKER && !WITH_INPUT) {
  console.log('[probe] 提示：结果页/详情页依赖起名结果，加 --flow 才能看到真实内容')
}

if (WITH_PICKER) {
  await runPicker()
}

if (WITH_INPUT) {
  await runInput()
}

if (WITH_BOOK) {
  await runBook()
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

  if (r.book) {
    const b = r.book
    if (b.__err) {
      console.log('  [ERR] 场景脚本异常: ' + String(b.__err).slice(0, 300))
    } else {
      console.log(
        `  起名流程=${b.flow} 记录=${b.records}（${b.recKind} / ${b.recTitle} / ${b.recSubtitle} / ` +
          `${b.recChips} chips / 带完整结果=${b.recHasPayload}）`
      )
      console.log(
        `  收藏：点击成功=${b.favClicked} 条数=${b.favs} 名字=${b.favName} ` +
          `存了用字=${b.favHasChars} 存了出处=${b.favHasPoetry} 卡片显示已收藏=${b.cardSaysFaved}`
      )
      console.log(
        `  名字本：${b.historyPath} 记录行=${b.recRows} 候选字=${b.recChipEls} 收藏行=${b.favRows}`
      )
      console.log('  记录文案: ' + String(b.historyText || '').slice(0, 200))
      console.log('  收藏文案: ' + String(b.favText || '').slice(0, 200))
      console.log(
        `  收藏→详情：${b.detailPath} 收藏按钮=${b.detailFavBtn} | ` +
          String(b.detailText || '').slice(0, 140)
      )
      console.log(
        `  记录→恢复：${b.restoredPath} 候选卡=${b.restoredCards} | ` +
          String(b.restoredText || '').slice(0, 140)
      )
      console.log(
        `  删除单条后记录=${b.recordsAfterDelete} 空态可见=${String(b.emptyAfterDelete || '').indexOf('还没有起名记录') !== -1}`
      )
      console.log(`  取消收藏后收藏数=${b.favsAfterDelete}`)
      console.log(`  清空：前=${b.recordsBeforeClear} 后=${b.recordsAfterClear}`)
    }
  }

  if (r.picker) {
    const p = r.picker
    if (p.__err) {
      console.log('  [ERR] 日期/时辰场景脚本异常: ' + String(p.__err).slice(0, 300))
    } else {
      console.log(
        `  页面上原生 picker 个数=${p.nativePickers}（应为 0）`
      )
      console.log(
        `  八字默认关=${p.dateRowHiddenByDefault} 打开后=${p.baziOnAfterClick}`
      )
      console.log(
        `  日期行：找到=${p.dateRowFound} 弹层开=${p.sheetOpen} 列数=${p.colCount} ` +
          `当月天数 ${p.dayCountBefore}→${p.dayCountAfter}`
      )
      console.log(
        `  选年月日=${p.pickYear}/${p.pickMonth}/${p.pickDay} 高亮格=${p.onCount} ` +
          `弹层关=${p.sheetClosed} 回填=${p.dateAfterPick}`
      )
      console.log(
        `  默认落点居中度（0 为正中）= ${JSON.stringify(p.centerOffset)}`
      )
      console.log(
        `  时辰弹层：旧控件已移除=${p.hourLegacyGone} 行=${p.hourRowFound} ` +
          `弹层=${p.hourSheetOpen} 单列=${p.hourSheetOneCol} 选项数=${p.hourOptionCount} ` +
          `标题=${p.hourTitle} 选后=${p.hourText} 关=${p.hourSheetClosed}`
      )
      console.log(
        `  八字开关：点前=${p.switchBefore} 点后=${p.switchAfter} 日期行已收起=${p.dateRowHidden}`
      )
    }
  }

  if (r.input) {
    const i = r.input
    if (i.__err) {
      console.log('  [ERR] 输入场景脚本异常: ' + String(i.__err).slice(0, 300))
    } else {
      console.log(
        `  点击输入框：命中=${i.clickRes && i.clickRes.命中} ` +
          `误派发后值=${JSON.stringify(i.clickRes && i.clickRes['点击后值'])}（应为空串）`
      )
      console.log(
        `  真实键入：焦点保持=${i.typed && i.typed['焦点还在']} ` +
          `输入框=${JSON.stringify(i.typed && i.typed['输入框值'])} ` +
          `data=${JSON.stringify(i.typed && i.typed['数据值'])}`
      )
      console.log(
        `  连续键入：焦点保持=${i.typed2 && i.typed2['焦点还在']} ` +
          `输入框=${JSON.stringify(i.typed2 && i.typed2['输入框值'])} ` +
          `data=${JSON.stringify(i.typed2 && i.typed2['数据值'])}`
      )
    }
  }
}

console.log(`\n合计硬报错：${hard}`)
console.log(hard === 0 ? '结论：预览各页均无报错。' : '结论：仍有报错，见上。')

try {
  cdp.ws.close()
} catch { /* ignore */ }
try { chrome && chrome.kill() } catch { /* ignore */ }   // --attach 模式下没有自己起的 Chrome
if (PROFILE) rmSync(PROFILE, { recursive: true, force: true })
process.exit(hard === 0 ? 0 : 1)
