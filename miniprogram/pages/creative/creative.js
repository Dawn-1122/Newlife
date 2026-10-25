// 创意起名页：网名昵称（平台/游戏/角色）/ 宠物 / 商业。
// mode 参数由起名类型选择页传入：netname | pet | business。
const api = require('../../utils/api')
const share = require('../../utils/share')
const rewardAd = require('../../utils/reward-ad')

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

    // 平台名称：目标平台（平台基因）
    platformTypes: api.PLATFORM_TYPES,
    platformType: 'xiaohongshu',

    // 游戏昵称：游戏类型（游戏文化生态）
    gameTypes: api.GAME_TYPES,
    gameType: 'fantasy',

    // 宠物
    petTypes: [
      { code: 'cat', name: '猫' },
      { code: 'dog', name: '狗' },
      { code: 'other', name: '其他' }
    ],
    petType: 'cat',

    // 商业
    industries: api.INDUSTRY_OPTIONS,
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
    // 广告位是否真的可用：决定按钮文案是「看广告解锁 AI」还是「生成名字」。
    // 未开通时先说清楚，不能让用户以为点了能拿到 AI 结果
    canWatchAd: false,

    // 共享输入 + 结果
    keywords: '',
    names: [],
    loading: false,
    generated: false,
    llmSource: '',    // llm=AI 生成 / local=本地降级（仅角色分支）
    fallbackNote: ''  // 降级说明（常驻显示在结果上方，不是一闪而过的 toast）
  },

  onLoad(options) {
    const mode = options && options.mode ? options.mode : 'netname'
    this.setData({ canWatchAd: this._canWatchAd() })
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
      generated: false,
      fallbackNote: ''
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

  onPlatformTypeTap(e) {
    this.setData({ platformType: e.currentTarget.dataset.code })
  },

  onGameTypeTap(e) {
    this.setData({ gameType: e.currentTarget.dataset.code })
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

  onIndustryTap(e) {
    this.setData({ industryIndex: Number(e.currentTarget.dataset.index) })
  },

  // 角色分支是否走「看广告解锁 AI 生成」：仅当处于 role 子页且填了自定义描述
  _hasDesc() {
    return (this.data.customDesc || '').trim().length > 0
  },

  _isLLMPath() {
    return this.data.mode === 'netname' && this.data.subKind === 'role' && this._hasDesc()
  },

  // 能不能真的走「看广告 → AI 生成」：广告位配了、宿主支持激励视频
  _canWatchAd() {
    return rewardAd.canWatch()
  },

  onGenerate() {
    if (this.data.loading) return
    if (this._isLLMPath()) {
      if (this._canWatchAd()) {
        this._watchAdThenGenerate()
      } else {
        // 广告位没配（或宿主不支持激励视频）时，过去只弹一句提示就结束：
        // 用户越认真填描述，越什么都拿不到 —— 填得越对越像惩罚。
        // 现在降级到本地词库先出名字，并说明描述这次没参与。
        this._fallbackToLocal(
          'AI 生成需要激励视频广告位，当前未开通。以下是本地词库生成的名字，自定义描述这次未参与。'
        )
      }
      return
    }
    this._generateLocal()
  },

  _generateLocal(options) {
    const note = (options && options.note) || ''
    const d = this.data
    const params = { count: 18 }

    if (d.mode === 'netname') {
      params.kind = d.subKind
      params.keywords = (d.keywords || '').trim()
      if (d.subKind === 'platform') {
        if (d.platformType) params.platform_type = d.platformType
      } else if (d.subKind === 'game') {
        if (d.gameType) params.game_type = d.gameType
      } else if (d.subKind === 'role') {
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
        this.setData({
          names: res.names || [],
          loading: false,
          generated: true,
          llmSource: '',
          // 后端本地兜底也会给 fallback_note，一起显示，不丢信息
          fallbackNote: note || res.fallback_note || ''
        })
      })
      .catch(err => {
        this.setData({ loading: false })
        wx.showToast({ title: (err && err.message) || '生成失败', icon: 'none' })
      })
  },

  // 任何一条「AI 走不通」的路径都收在这里：先出本地结果，再说清原因
  _fallbackToLocal(note) {
    this._generateLocal({ note: note })
  },

  // 看激励视频广告 → 解锁 AI 生成（广告位配置驱动）
  // 播放与失败收口都在 utils/reward-ad.js，这里只决定「失败之后怎么办」
  _watchAdThenGenerate() {
    rewardAd.watch({
      onReward: () => this._generateLLM(),
      onCancel: () => wx.showToast({ title: '看完广告才能解锁 AI 生成哦', icon: 'none' }),
      onFail: () => this._fallbackToLocal(
        '广告没能加载出来。以下改用本地词库生成，自定义描述这次未参与。'
      )
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
          llmSource: res.source || '',
          // 后端没配大模型时会降级本地并给 fallback_note；
          // 常驻显示在结果上方，别让它随 toast 一闪而过
          fallbackNote: res.fallback_note || ''
        })
      })
      .catch(err => {
        // AI 这条路断了也别让用户空手：退回本地词库，说明原因
        this.setData({ loading: false })
        console.warn('AI 生成失败', err)
        this._fallbackToLocal('AI 生成这次没成功。以下是本地词库生成的名字，自定义描述这次未参与。')
      })
  },

  onNameTap(e) {
    const name = e.currentTarget.dataset.name
    wx.setClipboardData({ data: name })
  },

  onShareAppMessage: share.defaultShare,

  onShareTimeline: share.defaultTimeline
})
