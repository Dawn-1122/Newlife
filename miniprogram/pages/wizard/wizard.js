const api = require('../../utils/api')
const share = require('../../utils/share')
const namebook = require('../../utils/namebook')

// 起名第二步（也是最后一步）：定偏好 → 选路径 → 生成。
//
// 三个偏好维度的**作用域各不相同**，不要混着理解：
//   气质 8（单选）  → 后端 style：来源偏好 + 意象关键词 + 选字倾向
//   期待 12（≤3）   → 后端 meanings：选字硬前置 + 排序
//   意象 7（≤2）    → **只影响「先字」字表的排序**，后端不作硬筛选
//                     （7 族只覆盖候选池约 35%，硬过滤会砍掉 65% 的好字）
//
// 三条路径：
//   直接推荐   → 按偏好直接出名字
//   从字出发   → 选字表里点字（selected_chars，后端「名字必须含所选字」硬约束）
//   从出处出发 → 限定典籍类目（source_classes 硬约束）
//
// 旧版「感觉卡」把气质与期待绑成一对一（8 张卡各带 1 风格 + 2 寓意），
// 用户想「温润 + 勇敢」时无路可走；现拆成三层独立标签，与后端入参一一对应。
const MEANING_MAX = api.MEANING_MAX_SELECT || 3
const IMAGERY_MAX = api.IMAGERY_MAX_SELECT || 2
const PICK_MAX = 3          // 「从字出发」最多选几个字
const CHAR_PAGE = 48        // 字表一次渲染多少个（全量 200+ 会撑爆 wxml 节点数）

