/**
 * 分享落地页（/pages/share/share）
 *
 * 为什么单独开一页，而不是直接分享 detail：
 *   detail 依赖 app.globalData.selectedName，好友冷启动点开分享卡时该数据不存在，
 *   onLoad 会直接 navigateBack —— 把 detail 当落地页，好友点进来看到的是一片空白。
 *   故落地页必须能用 URL 参数**重建内容**。
 *
 * 入参（除 n 外都可缺省，缺省即降级）：
 *   n     完整姓名（必填；读不出来就走错误态，不白屏）
 *   c     出处全称，如《诗经·周南·关雎》
 *   x     出处原句，如「关关雎鸠，在河之洲」
 *   a     作者，d 朝代（只作署名，缺了不显示）
 *   s     出处意境（「余味」那一句，取自诗库 scene 字段）
 *   g     male | female（只影响深度解读的用词，不影响页面主体）
 *   from  card（来自分享卡）
 *
 * 为什么出处要随链接带走，而不是落地页重新解析：
 *   生成器给名字配出处走的是「本次生成上下文里的那一条」，而落地页只有名字，
 *   用 /analyze 重新解析可能落到另一首同样含名字用字的诗 —— 分享卡写着
 *   「出自《山鬼》」，点开却是《秋胡行》，「有出处」这一页唯一的立身之本就成了假的。
 *   故分享路径自带出处原文；只有缺 c/x 时才回退到 /analyze 解析。
 *
 * 设计约束（产品层，勿改）：
 *   1. **不显示任何评分。** 推荐分只用于起名时的排序；落地页给名字定三六九等，
 *      等于替收件人评判他朋友的选择。
 *   2. 主体内容（名字 / 出处 / 用字）全部来自本地字库与诗库，**不依赖 LLM**；
 *      语境取义是渐进增强，取不到就少一行，不阻塞首屏、不报错。
 *   3. 小程序码区预留占位（见 wxml 的 qr-block），后端出码能力未配置时显示「名」印。
 */

const api = require('../../utils/api')
const share = require('../../utils/share')

const WUXING_CLASS = {
  金: 'wx-jin',
  木: 'wx-mu',
  水: 'wx-shui',
  火: 'wx-huo',
  土: 'wx-tu'
}

const NAME_MIN = 2
const NAME_MAX = 10
const FALLBACK_TEASER = '同一个字，在字典里是一个意思；在它出生的那句诗里，是另一个意思。'

// 分享链接里的中文可能已被解码，也可能是 %E6%B2%88 形态，两种都要吃得下
function safeDecode(raw) {
  const s = String(raw == null ? '' : raw)
  if (!s) return ''
  if (s.indexOf('%') === -1) return s
  try {
    return decodeURIComponent(s)
  } catch (e) {
    return s
  }
}

function isChineseName(s) {
  if (!s || s.length < NAME_MIN || s.length > NAME_MAX) return false
  for (let i = 0; i < s.length; i++) {
    const code = s.charCodeAt(i)
    if (code < 0x4e00 || code > 0x9fa5) return false
  }
  return true
}

// 把诗句切成「命中名字用字 / 未命中」两类片段，供高亮渲染
// （不用 rich-text：富文本要拼 HTML 字符串，转义一漏就是注入面）
function splitSegments(text, hits) {
  const src = String(text || '')
  const segs = []
  let buf = ''
  let bufHit = null
  for (let i = 0; i < src.length; i++) {
    const ch = src.charAt(i)
    const hit = !!hits[ch]
    if (bufHit === null) {
      buf = ch
      bufHit = hit
      continue
    }
    if (hit === bufHit) {
      buf += ch
      continue
    }
    segs.push({ i: segs.length, t: buf, hit: bufHit })
    buf = ch
    bufHit = hit
  }
  if (buf) segs.push({ i: segs.length, t: buf, hit: bufHit })
  return segs
}

