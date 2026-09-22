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

// （旧版 STYLE_EXAMPLES / MEANING_EXAMPLES 已删除：起名偏好由单一 FEELING_CARDS 承载，
//   两套面向用户的意象文案并存会互相漂移。）

// 起名「感觉」卡（起名第二步的唯一选择，展示层概念，不新增后端枚举）
//
// 设计意图：用户不想先回答「寓意优先还是八字优先」这类算法口径问题，
// 只想挑一种「感觉」。故把后端两个既有偏好维度合成一张卡：
//   1 个 style（单选）+ 2 个 meanings（多选，上限 3）
// 两者都是 NamingRequest / PrenatalRequest 的既有入参，无需改后端。
// 每张卡保持「一卡一风格」的一对一映射，确保偏好能真正硬分流选池，
// 而不是只做 tie-break（那样选不选结果都一样）。
// 新增/调整卡时务必核对 code 同时存在于 STYLE_OPTIONS 与 MEANING_OPTIONS。
const FEELING_CARDS = [
  { code: 'classic', title: '古意', imagery: '典正清贵，字有来历', style: 'classic', meanings: ['virtue', 'talent'] },
  { code: 'elegant', title: '清朗', imagery: '明净开阔，如秋长空', style: 'elegant', meanings: ['talent', 'wisdom'] },
  { code: 'warm', title: '温润', imagery: '温厚含蓄，如玉在怀', style: 'warm', meanings: ['virtue', 'gentle'] },
  { code: 'zen', title: '空灵', imagery: '疏朗留白，意远境幽', style: 'zen', meanings: ['tranquil', 'peace'] },
  { code: 'fresh', title: '明媚', imagery: '草木山川，轻盈明净', style: 'fresh', meanings: ['beauty', 'health'] },
  { code: 'grand', title: '峻拔', imagery: '格局开阔，气象不凡', style: 'grand', meanings: ['bravery', 'patriotic'] },
  { code: 'plain', title: '静笃', imagery: '质朴醇厚，沉静踏实', style: 'plain', meanings: ['peace', 'virtue'] },
  { code: 'modern', title: '简约', imagery: '明快自然，清简不繁', style: 'modern', meanings: ['wisdom', 'peace'] }
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
  recommendSources,
  sourceChars,
  nameMeaning,
  queryBazi,
  STYLE_OPTIONS,
  SOURCE_STYLE_MAP,
  getStyleCodes,
  MEANING_OPTIONS,
  FEELING_CARDS,
  RANGE_OPTIONS,
  DEFAULT_RANGE_DAYS
}
