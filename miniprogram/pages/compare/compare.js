/**
 * 对比 · 测候选名 / 双名对比
 *
 * ── 为什么两件事合成一个页面 ──
 * 「测候选名」和「双名对比」在用户这里是同一件事：手上不止一个名字，想并排看看。
 * 分成两个入口会让用户先做一个他并不关心的选择（我是要「测」还是「比」？），
 * 而页面本身、接口本身、结果本身都是同一份 —— 故只有一页、一张对照表。
 *
 * 名字从两处来：
 *   1. 释名页「手上不止一个名字」→ 空表，用户自己输；
 *   2. 名字本收藏页「对比」→ 队列里已有名字（utils/compare.js）。
 * 生辰不在这里问：从释名页进来时继承那份生辰（globalData.compareBirth），
 * 从收藏进来时没有生辰，就只比名字本身 —— 不为了多一行匹配度再抄一套日期弹层。
 */

const api = require('../../utils/api')
const share = require('../../utils/share')
const compare = require('../../utils/compare')

// 表头标签集中在这里，改文案不用在 buildRows 里到处找
const LABELS = {
  pinyin: '读音',
  wuxing: '用字五行',
  phon: '音律',
  strokes: '名用笔画',
  poetry: '出处',
  bazi: '与生辰'
}

function charsInfoOf(item) {
  return (item && item.chars_info) || []
}

// 名字的康熙笔画合计（只算名，不算姓 —— 姓是共用的，比了没意义）
function strokesOf(item) {
  let total = 0
  charsInfoOf(item).forEach(function (ci) {
    total += (ci && ci.kangxi_strokes) || 0
  })
  return total
}

function wuxingOf(item) {
  return charsInfoOf(item)
    .map(function (ci) { return ci.wuxing || '未知' })
    .join(' · ')
}

function poetryOf(item) {
  const list = (item && item.poetry_list) || []
  if (!list.length) return { source: '—', title: '' }
  return { source: list[0].source || '—', title: list[0].title || '' }
}

/**
 * 由解析结果拼出对照表的行。
 *
 * 只放**能并排比的事实**（音律、五行、笔画、出处、八字匹配）。
 * 不放五格吉凶（产品底线：不判吉凶）、不放「推荐分」（评分只作推荐分，
 * 不作等级分 —— 一旦并排成两列高低，就变成了评级）。
 * 定性的判断放到表下的「逐个说」，各自成句，不摆在一起比大小。
 */
function buildRows(items, withBazi) {
  const rows = []

  // 每个格子补一个稳定 key（行名 + 列序）：wx:for 用 wx:key 才不会有重复键告警，
  // 而 main 是展示文本，两个名字可能同值（同音），不能当 key
  const withKeys = function (key, build) {
    return {
      key: key,
      label: LABELS[key],
      cells: items.map(function (it, i) {
        const cell = build(it)
        cell.k = key + '-' + i
        return cell
      })
    }
  }

  rows.push(withKeys('pinyin', function (it) {
    const p = it.phonetics || {}
    return { main: (p.pinyins || []).join(' '), sub: '' }
  }))

  rows.push(withKeys('wuxing', function (it) {
    return { main: wuxingOf(it), sub: '' }
  }))

  rows.push(withKeys('phon', function (it) {
    const p = it.phonetics || {}
    return { main: (p.score || 0) + ' 分', sub: p.rhythm || '' }
  }))

  rows.push(withKeys('strokes', function (it) {
    return { main: String(strokesOf(it)), sub: '不含姓' }
  }))

  rows.push(withKeys('poetry', function (it) {
    const p = poetryOf(it)
    return { main: p.source, sub: p.title }
  }))

  if (withBazi) {
    rows.push(withKeys('bazi', function (it) {
      const m = it.bazi_match
      if (!m) return { main: '—', sub: '' }
      const matched = m.matched_wuxing || []
      return {
        main: matched.length ? '补 ' + matched.join('、') : '无补益',
        sub: '匹配 ' + (m.match_score || 0) + ' 分'
      }
    }))
  }

  return rows
}

