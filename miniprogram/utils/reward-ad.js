/**
 * 激励视频广告（唯一实现）
 *
 * 为什么单独抽出来：现在有两处要放激励视频 —— 创意起名的「看广告解锁 AI 生成」
 * 和换一批的「看广告 +1 次」。各自写一遍 `createRewardedVideoAd` + onError/onClose
 * + show/load 兜底，迟早出现两套不一样的失败处理（一处降级、一处白屏）。
 *
 * ── 回调只发一次 ──
 * onError 与 onClose 可能先后都触发（真机上广告加载失败后再关面板），
 * 若不收口就会「既降级又生成一轮」。这里用 settled 保证三个回调里只走一个。
 *
 * ── 广告位没配怎么办 ──
 * `canWatch()` 返回 false，调用方据此**不要**把按钮做成可点的样子 ——
 * 早期广告位 ID 为空是常态，这时候承诺「看广告换次数」是给不出的承诺。
 */

const api = require('./api')

/** 广告能力是否可用：广告位 ID 已配置 + 宿主支持激励视频 */
function canWatch() {
  return !!api.REWARDED_AD_UNIT_ID && !!wx.createRewardedVideoAd
}

/**
 * 播放一段激励视频。
 *
 * @param {object} handlers
 *   onReward() 看完（isEnded）时调用
 *   onCancel() 中途关掉时调用
 *   onFail()   加载/播放失败、或广告能力不可用时调用
 */
function watch(handlers) {
  const h = handlers || {}
  const onReward = h.onReward || function () {}
  const onCancel = h.onCancel || function () {}
  const onFail = h.onFail || function () {}

  if (!canWatch()) {
    onFail()
    return
  }

  const rewarded = wx.createRewardedVideoAd({ adUnitId: api.REWARDED_AD_UNIT_ID })

  let settled = false
  const once = function (fn) {
    if (settled) return
    settled = true
    fn()
  }

  rewarded.onError(function (err) {
    console.warn('激励视频加载失败', err)
    once(onFail)
  })

  rewarded.onClose(function (res) {
    if (res && res.isEnded) once(onReward)
    else once(onCancel)
  })

  rewarded.show().catch(function () {
    // 首次 show 常因未预加载失败：补一次 load 再 show
    rewarded.load()
      .then(function () { return rewarded.show() })
      .catch(function () { once(onFail) })
  })
}

module.exports = {
  canWatch,
  watch
}
