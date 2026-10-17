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

async function runFlow(path = 'direct') {
  label = path === 'direct' ? 'flow' : 'flow-' + path
  const before = consoleLines.length
  const NAMES = {
    direct: '资料 → 定偏好 → 生成',
    chars: '资料 → 定偏好 → 从字出发（点字）→ 生成',
    sources: '资料 → 定偏好 → 从出处出发（限定诗经）→ 生成'
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
 * 验证原生 picker / switch 替身在浏览器里真的能点、能选、能回填。
 *
 * 真机上它们是微信原生组件，所占区域就是整行右侧；但浏览器里 <picker>
 * 是未知名元素，默认会被 flex 布局压成文字宽度，出现「点空白处没反应」。
 * 此场景专门守卫命中区 + 弹层选择 + bindchange 回填这一整条链。
 */
async function runPicker() {
  label = 'picker'
  const before = consoleLines.length
  console.log('[probe] 验证 picker / switch 替身：真鼠标点击 → 弹层 → 选择 → 回填 …')

  const script = `(async () => {
    var wb = window.__wb
    var out = {}
    var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms) }) }
    function clickAt(x, y) {
      var t = document.elementFromPoint(x, y)
      if (!t) return false
      ;['mousedown', 'mouseup', 'click'].forEach(function (type) {
        t.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y }))
      })
      return true
    }
    function pickerValue(idx) {
      var p = document.querySelectorAll('.form-item picker')[idx]
      return p ? p.textContent.trim() : ''
    }

    await wb.goto('pages/name/name')
    await wait(700)

    // 1) 出生日期：点最右侧空白处，必须命中 picker 并打开弹层
    var dateEl = document.querySelectorAll('.form-item picker')[0]
    var r = dateEl.getBoundingClientRect()
    var hit = document.elementFromPoint(r.right - 6, r.top + r.height / 2)
    out.dateHitOnRight = !!(hit && hit.closest('picker') === dateEl)
    clickAt(r.right - 6, r.top + r.height / 2)
    await wait(400)
    out.dateModalOpen = document.getElementById('modal-mask').classList.contains('on')
    var input = document.getElementById('modal-body').querySelector('input')
    if (input) input.value = '1994-05-20'
    document.getElementById('modal-ok').click()
    await wait(400)
    out.dateAfterPick = pickerValue(0)

    // 2) 出生时辰（selector）
    var hourEl = document.querySelectorAll('.form-item picker')[1]
    var hr = hourEl.getBoundingClientRect()
    clickAt(hr.right - 6, hr.top + hr.height / 2)
    await wait(400)
    out.hourModalOpen = document.getElementById('modal-mask').classList.contains('on')
    var sel = document.getElementById('modal-body').querySelector('select')
    out.hourOptions = sel ? sel.options.length : 0
    if (sel) sel.value = '3'
    document.getElementById('modal-ok').click()
    await wait(400)
    out.hourAfterPick = pickerValue(1)

    // 3) switch：点一次应触发 bindchange，收起八字行
    var sw = document.querySelector('.wb-switch')
    out.switchBefore = sw && sw.classList.contains('wb-switch-on')
    var sr = sw.getBoundingClientRect()
    clickAt(sr.left + sr.width / 2, sr.top + sr.height / 2)
    await wait(400)
    out.switchAfter = document.querySelector('.wb-switch').classList.contains('wb-switch-on')
    out.dateRowHidden = document.body.innerText.indexOf('出生日期') === -1

    return out
  })()`

  const res = await evaluate(script)
  await sleep(500)
  const shot = await screenshot('picker')
  const issues = consoleLines.slice(before)
  results.push({
    page: 'picker / switch 替身',
    note: '日期/时辰选择器命中区与回填',
    reached: !!(res && res.dateModalOpen && res.hourModalOpen && res.dateAfterPick === '1994-05-20' && res.hourAfterPick.indexOf('卯时') !== -1),
    rep: {},
    issues,
    shot,
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
      console.log('  [ERR] picker 场景脚本异常: ' + String(p.__err).slice(0, 300))
    } else {
      console.log(
        `  日期：最右侧命中 picker=${p.dateHitOnRight} modal=${p.dateModalOpen} 回填=${p.dateAfterPick}`
      )
      console.log(
        `  时辰：modal=${p.hourModalOpen} 选项数=${p.hourOptions} 回填=${p.hourAfterPick}`
      )
      console.log(
        `  switch：点前=${p.switchBefore} 点后=${p.switchAfter} 日期行已收起=${p.dateRowHidden}`
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
