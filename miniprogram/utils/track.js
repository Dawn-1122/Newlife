/**
 * 本地埋点（行为计数）
 *
 * ── 为什么自己写一个，而不是接第三方统计 ──
 * 现在没有账号体系、没有后端存储、也没有隐私协议（见产品评审 P0-4）。
 * 在补齐这些之前就往上报数据，是拿用户的信任换几个数字。
 * 所以这里的埋点**只落在本机**：记「做了什么、几次、哪天」，不记任何身份信息、
 * 不上传、不联网。将来接了后端，只改本文件的 `flush()`，调用方一行不动。
 *
 * ── 记什么（都是产品决策需要的三个数）──
 *   naming_submit   起了几次名（判断起名流程走不走得通）
 *   naming_refresh  换了几次一批（判断候选池够不够、翻批是不是刚需）
 *   fav_toggle      收藏/取消几次（判断「名字本」有没有人真用）
 *
 * ── 怎么读 ──
 * `wx.getStorageSync('mt_track_v1')` 或本文件的 `summary()`。
 * 只保留最近 30 天按天计数：再长的历史对判断「最近有没有人用」没有帮助，
 * 却会让这个 key 一直长。
 */

const KEY = 'mt_track_v1'
const KEEP_DAYS = 30

// 事件名集中在这里：散在各页面里写字符串，早晚会出现 naming_submit / namingSubmit 两种拼法
const TRACK = {
  namingSubmit: 'naming_submit',
  namingRefresh: 'naming_refresh',
  favToggle: 'fav_toggle'
}

function todayKey() {
  const d = new Date()
  const m = d.getMonth() + 1
  const day = d.getDate()
  return d.getFullYear() + '-' + (m < 10 ? '0' + m : m) + '-' + (day < 10 ? '0' + day : day)
}

function read() {
  try {
    const value = wx.getStorageSync(KEY)
    if (value && typeof value === 'object') {
      // 拷贝一层再返回：不把存储里的对象直接交出去，
      // 否则调用方拿到的 summary 会随下一次 track 一起变（真机上是反序列化新对象，
      // 在内存版存储的测试里就会互相串）。
      return {
        counts: Object.assign({}, value.counts || {}),
        days: Object.assign({}, value.days || {})
      }
    }
  } catch (err) {
    // 读失败按空处理：埋点是辅助信息，绝不能影响主流程
  }
  return { counts: {}, days: {} }
}

function write(data) {
  try {
    wx.setStorageSync(KEY, data)
  } catch (err) {
    // 存不下就算了，不提示、不重试
  }
}

// 只留最近 KEEP_DAYS 天（按日期字符串排序即可，格式是 YYYY-MM-DD）
function trimDays(days) {
  const keys = Object.keys(days).sort()
  if (keys.length <= KEEP_DAYS) return days
  const kept = {}
  keys.slice(keys.length - KEEP_DAYS).forEach(function (k) {
    kept[k] = days[k]
  })
  return kept
}

/**
 * 记一次行为。失败静默 —— 埋点不该让用户看到任何错误。
 *
 * @param {string} event 事件名（用 TRACK 里的常量）
 * @param {object} [data] 附加维度，只允许计数用的短值（如 { kind: 'postnatal' }）
 *   不要放姓名、生日等任何可识别个人的内容。
 */
function track(event, data) {
  if (!event) return

  const store = read()
  store.counts[event] = (store.counts[event] || 0) + 1

  const day = todayKey()
  const bucket = store.days[day] || {}
  bucket[event] = (bucket[event] || 0) + 1
  store.days[day] = bucket

  // 附加维度单独计数：不存明细，避免这个 key 变成一份行为日志
  if (data && typeof data === 'object') {
    Object.keys(data).forEach(function (k) {
      const v = data[k]
      if (v === undefined || v === null || typeof v === 'object') return
      const key = event + '.' + k + ':' + String(v)
      store.counts[key] = (store.counts[key] || 0) + 1
    })
  }

  store.days = trimDays(store.days)
  write(store)
}

/** 供调试/导出：{ 事件: 次数 } */
function summary() {
  return read().counts
}

/** 清空（「清除本机数据」时一并调用） */
function clear() {
  try {
    wx.removeStorageSync(KEY)
  } catch (err) {
    // 同上，失败不影响主流程
  }
}

module.exports = {
  TRACK,
  track,
  summary,
  clear
}
