/**
 * 起名批次额度（每天 9 批，用完靠转发 / 看广告补）
 *
 * ── 为什么是「一个池子」而不是「换一批 3 次」──
 * 早先按「每次起名送 3 次换一批」算，问题有两个：
 *   1. 文案只能写「今天的换一批用完了」，可换一批其实不跟这一天绑定，读着自相矛盾；
 *   2. 用户回上一页重新提交就又是一批新的，比转发快得多 —— 额度拦不住任何人。
 * 现在起名与换一批**共用同一个池**（各扣 1 批）：一句话能讲清（「今天还能看 9 批」），
 * 重新生成也要扣，额度才真的是一道门。
 *
 * ── 为什么不做成账号额度 ──
 * 现在没有付费墙，配额只是软约束：清缓存能重置，但清缓存同时会丢名字本，
 * 用户成本比「多换几批」的收益高。而账号体系要先有隐私协议（评审 P0-4），
 * 否则收集 openid 就是审核与投诉风险。所以额度先落本机，
 * **将来接后端只改本文件的读写实现**，页面一行不动（与 utils/namebook.js 同一套做法）。
 *
 * ── 漏洞说明（刻意接受）──
 * 1. 清缓存 / 换设备 = 额度重置。理由见上。
 * 2. 转发奖励在「点开转发面板」时就发放，不等分享成功 —— 微信在多处基础库里
 *    不再可靠触发分享成功回调，与其做一个时灵时不灵的判定，不如承认它不精确，
 *    用「每天最多 3 次」把这个洞兜住。
 * 3. 回上一页重新提交一次起名，等于重新掷一次骰子（会拿到与刚才部分重合的一批），
 *    这一步**不扣**次数。前端分不清「今天第一次用」和「又搜了一次」，硬扣会把
 *    首次使用者挡在门外。要真正关门只能靠服务端签发额度（接后端时一并解决）。
 *    现阶段接受它：重新提交拿到的多半是熟面孔，想「一直翻新的」还是得在结果页
 *    点换一批；而把首次生成也计入额度，等于用户第一次打开就被要求转发，
 *    对早期增长是负的。
 */

const rewardAd = require('./reward-ad')

const KEY = 'mt_quota_v1'

// 每天免费批次数（一次起名或一次换一批各扣 1）
const FREE_PER_DAY = 9
// 转发一次补几批 / 每天最多领几次
const SHARE_BONUS = 3
const SHARE_TIMES_CAP = 2
// 看广告一次补几批 / 每天最多领几次
const AD_BONUS = 3
const AD_TIMES_CAP = 2

function todayKey() {
  const d = new Date()
  const m = d.getMonth() + 1
  const day = d.getDate()
  return d.getFullYear() + '-' + (m < 10 ? '0' + m : m) + '-' + (day < 10 ? '0' + day : day)
}

function emptyState(date) {
  return { date: date, used: 0, shareBonus: 0, adBonus: 0, shareCount: 0, adCount: 0 }
}

function read() {
  const today = todayKey()
  let value = null
  try {
    value = wx.getStorageSync(KEY)
  } catch (err) {
    // 读失败按「今天还没用过」处理：宁可多给一次，也不能让用户点不动
    value = null
  }

  if (!value || typeof value !== 'object' || value.date !== today) {
    // 跨天（或首次、或结构坏了）→ 新的一天从满额开始
    return emptyState(today)
  }

  return {
    date: today,
    used: Number(value.used) || 0,
    shareBonus: Number(value.shareBonus) || 0,
    adBonus: Number(value.adBonus) || 0,
    shareCount: Number(value.shareCount) || 0,
    adCount: Number(value.adCount) || 0
  }
}

function write(state) {
  try {
    wx.setStorageSync(KEY, state)
  } catch (err) {
    // 写不下就算了：额度是便宜的，不值得为它弹错误
  }
  return state
}

function remainingOf(state) {
  const total = FREE_PER_DAY + state.shareBonus + state.adBonus
  return Math.max(0, total - state.used)
}

/**
 * 当前额度。
 * @returns {{date, free, used, remaining, shareLeft, adLeft, canWatchAd:boolean}}
 *   shareLeft / adLeft = 今天还能各领几次
 */
function status() {
  const state = read()
  return {
    date: state.date,
    free: FREE_PER_DAY,
    used: state.used,
    remaining: remainingOf(state),
    // “还能领几次”而不是“还能领几批”：按钮上写次数，领一次 +3 批
    shareLeft: Math.max(0, SHARE_TIMES_CAP - state.shareCount),
    adLeft: Math.max(0, AD_TIMES_CAP - state.adCount),
    shareBonus: SHARE_BONUS,
    adBonus: AD_BONUS,
    canWatchAd: canWatchAd()
  }
}

/** 还能不能换一批 */
function canRefresh() {
  return remainingOf(read()) > 0
}

/**
 * 消耗一次（换一批成功拿到新名字之后才调）。
 * @returns {{ok: boolean, remaining: number, reason?: string}}
 */
function consume() {
  const state = read()
  if (remainingOf(state) <= 0) {
    return { ok: false, remaining: 0, reason: 'exhausted' }
  }
  state.used += 1
  write(state)
  return { ok: true, remaining: remainingOf(state) }
}

/**
 * 转发奖励 +3 批。
 * @returns {{ok: boolean, added?: number, remaining?: number, reason?: string}}
 *   reason='capped' 表示今天转发奖励已领完（不是出错）
 */
function grantByShare() {
  const state = read()
  if (state.shareCount >= SHARE_TIMES_CAP) {
    return { ok: false, reason: 'capped', remaining: remainingOf(state) }
  }
  state.shareCount += 1
  state.shareBonus += SHARE_BONUS
  write(state)
  return { ok: true, added: SHARE_BONUS, remaining: remainingOf(state) }
}

/**
 * 广告奖励 +3 批。广告位未开通时返回 reason='ad_unavailable'。
 * @returns {{ok: boolean, added?: number, remaining?: number, reason?: string}}
 */
function grantByAd() {
  if (!canWatchAd()) {
    return { ok: false, reason: 'ad_unavailable', remaining: remainingOf(read()) }
  }
  const state = read()
  if (state.adCount >= AD_TIMES_CAP) {
    return { ok: false, reason: 'capped', remaining: remainingOf(state) }
  }
  state.adCount += 1
  state.adBonus += AD_BONUS
  write(state)
  return { ok: true, added: AD_BONUS, remaining: remainingOf(state) }
}

/** 广告能力是否可用（与 utils/reward-ad.js 共用同一判定，避免两处口径不一致） */
function canWatchAd() {
  return rewardAd.canWatch()
}

/**
 * 现在点「看广告」能不能真拿到次数 = 广告能放 && 今天还有广告额度。
 *
 * 这个判断必须由配额这边给出，不能让页面自己拼 `canWatchAd() && adLeft > 0`：
 * 页面一旦只判一半，用户就会看完 30 秒视频才被告知「今天领完了」——
 * 那是最差的一种反馈，而且改广告逻辑时两处必然漂移。
 */
function canEarnByAd() {
  if (!canWatchAd()) return false
  return AD_TIMES_CAP - read().adCount > 0
}

module.exports = {
  FREE_PER_DAY,
  SHARE_BONUS,
  SHARE_TIMES_CAP,
  AD_BONUS,
  AD_TIMES_CAP,
  status,
  canRefresh,
  consume,
  grantByShare,
  grantByAd,
  canWatchAd,
  canEarnByAd
}
