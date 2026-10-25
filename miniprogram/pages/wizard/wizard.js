const api = require('../../utils/api')
const share = require('../../utils/share')
const namebook = require('../../utils/namebook')
const track = require('../../utils/track')
const quota = require('../../utils/quota')

// 起名第二步（也是最后一步）：定偏好 → 生成。
//
// 两个偏好维度的**作用域各不相同**，不要混着理解：
//   气质 8（单选）   → 后端 style：整批里至少一半名字出自该气质的典籍（硬名额）
//   期许 14（≤3）    → 后端 meanings：选字硬前置 + 排序；按 7 个方向分块渲染
//
// 「取名之法」那三条路径（直接推荐 / 先字后典 / 先典后字）已下线：
// 两条要用户先做一件他还没能力判断的事（从 300 多个裸字里挑、判断哪部典籍合适），
// 而出处偏好本来就该由「气质」承担。现在只有一条路：按期许与气质直接荐名。
const MEANING_MAX = api.MEANING_MAX_SELECT || 3

Page({
  data: {
    tab: 'postnatal',
    metaText: '',

    // 气质（单选）
    styles: [],
    styleCode: '',

    // 期许（≤3，按 7 个方向分组）
    meaningGroups: [],
    meaningCount: 0,
    meaningMax: MEANING_MAX,

    // 避讳
    avoidChars: '',
    avoidOpen: false,

    // 字辈（只读展示：从资料页带过来，位置=第二个字）
    genChar: '',

    // 今日批次（起名与换一批共用，见 utils/quota.js）
    quotaLeft: 0,
    quotaFree: 0,
    shareLeft: 0,
    shareBonus: 3,

    loading: false
  },

  onLoad() {
    const app = getApp()
    this.draft = Object.assign({}, app.globalData.draftParams || {})
    const tab = app.globalData.draftTab ||
      (this.draft.due_date ? 'prenatal' : 'postnatal')

    // 回填：从结果页「调整偏好」返回时 draft 里带着上次的 style/meanings
    const view = this.buildView({
      tab: tab,
      styleCode: this.draft.style || '',
      meaningCodes: (this.draft.meanings || []).slice()
    })
    view.genChar = this.draft.generational_char || ''
    this.setData(view)
  },

  onShow() {
    // 每次回到这一页都刷一次：用户可能刚在结果页转发领过批次
    this.syncQuota()
  },

  syncQuota() {
    const q = quota.status()
    this.setData({
      quotaLeft: q.remaining,
      quotaFree: q.free,
      shareLeft: q.shareLeft,
      shareBonus: q.shareBonus
    })
  },

  // 批次用完时，页面上直接给转发入口（open-type="share" 会走 onShareAppMessage）
  onShareAppMessage() {
    this._grantShareBonus()
    return share.defaultShare()
  },

  /**
   * 转发奖励发放 + 界面反馈（从 onShareAppMessage 里拆出来的副作用）。
   *
   * 必须拆：onShareAppMessage 的返回值只允许 title/path/imageUrl/promise，
   * 方法体里任何 `xxx:` 都会被 tests/test_share_policy.py 判成「返回了不支持的字段」。
   */
  _grantShareBonus() {
    const ret = quota.grantByShare()
    if (!ret.ok) return
    this.syncQuota()
    wx.showToast({ title: '已加 ' + ret.added + ' 批', icon: 'none' })
  },

  // ── 视图组装（一次 setData 铺满；数组项一律复制成新对象，
  //    因为 setData 的差量只到数组这一层，改数组内对象的字段不保证重绘）──

  buildView(state) {
    const meaningCodes = state.meaningCodes || []

    const styles = api.STYLE_OPTIONS.map(function (o) {
      return {
        code: o.code,
        name: o.name,
        short: o.short,
        selected: o.code === state.styleCode
      }
    })

    // 期许按 7 个方向分块：每块一句人话（subtitle）+ 该组下的标签
    const meaningGroups = api.MEANING_GROUPS.map(function (g) {
      const meanings = api.MEANING_OPTIONS
        .filter(function (m) { return m.group === g.code })
        .map(function (m) {
          return {
            code: m.code,
            name: m.name,
            selected: meaningCodes.indexOf(m.code) >= 0
          }
        })
      return { code: g.code, title: g.title, subtitle: g.subtitle, meanings: meanings }
    })

    return {
      tab: state.tab,
      metaText: this.buildMeta(state.tab),
      styles: styles,
      styleCode: state.styleCode || '',
      // 选中气质后给一句「这个气质用什么样的字」——用户挑标签时看不出差别，
      // 一半原因是他不知道这个标签背后是什么；说清字族，选与不选的体感就成立了。
      styleNote: api.styleNote(state.styleCode || ''),
      meaningGroups: meaningGroups,
      meaningCount: meaningCodes.length
    }
  },

  // 顶部一行上下文，让用户确认「在给谁起名」
  buildMeta(tab) {
    if (tab === 'prenatal') {
      return '预产期 ' + (this.draft.due_date || '未设置') +
        ' · ±' + (this.draft.range_days || 0) + '天'
    }
    const parts = []
    if (this.draft.surname) parts.push(this.draft.surname)
    parts.push(this.draft.gender === 'female' ? '女孩' : '男孩')
    parts.push(this.draft.name_length === 1 ? '单字名' : '双字名')
    if (this.draft.generational_char) parts.push('辈字「' + this.draft.generational_char + '」')
    if (this.draft.use_bazi) parts.push('已合出生历法')
    return parts.join(' · ')
  },

  // 当前选中的期许 codes（从分组的 meaningGroups 里扁平读）
  selectedMeaningCodes() {
    const codes = []
    this.data.meaningGroups.forEach(function (g) {
      g.meanings.forEach(function (m) { if (m.selected) codes.push(m.code) })
    })
    return codes
  },

  // ── 气质（单选，再点取消）──

  onStyleTap(e) {
    const code = e.currentTarget.dataset.code
    const next = this.data.styleCode === code ? '' : code
    this.setData(this.buildView({
      tab: this.data.tab,
      styleCode: next,
      meaningCodes: this.selectedMeaningCodes()
    }))
  },

  // ── 期许（≤3，跨组累计）──

  onMeaningTap(e) {
    const code = e.currentTarget.dataset.code
    const meaningGroups = this.data.meaningGroups.map(function (g) {
      return {
        code: g.code,
        title: g.title,
        subtitle: g.subtitle,
        meanings: g.meanings.map(function (m) { return Object.assign({}, m) })
      }
    })
    let target = null
    meaningGroups.forEach(function (g) {
      g.meanings.forEach(function (m) { if (m.code === code) target = m })
    })
    if (!target) return

    if (!target.selected && this.data.meaningCount >= MEANING_MAX) {
      wx.showToast({ title: '最多选 ' + MEANING_MAX + ' 个', icon: 'none' })
      return
    }
    target.selected = !target.selected
    const meaningCount = meaningGroups.reduce(function (n, g) {
      return n + g.meanings.filter(function (m) { return m.selected }).length
    }, 0)
    this.setData({ meaningGroups: meaningGroups, meaningCount: meaningCount })
  },

  // ── 避讳字 ──

  onToggleAvoid() {
    this.setData({ avoidOpen: !this.data.avoidOpen })
  },

  onAvoidInput(e) {
    this.setData({ avoidChars: e.detail.value })
  },

  parseAvoidChars() {
    const chars = []
    ;(this.data.avoidChars || '').split(/[,，、\s]+/).forEach(function (seg) {
      if (seg) chars.push(seg)
    })
    return chars
  },

  // ── 提交 ──

  async onSubmit() {
    // 起名也算 1 批（与换一批共用同一个池）。用完就拦在这里，
    // 而不是放用户进去再告诉他不能换 —— 后者更让人难受。
    if (!quota.canRefresh()) {
      this.syncQuota()
      wx.showToast({
        title: '今天的免费批次用完了，转发给朋友可再加 ' + quota.SHARE_BONUS + ' 批',
        icon: 'none',
        duration: 2800
      })
      return
    }

    const params = Object.assign({}, this.draft)

    // 剥离展示用字段，避免透传给后端
    delete params.birthDate
    delete params.hourText
    // 「取名之法」下线后不再有硬约束路径：清掉旧 draft 里可能残留的字段，
    // 否则从旧记录返回时会带着上一次的选字/典籍，界面上却看不到它们
    delete params.selected_chars
    delete params.source_classes

    // 气质 / 期许 → 后端既有入参
    const style = this.data.styleCode
    if (style) params.style = style
    else delete params.style

    const meanings = this.selectedMeaningCodes()
    if (meanings.length) params.meanings = meanings
    else delete params.meanings

    const avoid = this.parseAvoidChars()
    if (avoid.length) params.avoid_chars = avoid
    else delete params.avoid_chars

    // 字辈（资料页带入，双字名生效）
    if (this.draft.generational_char && this.draft.name_length === 2) {
      params.generational_char = this.draft.generational_char
    } else {
      delete params.generational_char
    }

    const app = getApp()
    this.setData({ loading: true })
    try {
      if (this.data.tab === 'prenatal') {
        const result = await api.prenatal(params)
        quota.consume()
        app.globalData.prenatalResult = result
        app.globalData.lastParams = params
        this.saveRecord('prenatal', params, result, 0)
        track.track(track.TRACK.namingSubmit, {
          kind: 'prenatal',
          style: params.style || 'none',
          bazi: 'no'
        })
        wx.navigateTo({ url: '/pages/prenatal-result/prenatal-result' })
      } else {
        const result = await api.generateNames(params)
        // 拿到了才扣：请求失败不该白扣一批
        quota.consume()
        // 每次起名 = 一个批次，深度寓意按批次单次解锁
        const batchId = Date.now()
        app.globalData.lastResult = result
        app.globalData.lastParams = params
        app.globalData.lastBatchId = batchId
        // 新一次起名：排除名单从这一批重新开始累计（不然上一轮的十几个名字会一直
        // 被排除，换个风格也翻不出来）
        app.globalData.shownNames = (result.names || []).map(function (n) {
          return n.given_name
        })
        this.saveRecord('postnatal', params, result, batchId)
        // 本地埋点（不上传，见 utils/track.js）：只记次数与粗维度
        track.track(track.TRACK.namingSubmit, {
          kind: 'postnatal',
          style: params.style || 'none',
          bazi: params.year ? 'yes' : 'no'
        })
        wx.navigateTo({ url: '/pages/result/result' })
      }
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '起名失败，请重试', icon: 'none' })
    } finally {
      this.setData({ loading: false })
      this.syncQuota()
    }
  },

  // 收进「名字本」（本机存储，见 utils/namebook.js）。
  // 存失败、或因满清理了旧记录都只提示、不阻断 —— 结果已经拿到了，
  // 不该因为存不下就不让看。
  saveRecord(kind, params, result, batchId) {
    namebook.notifySave(namebook.addRecord(namebook.buildRecord(kind, params, result, batchId)))
  },

  onShareTimeline: share.defaultTimeline
})