Page({
  data: {
    tab: 'postnatal',
    metaText: '',

    // 气质（单选）
    styles: [],
    styleCode: '',

    // 期待（≤3）
    meanings: [],
    meaningCount: 0,
    meaningMax: MEANING_MAX,

    // 意象（≤2，只排序不筛选）
    imageries: [],
    imageryCount: 0,
    imageryMax: IMAGERY_MAX,

    // 路径
    paths: [
      { code: 'direct', name: '直接推荐', desc: '按上面的偏好直接给名字' },
      { code: 'chars', name: '从字出发', desc: '先挑喜欢的字，再回出处' },
      { code: 'sources', name: '从出处出发', desc: '先圈定典籍，再挑字' }
    ],
    path: 'direct',

    // 从字出发：字表
    pickLoading: false,
    pickLoaded: false,
    pickStale: false,       // 偏好变了 → 字表需要重新载入
    pickTotal: 0,           // 池内字数
    pickFeasible: 0,        // 本姓真组得出名字的字数
    familyChips: [],        // 意象族筛选（含「全部」）
    familyFilter: '',
    charView: [],           // 当前渲染的字（已过滤 + 分页）
    charFiltered: 0,        // 过滤后的总数
    charVisible: CHAR_PAGE,
    pickedCount: 0,
    pickedText: '',
    pickMax: PICK_MAX,

    // 从出处出发
    sources: [],
    sourceCount: 0,

    // 避讳
    avoidChars: '',
    avoidOpen: false,

    loading: false
  },

  onLoad() {
    const app = getApp()
    this.draft = Object.assign({}, app.globalData.draftParams || {})
    const tab = app.globalData.draftTab ||
      (this.draft.due_date ? 'prenatal' : 'postnatal')

    // 回填：从结果页「调整偏好」返回时 draft 里带着上次的 style/meanings/...
    this.picked = {}                                  // 先字已选（不进 data，避免大数组 setData）
    this.imageryCodes = (app.globalData.draftImagery || []).slice()
    this.charAtoms = []                               // 字表全量（未过滤）

    if (this.draft.selected_chars) {
      this.draft.selected_chars.forEach(function (ch) {
        this.picked[ch] = true
      }.bind(this))
    }

    // 回填路径：从结果页「调整偏好」返回时必须停在原来那条路上。
    // 否则 draft 里带着 selected_chars/source_classes，界面却停在「直接推荐」，
    // 一提交就被静默丢掉——用户会以为「我选的字没生效」。
    let path = 'direct'
    if (tab !== 'prenatal') {
      if (this.draft.selected_chars) path = 'chars'
      else if (this.draft.source_classes) path = 'sources'
    }

    const view = this.buildView({
      tab: tab,
      styleCode: this.draft.style || '',
      meaningCodes: (this.draft.meanings || []).slice(),
      sourceCodes: (this.draft.source_classes || []).slice()
    })
    view.path = path
    this.setData(view)

    if (path === 'chars') this.loadPickable()
  },

  // ── 视图组装（一次 setData 铺满；数组项一律复制成新对象，
  //    因为 setData 的差量只到数组这一层，改数组内对象的字段不保证重绘）──

  buildView(state) {
    const meaningCodes = state.meaningCodes || []
    const sourceCodes = state.sourceCodes || []

    const styles = api.STYLE_OPTIONS.map(function (o) {
      return {
        code: o.code,
        name: o.name,
        short: o.short,
        selected: o.code === state.styleCode
      }
    })

    const meanings = api.MEANING_OPTIONS.map(function (o) {
      return {
        code: o.code,
        name: o.name,
        selected: meaningCodes.indexOf(o.code) >= 0
      }
    })

    const imageries = api.IMAGERY_FAMILIES.map(function (o) {
      return {
        code: o.code,
        name: o.name,
        radicals: o.radicals,
        selected: this.imageryCodes.indexOf(o.code) >= 0
      }
    }.bind(this))

    const sources = api.SOURCE_CLASSES.map(function (name) {
      return {
        code: name,
        name: name,
        selected: sourceCodes.indexOf(name) >= 0
      }
    })

    return {
      tab: state.tab,
      metaText: this.buildMeta(state.tab),
      styles: styles,
      styleCode: state.styleCode || '',
      meanings: meanings,
      meaningCount: meanings.filter(function (m) { return m.selected }).length,
      imageries: imageries,
      imageryCount: imageries.filter(function (i) { return i.selected }).length,
      sources: sources,
      sourceCount: sources.filter(function (s) { return s.selected }).length,
      pickedCount: Object.keys(this.picked || {}).length,
      pickedText: Object.keys(this.picked || {}).join(' ')
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
    if (this.draft.use_bazi) parts.push('已合八字')
    return parts.join(' · ')
  },

  // 当前选中的 codes（从 data 里读，避免再存一份状态导致不同步）
  selectedCodes(key) {
    return this.data[key].filter(function (x) { return x.selected })
      .map(function (x) { return x.code })
  },

  // ── 气质（单选，再点取消）──

  onStyleTap(e) {
    const code = e.currentTarget.dataset.code
    const next = this.data.styleCode === code ? '' : code
    this.setData(this.mergeView({ styleCode: next }))
    this.markPickStale()
  },

  // ── 期待（≤3）──

  onMeaningTap(e) {
    const code = e.currentTarget.dataset.code
    const meanings = this.data.meanings.map(function (m) { return Object.assign({}, m) })
    const target = meanings.filter(function (m) { return m.code === code })[0]
    if (!target) return

    if (!target.selected && this.data.meaningCount >= MEANING_MAX) {
      wx.showToast({ title: '最多选 ' + MEANING_MAX + ' 个', icon: 'none' })
      return
    }
    target.selected = !target.selected
    this.setData({ meanings: meanings, meaningCount: meanings.filter(function (m) {
      return m.selected
    }).length })
    this.markPickStale()
  },

  // ── 意象（≤2，只影响字表排序）──

  onImageryTap(e) {
    const code = e.currentTarget.dataset.code
    const idx = this.imageryCodes.indexOf(code)
    if (idx >= 0) {
      this.imageryCodes.splice(idx, 1)
    } else {
      if (this.imageryCodes.length >= IMAGERY_MAX) {
        wx.showToast({ title: '最多选 ' + IMAGERY_MAX + ' 个', icon: 'none' })
        return
      }
      this.imageryCodes.push(code)
    }
    getApp().globalData.draftImagery = this.imageryCodes.slice()
    const imageries = this.data.imageries.map(function (o) {
      return {
        code: o.code,
        name: o.name,
        radicals: o.radicals,
        selected: this.imageryCodes.indexOf(o.code) >= 0
      }
    }.bind(this))
    this.setData({
      imageries: imageries,
      imageryCount: imageries.filter(function (i) { return i.selected }).length
    })
    // 意象只影响排序，字表已在手就本地重排，不必再请求
    if (this.data.pickLoaded) this.sortAndRender()
  },

  mergeView(over) {
    const next = {
      styleCode: 'styleCode' in over ? over.styleCode : this.data.styleCode
    }
    return this.buildView({
      tab: this.data.tab,
      styleCode: next.styleCode,
      meaningCodes: this.selectedCodes('meanings'),
      sourceCodes: this.selectedCodes('sources')
    })
  },

  // ── 路径 ──

  onPathTap(e) {
    const code = e.currentTarget.dataset.code
    if (code === this.data.path) return
    this.setData({ path: code })
    if (code === 'chars' && !this.data.pickLoaded) this.loadPickable()
  },

  // 偏好变了 → 字表作废（字表是按偏好算出来的，不重载会给出过期结果）
  markPickStale() {
    if (this.data.pickLoaded) this.setData({ pickStale: true })
  },

  onReloadPick() {
    this.loadPickable()
  },

  // ── 从字出发：拉可选字表 ──

  async loadPickable() {
    if (this.data.pickLoading) return
    const params = this.buildPickParams()
    this.setData({ pickLoading: true })
    try {
      const res = await api.pickableChars(params)
      this.charAtoms = (res.chars || []).map(function (c) {
        return Object.assign({}, c)
      })
      this.pickMeta = {
        total: res.total,
        feasible: res.feasible,
        families: res.families || []
      }
      this.setData({ pickLoading: false, pickLoaded: true, pickStale: false })
      this.buildFamilyChips()
      this.sortAndRender()
    } catch (err) {
      this.setData({ pickLoading: false })
      wx.showToast({
        title: (err && err.message) || '字表加载失败，请重试',
        icon: 'none'
      })
    }
  },

  buildPickParams() {
    const p = {
      surname: this.draft.surname,
      gender: this.draft.gender || 'male',
      name_length: this.draft.name_length || 2,
      use_bazi: !!this.draft.use_bazi && !!this.draft.year
    }
    const style = this.data.styleCode || this.selectedCodes('styles')[0]
    if (style) p.style = style
    const meanings = this.selectedCodes('meanings')
    if (meanings.length) p.meanings = meanings
    if (this.imageryCodes.length) p.imagery_families = this.imageryCodes.slice()
    const avoid = this.parseAvoidChars()
    if (avoid.length) p.avoid_chars = avoid
    if (p.use_bazi) {
      p.year = this.draft.year
      p.month = this.draft.month
      p.day = this.draft.day
      p.hour = this.draft.hour
    }
    return p
  },

  // 意象族筛选条（含「全部」）：计数来自本次字表
  buildFamilyChips() {
    const counts = {}
    this.charAtoms.forEach(function (c) {
      if (c.family) counts[c.family] = (counts[c.family] || 0) + 1
    })
    // 该族在本姓氏下无可用字 → 不摆空筛选。
    // 字表是重载过的，若上次选中的族这次没字了，筛选必须跟着松开，
    // 否则会停在一个不存在的筛选上，显示一张空表。
    let filter = this.data.familyFilter
    if (filter && !counts[filter]) filter = ''

    const chips = [{
      code: '',
      name: '全部',
      count: this.charAtoms.length,
      selected: filter === ''
    }]
    api.IMAGERY_FAMILIES.forEach(function (f) {
      const n = counts[f.code] || 0
      if (!n) return
      chips.push({
        code: f.code,
        name: f.name,
        count: n,
        selected: filter === f.code
      })
    })
    this.setData({ familyChips: chips, familyFilter: filter })
  },

  onFamilyTap(e) {
    const code = e.currentTarget.dataset.code
    const chips = this.data.familyChips.map(function (c) {
      return Object.assign({}, c, { selected: c.code === code })
    })
    this.setData({ familyChips: chips, familyFilter: code })
    this.sortAndRender()
  },

  // 排序规则（与后端 pickable_chars 一致）：选中的意象族优先，其次看真能出多少名字。
  // 意象是「字面意象」，只该影响字表的摆放，不该把无族属的好字（诗/思/安/宜）筛掉。
  sortAndRender() {
    const fam = this.imageryCodes
    const filter = this.data.familyFilter
    const list = this.charAtoms.filter(function (c) {
      return !filter || c.family === filter
    })
    list.sort(function (a, b) {
      const am = fam.indexOf(a.family) >= 0 ? 0 : 1
      const bm = fam.indexOf(b.family) >= 0 ? 0 : 1
      if (am !== bm) return am - bm
      if (a.name_hits !== b.name_hits) return b.name_hits - a.name_hits
      if (a.partner_count !== b.partner_count) return b.partner_count - a.partner_count
      return a.char < b.char ? -1 : 1
    })
    const visible = Math.min(this.data.charVisible, list.length)
    this.setData({
      charFiltered: list.length,
      // 只带渲染真正用到的字段：字表最多 200+ 格，多带一个字段就是白烧一次 setData
      charView: list.slice(0, visible).map(function (c) {
        return {
          char: c.char,
          name_hits: c.name_hits,
          picked: !!this.picked[c.char]
        }
      }.bind(this)),
      pickTotal: this.pickMeta ? this.pickMeta.total : 0,
      pickFeasible: this.pickMeta ? this.pickMeta.feasible : 0
    })
  },

  onMoreChars() {
    this.setData({ charVisible: this.data.charVisible + CHAR_PAGE })
    this.sortAndRender()
  },

  // 单字点选：用路径式 setData 只更新这一格（整表重发会明显卡顿）
  onCharTap(e) {
    const idx = Number(e.currentTarget.dataset.idx)
    const cell = this.data.charView[idx]
    if (!cell) return

    if (!cell.picked && Object.keys(this.picked).length >= PICK_MAX) {
      wx.showToast({ title: '最多选 ' + PICK_MAX + ' 个字', icon: 'none' })
      return
    }
    const next = !cell.picked
    if (next) this.picked[cell.char] = true
    else delete this.picked[cell.char]

    const patch = {}
    patch['charView[' + idx + '].picked'] = next
    patch.pickedCount = Object.keys(this.picked).length
    patch.pickedText = Object.keys(this.picked).join(' ')
    this.setData(patch)
  },

  onClearPicked() {
    this.picked = {}
    this.setData({ pickedCount: 0, pickedText: '' })
    this.sortAndRender()
  },

  // ── 从出处出发 ──

  onSourceTap(e) {
    const code = e.currentTarget.dataset.code
    const sources = this.data.sources.map(function (s) {
      return Object.assign({}, s, { selected: s.code === code ? !s.selected : s.selected })
    })
    this.setData({
      sources: sources,
      sourceCount: sources.filter(function (s) { return s.selected }).length
    })
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
    const path = this.data.tab === 'prenatal' ? 'direct' : this.data.path

    if (path === 'chars' && !this.data.pickedCount) {
      wx.showToast({ title: '先点几个字，或改用直接推荐', icon: 'none' })
      return
    }
    if (path === 'sources' && !this.data.sourceCount) {
      wx.showToast({ title: '先选典籍范围，或改用直接推荐', icon: 'none' })
      return
    }

    const params = Object.assign({}, this.draft)

    // 剥离展示用字段，避免透传给后端
    delete params.birthDate
    delete params.hourText

    // 三层偏好 → 后端既有入参
    const style = this.data.styleCode
    if (style) params.style = style
    else delete params.style

    const meanings = this.selectedCodes('meanings')
    if (meanings.length) params.meanings = meanings
    else delete params.meanings

    const avoid = this.parseAvoidChars()
    if (avoid.length) params.avoid_chars = avoid
    else delete params.avoid_chars

    // 路径 → 硬约束
    if (path === 'chars') {
      params.selected_chars = Object.keys(this.picked)
      delete params.source_classes
    } else if (path === 'sources') {
      params.source_classes = this.selectedCodes('sources')
      delete params.selected_chars
    } else {
      delete params.selected_chars
      delete params.source_classes
    }

    const app = getApp()
    this.setData({ loading: true })
    try {
      if (this.data.tab === 'prenatal') {
        const result = await api.prenatal(params)
        app.globalData.prenatalResult = result
        app.globalData.lastParams = params
        this.saveRecord('prenatal', params, result, 0)
        wx.navigateTo({ url: '/pages/prenatal-result/prenatal-result' })
      } else {
        const result = await api.generateNames(params)
        // 每次起名 = 一个批次，深度寓意按批次单次解锁
        const batchId = Date.now()
        app.globalData.lastResult = result
        app.globalData.lastParams = params
        app.globalData.lastBatchId = batchId
        this.saveRecord('postnatal', params, result, batchId)
        wx.navigateTo({ url: '/pages/result/result' })
      }
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '起名失败，请重试', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  // 收进「名字本」（本机存储，见 utils/namebook.js）。
  // 存失败只提示、不阻断 —— 结果已经拿到了，不该因为存不下就看不成。
  saveRecord(kind, params, result, batchId) {
    const ret = namebook.addRecord(namebook.buildRecord(kind, params, result, batchId))
    if (!ret.ok) {
      wx.showToast({ title: ret.error, icon: 'none' })
    }
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