Page({
  data: {
    names: [],
    items: [],
    rows: [],
    rejected: [],
    verdicts: [],
    input: '',
    loading: false,
    loadError: '',
    birth: null,
    birthText: '',
    max: compare.MAX
  },

  onLoad() {
    const app = getApp()
    const birth = app.globalData.compareBirth || null
    this.setData({
      birth: birth,
      birthText: birth
        ? birth.year + '-' + birth.month + '-' + birth.day +
          (birth.hourUnknown ? ' · 时辰未知' : '')
        : ''
    })
    this.reload()
  },

  onShow() {
    // 从别的页面回来时队列可能变了（比如又收藏了一个名字）
    const names = compare.list()
    if (names.join('|') !== this.data.names.join('|')) this.reload()
  },

  onInput(e) {
    this.setData({ input: e.detail.value })
  },

  // ── 增删名字 ──

  onAddTap() {
    const raw = (this.data.input || '').trim()
    if (!raw) {
      wx.showToast({ title: '先输入一个名字', icon: 'none' })
      return
    }
    // 支持一次粘多个：空格、逗号、顿号、换行都当分隔符
    const parts = raw.split(/[\s,，、;；]+/).filter(function (s) { return s })
    let refused = 0
    let full = false

    parts.forEach(function (name) {
      const ret = compare.add(name)
      if (!ret.ok) {
        if (ret.full) full = true
        else refused++
      }
    })

    if (full) {
      wx.showToast({ title: '最多并排 ' + compare.MAX + ' 个，先去掉一个', icon: 'none' })
    } else if (refused) {
      wx.showToast({ title: '有 ' + refused + ' 个名字没能加入', icon: 'none' })
    }

    this.setData({ input: '' })
    this.reload()
  },

  onRemoveTap(e) {
    compare.remove(e.currentTarget.dataset.name)
    this.reload()
  },

  onClearTap() {
    compare.clear()
    this.setData({ items: [], rows: [], verdicts: [], rejected: [] })
    this.reload()
  },

  // 点列头 → 看这个名的完整释名结果（复用释名结果页，不另做一套）
  onOpenDetail(e) {
    const index = e.currentTarget.dataset.index
    const item = this.data.items[index]
    if (!item) return
    const app = getApp()
    app.globalData.analyzeResult = item
    wx.navigateTo({ url: '/pages/analyze-result/analyze-result' })
  },

  // ── 请求 ──

  reload() {
    const names = compare.list()
    this.setData({ names: names })

    if (!names.length) {
      this.setData({ items: [], rows: [], verdicts: [], rejected: [], loadError: '' })
      return
    }

    const birth = this.data.birth || {}
    const params = { names: names }
    if (birth.year && birth.month && birth.day) {
      params.year = birth.year
      params.month = birth.month
      params.day = birth.day
      // 时辰未知就不传 hour，后端按 hour_known=false 处理，不拿午时冒充
      if (!birth.hourUnknown && birth.hour !== undefined) params.hour = birth.hour
    }

    this.setData({ loading: true, loadError: '' })
    const self = this
    api.analyzeBatch(params).then(function (res) {
      const items = (res && res.items) || []
      self.setData({
        items: items,
        rows: buildRows(items, !!(birth.year && birth.month && birth.day)),
        verdicts: items.map(function (it) {
          return { name: it.full_name, text: it.verdict || '' }
        }),
        rejected: (res && res.rejected) || []
      })
    }).catch(function (err) {
      self.setData({
        items: [],
        rows: [],
        verdicts: [],
        loadError: (err && err.message) || '没能算出来，稍后再试'
      })
    }).then(function () {
      self.setData({ loading: false })
    })
  },

  onRetry() {
    this.reload()
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
