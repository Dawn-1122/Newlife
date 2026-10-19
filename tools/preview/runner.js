/**
 * 名堂 · 小程序 Web 预览运行时（开发期用，不替代真机）
 *
 * 为什么需要它：微信小程序的运行时是微信客户端私有的（渲染层 + wx.* 原生能力 +
 * 私有编译链），浏览器里**跑不起真正的小程序**，所以官方路径只有微信开发者工具。
 * 但「开发期看页面 + 看真实数据」这件事可以在这里做：
 *
 *   本文件把「真实的 wxml / wxss / 页面 js / utils」原样读进来，
 *   用一个小型解释层把 WXML 渲染成 HTML、把 rpx 换算成 px、
 *   用 stub 顶掉 wx.* / getApp() / Page()，于是**页面 js 真的在浏览器里跑**：
 *   setData、筛选、换一批、页间跳转、分享文案都能用，数据走真实后端。
 *
 * 单源原则：本运行时**不复制任何页面的结构或样式** —— 它读的就是
 * miniprogram/ 下的原始文件，所以改页面不需要同步改预览（不会漂移）。
 *
 * 不覆盖的部分（这些只能在开发者工具里验）：
 *   wx.* 原生能力全集、原生组件（picker/switch）的真实交互、真机渲染差异、
 *   分包/插件/云能力、审核相关行为。
 *
 * 用法见 tools/preview/README.md。
 */

