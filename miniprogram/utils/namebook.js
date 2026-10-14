/**
 * 名字本 · 本地持久化层（起名记录 + 收藏名字）
 *
 * ── 为什么需要这个文件 ──
 * 起名结果、孕期参考、名字测评的结果此前**只写在 `app.globalData` 里**（纯内存）。
 * 小程序被销毁、用户划掉后台、换台设备，这些结果就没了 —— 用户回不到
 * 「上次给我家孩子起的那批名字」，也留不住一眼看中的那个名字。
 * 「名字本」这个功能缺的正是一层落盘。
 *
 * 落盘用 `wx.setStorageSync`：小程序端唯一的本地持久化能力
 * （页面 JS 里没有 window / localStorage / sessionStorage）。
 * 数据只存在用户自己这台设备的微信里，不上传、不联网也能用。
 *
 * ── 边界（必须知道）──
 * 1. **本地 = 单机。** 换手机、清微信缓存、卸载重装都会丢，也不会多端同步。
 *    要做到跨设备、多端、多人共享，只能接后端。届时**只替换本文件的读写实现**，
 *    页面调用方一行都不用改 —— 所以落盘细节全部收在这里，
 *    页面里一律通过本模块读写，不要直接碰 `wx.setStorageSync`。
 * 2. **容量。** 微信限制：单个 key ≤ 1MB，单小程序总量 ≤ 10MB。
 *    实测一次起名返回约 39KB（20 个候选），故记录按「条数 + 字节数」双上限保留，
 *    超出丢最旧的（见 `trim`）。字节数按 UTF-8 实算，中文按 3 字节计。
 * 3. **写失败不静默。** 存储写满时 `wx.setStorageSync` 会抛错，
 *    本模块一律捕获并返回 `{ ok: false, error }`，由页面弹提示 —— 不能装作存上了。
 */

// 存储键带版本号：将来结构变了就升版本，旧数据自然失效，不必写迁移逻辑
const RECORD_KEY = 'mt_records_v1'
const FAV_KEY = 'mt_favs_v1'

// 保留上限
const RECORD_LIMIT = 10 // 一次起名 ≈ 39KB，10 批 ≈ 520KB（远低于单 key 1MB）
const FAV_LIMIT = 60 // 单名 ≈ 1.8KB，60 个 ≈ 110KB
const RECORD_MAX_BYTES = 620 * 1024
const FAV_MAX_BYTES = 200 * 1024

// 记录类型 → 展示名（历史列表用）
const KIND_LABEL = {
  postnatal: '起名',
  prenatal: '孕期参考',
  analyze: '名字测评'
}

// --------------------------------------------------------------------------- //
// 底层读写
// --------------------------------------------------------------------------- //

function readList(key) {
  try {
    const value = wx.getStorageSync(key)
    return Array.isArray(value) ? value : []
  } catch (err) {
    // 读失败按空处理：名字本是辅助功能，不能因为存储异常让页面白屏
    return []
  }
}

function writeList(key, list) {
  try {
    wx.setStorageSync(key, list)
    return { ok: true }
  } catch (err) {
    return { ok: false, error: '本机存储写入失败（可能已满），请先删掉一些旧记录再试' }
  }
}

function removeKey(key) {
  try {
    wx.removeStorageSync(key)
    return { ok: true }
  } catch (err) {
    return { ok: false, error: '本机存储清理失败，请稍后重试' }
  }
}

// UTF-8 字节数（微信按 UTF-8 计单 key 上限，中文 3 字节）
function byteLen(text) {
  let total = 0
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i)
    if (code < 0x80) total += 1
    else if (code < 0x800) total += 2
    else total += 3
  }
  return total
}

// 双上限裁剪：先按条数截断，再按字节数从尾部丢，直到进预算
function trim(list, limit, maxBytes) {
  const kept = list.slice(0, limit)
  while (kept.length > 1 && byteLen(JSON.stringify(kept)) > maxBytes) {
    kept.pop()
  }
  return kept
}

// --------------------------------------------------------------------------- //
// 展示用格式化
// --------------------------------------------------------------------------- //

function pad2(n) {
  return n < 10 ? '0' + n : String(n)
}

// '2026-10-14 15:04'
function formatTime(ts) {
  const d = new Date(ts)
  return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) +
    ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes())
}

function pinyinOf(name) {
  const pinyins = (name && name.phonetics && name.phonetics.pinyins) || []
  return pinyins.join(' · ')
}

function genderText(gender) {
  return gender === 'female' ? '女孩' : '男孩'
}

function styleText(code) {
  const found = STYLE_SHORT[code]
  return found || ''
}

// 与 utils/api.js 的 STYLE_OPTIONS.short 一致（只用于历史条目的副标题）
const STYLE_SHORT = {
  classic: '古风',
  modern: '现代',
  grand: '大气',
  fresh: '清新',
  warm: '温润',
  elegant: '清朗',
  plain: '质朴',
  zen: '空灵'
}

// --------------------------------------------------------------------------- //
// 记录（一批结果）
// --------------------------------------------------------------------------- //

/**
 * 把一次请求的结果整理成「名字本」里的一条记录。
 *
 * 三个调用点（wizard / result「换一批」/ analyze）都走这里，
 * 保证记录结构只有一处定义，不会各自漂移。
 *
 * @param {'postnatal'|'prenatal'|'analyze'} kind
 * @param {object} params  原始请求参数（「调整偏好」要靠它回填）
 * @param {object} result  后端原始返回
 * @param {number} [batchId] 起名批次（深度寓意的解锁按批次，恢复时要带回去）
 */
