const api = require('../../utils/api')
const namebook = require('../../utils/namebook')
const share = require('../../utils/share')
const track = require('../../utils/track')

Page({
  data: {
    name: null,
    pinyinText: '',

    // 是否已收进「名字本」（本机存储，见 utils/namebook.js）
    fav: false,

    // 语境义项（免费）：各字在本出处语境下的取义
    ctxSenses: [],

    // 契合点：这个选字为什么对得上所选的期许（文化记号，见后端 core/meaning_culture.py）
    meaningFit: [],

    // 深度寓意（多层余味，分享解锁）
    unlocked: false,
    deepLoading: false,
    deepMeaning: null,
    layers: [],
    meaningSource: ''
  },

  // 语境义项 → 展示结构 [{char, words, general}]，并把 senses 挂到逐字上
  buildCtxSenses(list) {
    return (list || [])
      .filter(item => item && item.char)
      .map(item => ({
        char: item.char,
        senses: item.senses || [],
        words: (item.senses || []).join('、'),
        general: item.general || '',
        // 该字不在名字主出处里，义项取自它自己最贴合的句子
        fromMain: item.from_main !== false
      }))
  },

  onLoad() {
    const app = getApp()
    let name = app.globalData.selectedName

    if (!name) {
      wx.navigateBack()
      return
    }

    // 把语境义项挂到逐字上（用字解析区按语境释义）
    const ctxSenses = this.buildCtxSenses(name.context_senses)
    const senseMap = {}
    ctxSenses.forEach(item => { senseMap[item.char] = item.senses })
    name = Object.assign({}, name, {
      chars_info: (name.chars_info || []).map(c =>
        Object.assign({}, c, { senses: senseMap[c.char] || [] })
      )
    })

    // 按起名批次单次解锁：分享一次，本批次所有名字的深度寓意均可看
    const batchId = app.globalData.lastBatchId || 'default'
    const unlocked = !!wx.getStorageSync('unlock_' + batchId)
    this.batchId = batchId

    // 契合点：后端给的是期许 code，这里翻成中文名再上屏（wxml 里不做映射）
    const meaningFit = (name.meaning_fit || []).map(f => Object.assign({}, f, {
      titles: api.meaningNames(f.codes)
    }))

    // 气质契合点：一个字族说明 + 本名命中的字。
    // 不做成逐字一行 —— 同一气质的说明对每个字都一样，逐行重复只是噪音。
    // style code 挂在命中项上（见 core/meaning_culture.style_hits），
    // 从名字本回看时不再依赖当初的请求参数。
    const styleHits = name.style_fit || []
    const styleFit = styleHits.length
      ? {
          name: api.styleName(styleHits[0].style),
          note: styleHits[0].note,
          chars: styleHits.map(f => f.char).join('、')
        }
      : null

    this.setData({
      name,
      pinyinText: name.phonetics.pinyins.join(' · '),
      ctxSenses,
      meaningFit,
      styleFit,
      unlocked,
      fav: namebook.isFav(name.full_name)
    })

    if (unlocked) {
      this.loadDeepMeaning()
    }
  },

  async loadDeepMeaning() {
    const app = getApp()
    const name = this.data.name
    const params = app.globalData.lastParams || {}

    this.setData({ deepLoading: true })
    try {
      const result = await api.nameMeaning({
        full_name: name.full_name,
        gender: params.gender || 'male',
        year: params.year,
        month: params.month,
        day: params.day,
        hour: params.hour,
        minute: params.minute
      })
      // 深度解读可能定位到更贴合的出处，其语境义项更准，优先采用
      const deepCtx = this.buildCtxSenses(result.context_senses)
      this.setData({
        deepMeaning: result,
        layers: result.layers || [],
        meaningSource: result.meaning_source || '',
        ctxSenses: deepCtx.length ? deepCtx : this.data.ctxSenses,
        deepLoading: false
      })
    } catch (err) {
      this.setData({ deepLoading: false })
      wx.showToast({ title: (err && err.message) || '深度解读加载失败', icon: 'none' })
    }
  },

  markUnlocked() {
    wx.setStorageSync('unlock_' + (this.batchId || 'default'), true)
    this.setData({ unlocked: true })
    if (!this.data.deepMeaning) {
      this.loadDeepMeaning()
    }
  },

  // 收藏 / 取消收藏：和结果页共用同一套落盘（utils/namebook.js）
  onFavTap() {
    const name = this.data.name
    const app = getApp()
    const ret = namebook.toggleFav(name, app.globalData.lastParams, app.globalData.lastBatchId)
    if (!ret.ok) {
      wx.showToast({ title: ret.error, icon: 'none' })
      return
    }
    this.setData({ fav: !!ret.added })
    track.track(track.TRACK.favToggle, { added: ret.added ? 'yes' : 'no' })
    wx.showToast({ title: ret.added ? '已收藏' : '已取消收藏', icon: 'none' })
  },

  onCopyTap() {
    const name = this.data.name
    let poetry = ''

    if (name.poetry) {
      // 优先用诗库自带的 citation（《诗经·秦风·蒹葭》），它比「来源·篇名」拼串准确
      const citation = name.poetry.citation
        || `「${name.poetry.source}·${name.poetry.title}」`
      poetry = '\n出处：' + citation + '\n' + name.poetry.text
    }

    // 不写分数：推荐分只用于起名时的排序，落到「被复制出去的那段文字」上
    // 就成了给名字定等级（见 MEMORY.md 的产品原则）。
    const text = `${name.full_name}${poetry}\n${name.meaning}`

    wx.setClipboardData({
      data: text,
      success() {
        wx.showToast({ title: '已复制', icon: 'success' })
      }
    })
  },

  onShareAppMessage() {
    // ⚠️ 微信 onShareAppMessage 的返回值只支持 title / path / imageUrl / promise 四个字段
    //    （官方文档：框架接口 / Page，onShareAppMessage 小节），平台**不提供**
    //    「分享成功」回调。此前这里写了 success 字段，会被静默忽略 →
    //    markUnlocked() 永不执行 → 深度寓意永远锁着，「分享解锁」整条链路是死的。
    //    现改为「用户发起分享即解锁」：本函数被调用本身就代表用户点了分享入口
    //    （页面内 open-type="share" 按钮，或右上角菜单「转发」），
    //    这是官方允许的、最接近「已分享」的时机。
    //    ⚠️ 代价：用户在分享面板里点取消也会解锁 —— 平台层面无法区分，属于已知取舍。
    this.markUnlocked()

    // 落地页指向 /pages/share/share 并带上名字与整条出处：
    // 指向 home 会把「他分享的是哪个名字」丢干净，指向 detail 则因冷启动没有
    // globalData.selectedName 而白屏（见 share.js 顶部注释）。
    const app = getApp()
    const params = app.globalData.lastParams || {}
    return share.nameShare(this.data.name.full_name, this.data.name.poetry, params.gender)
  },

  // 分享到朋友圈同样解锁（该场景不支持自定义 path，只能带 query）
  onShareTimeline() {
    this.markUnlocked()
    const app = getApp()
    const params = app.globalData.lastParams || {}
    return share.nameTimeline(this.data.name.full_name, this.data.name.poetry, params.gender)
  }
})
