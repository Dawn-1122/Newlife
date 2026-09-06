/**
 * 网络请求工具 + 前端枚举镜像
 *
 * 枚举单一事实来源在后端 app/core/naming_options.py，
 * 小程序无共享包，需在此手工同步，改动时两处一起改。
 */

// 风格枚举（与后端 STYLE_OPTIONS 镜像）
const STYLE_OPTIONS = [
  { code: 'classic', name: '古风雅致' },
  { code: 'modern', name: '现代简约' },
  { code: 'grand', name: '大气沉稳' },
  { code: 'fresh', name: '清新灵动' },
  { code: 'warm', name: '温润内敛' },
  { code: 'elegant', name: '清朗俊逸' },
  { code: 'plain', name: '质朴厚重' },
  { code: 'zen', name: '空灵禅意' }
]

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

// 风格卡（wizard Step1 展示，用意象描述代替示例名，避免示例名引导用户判断）
const STYLE_EXAMPLES = [
  { code: 'classic', name: '古风雅致', feeling: '温润如玉，字句皆有出处', imagery: '雅正 · 清贵 · 有古意' },
  { code: 'modern', name: '现代简约', feeling: '朗朗上口，简约不简单', imagery: '明快 · 自然 · 易读易写' },
  { code: 'grand', name: '大气沉稳', feeling: '格局开阔，气度不凡', imagery: '壮阔 · 恢弘 · 家国山河' },
  { code: 'fresh', name: '清新灵动', feeling: '山水草木，轻盈自然', imagery: '清新 · 生机 · 春意盎然' },
  { code: 'warm', name: '温润内敛', feeling: '温厚含蓄，不事张扬', imagery: '温润 · 敦厚 · 谦和内敛' },
  { code: 'elegant', name: '清朗俊逸', feeling: '清俊飘逸，气象开阔', imagery: '清朗 · 俊逸 · 洒脱旷达' },
  { code: 'plain', name: '质朴厚重', feeling: '朴实厚重，踏实可靠', imagery: '质朴 · 醇厚 · 深沉稳重' },
  { code: 'zen', name: '空灵禅意', feeling: '空灵留白，意境幽远', imagery: '空灵 · 超然 · 静谧悠远' }
]

// 寓意卡（wizard Step2 展示，12 个寓意，用意象描述代替示例名）
const MEANING_EXAMPLES = [
  { code: 'wisdom', name: '智慧', feeling: '聪慧明达，才思敏捷', imagery: '求索 · 通达 · 明理' },
  { code: 'health', name: '健康', feeling: '身强体健，茁壮成长', imagery: '生机 · 长寿 · 康健' },
  { code: 'bravery', name: '勇敢', feeling: '勇毅果敢，无畏前行', imagery: '坚韧 · 进取 · 担当' },
  { code: 'gentle', name: '温婉', feeling: '温柔娴静，婉约有礼', imagery: '娴静 · 清雅 · 柔美' },
  { code: 'wealth', name: '富贵', feeling: '丰裕富足，前程似锦', imagery: '祥瑞 · 华贵 · 锦绣' },
  { code: 'peace', name: '平安', feeling: '安宁顺遂，岁月静好', imagery: '祥和 · 安定 · 顺遂' },
  { code: 'talent', name: '才华', feeling: '才华横溢，文采斐然', imagery: '文采 · 卓越 · 出众' },
  { code: 'virtue', name: '品德', feeling: '德才兼备，品行高洁', imagery: '君子 · 高洁 · 仁德' },
  { code: 'beauty', name: '美丽', feeling: '清丽俊秀，如玉温润', imagery: '美玉 · 芬芳 · 清丽' },
  { code: 'loyal', name: '忠义', feeling: '忠诚赤诚，坚贞不移', imagery: '忠贞 · 节操 · 信义' },
  { code: 'patriotic', name: '家国', feeling: '胸怀天下，济世安邦', imagery: '壮志 · 济世 · 凌云' },
  { code: 'tranquil', name: '宁静', feeling: '淡泊安然，宁静致远', imagery: '淡泊 · 超然 · 悠然' }
]

// 预产期浮动档位（与后端 RANGE_OPTIONS 镜像）
const RANGE_OPTIONS = [0, 3, 7, 14]
const DEFAULT_RANGE_DAYS = 7
const MEANING_MAX_SELECT = 3

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
  MEANING_OPTIONS,
  STYLE_EXAMPLES,
  MEANING_EXAMPLES,
  RANGE_OPTIONS,
  DEFAULT_RANGE_DAYS,
  MEANING_MAX_SELECT
}
