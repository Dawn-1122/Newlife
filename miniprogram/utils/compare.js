/**
 * 对比队列（「测候选名 / 双名对比」用的待比名单）
 *
 * ── 为什么需要一个队列 ──
 * 对比是**跨页面攒**出来的：在收藏页看中两个名字、或在释名页手输几个候选，
 * 名字分散在不同页面。小程序页面之间没有 URL 参数可传（不是浏览器路由），
 * 页面栈也不能带结构化数据回来，所以只能有一份共享状态。
 *
 * 放在 `app.globalData` 而不是本地存储：对比是一次性的并置动作，
 * 攒到第二天再比意义不大；而收藏本身已经持久化，随时能重新加入。
 * （若将来要做「跨天比对」，只改这个文件的读写实现，页面不用动。）
 *
 * ── 上限 3 ──
 * 并排对照表在手机上最多容得下 3 列（再宽每格只剩四五个字，读不成句）。
 * 也符合真实决策场景：五六个候选最终总要收敛到两三个再比。
 * 满了**不挤掉最早的那个**，直接拒绝并让调用方提示 —— 静默替换会让人
 * 以为自己加进去了，实际换掉的是另一个。
 */

const KEY = 'compareNames'
const MAX = 3

function read() {
  const app = getApp()
  const list = (app && app.globalData && app.globalData[KEY]) || []
  return Array.isArray(list) ? list : []
}

function write(list) {
  const app = getApp()
  if (app && app.globalData) app.globalData[KEY] = list
  return list
}

/** 当前待比名单（姓名数组，按加入顺序） */
function list() {
  return read().slice()
}

/** 是否已在队列里 */
function has(name) {
  return read().indexOf(name) !== -1
}

/**
 * 加入一个名字。
 * @returns {{ok: boolean, full?: boolean, names?: string[], error?: string}}
 *   full = 已满 MAX 个，调用方应提示「先去掉一个」
 */
function add(name) {
  const value = (name || '').trim()
  if (!value) {
    return { ok: false, error: '名字为空，无法加入对比' }
  }

  const current = read()
  if (current.indexOf(value) !== -1) {
    // 重复加入视为「保留」，不开新位置，但也不算失败
    return { ok: true, names: current.slice() }
  }
  if (current.length >= MAX) {
    return { ok: false, full: true, names: current.slice() }
  }

  const next = current.concat([value])
  write(next)
  return { ok: true, names: next.slice() }
}

/** 移除一个名字 */
function remove(name) {
  const next = read().filter(function (n) {
    return n !== name
  })
  write(next)
  return next.slice()
}

/** 清空 */
function clear() {
  write([])
  return []
}

module.exports = {
  MAX,
  list,
  has,
  add,
  remove,
  clear
}