(function (root, factory) {
  var api = factory()
  if (typeof module !== 'undefined' && module.exports) module.exports = api
  if (root) root.WBPreview = api
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict'

  // ══════════════════════════════════════════════════════════════
  // 1. WXML 解析
  // ══════════════════════════════════════════════════════════════

  var VOID_TAGS = { image: 1, input: 1, 'cover-image': 1 }

  function parseWxml(src) {
    var i = 0
    var n = src.length
    var rootNodes = []
    var stack = [rootNodes]

    function pushText(text) {
      if (!text) return
      stack[stack.length - 1].push({ type: 'text', value: text })
    }

    while (i < n) {
      var lt = src.indexOf('<', i)
      if (lt === -1) { pushText(src.slice(i)); break }
      if (lt > i) pushText(src.slice(i, lt))

      if (src.startsWith('<!--', lt)) {
        var cend = src.indexOf('-->', lt)
        i = cend === -1 ? n : cend + 3
        continue
      }
      if (src.charAt(lt + 1) === '/') {
        var close = src.indexOf('>', lt)
        i = close === -1 ? n : close + 1
        if (stack.length > 1) stack.pop()
        continue
      }

      // 开标签
      var j = lt + 1
      while (j < n && !/[\s/>]/.test(src.charAt(j))) j++
      var tag = src.slice(lt + 1, j)
      var attrs = {}
      var selfClose = false

      while (j < n) {
        while (j < n && /\s/.test(src.charAt(j))) j++
        if (src.charAt(j) === '/' && src.charAt(j + 1) === '>') { selfClose = true; j += 2; break }
        if (src.charAt(j) === '>') { j++; break }
        var k = j
        while (k < n && !/[\s=/>]/.test(src.charAt(k))) k++
        var name = src.slice(j, k)
        j = k
        while (j < n && /\s/.test(src.charAt(j))) j++
        var value = true
        if (src.charAt(j) === '=') {
          j++
          while (j < n && /\s/.test(src.charAt(j))) j++
          var q = src.charAt(j)
          if (q === '"' || q === "'") {
            var endQ = src.indexOf(q, j + 1)
            value = src.slice(j + 1, endQ === -1 ? n : endQ)
            j = endQ === -1 ? n : endQ + 1
          } else {
            var e2 = j
            while (e2 < n && !/[\s>]/.test(src.charAt(e2))) e2++
            value = src.slice(j, e2)
            j = e2
          }
        }
        if (name) attrs[name] = value
      }

      var node = { type: 'element', tag: tag, attrs: attrs, children: [] }
      stack[stack.length - 1].push(node)

      // <wxs> 内部是裸 JS，含 < > 等字符，必须整体吞掉
      if (tag === 'wxs') {
        var wend = src.indexOf('</wxs>', j)
        node.raw = src.slice(j, wend === -1 ? n : wend)
        i = wend === -1 ? n : wend + '</wxs>'.length
        continue
      }

      if (!selfClose && !VOID_TAGS[tag]) stack.push(node.children)
      i = j
    }
    return rootNodes
  }

  // ══════════════════════════════════════════════════════════════
  // 2. 表达式求值
  // ══════════════════════════════════════════════════════════════

  function evalExpr(expr, scope, onError) {
    try {
      // with($s) 让 `surname` 这类裸标识符直接取 data 上的字段
      var fn = new Function('$s', 'with($s){ return (' + expr + ') }')
      return fn(scope)
    } catch (err) {
      if (onError) onError(expr, err)
      return undefined
    }
  }

  var ONLY_MUSTACHE = /^\s*\{\{([\s\S]*)\}\}\s*$/
  var MUSTACHE = /\{\{([\s\S]*?)\}\}/g

  /**
   * 属性/文本插值：整体就是一个 {{}} 时保留原始类型，否则拼成字符串。
   *
   * 注意：判「整体就是一个 mustache」不能只看首尾 —— 像
   * `{{a}} · 喜用神：{{b}}` 这种多段插值首尾也都是 {{ }}，
   * 贪婪匹配会把 `a}} · 喜用神：{{b` 整段当成一个表达式，
   * 于是报 "Unexpected token '}'"。必须再确认内部没有 {{ / }}。
   */
  function interpolate(value, scope, onError) {
    if (typeof value !== 'string') return value
    var only = ONLY_MUSTACHE.exec(value)
    if (only && only[1].indexOf('{{') === -1 && only[1].indexOf('}}') === -1) {
      return evalExpr(only[1], scope, onError)
    }
    return value.replace(MUSTACHE, function (_, expr) {
      var v = evalExpr(expr, scope, onError)
      return v === null || v === undefined || v === false ? '' : String(v)
    })
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/"/g, '&quot;')
  }

  // ══════════════════════════════════════════════════════════════
  // 3. WXML → HTML
  // ══════════════════════════════════════════════════════════════

  var EVENT_ATTRS = [
    'bindtap', 'catchtap', 'bindinput', 'bindchange', 'bindconfirm',
    'bindblur', 'bindfocus', 'bindlongpress'
  ]
  var SKIP_ATTRS = { 'wx:if': 1, 'wx:elif': 1, 'wx:else': 1, 'wx:for': 1, 'wx:for-item': 1, 'wx:for-index': 1, 'wx:key': 1 }

  // 组件标签映射：**尽量保留原标签名**（view/text/scroll-view/picker…），
  // 这样 wxss 里的元素选择器（如 `.footer-note text`）能原样命中；
  // 只有 image 必须换成真 <img> 才能显示图片，block 是透明容器。
  function mapTag(tag) {
    if (tag === 'block') return null
    if (tag === 'image' || tag === 'cover-image') return 'img'
    return tag
  }

  function isWhitespaceText(node) {
    return node.type === 'text' && !node.value.trim()
  }

  function renderNodes(nodes, scope, ctx) {
    var html = ''
    var chain = null // 'pending' | 'done' | null

    for (var idx = 0; idx < nodes.length; idx++) {
      var node = nodes[idx]

      if (node.type === 'text') {
        if (isWhitespaceText(node)) continue
        chain = null
        var t = interpolate(node.value, scope, ctx.onExprError)
        if (t !== null && t !== undefined && t !== false) html += escapeHtml(t)
        continue
      }

      var attrs = node.attrs
      var hasIf = 'wx:if' in attrs
      var hasElif = 'wx:elif' in attrs
      var hasElse = 'wx:else' in attrs

      if (hasIf) {
        var ok = !!interpolate(attrs['wx:if'], scope, ctx.onExprError)
        chain = ok ? 'done' : 'pending'
        if (!ok) continue
      } else if (hasElif || hasElse) {
        if (chain !== 'pending') continue
        if (hasElif) {
          if (!interpolate(attrs['wx:elif'], scope, ctx.onExprError)) continue
        }
        chain = 'done'
      } else {
        chain = null
      }

      html += renderElement(node, scope, ctx)
    }
    return html
  }

  function renderElement(node, scope, ctx) {
    var attrs = node.attrs

    // wx:for —— 展开成多次渲染
    if ('wx:for' in attrs) {
      var list = interpolate(attrs['wx:for'], scope, ctx.onExprError)
      if (!Array.isArray(list)) list = []
      var itemName = attrs['wx:for-item'] || 'item'
      var indexName = attrs['wx:for-index'] || 'index'
      var out = ''
      for (var i = 0; i < list.length; i++) {
        var child = Object.create(scope)
        child[itemName] = list[i]
        child[indexName] = i
        out += renderOnce(node, child, ctx)
      }
      return out
    }
    return renderOnce(node, scope, ctx)
  }

  function renderOnce(node, scope, ctx) {
    var tag = mapTag(node.tag)
    if (tag === null) return renderNodes(node.children, scope, ctx)

    var attrs = node.attrs
    var out = '<' + tag
    var style = []
    var classList = []
    var events = []

    for (var key in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, key)) continue
      var raw = attrs[key]

      if (SKIP_ATTRS[key]) continue
      if (key === 'checked' && node.tag === 'switch') continue

      if (EVENT_ATTRS.indexOf(key) !== -1) {
        events.push({ type: eventTypeOf(key), handler: String(raw) })
        continue
      }

      if (key === 'mode' && node.tag === 'image') {
        if (raw === 'widthFix') style.push('width:100%;height:auto')
        else if (raw === 'aspectFill') style.push('object-fit:cover')
        continue
      }
      if (key === 'open-type') {
        out += ' data-open-type="' + escapeAttr(raw) + '"'
        continue
      }

      // picker 是原生组件，浏览器里没有 → 把语义搬到 data-* 上，
      // 由 harness 用原生 date/select 弹层接管
      if (node.tag === 'picker') {
        if (key === 'mode') { out += ' data-mp-picker="' + escapeAttr(raw) + '"'; continue }
        if (key === 'range') {
          var rangeVal = interpolate(raw, scope, ctx.onExprError) || []
          out += ' data-mp-range="' + escapeAttr(encodeURIComponent(JSON.stringify(rangeVal))) + '"'
          continue
        }
        if (key === 'value') {
          out += ' data-mp-value="' + escapeAttr(interpolate(raw, scope, ctx.onExprError)) + '"'
          continue
        }
        if (key === 'range-key') { out += ' data-mp-range-key="' + escapeAttr(raw) + '"'; continue }
      }
      if (key === 'loading' || key === 'disabled') {
        if (interpolate(raw, scope, ctx.onExprError)) out += ' ' + key
        continue
      }

      var value = interpolate(raw, scope, ctx.onExprError)
      if (value === null || value === undefined || value === false) continue

      if (key === 'class') {
        var cls = String(value).trim()
        if (cls) classList.push(cls)
        continue
      }
      if (key === 'style') {
        if (value) style.push(String(value))
        continue
      }
      if ((key === 'src' || key === 'imageUrl') && typeof value === 'string' && value.charAt(0) === '/') {
        // 小程序里 `/images/x.jpg` 是「包内根路径」，映射到预览服务的 /mp/ 前缀；
        // 两边都去一下斜杠，避免拼出 /mp//images/x.jpg
        out += ' src="' + escapeAttr(ctx.mpBase.replace(/\/+$/, '') + '/' + value.replace(/^\/+/, '')) + '"'
        continue
      }
      out += ' ' + key + '="' + escapeAttr(value === true ? '' : value) + '"'
    }

    // switch 组件：自绘开关替身（原生组件在浏览器里不存在）
    if (node.tag === 'switch') {
      classList.push('wb-switch')
      if (interpolate(attrs.checked, scope, ctx.onExprError)) classList.push('wb-switch-on')
    }

    if (classList.length) out += ' class="' + escapeAttr(classList.join(' ')) + '"'
    if (style.length) out += ' style="' + escapeAttr(style.join(';')) + '"'

    // 事件用委托：只挂一个编号，真实监听在 harness 上。
    // data-wb-h 额外带上处理器名，方便调试与自动化定位（不影响逻辑）。
    for (var e = 0; e < events.length; e++) {
      out += ' data-wb-ev="' + ctx.registerEvent(events[e]) + '"'
      out += ' data-wb-h="' + escapeAttr(events[e].handler) + '"'
    }

    if (tag === 'img') return out + ' />'
    return out + '>' + renderNodes(node.children, scope, ctx) + '</' + tag + '>'
  }

  function eventTypeOf(bindKey) {
    if (bindKey.indexOf('input') !== -1) return 'input'
    if (bindKey.indexOf('change') !== -1) return 'change'
    if (bindKey.indexOf('confirm') !== -1) return 'change'
    if (bindKey.indexOf('longpress') !== -1) return 'longpress'
    return 'tap'
  }

  // ══════════════════════════════════════════════════════════════
  // 4. WXSS 处理
  // ══════════════════════════════════════════════════════════════

  /**
   * 展开 WXSS 的 @import
   *
   * 真机的编译链会把 `@import "../../styles/x.wxss";` 内联进来，**浏览器不认识它**：
   * 浏览器会把它当普通样式表引用去请求 `/styles/x.wxss`，而那个路径在预览服务里
   * 并不存在（预览器是按 `miniprogram/` 的清单取文件的），于是 404 + 样式整段丢失。
   * 表现是「预览里页面像没样式，真机却是好的」—— 这种偏差最容易把人带偏。
   *
   * 故在预览侧按文件路径递归内联。循环引用用 seen 挡住，缺失文件留一条注释。
   */
  function inlineWxssImports(css, fromPath, files, root, seen) {
    var guard = seen || {}
    return String(css).replace(
      /@import\s+(?:url\()?\s*["']([^"']+)["']\s*\)?\s*;/g,
      function (whole, rel) {
        var target = joinPath(fromPath, rel)
        var key = root + target
        if (guard[key]) return '/* @import 循环引用，已跳过: ' + rel + ' */'
        if (!files[key]) return '/* @import 找不到文件: ' + rel + ' */'
        guard[key] = 1
        return inlineWxssImports(files[key], target, files, root, guard)
      }
    )
  }

  /**
   * rpx → calc(N * var(--rpx))；page 选择器 → .wb-page-root；image 元素选择器 → img
   *
   * opts 给齐时（{fromPath, files, root}）先把 @import 内联进来，见上面的说明。
   */
  function transformWxss(css, opts) {
    var src = css
    if (opts && opts.files && opts.fromPath) {
      src = inlineWxssImports(css, opts.fromPath, opts.files, opts.root || ROOT)
    }
    return String(src)
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/(^|[^.\w#-])page(\s*[{,])/g, '$1.wb-page-root$2')
      .replace(/(^|[\s,>+~])(image|cover-image)(?=[\s,{.:>+~\[])/g, '$1img')
      .replace(/(-?\d*\.?\d+)rpx/g, function (_, num) {
        return 'calc(' + num + ' * var(--rpx))'
      })
  }

  // ══════════════════════════════════════════════════════════════
  // 5. 运行时
  // ══════════════════════════════════════════════════════════════

  var ROOT = 'miniprogram/'

  function deepClone(v) {
    return v === undefined ? v : JSON.parse(JSON.stringify(v))
  }

  function joinPath(fromFile, req) {
    var dir = fromFile.replace(/[^/]*$/, '')
    var parts = (dir + req).split('/')
    var out = []
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i]
      if (!p || p === '.') continue
      if (p === '..') out.pop()
      else out.push(p)
    }
    return out.join('/')
  }

  function createRuntime(opts) {
    var files = opts.files || {}
    var log = opts.log || function () {}
    var ui = opts.ui || {}
    var MP = opts.mpBase || 'mp/'
    var appPath = ROOT + 'app.json'
    var appJson = JSON.parse(files[appPath])
    var API_BASE = opts.apiBase

    var appConfig = { globalData: {} }
    var moduleCache = {}
    var pageConfigs = {}
    // 页面实例保活：模拟小程序页面栈 —— navigateTo 建新实例，
    // navigateBack 复用栈里那个实例（数据还在，不会因为返回就丢掉筛选状态）
    var pageInstances = {}
    var storage = {}

    // ---- wx shim ----
    var wxImpl = {
      request: function (o) {
        var url = String(o.url || '')
        var body = o.data
        var init = { method: o.method || 'GET', headers: {} }
        if (init.method === 'GET') {
          var qs = body && Object.keys(body).length
            ? '?' + Object.keys(body).map(function (k) {
              return k + '=' + encodeURIComponent(body[k])
            }).join('&')
            : ''
          url += qs
        } else {
          init.headers['Content-Type'] = 'application/json'
          init.body = JSON.stringify(body || {})
        }
        fetch(url, init).then(function (res) {
          return res.text().then(function (text) {
            var data
            try { data = text ? JSON.parse(text) : {} } catch (e) { data = { message: text } }
            if (res.status >= 200 && res.status < 300) {
              o.success && o.success({ statusCode: res.status, data: data })
            } else {
              o.fail && o.fail({ statusCode: res.status, data: data })
            }
            o.complete && o.complete()
          })
        }).catch(function (err) {
          log('wx.request 失败: ' + url + ' → ' + err.message, 'error')
          o.fail && o.fail({ errMsg: String(err) })
          o.complete && o.complete()
        })
      },
      showToast: function (o) { ui.toast && ui.toast((o && o.title) || '') },
      showModal: function (o) {
        var opts = o || {}
        var handled = function (res) {
          opts.success && opts.success(res)
          opts.complete && opts.complete(res)
        }
        if (ui.modal) {
          ui.modal(opts, handled)
        } else {
          // 宿主没给弹窗替身时，默认「确定」——真机上这里必然有原生弹窗
          handled({ confirm: true, cancel: false })
        }
      },
      showLoading: function () {},
      hideLoading: function () {},
      setNavigationBarTitle: function (o) { ui.setTitle && ui.setTitle((o && o.title) || '') },
      navigateTo: function (o) { runtime.navigate((o && o.url) || '', 'push') },
      redirectTo: function (o) { runtime.navigate((o && o.url) || '', 'replace') },
      reLaunch: function (o) { runtime.navigate((o && o.url) || '', 'reset') },
      switchTab: function (o) { runtime.navigate((o && o.url) || '', 'reset') },
      navigateBack: function () { runtime.back() },
      getStorageSync: function (k) { return storage[k] === undefined ? '' : storage[k] },
      setStorageSync: function (k, v) { storage[k] = v },
      removeStorageSync: function (k) { delete storage[k] },
      setClipboardData: function (o) {
        var text = (o && o.data) || ''
        try { navigator.clipboard && navigator.clipboard.writeText(text) } catch (e) {}
        log('已复制到剪贴板：' + text.replace(/\n/g, ' ⏎ '))
        ui.toast && ui.toast('已复制')
        o && o.success && o.success()
      },
      showShareMenu: function () {},
      onShareAppMessage: function () {}
    }

    var wx = new Proxy(wxImpl, {
      get: function (t, k) {
        if (k in t) return t[k]
        return function () {
          log('预览未实现 wx.' + String(k) + '（真机才有对应能力）', 'warn')
        }
      }
    })

    function getApp() { return appConfig }

    // ---- 模块加载 ----
    // 注意：loadModule 返回的是 module.exports（业务代码要用的），
    // 而 Page() 抓到的配置挂在「模块记录」上 —— 必须单独存一张表，
    // 不能指望从 exports 上取回来（exports 可能被页面置空或替换）。
    function loadModule(path) {
      if (moduleCache[path]) return moduleCache[path].exports
      var code = files[path]
      var mod = { exports: {} }
      moduleCache[path] = mod
      if (code === undefined) {
        log('模块缺失：' + path, 'error')
        return mod.exports
      }
      var pageCapture = null
      var fn = new Function(
        'module', 'exports', 'require', 'getApp', 'wx', 'Page', 'App', 'console',
        code + '\n//# sourceURL=' + path
      )
      fn(
        mod, mod.exports,
        function (req) { return loadModule(joinPath(path, req) + '.js') },
        getApp, wx,
        function (cfg) { pageCapture = cfg },
        function (cfg) { appConfig = cfg },
        console
      )
      if (pageCapture) pageConfigs[path] = pageCapture
      return mod.exports
    }

    function pageConfigOf(path) {
      if (!moduleCache[path]) loadModule(path)
      return pageConfigs[path] || null
    }

    // ---- app.js ----
    loadModule(ROOT + 'app.js')
    if (API_BASE) appConfig.globalData.apiBase = API_BASE
    log('apiBase = ' + appConfig.globalData.apiBase)

    // ---- 页面 ----

    function collectWxs(nodes, scope) {
      for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i]
        if (node.type !== 'element') continue
        if (node.tag === 'wxs') {
          var name = node.attrs.module
          if (!name) continue
          var mod = { exports: {} }
          try {
            new Function('module', 'exports', node.raw || '')(mod, mod.exports)
            scope[name] = mod.exports
          } catch (e) {
            log('wxs 模块 ' + name + ' 求值失败：' + e.message, 'error')
            scope[name] = {}
          }
          continue
        }
        collectWxs(node.children || [], scope)
      }
    }

    var runtime = {
      appJson: appJson,
      app: null,
      current: null,
      stack: [],

      navigate: function (url, mode) {
        var path = url
        var query = {}
        var qi = url.indexOf('?')
        if (qi !== -1) {
          path = url.slice(0, qi)
          url.slice(qi + 1).split('&').forEach(function (kv) {
            if (!kv) return
            var p = kv.split('=')
            query[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || '')
          })
        }
        var pagePath = path.replace(/^\//, '')
        if (!files[ROOT + pagePath + '.wxml']) {
          log('页面不存在：' + pagePath, 'error')
          return
        }
        if (mode === 'reset') {
          // reLaunch / switchTab：重建整个页面栈，实例全部销毁
          this.stack = []
          pageInstances = {}
        } else if (mode === 'replace') {
          // redirectTo：当前页面实例被替换掉
          if (this.current) delete pageInstances[this.current.path]
        } else if (this.current) {
          this.stack.push({ path: this.current.path, query: this.current.query })
        }
        this.open(pagePath, query)
      },

      back: function () {
        var prev = this.stack.pop()
        if (prev) this.open(prev.path, prev.query, true)
        else log('已是首个页面', 'warn')
      },

      open: function (pagePath, query, isBack) {
        var modPath = ROOT + pagePath + '.js'
        var cfg = pageConfigOf(modPath)
        if (!cfg) { log('页面未调用 Page()：' + pagePath, 'error'); return }

        var inst = pageInstances[pagePath]
        var isNew = !inst

        if (isNew) {
          inst = Object.create(cfg)
          inst.data = deepClone(cfg.data || {})
          inst.__path = pagePath

          // ── setData：只更新数据；**只有当前显示的页面才重绘** ──
          // 这一条是必须的：真机上后台页面 setData 也会更新数据，但不会重绘。
          // 反例：感觉页 onSubmit 在 wx.navigateTo 之后还有
          //   finally { this.setData({ loading: false }) }
          // 如果允许它重绘，就会把已经打开的「结果页」画面覆盖回「感觉页」——
          // 表现是「点了生成名字，页面纹丝不动」，而且没有任何报错。
          inst.setData = function (patch, cb) {
            for (var k in patch) {
              if (!Object.prototype.hasOwnProperty.call(patch, k)) continue
              if (k.indexOf('.') !== -1) {
                var segs = k.split('.')
                var cur = inst.data
                for (var s = 0; s < segs.length - 1; s++) {
                  if (cur[segs[s]] === undefined) cur[segs[s]] = {}
                  cur = cur[segs[s]]
                }
                cur[segs[segs.length - 1]] = patch[k]
              } else {
                inst.data[k] = patch[k]
              }
            }
            if (runtime.current && runtime.current.instance === inst) render()
            if (cb) setTimeout(cb, 0)
          }

          inst.__render = function () { render() }

          // 事件派发（由 harness 的委托监听调用）
          inst.__fire = function (evIndex, domEvent, detail) {
            var ev = (runtime.current && runtime.current.instance === inst)
              ? runtime.current.events[evIndex]
              : null
            if (!ev) return
            var el = domEvent && domEvent.currentTarget ? domEvent.currentTarget : null
            var dataset = {}
            if (el && el.dataset) {
              for (var dk in el.dataset) dataset[dk] = el.dataset[dk]
            }
            var handler = inst[ev.handler]
            if (typeof handler !== 'function') {
              log('页面没有定义事件处理器：' + ev.handler, 'warn')
              return
            }
            var ret = null
            try {
              ret = handler.call(inst, {
                type: ev.type,
                detail: detail || {},
                currentTarget: { dataset: dataset, id: el && el.id },
                target: { dataset: dataset }
              })
            } catch (err) {
              log('事件 ' + ev.handler + ' 抛错：' + err.message, 'error')
            }
            // async 处理器（如 onSubmit）抛错会变成 rejected promise，
            // 不会被上面的 try/catch 接住 —— 必须显式接，否则「点了没反应」
            // 这类问题在预览里会完全静默，只能靠猜。
            if (ret && typeof ret.then === 'function') {
              ret.catch(function (err) {
                log('事件 ' + ev.handler + ' 的异步处理失败：' + ((err && err.message) || err), 'error')
              })
            }
            if (ev.type === 'tap') {
              var openType = el && el.getAttribute && el.getAttribute('data-open-type')
              if (openType === 'share' && typeof inst.onShareAppMessage === 'function') {
                var shareReturn = inst.onShareAppMessage({ from: 'button', target: el })
                log('分享卡片：title=' + JSON.stringify(shareReturn && shareReturn.title) +
                  ' path=' + JSON.stringify(shareReturn && shareReturn.path))
                ui.toast && ui.toast('分享：' + ((shareReturn && shareReturn.title) || ''))
              }
            }
          }

          pageInstances[pagePath] = inst
        }

        function render() {
          var wxmlPath = ROOT + pagePath + '.wxml'
          var nodes = parseWxml(files[wxmlPath] || '')
          var wxsScope = {}
          collectWxs(nodes, wxsScope)
          var scope = Object.create(null)
          for (var k in wxsScope) scope[k] = wxsScope[k]
          for (var d in inst.data) scope[d] = inst.data[d]

          var events = []
          var html = renderNodes(nodes, scope, {
            mpBase: MP,
            registerEvent: function (ev) { events.push(ev); return events.length - 1 },
            onExprError: function (expr, err) {
              log('表达式求值失败 {{' + expr + '}}: ' + err.message, 'warn')
            }
          })

          // 先把 current 指到「即将显示的页面」，再 mount：
          // 因为 mount 之后可能同步触发 setData（如 onShow 里的首屏请求），
          // 那时必须已经知道自己是可见页面，否则会被自己的重绘判成后台页面。
          runtime.current = { path: pagePath, query: query, instance: inst, events: events }
          ui.mount && ui.mount(html, events, inst)
          ui.setNav && ui.setNav({
            path: pagePath,
            canBack: runtime.stack.length > 0,
            title: (JSON.parse(files[ROOT + pagePath + '.json'] || '{}').navigationBarTitleText) || ''
          })
        }

        // 生命周期：onLoad / onReady 只在首次进入该页面时各跑一次；onShow 每次显示都跑
        if (isNew) {
          if (typeof inst.onLoad === 'function') inst.onLoad(query || {})
        }
        if (typeof inst.onShow === 'function') inst.onShow()
        render()
        if (isNew && typeof inst.onReady === 'function') inst.onReady()
      }
    }

    // 暴露给 harness / 调试台：读 globalData 用（getApp() 才是页面里的正路）
    runtime.getApp = getApp
    // 本地存储替身的内容（自检用，真机上是 wx.getStorage 系列）
    runtime.debugStorage = function (key) { return storage[key] }

    return runtime
  }

  return {
    version: '1.0.0',
    parseWxml: parseWxml,
    renderNodes: renderNodes,
    transformWxss: transformWxss,
    interpolate: interpolate,
    createRuntime: createRuntime
  }
})
