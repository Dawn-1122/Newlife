/**
 * 十二时辰
 *
 * 「起名」与「释名」两页都要让用户选时辰，网格的排列、子时落在 23 点这些
 * 细节一旦分头维护，早晚会一边 12 格一边 11 格。故集中在这里。
 *
 * 为什么不用原生 `<picker mode="selector">`：预览环境里原生 picker 点不开，
 * 用户选不了时辰；改成 12 个格子直接点，同时把「23-1」这种时段写出来，
 * 用户不必先换算子时是几点。
 */

const HOURS = [
  { label: '子', span: '23-1', hour: 23 },
  { label: '丑', span: '1-3', hour: 1 },
  { label: '寅', span: '3-5', hour: 3 },
  { label: '卯', span: '5-7', hour: 5 },
  { label: '辰', span: '7-9', hour: 7 },
  { label: '巳', span: '9-11', hour: 9 },
  { label: '午', span: '11-13', hour: 11 },
  { label: '未', span: '13-15', hour: 13 },
  { label: '申', span: '15-17', hour: 15 },
  { label: '酉', span: '17-19', hour: 17 },
  { label: '戌', span: '19-21', hour: 19 },
  { label: '亥', span: '21-23', hour: 21 }
]

// 默认「未知」时取正午前后偏中间的一格没有意义，直接取索引 8（申时）会误导，
// 所以各页自己决定默认值；这里只提供越界兜底，避免索引错位取到 undefined。
function hourOf(index) {
  const i = Number(index)
  if (!isFinite(i) || i < 0 || i >= HOURS.length) return HOURS[0].hour
  return HOURS[i].hour
}

function labelOf(index) {
  const i = Number(index)
  if (!isFinite(i) || i < 0 || i >= HOURS.length) return HOURS[0].label + '时'
  return HOURS[i].label + '时'
}

module.exports = {
  HOURS,
  hourOf,
  labelOf
}
