const api = require('../../utils/api')
const share = require('../../utils/share')
const namebook = require('../../utils/namebook')

// 结果页风格筛选条：全部 + 8 个风格（与后端 STYLE_OPTIONS 同源，见 utils/api.js）
const styleFilters = [{ code: '', name: '全部' }].concat(
  api.STYLE_OPTIONS.map(function (o) {
    return { code: o.code, name: o.short || o.name }
  })
)

// 取一个候选名的用字（优先 chars_info，兜底 given_name）
function charsOf(n) {
  const out = []
  ;(n.chars_info || []).forEach(function (ci) {
    if (ci && ci.char) out.push(ci.char)
  })
  if (!out.length && n.given_name) {
    n.given_name.split('').forEach(function (c) { out.push(c) })
  }
  return out
}

// 出处筛选：只列出本批候选里真实出现的出处。
// 不预设全集，否则会出现「选了却筛不出任何名字」的空选项。
function buildSourceFilters(allNames) {
  const seen = {}
  const list = [{ code: '', name: '全部' }]
  allNames.forEach(function (n) {
    const s = (n.poetry && n.poetry.source) || ''
    if (s && !seen[s]) {
      seen[s] = true
      list.push({ code: s, name: s })
    }
  })
  return list
}

// 用字筛选：取候选里出现频次最高的字。
// 这一步承接了原先放在起名向导里的「精选用字」，改成生成后再收敛。
function buildCharFilters(allNames, limit) {
  const freq = {}
  allNames.forEach(function (n) {
    charsOf(n).forEach(function (c) {
      freq[c] = (freq[c] || 0) + 1
    })
  })
  return Object.keys(freq)
    .sort(function (a, b) { return freq[b] - freq[a] })
    .slice(0, limit || 24)
    .map(function (c) { return { code: c, name: c } })
}

