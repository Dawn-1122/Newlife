// 创意起名页：网名昵称（平台/游戏/角色）/ 宠物 / 商业。
// mode 参数由起名类型选择页传入：netname | pet | business。
const api = require('../../utils/api')
const share = require('../../utils/share')

const NETNAME_SUBTABS = [
  { code: 'platform', name: '平台名称', ph: '比如：摄影师、爱喝咖啡、养三只猫' },
  { code: 'game', name: '游戏昵称', ph: '比如：开放世界、硬核射击、休闲经营' },
  { code: 'role', name: '虚构角色', ph: '比如：赛博朋克世界观下的义体医生' }
]

const KW_LABELS = {
  netname: '一句话介绍',
  pet: '特点 / 毛色（选填）',
  business: '主营 / 品类（选填）'
}

const KW_PLACEHOLDERS = {
  pet: '比如：橘色、爱吃、圆滚滚',
  business: '比如：手工咖啡、云南豆'
}

Page({
  data: {
    mode: 'netname', // netname | pet | business
    title: '',
    sub: '',
    kwLabel: '',
    placeholder: '',

    // 网名昵称
    subTabs: NETNAME_SUBTABS,
    subKind: 'platform',

    // 宠物
    petTypes: [
      { code: 'cat', name: '猫' },
      { code: 'dog', name: '狗' },
      { code: 'other', name: '其他' }
    ],
    petType: 'cat',

    // 商业
    industries: api.INDUSTRY_OPTIONS,
    industryNames: api.INDUSTRY_OPTIONS.map(i => i.name),
    industryIndex: 0,

    // 虚拟角色：性别 + 小说类型 + 性格特征 + 自定义描述（AI）
    roleGenders: [
      { code: 'male', name: '男' },
      { code: 'female', name: '女' }
    ],
    roleGender: '', // 选中性别 code（单选，再点取消；空=不限）
    genres: api.NOVEL_GENRES,
    traits: api.CHARACTER_TRAITS,
    genre: '',      // 选中的小说类型 code（单选，再点取消）
    trait: '',      // 选中的性格特征 code（单选，再点取消）
    customDesc: '', // 自定义描述（填了走看广告解锁 AI 生成）
    isLLMPath: false,

    // 共享输入 + 结果
    keywords: '',
    names: [],
    loading: false,
    generated: false,
    llmSource: ''   // llm=AI 生成 / local=本地降级（仅角色分支）
  },

  onLoad(options) {
    const mode = options && options.mode ? options.mode : 'netname'
    this._applyMode(mode)
  },

  _applyMode(mode) {
    const meta = {
      netname: { title: '网名昵称', sub: '平台 · 游戏 · 角色' },
      pet: { title: '宠物起名', sub: '给毛孩子一个有讲头的名' },
      business: { title: '商业名称', sub: '店名 · 品牌 · 字号' }
    }[mode] || { title: '网名昵称', sub: '' }
    const placeholder = mode === 'netname'
      ? NETNAME_SUBTABS[0].ph
      : (KW_PLACEHOLDERS[mode] || '')
    this.setData({
      mode,
      title: meta.title,
      sub: meta.sub,
      kwLabel: KW_LABELS[mode] || '',
      placeholder,
      names: [],
      generated: false
    })
    wx.setNavigationBarTitle({ title: meta.title })
  },

  onSubTabTap(e) {
    const kind = e.currentTarget.dataset.kind
    const tab = NETNAME_SUBTABS.find(t => t.code === kind)
    this.setData({
      subKind: kind,
      placeholder: tab ? tab.ph : '',
      isLLMPath: kind === 'role' && this._hasDesc()
    })
  },

  onKeywordsInput(e) {
    this.setData({ keywords: e.detail.value })
  },

  onGenreTap(e) {
    const code = e.currentTarget.dataset.code
    this.setData({ genre: this.data.genre === code ? '' : code })
  },

  onRoleGenderTap(e) {
    const code = e.currentTarget.dataset.code
    this.setData({ roleGender: this.data.roleGender === code ? '' : code })
  },

  onTraitTap(e) {
    const code = e.currentTarget.dataset.code
    this.setData({ trait: this.data.trait === code ? '' : code })
  },

  onCustomDescInput(e) {
    const val = e.detail.value
    this.setData({
      customDesc: val,
      isLLMPath: this.data.subKind === 'role' && (val || '').trim().length > 0
    })
  },

  onPetTypeTap(e) {
    this.setData({ petType: e.currentTarget.dataset.type })
  },

  onIndustryChange(e) {
    this.setData({ industryIndex: Number(e.detail.value) })
  },

  // 角色分支是否走「看广告解锁 AI 生成」：仅当处于 role 子页且填了自定义描述
  _hasDesc() {
    return (this.data.customDesc || '').trim().length > 0
  },

  _isLLMPath() {
    return this.data.mode === 'netname' && this.data.subKind === 'role' && this._hasDesc()
  },

  onGenerate() {
    if (this.data.loading) return
    if (this._isLLMPath()) {
      this._watchAdThenGenerate()
      return
    }
    this._generateLocal()
  },

  _generateLocal() {
    const d = this.data
    const params = { count: 18 }

    if (d.mode === 'netname') {
      params.kind = d.subKind
      params.keywords = (d.keywords || '').trim()
      if (d.subKind === 'role') {
        if (d.roleGender) params.gender = d.roleGender
        if (d.genre) params.genre = d.genre
        if (d.trait) params.trait = d.trait
      }
    } else if (d.mode === 'pet') {
      params.kind = 'pet'
      params.pet_type = d.petType
      params.keywords = (d.keywords || '').trim()
    } else {
      params.kind = 'business'
      params.industry = d.industries[d.industryIndex].code
      params.keywords = (d.keywords || '').trim()
    }

    this.setData({ loading: true })
    api.creativeGenerate(params)
      .then(res => {
        this.setData({ names: res.names || [], loading: false, generated: true, llmSource: '' })
      })
      .catch(err => {
        this.setData({ loading: false })
        wx.showToast({ title: (err && err.message) || '生成失败', icon: 'none' })
      })
  },

  // 看激励视频广告 → 解锁 AI 生成（广告位配置驱动）
  _watchAdThenGenerate() {
    const adUnitId = api.REWARDED_AD_UNIT_ID
    if (!adUnitId) {
      wx.showToast({ title: '广告位未配置，暂无法解锁 AI 生成', icon: 'none' })
      return
    }
    if (!wx.createRewardedVideoAd) {
      wx.showToast({ title: '当前环境不支持激励视频广告', icon: 'none' })
      return
    }

    const rewarded = wx.createRewardedVideoAd({ adUnitId })
    rewarded.onError(err => {
      console.warn('激励视频加载失败', err)
      wx.showToast({ title: '广告加载失败，请稍后再试', icon: 'none' })
    })
    rewarded.onClose(res => {
      if (res && res.isEnded) {
        this._generateLLM()
      } else {
        wx.showToast({ title: '看完广告才能解锁 AI 生成哦', icon: 'none' })
      }
    })
    rewarded.show().catch(() => {
      rewarded.load()
        .then(() => rewarded.show())
        .catch(() => wx.showToast({ title: '广告加载失败，请稍后再试', icon: 'none' }))
    })
  },

  _generateLLM() {
    const d = this.data
    const params = {
      description: (d.customDesc || '').trim(),
      count: 18
    }
    if (d.roleGender) params.gender = d.roleGender
    if (d.genre) params.genre = d.genre
    if (d.trait) params.trait = d.trait

    this.setData({ loading: true })
    api.llmGenerate(params)
      .then(res => {
        this.setData({
          names: res.names || [],
          loading: false,
          generated: true,
          llmSource: res.source || ''
        })
        if (res.fallback_note) {
          wx.showToast({ title: res.fallback_note, icon: 'none', duration: 2500 })
        }
      })
      .catch(err => {
        this.setData({ loading: false })
        wx.showToast({ title: (err && err.message) || '生成失败', icon: 'none' })
      })
  },

  onNameTap(e) {
    const name = e.currentTarget.dataset.name
    wx.setClipboardData({ data: name })
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
