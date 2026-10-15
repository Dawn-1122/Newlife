/**
 * 网络请求工具 + 前端枚举镜像
 *
 * 枚举单一事实来源在后端 app/core/naming_options.py，
 * 小程序无共享包，需在此手工同步，改动时两处一起改。
 */

// 风格枚举（与后端 STYLE_OPTIONS 镜像；sources 对应后端 source_preference）
// short 用于结果页筛选条（2 字，避免 8 个筛选项挤出屏幕）
const STYLE_OPTIONS = [
  { code: 'classic', name: '古风雅致', short: '古风', sources: ['诗经', '楚辞', '汉魏古诗', '五代词'] },
  { code: 'modern', name: '现代简约', short: '现代', sources: ['唐诗', '宋词'] },
  { code: 'grand', name: '大气沉稳', short: '大气', sources: ['经史子集', '汉魏古诗'] },
  { code: 'fresh', name: '清新灵动', short: '清新', sources: ['诗经', '唐诗'] },
  { code: 'warm', name: '温润内敛', short: '温润', sources: ['诗经', '经史子集', '五代词', '清词'] },
  { code: 'elegant', name: '清朗俊逸', short: '清朗', sources: ['唐诗', '宋词', '五代词', '清词'] },
  { code: 'plain', name: '质朴厚重', short: '质朴', sources: ['经史子集', '汉魏古诗'] },
  { code: 'zen', name: '空灵禅意', short: '空灵', sources: ['唐诗', '宋词', '清词'] }
]

// 出处 → 风格 codes 反向映射（由 STYLE_OPTIONS.sources 派生，勿手工维护）
// 重要：这是一对多映射 —— 同一条出处可属于多个风格
//（如「唐诗」同时属于 现代简约/清新灵动/清朗俊逸/空灵禅意）；
// 因此结果页的风格筛选必须用「命中任一」判定，不能用单值归类。
const SOURCE_STYLE_MAP = (function () {
  const map = {}
  STYLE_OPTIONS.forEach(function (opt) {
    (opt.sources || []).forEach(function (source) {
      if (!map[source]) map[source] = []
      map[source].push(opt.code)
    })
  })
  return map
})()

// 取一条出处命中的全部风格 codes（无出处或出处不在映射内时返回空数组）
function getStyleCodes(source) {
  return SOURCE_STYLE_MAP[source] || []
}

// 寓意枚举（与后端 MEANING_OPTIONS 镜像）
const MEANING_OPTIONS = [
  { code: 'wisdom', name: '智慧' },
  { code: 'health', name: '健康' },
  { code: 'bravery', name: '勇敢' },
  { code: 'gentle', name: '温婉' },
  { code: 'wealth', name: '富贵' },
  { code: 'peace', name: '平安' },
  { code: 'talent', name: '才华' },
  { code: 'virtue', name: '品德' },
  { code: 'beauty', name: '美丽' },
  { code: 'loyal', name: '忠义' },
  { code: 'patriotic', name: '家国' },
  { code: 'tranquil', name: '宁静' }
]

// ── 偏好选择（27 个标签 = 气质 8 + 期待 12 + 意象 7）──
//
// 设计意图：用户不想先回答「寓意优先还是八字优先」这类算法口径问题，
// 只想从一片标签里挑出自己要的那几个感觉——像 B 站/小红书的兴趣画像一样。
//
// 三个维度的**作用域各不相同**，不要混着理解：
//   气质（STYLE_OPTIONS，单选）  → 后端 style 参数：来源偏好 + 意象关键词 + 选字倾向
//   期待（MEANING_OPTIONS，≤3）  → 后端 meanings 参数：选字硬前置 + 排序
//   意象（IMAGERY_FAMILIES，≤2） → **只影响「先字」字表的排序**（见下）
//
// 旧版「感觉卡」FEELING_CARDS（1 风格 + 2 寓意打包成 8 张卡）已废除：
// 它把气质与期待绑死成一对一，用户想「温润 + 勇敢」时无路可走。

// 寓意/期待最多选几个（与后端 MEANING_MAX_SELECT 镜像）
const MEANING_MAX_SELECT = 3