Page({
  data: {
    bazi: null,
    allNames: [],
    names: [],
    xiyongText: '',
    wuxingList: [],
    wuxingFilter: '',
    styleFilter: '',
    sourceFilter: '',
    charFilter: '',
    loading: false,
    fallbackNote: '',

    // 八字排盘卡默认折叠、筛选栏默认只显示五行
    baziOpen: false,
    filterOpen: false,

    // 已收藏的全名映射 { 全名: true }，供每张卡片显示收藏态
    favIds: {},

    wuxingFilters: [
      { code: '', name: '全部' },
      { code: '金', name: '金' },
      { code: '木', name: '木' },
      { code: '水', name: '水' },
      { code: '火', name: '火' },
      { code: '土', name: '土' }
    ],
    styleFilters: styleFilters,
    sourceFilters: [{ code: '', name: '全部' }],
    charFilters: []
  },

  onLoad() {
    const app = getApp()
    const result = app.globalData.lastResult

    if (!result) {
      wx.navigateBack()
      return
    }

    this.renderResult(result)
  },

  renderResult(result) {
    const wuxingList = []
    if (result.bazi && result.bazi.wuxing) {
      const pct = result.bazi.wuxing.percentages
      const order = ['金', '木', '水', '火', '土']
      for (const name of order) {
        wuxingList.push({ name, percent: pct[name] || 0 })
      }
    }

    const xiyongText = result.bazi
      ? result.bazi.xiyong.xi_wuxing.join('、')
      : ''

    // 给每个名字加上拼音展示文本，作为全量候选池
    const allNames = (result.names || []).map(function (n) {
      n.pinyinText = (n.phonetics && n.phonetics.pinyins) ? n.phonetics.pinyins.join(' · ') : ''
      return n
    })

    this.setData({
      bazi: result.bazi,
      allNames: allNames,
      xiyongText: xiyongText,
      wuxingList: wuxingList,
      fallbackNote: result.fallback_note || '',
      // 候选变了，筛选项随之重建
      sourceFilters: buildSourceFilters(allNames),
      charFilters: buildCharFilters(allNames),
      // 已收藏的全名映射，applyFilter 渲染时按它打标
      favIds: namebook.favMap()
    })
    this.applyFilter()
  },

  applyFilter() {
    const wuxingFilter = this.data.wuxingFilter
    const styleFilter = this.data.styleFilter
    const sourceFilter = this.data.sourceFilter
    const charFilter = this.data.charFilter
    const favIds = this.data.favIds || {}

    const names = this.data.allNames.filter(function (n) {
      if (wuxingFilter) {
        const chars = n.chars_info || []
        let hit = false
        for (let i = 0; i < chars.length; i++) {
          if (chars[i].wuxing === wuxingFilter) {
            hit = true
            break
          }
        }
        if (!hit) return false
      }

      if (styleFilter) {
        // 一对多判定：一条出处可同时属于多个风格，命中任一即保留
        const source = (n.poetry && n.poetry.source) || ''
        if (api.getStyleCodes(source).indexOf(styleFilter) === -1) return false
      }

      if (sourceFilter) {
        if (((n.poetry && n.poetry.source) || '') !== sourceFilter) return false
      }

      if (charFilter) {
        if (charsOf(n).indexOf(charFilter) === -1) return false
      }

      return true
    })

    // 渲染项按收藏态复制一份：不直接改 allNames 里的对象，
    // 避免 wx:for 复用旧对象时收藏标记不刷新（setData 的差量只到数组这一层）
    const decorated = names.map(function (n) {
      return Object.assign({}, n, { fav: !!favIds[n.full_name] })
    })

    this.setData({ names: decorated })
  },

  onWuxingFilterTap(e) {
    this.setData({ wuxingFilter: e.currentTarget.dataset.code })
    this.applyFilter()
  },

  onStyleFilterTap(e) {
    this.setData({ styleFilter: e.currentTarget.dataset.code })
    this.applyFilter()
  },

  // 再点一次已选中的项 = 取消该项筛选
  onSourceFilterTap(e) {
    const code = e.currentTarget.dataset.code
    this.setData({ sourceFilter: this.data.sourceFilter === code ? '' : code })
    this.applyFilter()
  },

  onCharFilterTap(e) {
    const code = e.currentTarget.dataset.code
    this.setData({ charFilter: this.data.charFilter === code ? '' : code })
    this.applyFilter()
  },

  onResetFilter() {
    this.setData({ wuxingFilter: '', styleFilter: '', sourceFilter: '', charFilter: '' })
    this.applyFilter()
  },

  async onRefresh() {
    if (this.data.loading) return

    const app = getApp()
    const params = app.globalData.lastParams

    if (!params) {
      wx.showToast({ title: '请求参数已失效，请重新起名', icon: 'none' })
      return
    }

    this.setData({ loading: true })
    try {
      // 复用原始请求参数重新调用；后端无固定 seed，天然得到不同候选
      const result = await api.generateNames(params)
      // 换一批 = 新批次，深度寓意需重新解锁
      const batchId = Date.now()
      app.globalData.lastResult = result
      app.globalData.lastBatchId = batchId
      // 换一批后重置筛选，展示全新候选
      this.setData({ wuxingFilter: '', styleFilter: '', sourceFilter: '', charFilter: '' })
      this.renderResult(result)

      // 每一批都收进「名字本」，否则「换一批」出来的好名字看完就没了
      const saved = namebook.addRecord(
        namebook.buildRecord('postnatal', params, result, batchId)
      )
      if (!saved.ok) {
        wx.showToast({ title: saved.error, icon: 'none' })
      } else {
        wx.showToast({ title: '已换一批', icon: 'none' })
      }
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '换一批失败，请重试', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  onNameTap(e) {
    const index = e.currentTarget.dataset.index
    const app = getApp()
    app.globalData.selectedName = this.data.names[index]
    wx.navigateTo({
      url: '/pages/detail/detail'
    })
  },

  // 展开 / 收起八字排盘卡
  onBaziToggle() {
    this.setData({ baziOpen: !this.data.baziOpen })
  },

  // 展开 / 收起筛选栏的其余维度
  onToggleFilter() {
    this.setData({ filterOpen: !this.data.filterOpen })
  },

  onBaziTap() {
    wx.navigateTo({
      url: '/pages/bazi/bazi'
    })
  },

  // 回跳起名第二步（挑一种感觉）并回填上次所选
  onAdjustPref() {
    const app = getApp()
    const params = app.globalData.lastParams

    if (!params) {
      wx.showToast({ title: '请求参数已失效，请重新起名', icon: 'none' })
      return
    }

    app.globalData.draftParams = params
    app.globalData.draftTab = params.due_date ? 'prenatal' : 'postnatal'
    wx.navigateTo({ url: '/pages/wizard/wizard' })
  },

  onBackHome() {
    wx.reLaunch({ url: '/pages/home/home' })
  },

  // ── 收藏（本机存储，落盘逻辑见 utils/namebook.js）──
  // 卡片本身是「查看详情」，故收藏用 catchtap 绑定，避免冒泡把详情页也打开了
  onFavTap(e) {
    const name = this.data.names[e.currentTarget.dataset.index]
    if (!name) return

    const app = getApp()
    // 连 params / batchId 一起存：从名字本点进详情时，深度寓意的解锁状态要对得上
    const ret = namebook.toggleFav(name, app.globalData.lastParams, app.globalData.lastBatchId)
    if (!ret.ok) {
      wx.showToast({ title: ret.error, icon: 'none' })
      return
    }
    this.setData({ favIds: namebook.favMap() })
    this.applyFilter()
    wx.showToast({ title: ret.added ? '已收藏' : '已取消收藏', icon: 'none' })
  },

  // 结果页是一批名字，分享其中单个会以偏概全，故落到起名入口
  onShareAppMessage: share.namingShare,

  onShareTimeline: share.namingTimeline
})
