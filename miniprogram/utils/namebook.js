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
 *    实测一次起名返回约 39KB（20 个候选）。同一次起名翻多批**合并成一条**
 *    （见 `paramsKey` / `mergeInto`），不按批次叠记录；整体再由「条数 + 字节数」
 *    双上限兜住，超出时丢最旧的，并把 `dropped` 回传给页面 —— 不再静默丢弃。
 *    字节数按 UTF-8 实算，中文按 3 字节计。
 * 3. **写失败不静默。** 存储写满时 `wx.setStorageSync` 会抛错，
 *    本模块一律捕获并返回 `{ ok: false, error }`，由页面弹提示 —— 不能装作存上了。
 */

// 存储键带版本号：将来结构变了就升版本，旧数据自然失效，不必写迁移逻辑
const RECORD_KEY = 'mt_records_v1'
const FAV_KEY = 'mt_favs_v1'

// 保留上限
//
// RECORD_LIMIT 从 10 提到 20，配合下面的「按参数合并」：
// 一次起名翻 5 批只占 1 条记录，20 条才够装下不同条件的多次起名。
// 总字节仍由 RECORD_MAX_BYTES 兜住（单 key ≤ 1MB 是微信硬限）。
const RECORD_LIMIT = 20
const FAV_LIMIT = 60 // 单名 ≈ 1.8KB，60 个 ≈ 110KB
const RECORD_MAX_BYTES = 620 * 1024
const FAV_MAX_BYTES = 200 * 1024

// 合并后的单条记录最多留多少候选名（约 6 批 × 20）。
// 再往后就丢最旧批次的名字 —— 否则「同一次起名」可以无限翻，把单条记录撑到超限。
const MERGE_MAX_NAMES = 120

// 参与「同一次起名」判定的参数：这些键不同就是不同的起名，不能合并
// exclude_names 是「换一批」的排除名单，每批都不一样，必须排除在指纹之外
const KEY_IGNORE = { exclude_names: true }


// 记录类型 → 展示名（历史列表用）
const KIND_LABEL = {
  postnatal: '起名',
  prenatal: '孕期参考',
  analyze: '释名'
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
//
// 返回 dropped 是重点：早期版本这里静默 pop，用户翻了十几批之后最早的记录
// 无声无息消失，也不知道什么时候没的。调用方拿 dropped 才能说一句
// 「名字本已满，最早的 N 条已清理」。
function trim(list, limit, maxBytes) {
  const kept = list.slice(0, limit)
  let dropped = list.length - kept.length
  while (kept.length > 1 && byteLen(JSON.stringify(kept)) > maxBytes) {
    kept.pop()
    dropped++
  }
  return { kept: kept, dropped: dropped }
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
// 记录（一次起名 = 一条，多批合并）
// --------------------------------------------------------------------------- //

/**
 * 参数指纹：判断两次结果是否属于「同一次起名」。
 *
 * 起名是「提交条件 → 拿到一批名字 → 换一批 → 再换一批」的循环，
 * 换一批并不改变条件。早期版本每批都写一条新记录，于是同一次起名翻 10 批
 * 就把 RECORD_LIMIT 占满，把孕期参考、释名、别的条件的起名统统挤掉 ——
 * 用户看到的只是「上次那批名字不见了」。
 *
 * 指纹按「键名排序 + 值」拼串，数组排序后拼，保证同样条件得到同样的串。
 * exclude_names（换一批的排除名单）每批都不同，必须排除在指纹之外。
 */
function paramsKey(kind, params) {
  const p = params || {}
  const parts = []
  Object.keys(p).sort().forEach(function (k) {
    if (KEY_IGNORE[k]) return
    let v = p[k]
    if (v === undefined || v === null || v === '') return
    if (Array.isArray(v)) v = v.slice().sort().join(',')
    parts.push(k + '=' + String(v))
  })
  return kind + '|' + parts.join('&')
}

/**
 * 从 {五行: 0~1} 里取占比最高的 n 项，拼成「木 33%、火 27%」这样的串。
 * 只做降序取数，不判断好坏 —— 孕期记录只描述分布。
 */
function topWuxingText(dist, n) {
  const list = Object.keys(dist || {}).map(function (k) {
    return { name: k, pct: Math.round((dist[k] || 0) * 100) }
  })
  list.sort(function (a, b) { return b.pct - a.pct })
  return list.slice(0, n)
    .filter(function (it) { return it.pct > 0 })
    .map(function (it) { return it.name + ' ' + it.pct + '%' })
    .join('、')
}

/**
 * 由 payload / params 算出列表要显示的标题、副标题、候选名摘要。
 * 合并之后要按合并结果重算，所以拆成独立函数而不是塞在 buildRecord 里。
 */
function describeRecord(record) {
  const kind = record.kind
  const params = record.params || {}
  const result = record.payload || {}
  const batches = record.batches || 1

  record.chips = []

  if (kind === 'postnatal') {
    const names = result.names || []
    // 只留前 8 个进列表摘要，整份结果仍完整存在 payload 里
    record.chips = names.slice(0, 8).map(function (n) {
      return { text: n.full_name, score: (n.scores && n.scores.overall) || 0 }
    })
    record.title = (params.surname || '') + ' · ' + genderText(params.gender) +
      ' · ' + (params.name_length === 1 ? '单字名' : '双字名')
    const style = styleText(params.style)
    record.subtitle = '共 ' + names.length + ' 个候选' +
      (batches > 1 ? ' · 翻 ' + batches + ' 批' : '') +
      (style ? ' · ' + style : '')
  } else if (kind === 'prenatal') {
    // 合规口径：孕期只出历法统计，不出建议。所以这里也不再拼「稳定五行 / 候选字」，
    // 改成把日柱天干五行里占比最高的两项写进副标题（纯计数，不做判断）。
    const dist = (result.probabilistic && result.probabilistic.day_master_wuxing_dist) || {}
    const top = topWuxingText(dist, 2)
    record.title = (params.surname || '') + ' · 预产期 ' + (params.due_date || '未设置')
    record.subtitle = '浮动 ±' + (params.range_days || 0) + ' 天' +
      (batches > 1 ? ' · 存 ' + batches + ' 次' : '') +
      (top ? ' · 日柱五行 ' + top : '')
  } else {
    const score = (result.phonetics && result.phonetics.score) || 0
    record.title = result.full_name || params.full_name || ''
    record.subtitle = '音律 ' + score + ' 分' +
      (batches > 1 ? ' · 查 ' + batches + ' 次' : '')
  }

  return record
}

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
    key: paramsKey(kind, params),
    createdAt: Date.now(),
    updatedAt: Date.now(),
    batches: 1,
    params: params || {},
    batchId: batchId || 0,
    payload: result
  }

  return describeRecord(record)
}

