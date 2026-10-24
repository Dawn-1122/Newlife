/**
 * 十二时辰 + 「不清楚」
 *
 * 「起名」与「释名」两页都要让用户选时辰，选项一旦分头维护，早晚会一边 12 项
 * 一边 11 项。故集中在这里。
 *
 * 为什么不用原生 `<picker mode="selector">`：预览环境里原生 picker 点不开，
 * 用户选不了时辰；改成与「出生日期」同一套底部弹层（单列）。同时把
 * 「23:00–01:00」这种钟点写出来，用户不必先换算子时是几点。
 *
 * ── 为什么单列一个「不清楚」（UNKNOWN_INDEX）──
 * 释名多是给人已经取好的名字看，很多人根本不知道自己的出生时辰；
 * 早年这两页把默认值放在索引 8（申时 = 15:00–17:00），用户没动过那一栏，
 * 页面就把「申时」当成他给的事实排进四柱、算进喜用神，一路展示下去。
 * 现在「不清楚」是一个显式选项，且是释名的默认值：
 * 不知道就是不知道，时柱不参与推断，也不在页面上冒充事实。
 */

const HOURS = [
  { label: '子', name: '子时', span: '23:00–01:00', hour: 23 },
  { label: '丑', name: '丑时', span: '01:00–03:00', hour: 1 },
  { label: '寅', name: '寅时', span: '03:00–05:00', hour: 3 },
  { label: '卯', name: '卯时', span: '05:00–07:00', hour: 5 },
  { label: '辰', name: '辰时', span: '07:00–09:00', hour: 7 },
  { label: '巳', name: '巳时', span: '09:00–11:00', hour: 9 },
  { label: '午', name: '午时', span: '11:00–13:00', hour: 11 },
  { label: '未', name: '未时', span: '13:00–15:00', hour: 13 },
  { label: '申', name: '申时', span: '15:00–17:00', hour: 15 },
  { label: '酉', name: '酉时', span: '17:00–19:00', hour: 17 },
  { label: '戌', name: '戌时', span: '19:00–21:00', hour: 19 },
  { label: '亥', name: '亥时', span: '21:00–23:00', hour: 21 }
]

// 「不清楚」排在 12 个真实时辰之后：老记录里存的 0–11 索引仍然指向原来那一格，
// 不必写迁移。
const UNKNOWN_INDEX = HOURS.length

const UNKNOWN = { label: '—', name: '不清楚', span: '不填也可', hour: null }

// 供页面 wx:for 使用的完整选项（12 真实 + 1 不清楚）
const HOUR_OPTIONS = HOURS.concat([UNKNOWN])

function isUnknown(index) {
  return Number(index) === UNKNOWN_INDEX
}

/**
 * 索引 → 小时（0–23）。未知返回 null —— 调用方据此**不传** hour 字段，
 * 而不是塞一个 12 让后端以为用户选了午时。
 */
function hourOf(index) {
  if (isUnknown(index)) return null
  const i = Number(index)
  if (!isFinite(i) || i < 0 || i >= HOURS.length) return null
  return HOURS[i].hour
}

/** 索引 → 展示名（'子时' / '不清楚'） */
function labelOf(index) {
  if (isUnknown(index)) return UNKNOWN.name
  const i = Number(index)
  if (!isFinite(i) || i < 0 || i >= HOURS.length) return UNKNOWN.name
  return HOURS[i].name
}

module.exports = {
  HOURS,
  HOUR_OPTIONS,
  UNKNOWN_INDEX,
  isUnknown,
  hourOf,
  labelOf
}
