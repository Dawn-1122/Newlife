const api = require('../../utils/api')

Page({
  data: {
    name: null,
    pinyinText: '',

    // 语境义项（免费）：各字在本出处语境下的取义
    ctxSenses: [],

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

    this.setData({
      name,
      pinyinText: name.phonetics.pinyins.join(' · '),
      ctxSenses,
      unlocked
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

  onCopyTap() {
    const name = this.data.name
    const poetry = name.poetry
      ? `\n出处：「${name.poetry.source}·${name.poetry.title}」\n${name.poetry.text}`
      : ''

    const text = `${name.full_name}\n综合评分: ${name.scores.overall}分${poetry}\n${name.meaning}`

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

    const name = this.data.name
    return {
      title: `「${name.full_name}」综合评分${name.scores.overall}分`,
      path: '/pages/home/home'
    }
  },

  // 分享到朋友圈同样解锁（该场景不支持自定义 path，只能带 query）
  onShareTimeline() {
    this.markUnlocked()
    const name = this.data.name
    return {
      title: `「${name.full_name}」综合评分${name.scores.overall}分`
    }
  }
})
