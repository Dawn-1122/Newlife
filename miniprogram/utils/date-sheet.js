/**
 * 自绘日期选择器 · 数据层
 *
 * 为什么不用原生 `<picker mode="date">`：
 *   预览环境里原生 picker 点不开 —— 用户选不了日期，点「下一步」只会收到
 *   「请选择出生日期」，看上去像起名功能坏了。改成三列 scroll-view 自绘，
 *   整条链路只用 view / scroll-view，不依赖任何原生表单组件。
 *
 * 这里只放**数据与状态迁移**（视图与样式由 app.wxss 里的 .sheet-* 统一提供），
 * 免得「起名」和「释名」两处各写一遍日期推算，闰月、大小月迟早对不上。
 */

const MIN_YEAR = 1900

function pad2(n) {
  return n < 10 ? '0' + n : '' + n
}

function daysInMonth(year, month) {
  return new Date(year, month, 0).getDate()
}

function range(from, to) {
  const out = []
  for (let v = from; v <= to; v++) out.push(v)
  return out
}

function parse(text) {
  if (!text || typeof text !== 'string') return null
  const parts = text.split('-')
  if (parts.length !== 3) return null
  const y = Number(parts[0])
  const m = Number(parts[1])
  const d = Number(parts[2])
  if (!y || !m || !d) return null
  return { y: y, m: m, d: d }
}

function clampYear(year, minYear, maxYear) {
  if (year < minYear) return minYear
  if (year > maxYear) return maxYear
  return year
}

/**
 * 打开弹层时构造初始状态
 *
 * @param {object} opts
 *   value      当前已选日期 'YYYY-MM-DD'，空则用 fallback
 *   fallback   没选过时的默认日期 'YYYY-MM-DD'，缺省为今天
 *   minYear    可选最早年份
 *   maxYear    可选最晚年份，缺省今年
 *   title      弹层标题
 */
function build(opts) {
  const o = opts || {}
  const today = new Date()
  const maxYear = o.maxYear || today.getFullYear()
  const minYear = o.minYear || MIN_YEAR

  const seed = parse(o.value) || parse(o.fallback) || {
    y: today.getFullYear(),
    m: today.getMonth() + 1,
    d: today.getDate()
  }

  const year = clampYear(seed.y, minYear, maxYear)
  const month = Math.min(Math.max(seed.m, 1), 12)
  const maxDay = daysInMonth(year, month)
  const day = Math.min(Math.max(seed.d, 1), maxDay)

  return {
    title: o.title || '选择日期',
    years: range(minYear, maxYear),
    months: range(1, 12),
    days: range(1, maxDay),
    year: year,
    month: month,
    day: day,
    yearAnchor: 'y' + year,
    monthAnchor: 'm' + month,
    dayAnchor: 'd' + day
  }
}

// 换年：2 月 29 日这类要跟着收，否则会出现「2023-02-29」这种不存在的那天
function withYear(sheet, year) {
  if (!sheet) return sheet
  const maxDay = daysInMonth(year, sheet.month)
  const day = Math.min(sheet.day, maxDay)
  return Object.assign({}, sheet, {
    year: year,
    days: range(1, maxDay),
    day: day,
    dayAnchor: 'd' + day
  })
}

function withMonth(sheet, month) {
  if (!sheet) return sheet
  const maxDay = daysInMonth(sheet.year, month)
  const day = Math.min(sheet.day, maxDay)
  return Object.assign({}, sheet, {
    month: month,
    days: range(1, maxDay),
    day: day,
    dayAnchor: 'd' + day
  })
}

function withDay(sheet, day) {
  if (!sheet) return sheet
  return Object.assign({}, sheet, { day: day })
}

function format(sheet) {
  if (!sheet) return ''
  return sheet.year + '-' + pad2(sheet.month) + '-' + pad2(sheet.day)
}

// 今天（各页判断「已出生」默认值用）
function today() {
  const d = new Date()
  return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate())
}

// 今天往后 n 天（预产期默认值用）
function daysLater(n) {
  const d = new Date(new Date().getTime() + n * 86400000)
  return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate())
}

module.exports = {
  MIN_YEAR,
  pad2,
  daysInMonth,
  range,
  build,
  withYear,
  withMonth,
  withDay,
  format,
  today,
  daysLater
}