Page({
  data: {
    status: 'loading', // loading | ready | error
    fullName: '',
    given: '',
    pinyinText: '',
    poem: null,
    poemText: '',
    poemSegs: [],
    poemNote: '',
    chars: [],
    teaser: '',
    fromCard: false,
    qrUrl: '', // 后端出码能力就绪后填入，空则显示占位
    errMsg: ''
  },

  onLoad(options) {
    const opt = options || {}
    const fullName = safeDecode(opt.n).replace(/\s/g, '')

    // 兼容旧链接（src/t 只用于解析时对诗，新链接直接带 c/x）
    this.src = safeDecode(opt.src)
    this.poemTitle = safeDecode(opt.t)

    // 分享时看到的出处，随链接带回
    this.carried = {
      citation: safeDecode(opt.c),
      text: safeDecode(opt.x),
      author: safeDecode(opt.a),
      dynasty: safeDecode(opt.d),
      scene: safeDecode(opt.s)
    }

    this.gender = opt.g === 'female' ? 'female' : 'male'
    this.poemRecord = null
    this.analyzeResult = null

    this.setData({ fromCard: opt.from === 'card' })

    if (!isChineseName(fullName)) {
      this.setData({
        status: 'error',
        errMsg: '链接里的名字读不出来，可能被截断了'
      })
      return
    }

    this.setData({ fullName })
    wx.setNavigationBarTitle({ title: fullName + ' · 名堂' })
    this.loadName(fullName)
  },

  async loadName(fullName) {
    try {
      const res = await api.analyzeName({ full_name: fullName, gender: this.gender })
      this.analyzeResult = res

      const given = res.given_name || fullName.slice(1)
      const poem = this.resolvePoem(res, given)
      this.poemRecord = poem

      const chars = this.buildChars(res.chars_info)
      const hits = {}
      for (let i = 0; i < given.length; i++) hits[given.charAt(i)] = true

      const display = this.pickPoemText(poem, given)

      this.setData({
        status: 'ready',
        fullName: res.full_name || fullName,
        given: given,
        pinyinText: (((res.phonetics || {}).pinyins) || []).join(' · '),
        poem: poem,
        poemText: display.text,
        poemSegs: display.text ? splitSegments(display.text, hits) : [],
        poemNote: this.buildPoemNote(given, display.hitChars),
        chars: chars,
        teaser: this.buildTeaser(poem)
      })

      // 语境取义：慢、可失败，能到就补上，到不了就少一行
      this.loadSenses(fullName)

      // 小程序码：未配置出码能力时保持占位印
      this.loadQrcode()
    } catch (err) {
      this.setData({
        status: 'error',
        errMsg: (err && err.message) || '名字加载失败，请稍后再试'
      })
    }
  },

  // 出处优先用链接自带的（= 分享者当时看到的那一首），没有才回落到本地解析
  resolvePoem(res, given) {
    const carried = this.carried || {}
    if (carried.text) {
      return {
        citation: carried.citation || '',
        title: '',
        source: '',
        author: carried.author || '',
        dynasty: carried.dynasty || '',
        text: carried.text,
        scene: carried.scene || ''
      }
    }
    return this.pickPoem(res, given)
  },

  // 诗库里同一批候选诗可能有多首，优先锁定分享时那一首
  pickPoem(res, given) {
    const list = (res.poetry_list && res.poetry_list.length)
      ? res.poetry_list
      : (res.poetry ? [res.poetry] : [])
    if (!list.length) return null

    const wantTitle = this.poemTitle
    const wantSrc = this.src
    const chars = String(given || '').split('')

    // 一首诗里到底命中几个名字用字（摘句优先，摘句没有再看全篇）
    const score = function (p) {
      if (!p) return 0
      const excerpt = String(p.text || '')
      const full = String(p.original_text || '')
      let n = 0
      for (let i = 0; i < chars.length; i++) {
        const c = chars[i]
        if (!c) continue
        if (excerpt.indexOf(c) !== -1 || full.indexOf(c) !== -1) n++
      }
      return n
    }

    // 最佳候选：命中数最多；同分取靠前的（诗库顺序本身带推荐度）
    const bestOf = function (pool) {
      let best = null
      let bestScore = -1
      for (let i = 0; i < pool.length; i++) {
        const s = score(pool[i])
        if (s > bestScore) {
          bestScore = s
          best = pool[i]
        }
      }
      return bestScore > 0 ? best : null
    }

    // ① 精确锁定分享时那一首（换诗会让收件人看到与分享卡不符的出处）
    if (wantTitle) {
      for (let i = 0; i < list.length; i++) {
        if (list[i] && list[i].title === wantTitle) return list[i]
      }
    }

    // ② 同出处里挑命中最多的
    if (wantSrc) {
      const sameSrc = []
      for (let i = 0; i < list.length; i++) {
        if (list[i] && list[i].source === wantSrc) sameSrc.push(list[i])
      }
      const hit = bestOf(sameSrc)
      if (hit) return hit
      if (sameSrc.length) return sameSrc[0]
    }

    // ③ 全池里挑命中最多的
    return bestOf(list) || list[0]
  },

  buildChars(charsInfo) {
    return (charsInfo || [])
      .filter(function (c) { return c && c.char })
      .map(function (c) {
        return {
          char: c.char,
          pinyin: c.pinyin || '',
          wuxing: c.wuxing || '',
          wuxingClass: WUXING_CLASS[c.wuxing] || '',
          strokes: c.kangxi_strokes || 0,
          meaning: c.meaning || '',
          sensesText: ''
        }
      })
  },

  // 挑一句**真的含名字用字**的原文。
  // 诗库的倒排索引建在 recommend_chars 上，而 recommend_chars 可能取自全篇，
  // 于是 poem.text（摘句）里未必有名字用字。这时去 original_text 里捞含字的那一句，
  // 而不是硬拿摘句充数 —— 「有出处」是这一页唯一的立身之本，不能是假的。
  pickPoemText(poem, given) {
    if (!poem) return { text: '', hitChars: [] }

    const chars = String(given || '').split('')
    const excerpt = String(poem.text || '')
    const full = String(poem.original_text || '')

    function hitsIn(text) {
      const out = []
      for (let i = 0; i < chars.length; i++) {
        const c = chars[i]
        if (c && text.indexOf(c) !== -1 && out.indexOf(c) === -1) out.push(c)
      }
      return out
    }

    const excerptHits = hitsIn(excerpt)
    if (excerptHits.length) return { text: excerpt, hitChars: excerptHits }

    // 摘句不含名字用字：从全篇按句切，取第一句含字的
    // ⚠️ 这里的引号写 `\u0022` 而不是字面双引号：tests/test_share_policy.py 会先剥掉
    //    JS 字符串再做花括号配对，正则字符类里出现字面双引号会把它的扫描状态带偏，
    //    导致本页的 onShareAppMessage 被判定为「未定义」。
    if (full) {
      const sentences = full.split(/[。！？；\n]/)
      for (let i = 0; i < sentences.length; i++) {
        const s = sentences[i].replace(/^[\u0022「『“‘\s]+/, '').trim()
        if (!s) continue
        const hits = hitsIn(s)
        if (hits.length) return { text: s, hitChars: hits }
      }
    }

    return { text: excerpt, hitChars: [] }
  },

  buildPoemNote(given, hitChars) {
    const chars = String(given || '').split('')
    if (!chars.length) return ''

    if (hitChars.length >= chars.length) return '名字用字已在句中标出'
    if (hitChars.length) return '此句含名中「' + hitChars.join('」「') + '」字'
    return '此句与名字意境相通'
  },

  // 一句「余味」：诗库自带 scene（寄托清雅高洁、淡泊宁静之志）最贴切。
  // 没有 scene 时不要拿字义硬凑 —— 那会和下面的「名字用字」重复，
  // 退成一句能引出「语境取义」的话更实在。
  buildTeaser(poem) {
    if (poem && poem.scene) return poem.scene
    return FALLBACK_TEASER
  },

  async loadSenses(fullName) {
    try {
      const res = await api.nameMeaning({ full_name: fullName, gender: this.gender })
      const map = {}
      ;(res.context_senses || []).forEach(function (item) {
        if (!item || !item.char) return
        // 该字的义项若取自别的句子，挂在这个出处下会误导，宁可不显示
        if (item.from_main === false) return
        const senses = item.senses || []
        if (senses.length) map[item.char] = senses.join(' · ')
      })

      if (!Object.keys(map).length) return

      const chars = this.data.chars.map(function (c) {
        return Object.assign({}, c, { sensesText: map[c.char] || c.sensesText })
      })
      this.setData({ chars: chars })
    } catch (e) {
      // 深度解读不可用不影响落地页主体，静默即可
    }
  },

  // 小程序码：后端未配置 AppID/Secret 时返回 501，这里保持占位印
  async loadQrcode() {
    try {
      const url = await api.shareQrcode()
      if (url) this.setData({ qrUrl: url })
    } catch (e) {
      // 开发期（未提审）拿不到码是正常状态，占位印就是为它留的
    }
  },

  // 看完整解读：detail 依赖 globalData.selectedName，这里用解析结果重建一份再跳，
  // 否则 detail.onLoad 会因取不到名字而 navigateBack（冷启动没有上一页）
  onOpenDetail() {
    const res = this.analyzeResult
    if (!res) {
      this.onStartNaming()
      return
    }

    const app = getApp()
    app.globalData.selectedName = {
      full_name: this.data.fullName,
      given_name: this.data.given,
      chars_info: res.chars_info || [],
      poetry: this.poemRecord,
      phonetics: res.phonetics || {},
      wuge: res.wuge || {},
      meaning: '',
      context_senses: []
    }
    app.globalData.lastParams = { gender: this.gender }

    wx.navigateTo({
      url: '/pages/detail/detail',
      fail: function () {
        wx.showToast({ title: '打开失败，请重试', icon: 'none' })
      }
    })
  },

  onStartNaming() {
    wx.navigateTo({
      url: '/pages/name/name',
      fail: function () {
        wx.reLaunch({ url: '/pages/name/name' })
      }
    })
  },

  onAnalyzeMine() {
    wx.navigateTo({
      url: '/pages/analyze/analyze',
      fail: function () {
        wx.reLaunch({ url: '/pages/analyze/analyze' })
      }
    })
  },

  // ── 分享 ──
  // ⚠️ onShareAppMessage 只认 title / path / imageUrl / promise，
  //    写 success 会被静默忽略（detail 的分享解锁曾因此整条链路失效）。
  //    该约束由 tests/test_share_policy.py 门禁。

  // 交给统一分享工具组包：本页与 detail 页共用同一套参数口径，
  // 否则两处各写一遍，迟早漂移成「分享卡写一首、落地页显示另一首」
  sharePoem() {
    const poem = this.poemRecord || this.data.poem
    if (!poem) return null
    return {
      citation: poem.citation,
      // 显示的是哪一句就带走哪一句（可能取自全篇，未必等于 poem.text）
      text: this.data.poemText || poem.text,
      author: poem.author,
      dynasty: poem.dynasty,
      scene: poem.scene
    }
  },

  onShareAppMessage() {
    return share.nameShare(this.data.fullName, this.sharePoem(), this.gender)
  },

  // 朋友圈不支持自定义 path，只能带 query
  onShareTimeline() {
    return share.nameTimeline(this.data.fullName, this.sharePoem(), this.gender)
  }
})