// 按 id 去重合并（前者优先，用于「新一批在前、旧批次在后」）
function unionBy(first, second, idOf) {
  const seen = {}
  const out = []
  first.concat(second).forEach(function (item) {
    const id = idOf(item)
    if (!id || seen[id]) return
    seen[id] = true
    out.push(item)
  })
  return out
}

/**
 * 把新一批并进旧记录。
 *
 * 为什么留 union 而不是只留最新一批：名字本的用途是「回头还能找到那个名字」，
 * 只留最新一批等于前几批的名字虽然存了却点不进去 —— 从列表点开恢复上下文时，
 * 结果页只认 payload。合并后 payload.names 是全量，点进去能看到这次起名的所有名字，
 * 「换一批」的排除名单也自然是全量，不会把翻过的名字再抽回来。
 */
function mergeInto(old, incoming) {
  const out = Object.assign({}, old)
  out.updatedAt = Date.now()
  out.batches = (old.batches || 1) + 1
  // 批次号跟最新一批走：深度寓意的解锁键按批次存，恢复时要对得上最后一批
  out.batchId = incoming.batchId || old.batchId
  // 同指纹下参数应完全一致，取新的更稳妥（旧记录可能是更早版本的字段集）
  out.params = incoming.params || old.params

  if (incoming.kind === 'postnatal') {
    const prevNames = (old.payload && old.payload.names) || []
    const nextNames = (incoming.payload && incoming.payload.names) || []
    const names = unionBy(nextNames, prevNames, function (n) {
      return n && n.full_name
    })
    // 八字 / 喜用神同参数下一致，以最新一批为底；候选换成累计去重后的列表
    out.payload = Object.assign({}, incoming.payload, {
      names: names.slice(0, MERGE_MAX_NAMES)
    })
  } else if (incoming.kind === 'prenatal') {
    // 孕期参考只出历法统计，同一组参数算出来的结果必然一样，没有可累加的东西
    // （早期这里合并过 safe_chars 候选字，合规收敛后建议能力已下线）。
    out.payload = incoming.payload
  } else {
    // 释名：同一个名字重复查，结论不变，只记次数
    out.payload = incoming.payload
  }

  return describeRecord(out)
}

/**
 * 新增一条记录。同一次起名（参数指纹相同）翻多批时合并进原记录，不新增一条。
 *
 * @returns {{ok: boolean, record?: object, merged?: boolean, dropped?: number, error?: string}}
 *   dropped = 本次因为超出上限被清掉的旧记录条数（早期版本静默丢弃，用户不知情）
 */
function addRecord(record) {
  if (!record || !record.id) {
    return { ok: false, error: '记录内容为空，未保存' }
  }

  const key = record.key || paramsKey(record.kind, record.params)
  record.key = key

  const prev = readList(RECORD_KEY)
  const rest = []
  let old = null
  prev.forEach(function (r) {
    if (!old && r.key === key) {
      old = r
    } else {
      rest.push(r)
    }
  })

  const next = old ? mergeInto(old, record) : record
  const trimmed = trim([next].concat(rest), RECORD_LIMIT, RECORD_MAX_BYTES)
  const res = writeList(RECORD_KEY, trimmed.kept)

  return Object.assign({
    record: next,
    merged: !!old,
    dropped: trimmed.dropped
  }, res)
}


function listRecords() {
  return readList(RECORD_KEY).map(function (r) {
    return Object.assign({}, r, { createdText: formatTime(r.createdAt) })
  })
}

/**
 * 把 addRecord 的结果翻译成给用户的提示（写失败 / 清理了旧记录）。
 *
 * 「记录被清理」这件事只在这里说一次：三个调用点各写一套迟早会漂移，
 * 而静默丢记录正是这次要修的问题，不能留着任何一条路径不说。
 *
 * @returns {boolean} 是否弹出了提示（调用方据此决定要不要再弹自己的成功提示）
 */
function notifySave(ret) {
  if (!ret) return false
  if (!ret.ok) {
    wx.showToast({ title: ret.error || '保存失败', icon: 'none' })
    return true
  }
  if (ret.dropped > 0) {
    wx.showToast({
      title: '名字本已满，清理了 ' + ret.dropped + ' 条最早记录',
      icon: 'none',
      duration: 2600
    })
    return true
  }
  return false
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

  const trimmed = trim([entry].concat(list), FAV_LIMIT, FAV_MAX_BYTES)
  const added = writeList(FAV_KEY, trimmed.kept)
  return Object.assign({ added: true, dropped: trimmed.dropped }, added)
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
  MERGE_MAX_NAMES,
  KIND_LABEL,
  formatTime,
  pinyinOf,
  paramsKey,
  buildRecord,
  addRecord,
  notifySave,
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
