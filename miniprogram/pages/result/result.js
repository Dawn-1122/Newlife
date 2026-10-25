const api = require('../../utils/api')
const share = require('../../utils/share')
const namebook = require('../../utils/namebook')
const score = require('../../utils/score')
const track = require('../../utils/track')
const quota = require('../../utils/quota')
const rewardAd = require('../../utils/reward-ad')

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
    wuxingList: [],
    wuxingFilter: '',
    // 时辰是否用户真填过；false 时时柱显示「未填」，排盘按午时代入并注明
    hourKnown: true,
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

    // ── 换一批配额（见 utils/quota.js）──
    quotaLeft: 0,        // 今天还能换几次
    quotaExhausted: false,
    shareLeft: 0,        // 今天还能靠转发领几次
    shareBonus: 3,       // 转发一次补几批（文案里的 +N）
    adLeft: 0,           // 今天还能靠看广告领几次
    adBonus: 3,          // 看一次广告补几批（文案里的 +N，与 shareBonus 是两套数）
    quotaFree: 9,        // 每天免费批次数（起名与换一批共用）
    canWatchAd: false,   // 广告位是否已开通（未开通时按钮明说）
    canEarnAd: false,    // 现在点广告是不是真能拿到次数（未开通 / 今日领完都为 false）

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

    this.syncQuota()
    this.renderResult(result)
  },

  // 把配额状态搬进 data：按钮文案与补次数面板都看这一份
  syncQuota() {
    const q = quota.status()
    this.setData({
      quotaLeft: q.remaining,
      quotaExhausted: q.remaining <= 0,
      shareLeft: q.shareLeft,
      shareBonus: q.shareBonus,
      adLeft: q.adLeft,
      adBonus: q.adBonus,
      quotaFree: q.free,
      canWatchAd: q.canWatchAd,
      // 样式用「能不能拿到次数」而不是「广告能不能放」：额度领完时按钮也该暗下来，
      // 与尚未开通同一种视觉，别让它看着像还有戏
      canEarnAd: quota.canEarnByAd()
    })
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

    // 时辰是不是用户真的填过：没填时内部按午时代入，
    // 页面不能把「午时」当成他给的事实展示（见 utils/hours.js 注释）
    const params = getApp().globalData.lastParams || {}
    const hourKnown = params.hour !== undefined && params.hour !== null

    // 给每个名字加上拼音展示文本，作为全量候选池
    const allNames = (result.names || []).map(function (n) {
      n.pinyinText = (n.phonetics && n.phonetics.pinyins) ? n.phonetics.pinyins.join(' · ') : ''
      // 推荐值 = 韵味原分折算到可达满分后的展示刻度（换算见 utils/score.js）
      Object.assign(n, score.badge(n.scores && n.scores.overall))
      return n
    })

    this.setData({
      bazi: result.bazi,
      allNames: allNames,
      wuxingList: wuxingList,
      hourKnown: hourKnown,
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
        // 按气质**字族**判定，与生成端同一把尺子（见 utils/api.js 的 chars 注释）。
        // 早先按出处判：一段语料天然属于多个气质，用户选了「空灵禅意」再点「空灵」
        // 反而会筛掉一半名字 —— 两处判定不同源，就成了自相矛盾的功能。
        const family = api.styleFamily(styleFilter)
        if (!family) return false
        const chars = charsOf(n)
        let hit = false
        for (let i = 0; i < chars.length; i++) {
          if (family.indexOf(chars[i]) >= 0) {
            hit = true
            break
          }
        }
        if (!hit) return false
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
      // 契合点：把「这个字为什么对得上你选的东西」摊在卡片上。
      // 卡片只放一行 —— 期许优先，没有期许时退回气质：
      //   期许是「某个愿望的落点」（松 → 岁寒后凋），比气质更具体；
      //   气质是「整批的调子」（云、月 → 空灵），一句话就够。
      // 两项都选了、又想知道全部理由的，去详情页。
      const fit = n.meaning_fit || []
      const sfit = n.style_fit || []
      let fitLabel = ''
      let fitTitle = ''
      let fitLine = ''
      if (fit.length) {
        const first = fit[0]
        fitLabel = '契合'
        fitTitle = api.meaningNames(first.codes)
        fitLine = first.char + '：' + (first.note || '取这一字的寓意')
      } else if (sfit.length) {
        const chars = sfit.map(function (f) { return f.char }).join('、')
        fitLabel = '气质'
        fitTitle = api.styleName(sfit[0].style)
        // 气质说明对同一批名字都一样（「多用云、月、苔、石这类留白的字」），
        // 逐张卡重复六遍就成了套话。卡片只回答「是哪几个字」，
        // 说明放在详情页一次说清。
        fitLine = chars + ' 取自这一路的字'
      }
      return Object.assign({}, n, {
        fav: !!favIds[n.full_name],
        fitLabel: fitLabel,
        fitTitle: fitTitle,
        fitLine: fitLine
      })
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

    // 配额先拦一道：没次数就别发请求（省一次网络往返，也让「次数」成为看得见的规则）
    if (!quota.canRefresh()) {
      this.syncQuota()
      wx.showToast({
        title: '今天的换一批用完了，转发或看广告可加次数',
        icon: 'none',
        duration: 2600
      })
      return
    }

    const app = getApp()
    const params = app.globalData.lastParams

    if (!params) {
      wx.showToast({ title: '请求参数已失效，请重新起名', icon: 'none' })
      return
    }

    this.setData({ loading: true })
    try {
      // 复用原始请求参数重新调用，并带上「已展示过的名字」：
      // 后端没有固定 seed，不带排除名单时就等于重新掷骰子——高分池只有二三十个，
      // 连翻两批必然把同一批名字抽回来（实测顾/男 三批全是清浅、素秋、清秋）。
      // 只留最近 120 个，请求体不会越滚越大。
      const shown = (app.globalData.shownNames || []).slice(-120)
      const reqParams = Object.assign({}, params, { exclude_names: shown })
      const result = await api.generateNames(reqParams)
      if (!(result.names || []).length) {
        // 池子翻完了：保留当前这批，不要把列表刷成空页，也不要记进名字本
        wx.showToast({
          title: result.fallback_note || '这一批已经翻完了，换个风格再试试',
          icon: 'none',
          duration: 2500
        })
        return
      }
      app.globalData.shownNames = shown.concat(
        (result.names || []).map(function (n) { return n.given_name })
      )
      // 换一批 = 新批次，深度寓意需重新解锁
      const batchId = Date.now()
      app.globalData.lastResult = result
      app.globalData.lastBatchId = batchId
      // 真拿到新名字了才扣次数：翻完了（空结果）不扣，那是池子的问题不是用户的
      quota.consume()
      this.syncQuota()
      // 换一批后重置筛选，展示全新候选
      this.setData({ wuxingFilter: '', styleFilter: '', sourceFilter: '', charFilter: '' })
      this.renderResult(result)

      // 每一批都收进「名字本」：同一次起名的多批会并进同一条记录
      // （合并规则见 utils/namebook.js 的 paramsKey），不会把别的记录挤掉
      const saved = namebook.addRecord(
        namebook.buildRecord('postnatal', params, result, batchId)
      )
      if (!saved.ok) {
        wx.showToast({ title: saved.error, icon: 'none' })
      } else if (saved.dropped > 0) {
        wx.showToast({
          title: '已换一批（名字本已满，清理 ' + saved.dropped + ' 条最早记录）',
          icon: 'none',
          duration: 2600
        })
      } else {
        // merged=true 说明这一批并进了本次起名的那条记录，而不是新开一条
        wx.showToast({ title: saved.merged ? '已换一批 · 并入本次记录' : '已换一批', icon: 'none' })
      }
      track.track(track.TRACK.namingRefresh)
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
    track.track(track.TRACK.favToggle, { added: ret.added ? 'yes' : 'no' })
    wx.showToast({ title: ret.added ? '已收藏' : '已取消收藏', icon: 'none' })
  },

  // ── 补次数：转发 / 看广告 ──

  /**
   * 转发 +1 次换一批。
   *
   * 发放在**点开转发面板时**，不等分享成功：微信在多处基础库里不再可靠触发
   * 分享成功回调，与其做个时灵时不灵的判定，不如承认它不精确 ——
   * 每天最多领 3 次把这个洞兜住了（见 utils/quota.js 顶部）。
   *
   * 这里只负责返回分享内容；发放奖励与提示放在 _grantShareBonus()。
   * 不只是为了分工好看：微信只认 title/path/imageUrl/promise 四个字段，
   * 其余键（连提示语的 icon 也算）写在返回值旁边，看代码的人会误以为
   * 它们会随分享一起生效。
   */
  onShareAppMessage() {
    this._grantShareBonus()
    // 结果页是一批名字，分享其中单个会以偏概全，故落到起名入口
    return share.namingShare()
  },

  /** 转发奖励发放 + 界面反馈（从 onShareAppMessage 里拆出来的副作用） */
  _grantShareBonus() {
    const ret = quota.grantByShare()
    if (!ret.ok) return
    this.syncQuota()
    wx.showToast({ title: '已加 ' + ret.added + ' 批', icon: 'none' })
  },

  onWatchAdTap() {
    if (!quota.canWatchAd()) {
      wx.showToast({ title: '广告位还没开通，先用转发加次数', icon: 'none', duration: 2400 })
      return
    }

    // 今日广告次数已领完就别放视频了：让人看完 30 秒再说「领完了」是最差的一种反馈，
    // 而这一栏又不能做成禁用态（广告位未开通时同样不可用，用户需要知道为什么点不动）。
    // 能不能拿次数由 quota 统一判定，页面不要自己拼条件（见 utils/quota.js canEarnByAd）。
    // 上面已经排除了「广告位未开通」，这里 !canEarnByAd() 只剩「今天的额度领完了」。
    if (!quota.canEarnByAd()) {
      wx.showToast({ title: '今天的广告次数已经领完，明天再来', icon: 'none', duration: 2400 })
      return
    }

    const self = this
    rewardAd.watch({
      onReward() {
        const ret = quota.grantByAd()
        self.syncQuota()
        wx.showToast({
          title: ret.ok ? '已加 ' + ret.added + ' 批' : '今天的广告次数已领完',
          icon: 'none'
        })
      },
      onCancel() {
        wx.showToast({ title: '看完广告才能加次数', icon: 'none' })
      },
      onFail() {
        wx.showToast({ title: '广告没能加载出来，先转发获取吧', icon: 'none' })
      }
    })
  },

  onShareTimeline: share.namingTimeline
})