function buildRecord(kind, params, result, batchId) {
  const record = {
    id: 'rec_' + Date.now() + '_' + Math.floor(Math.random() * 1000),
    kind: kind,
    kindLabel: KIND_LABEL[kind] || '记录',
    createdAt: Date.now(),
    params: params || {},
    batchId: batchId || 0,
    payload: result,
    chips: []
  }

  if (kind === 'postnatal') {
    const names = (result && result.names) || []
    // 只留前 8 个进列表摘要，整份结果仍完整存在 payload 里
    record.chips = names.slice(0, 8).map(function (n) {
      return { text: n.full_name, score: (n.scores && n.scores.overall) || 0 }
    })
    record.title = (params.surname || '') + ' · ' + genderText(params.gender) +
      ' · ' + (params.name_length === 1 ? '单字名' : '双字名')
    const style = styleText(params.style)
    record.subtitle = '共 ' + names.length + ' 个候选' + (style ? ' · ' + style : '')
  } else if (kind === 'prenatal') {
    const stable = (result && result.suggestion && result.suggestion.stable_wuxing) || []
    const safeChars = (result && result.suggestion && result.suggestion.safe_chars) || []
    record.chips = safeChars.slice(0, 10).map(function (c) {
      return { text: c, score: 0 }
    })
    record.title = (params.surname || '') + ' · 预产期 ' + (params.due_date || '未设置')
    record.subtitle = '浮动 ±' + (params.range_days || 0) + ' 天' +
      (stable.length ? ' · 稳定五行 ' + stable.join('、') : '')
  } else {
    const score = (result && result.phonetics && result.phonetics.score) || 0
    record.title = (result && result.full_name) || (params.full_name || '')
    record.subtitle = '音律 ' + score + ' 分'
  }

  return record
}

/**
 * 新增一条记录（最新的排最前，超出上限丢最旧）。
 * @returns {{ok: boolean, record?: object, error?: string}}
 */
function addRecord(record) {
  if (!record || !record.id) {
    return { ok: false, error: '记录内容为空，未保存' }
  }
  const list = [record].concat(readList(RECORD_KEY).filter(function (r) {
    return r.id !== record.id
  }))
  const res = writeList(RECORD_KEY, trim(list, RECORD_LIMIT, RECORD_MAX_BYTES))
  return Object.assign({ record: record }, res)
}

function listRecords() {
  return readList(RECORD_KEY).map(function (r) {
    return Object.assign({}, r, { createdText: formatTime(r.createdAt) })
  })
}

function getRecord(id) {
  const list = readList(RECORD_KEY)
  for (let i = 0; i < list.length; i++) {
    if (list[i].id === id) return list[i]
  }
  return null
}

function removeRecord(id) {
  const list = readList(RECORD_KEY).filter(function (r) {
    return r.id !== id
  })
  return writeList(RECORD_KEY, list)
}

function clearRecords() {
  return removeKey(RECORD_KEY)
}

// --------------------------------------------------------------------------- //
// 收藏（单个名字）
// --------------------------------------------------------------------------- //

function favIdOf(name) {
  return (name && name.full_name) || ''
}

/**
 * 收藏 / 取消收藏。同一个名字只留一条（按全名去重）。
 * @param {object} name   候选名对象（整份存下来，详情页要用到用字/出处/五格）
 * @param {object} [params] 该批请求参数（详情页的深度寓意要用）
 * @param {number} [batchId] 起名批次（对应深度寓意的解锁状态）
 * @returns {{ok: boolean, added?: boolean, error?: string}}
 */
function toggleFav(name, params, batchId) {
  const id = favIdOf(name)
  if (!id) {
    return { ok: false, error: '这个名字缺少姓名，无法收藏' }
  }

  const list = readList(FAV_KEY)
  let index = -1
  for (let i = 0; i < list.length; i++) {
    if (list[i].id === id) {
      index = i
      break
    }
  }

  // 已收藏 → 取消
  if (index >= 0) {
    list.splice(index, 1)
    const removed = writeList(FAV_KEY, list)
    return Object.assign({ added: false }, removed)
  }

  const entry = {
    id: id,
    savedAt: Date.now(),
    savedText: formatTime(Date.now()),
    full_name: id,
    given_name: (name && name.given_name) || '',
    pinyinText: pinyinOf(name),
    overall: (name && name.scores && name.scores.overall) || 0,
    source: (name && name.poetry && name.poetry.source) || '',
    title: (name && name.poetry && name.poetry.title) || '',
    batchId: batchId || 0,
    params: params || {},
    // 整份候选名对象：详情页的用字解析 / 出处 / 五格 / 语境义项都靠它
    data: name
  }

  const added = writeList(FAV_KEY, trim([entry].concat(list), FAV_LIMIT, FAV_MAX_BYTES))
  return Object.assign({ added: true }, added)
}

function listFavs() {
  return readList(FAV_KEY)
}

/** 供列表页/结果页做「是否已收藏」判定：返回 { 全名: true } 映射 */
function favMap() {
  const map = {}
  readList(FAV_KEY).forEach(function (f) {
    map[f.id] = true
  })
  return map
}

function isFav(fullName) {
  return !!favMap()[fullName]
}

function removeFav(id) {
  const list = readList(FAV_KEY).filter(function (f) {
    return f.id !== id
  })
  return writeList(FAV_KEY, list)
}

function clearFavs() {
  return removeKey(FAV_KEY)
}

module.exports = {
  RECORD_LIMIT,
  FAV_LIMIT,
  KIND_LABEL,
  formatTime,
  pinyinOf,
  buildRecord,
  addRecord,
  listRecords,
  getRecord,
  removeRecord,
  clearRecords,
  toggleFav,
  listFavs,
  favMap,
  isFav,
  removeFav,
  clearFavs
}
