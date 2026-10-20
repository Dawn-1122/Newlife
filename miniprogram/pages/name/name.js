/**
 * 起名第一步 · 填资料
 *
 * 版式约定（2026-10-20 改）：
 *   **不再分「已出生 / 未出生」两个 tab。** 一张表填到底，只有打开「八字分析」时
 *   才追问宝宝出生没有 —— 因为「出生没有」只影响八字，不影响姓氏、性别、字数。
 *   先用 tab 让用户回答一个与当前操作无关的问题，是把结构成本转嫁给用户。
 *
 *   八字关 → 不选任何日期，只按字形、出处与偏好出名字
 *   八字开 + 已出生 → 出生日期 + 时辰 → /generate（带八字）
 *   八字开 + 未出生 → 预产期 + 浮动区间 → /prenatal（只出五行参考，不出名字）
 *
 * 为什么日期不用原生 picker：
 *   预览环境里 `<picker mode="date">` 点不开，用户选不了日期，点「下一步」只会收到
 *   「请选择出生日期」——看起来像起名坏了。故改成自绘三列滚选（scroll-view），
 *   时辰同理改成 12 个时辰格，整页不依赖任何原生 picker。
 */

const api = require('../../utils/api')
const share = require('../../utils/share')
const ds = require('../../utils/date-sheet')
const hours = require('../../utils/hours')

const HOURS = hours.HOURS

