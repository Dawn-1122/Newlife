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

    // 共享输入 + 结果
    keywords: '',
    names: [],
    loading: false,
    generated: false
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
    this.setData({ subKind: kind, placeholder: tab ? tab.ph : '' })
  },

  onKeywordsInput(e) {
    this.setData({ keywords: e.detail.value })
  },

  onPetTypeTap(e) {
    this.setData({ petType: e.currentTarget.dataset.type })
  },

  onIndustryChange(e) {
    this.setData({ industryIndex: Number(e.detail.value) })
  },

  onGenerate() {
    if (this.data.loading) return
    const d = this.data
    const params = { count: 18 }

    if (d.mode === 'netname') {
      params.kind = d.subKind
      params.keywords = (d.keywords || '').trim()
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
        this.setData({ names: res.names || [], loading: false, generated: true })
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
