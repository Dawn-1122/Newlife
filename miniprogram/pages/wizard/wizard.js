const api = require('../../utils/api')
const share = require('../../utils/share')
const namebook = require('../../utils/namebook')

// 起名第二步（也是最后一步）：定偏好 → 选路径 → 生成。
//
// 两个偏好维度的**作用域各不相同**，不要混着理解：
//   气质 8（单选）   → 后端 style：来源偏好 + 意象关键词 + 选字倾向
//   期许 14（≤3）    → 后端 meanings：选字硬前置 + 排序；按 7 个方向分块渲染
//
// 意象（字形部首族）**不再是用户输入**：它是名字读出来之后用户「感受到」的画面，
// 属于产出侧——只在字卡上挂个小标签展示，不让父母一开始就勾「我要草木字」。
//
// 三条路径：
//   直接推荐 → 按偏好直接出名字
//   先字后典 → 先挑喜欢的字，再溯其出处（selected_chars 硬约束）
//   先典后字 → 先圈定典籍，再从中择字（source_classes 硬约束）
const MEANING_MAX = api.MEANING_MAX_SELECT || 3
const PICK_MAX = 3          // 「先字后典」最多选几个字
const CHAR_PAGE = 48        // 字表一次渲染多少个（全量 200+ 会撑爆 wxml 节点数）

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

    // 路径
    paths: [
      { code: 'direct', name: '直接推荐', desc: '按你的期许与气质，直接荐名' },
      { code: 'chars', name: '先字后典', desc: '先挑喜欢的字，再溯其出处' },
      { code: 'sources', name: '先典后字', desc: '先定典籍，再从中择字' }
    ],
    path: 'direct',

    // 先字后典：字表
    pickLoading: false,
    pickLoaded: false,
    pickStale: false,       // 偏好变了 → 字表需要重新载入
    pickTotal: 0,           // 池内字数
    pickFeasible: 0,        // 本姓真组得出名字的字数
    charView: [],           // 当前渲染的字（分页）
    charFiltered: 0,        // 过滤后的总数
    charVisible: CHAR_PAGE,
    pickedCount: 0,
    pickedText: '',
    pickMax: PICK_MAX,

    // 先典后字
    sources: [],
    sourceCount: 0,

    // 避讳
    avoidChars: '',
    avoidOpen: false,

    // 字辈（只读展示：从资料页带过来，位置=第二个字）
    genChar: '',

    loading: false
  },

  onLoad() {
    const app = getApp()
    this.draft = Object.assign({}, app.globalData.draftParams || {})
    const tab = app.globalData.draftTab ||
      (this.draft.due_date ? 'prenatal' : 'postnatal')

    // 回填：从结果页「调整偏好」返回时 draft 里带着上次的 style/meanings/...
    this.picked = {}                                  // 先字已选（不进 data，避免大数组 setData）
    this.charAtoms = []                               // 字表全量

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
    view.genChar = this.draft.generational_char || ''
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
      meaningGroups: meaningGroups,
      meaningCount: meaningCodes.length,
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
    if (this.draft.generational_char) parts.push('辈字「' + this.draft.generational_char + '」')
    if (this.draft.use_bazi) parts.push('已合八字')
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

  // 当前选中的典籍 codes
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
    this.markPickStale()
  },

  mergeView(over) {
    const next = {
      styleCode: 'styleCode' in over ? over.styleCode : this.data.styleCode
    }
    return this.buildView({
      tab: this.data.tab,
      styleCode: next.styleCode,
      meaningCodes: this.selectedMeaningCodes(),
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

  // ── 先字后典：拉可选字表 ──

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
        feasible: res.feasible
      }
      this.setData({ pickLoading: false, pickLoaded: true, pickStale: false })
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
    const style = this.data.styleCode
    if (style) p.style = style
    const meanings = this.selectedMeaningCodes()
    if (meanings.length) p.meanings = meanings
    if (this.draft.generational_char) p.generational_char = this.draft.generational_char
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

  // 排序：真能出多少名字优先（意象只作展示标签，不参与摆放）
  sortAndRender() {
    const list = this.charAtoms.slice()
    list.sort(function (a, b) {
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
          family: c.family || '',
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

  // ── 先典后字 ──

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