Page({
  data: {
    // ── 公共字段（与八字无关）──
    surname: '',
    gender: 'male',
    nameLength: 2,
    generationalChar: '',

    // ── 八字分支 ──
    // 默认关：八字是加分项，不该在用户还没表达意愿时就拦着「下一步」要生日。
    // 关着也能出名字（按字形、音律与出处），开了才追问出生状态与生辰。
    useBazi: false,
    born: true, // 仅 useBazi 时有意义：已出生 / 未出生
    birthDate: '',
    hourIndex: 8,
    hourText: hours.labelOf(8),
    hours: HOURS,
    dueDate: '',
    rangeDays: api.DEFAULT_RANGE_DAYS,
    rangeOptions: api.RANGE_OPTIONS,

    // 自绘弹层（null 表示未打开）；日期与时辰共用，靠 kind 区分画什么
    sheet: null,

    loading: false
  },

  onLoad(options) {
    // 兼容旧的深链「孕期参考起名」：等价于 开八字 + 未出生
    if (options && options.tab === 'prenatal') {
      this.setData({ useBazi: true, born: false })
    }
  },

  // ── 公共字段 ──

  onSurnameInput(e) {
    this.setData({ surname: e.detail.value })
  },

  onGenderTap(e) {
    this.setData({ gender: e.currentTarget.dataset.gender })
  },

  onLengthTap(e) {
    this.setData({ nameLength: parseInt(e.currentTarget.dataset.length, 10) })
  },

  onGenerationalInput(e) {
    this.setData({ generationalChar: e.detail.value })
  },

  // ── 八字开关与出生状态 ──

  onBaziToggle() {
    const next = !this.data.useBazi
    // 关掉八字时保留已选日期：用户可能只是临时对比，不想丢掉填过的生辰
    this.setData({ useBazi: next })
  },

  onBornTap(e) {
    this.setData({ born: e.currentTarget.dataset.born === 'true' })
  },

  // 时辰与日期用同一个弹层：点一行 → 底部弹层选一列 → 确定回填
  onOpenHour() {
    this.setData({
      sheet: {
        kind: 'hour',
        title: '出生时辰',
        hour: this.data.hourIndex,
        hourAnchor: 'h' + this.data.hourIndex
      }
    })
  },

  onPickHour(e) {
    const idx = Number(e.currentTarget.dataset.idx)
    this.setData({
      sheet: Object.assign({}, this.data.sheet, { hour: idx, hourAnchor: 'h' + idx })
    })
  },

  onRangeTap(e) {
    this.setData({ rangeDays: Number(e.currentTarget.dataset.range) })
  },

  // ── 弹层（日期 / 时辰共用） ──

  openDateSheet(mode) {
    const isBirth = mode === 'birth'
    const now = new Date()

    this.setData({
      sheet: Object.assign(
        ds.build({
          value: isBirth ? this.data.birthDate : this.data.dueDate,
          // 出生默认今天（起名多是新生儿）；预产期默认往后三个月，更接近真实输入
          fallback: isBirth ? ds.today() : ds.daysLater(90),
          minYear: isBirth ? ds.MIN_YEAR : now.getFullYear() - 1,
          maxYear: isBirth ? now.getFullYear() : now.getFullYear() + 2,
          title: isBirth ? '出生日期' : '预产期'
        }),
        // kind 决定弹层里画三列日期还是单列时辰
        { mode: mode, kind: 'date' }
      )
    })
  },

  onOpenBirthDate() {
    this.openDateSheet('birth')
  },

  onOpenDueDate() {
    this.openDateSheet('due')
  },

  onPickYear(e) {
    this.setData({ sheet: ds.withYear(this.data.sheet, Number(e.currentTarget.dataset.v)) })
  },

  onPickMonth(e) {
    this.setData({ sheet: ds.withMonth(this.data.sheet, Number(e.currentTarget.dataset.v)) })
  },

  onPickDay(e) {
    this.setData({ sheet: ds.withDay(this.data.sheet, Number(e.currentTarget.dataset.v)) })
  },

  onSheetCancel() {
    this.setData({ sheet: null })
  },

  onSheetConfirm() {
    const sheet = this.data.sheet
    if (!sheet) return
    if (sheet.kind === 'hour') {
      this.setData({
        hourIndex: sheet.hour,
        hourText: hours.labelOf(sheet.hour),
        sheet: null
      })
      return
    }
    const text = ds.format(sheet)
    if (sheet.mode === 'birth') this.setData({ birthDate: text, sheet: null })
    else this.setData({ dueDate: text, sheet: null })
  },

  // 弹层内部点击不应关掉弹层（catchtap 只是止血，真正的关闭只有取消/确定）
  noop() {},

  // ── 下一步 ──

  onNext() {
    const app = getApp()
    const surname = (this.data.surname || '').trim()
    const useBazi = this.data.useBazi
    const prenatal = useBazi && !this.data.born

    // 未出生走的是「孕期参考」，不出名字，也不需要姓氏
    if (!prenatal) {
      if (!surname) {
        wx.showToast({ title: '请输入姓氏', icon: 'none' })
        return
      }
      if (surname.length > 4) {
        wx.showToast({ title: '姓氏最多 4 个字', icon: 'none' })
        return
      }
    }

    if (useBazi && this.data.born && !this.data.birthDate) {
      wx.showToast({ title: '请选择出生日期', icon: 'none' })
      return
    }
    if (prenatal && !this.data.dueDate) {
      wx.showToast({ title: '请选择预产期', icon: 'none' })
      return
    }

    if (prenatal) {
      app.globalData.draftParams = {
        due_date: this.data.dueDate,
        range_days: this.data.rangeDays,
        gender: this.data.gender
      }
      app.globalData.draftTab = 'prenatal'
    } else {
      const draft = {
        surname: surname,
        gender: this.data.gender,
        name_length: this.data.nameLength,
        max_results: 50,
        use_bazi: useBazi,
        use_poetry: true,
        // 展示用字段（提交时会剥离，不透传给后端）
        birthDate: this.data.birthDate,
        hourText: hours.labelOf(this.data.hourIndex)
      }

      // 字辈：仅双字名生效，固定在名字第二个字
      const genChar = (this.data.generationalChar || '').trim()
      if (this.data.nameLength === 2 && genChar) {
        draft.generational_char = genChar
      }

      if (useBazi && this.data.birthDate) {
        const parts = this.data.birthDate.split('-')
        draft.year = Number(parts[0])
        draft.month = Number(parts[1])
        draft.day = Number(parts[2])
        draft.hour = hours.hourOf(this.data.hourIndex)
      }

      app.globalData.draftParams = draft
      app.globalData.draftTab = 'postnatal'
    }

    wx.navigateTo({ url: '/pages/wizard/wizard' })
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