// 字形意象族（与后端 IMAGERY_FAMILY_PRIORITY / FILTERABLE_IMAGERY_FAMILIES 镜像）
//
// 作用域：给「先字」字表排序与筛选——**不作硬分区**。
// 实测 7 族只覆盖候选池约 35%（金族全池仅 4 字，女性向 2 字），硬过滤会砍掉
// 65% 的好字（诗/思/安/宜 这类无族属字），所以它们不做后台硬筛选，
// 只做两件事：① 偏好页点选后，把该族的字排到字表最前；② 字表页手动按族看。
// radicals 是**去重后的有效部首**——「日」同时属于火与日月星辰，按优先级归日月星辰，
// 故火族不再列「日」（否则用户会问「我选了火怎么没有星」）。
const IMAGERY_FAMILIES = [
  { code: '日月星辰', name: '日月星辰', radicals: '日 月 星' },
  { code: '草木', name: '草木', radicals: '木 艹 艸 禾 竹' },
  { code: '水', name: '水', radicals: '水 氵 雨' },
  { code: '玉', name: '玉', radicals: '玉 王 石' },
  { code: '金', name: '金', radicals: '金 钅 釒' },
  { code: '火', name: '火', radicals: '火 灬' },
  { code: '土', name: '土', radicals: '土 山 田' }
]

// 意象族最多选几个（与后端 IMAGERY_MAX_SELECT 镜像）
const IMAGERY_MAX_SELECT = 2

// 出处类目（与后端 SOURCE_CLASSES 镜像）——「先出处后字」路径的 8 个选项，
// 也是 /generate 的 source_classes 合法取值。字源 4 部典籍（周易/山海经/
// 本草纲目/神农本草经）归入「经史子集」，选它会一并纳入。
const SOURCE_CLASSES = [
  '诗经', '楚辞', '汉魏古诗', '唐诗', '五代词', '宋词', '清词', '经史子集'
]

// 预产期浮动档位（与后端 RANGE_OPTIONS 镜像）
const RANGE_OPTIONS = [0, 3, 7, 14]
const DEFAULT_RANGE_DAYS = 7

function request(url, method = 'GET', data = {}) {
  const app = getApp()
  return new Promise((resolve, reject) => {
    wx.request({
      url: app.globalData.apiBase + url,
      method: method,
      data: data,
      header: {
        'Content-Type': 'application/json'
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          reject(res.data || { message: '请求失败' })
        }
      },
      fail(err) {
        reject({ message: '网络错误，请检查网络连接' })
      }
    })
  })
}

/**
 * 生成名字（产后精确起名）
 */
function generateNames(params) {
  return request('/generate', 'POST', params)
}

/**
 * 预产期起名（孕期范围参考）
 */
function prenatal(params) {
  return request('/prenatal', 'POST', params)
}

/**
 * 解析名字（名字测评）
 */
function analyzeName(params) {
  return request('/analyze', 'POST', params)
}

/**
 * 两阶段第一步：推荐选字范围（按五行分组，喜用神优先）
 */
function recommendChars(params) {
  return request('/recommend-chars', 'POST', params)
}

/**
 * 「先字后出处」第一步：可选字表
 *
 * 返回**真的组得出名字**的字（后端已算过门槛），不是字库铺满的候选。
 * 字表与姓氏强相关（姓「林」时名字两字全平触发三连同调，整类字全灭），
 * 故必须每次带 surname 请求，不要在前端缓存跨姓氏复用。
 */
function pickableChars(params) {
  return request('/pickable-chars', 'POST', params)
}

/**
 * 两模式流程第一步：推荐意境来源（寓意优先 / 命格优先）
 */
function recommendSources(params) {
  return request('/recommend-sources', 'POST', params)
}

/**
 * 两模式流程第二步：在选定来源内按八字喜用神推荐字
 */
function sourceChars(params) {
  return request('/source-chars', 'POST', params)
}

/**
 * 名字深度寓意（详情页懒加载，多层余味）
 */
function nameMeaning(params) {
  return request('/name/meaning', 'POST', params)
}

/**
 * 查询八字
 */
function queryBazi(params) {
  const query = Object.keys(params)
    .filter(k => params[k] !== null && params[k] !== undefined)
    .map(k => `${k}=${encodeURIComponent(params[k])}`)
    .join('&')
  return request('/bazi?' + query)
}

module.exports = {
  request,
  generateNames,
  prenatal,
  analyzeName,
  recommendChars,
  pickableChars,
  recommendSources,
  sourceChars,
  nameMeaning,
  queryBazi,
  STYLE_OPTIONS,
  SOURCE_STYLE_MAP,
  getStyleCodes,
  MEANING_OPTIONS,
  MEANING_MAX_SELECT,
  IMAGERY_FAMILIES,
  IMAGERY_MAX_SELECT,
  SOURCE_CLASSES,
  RANGE_OPTIONS,
  DEFAULT_RANGE_DAYS
}
