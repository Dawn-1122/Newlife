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
  { code: 'fresh', name: '清新灵动' }
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
  { code: 'virtue', name: '品德' }
]

// 风格示例卡（wizard Step1 展示，示例名带出处）
const STYLE_EXAMPLES = [
  {
    code: 'classic',
    name: '古风雅致',
    feeling: '温润如玉，字句皆有出处',
    examples: [
      { name: '修远', source: '离骚' },
      { name: '清扬', source: '野有蔓草' },
      { name: '灼华', source: '桃夭' }
    ]
  },
  {
    code: 'modern',
    name: '现代简约',
    feeling: '朗朗上口，简约不简单',
    examples: [
      { name: '云帆', source: '行路难' },
      { name: '晴川', source: '黄鹤楼' },
      { name: '星河', source: '渔家傲' }
    ]
  },
  {
    code: 'grand',
    name: '大气沉稳',
    feeling: '格局开阔，气度不凡',
    examples: [
      { name: '行健', source: '周易乾卦' },
      { name: '厚德', source: '周易坤卦' },
      { name: '星汉', source: '观沧海' }
    ]
  },
  {
    code: 'fresh',
    name: '清新灵动',
    feeling: '山水草木，轻盈自然',
    examples: [
      { name: '清露', source: '野有蔓草' },
      { name: '采薇', source: '小雅采薇' },
      { name: '初晴', source: '' }
    ]
  }
]

// 寓意示例卡（wizard Step2 展示，8 个寓意，每个配一句感受 + 2 个示例名）
const MEANING_EXAMPLES = [
  { code: 'wisdom', name: '智慧', feeling: '聪慧明达，才思敏捷', examples: ['知新', '思博'] },
  { code: 'health', name: '健康', feeling: '身强体健，茁壮成长', examples: ['康宁', '松年'] },
  { code: 'bravery', name: '勇敢', feeling: '勇毅果敢，无畏前行', examples: ['毅然', '勇毅'] },
  { code: 'gentle', name: '温婉', feeling: '温柔娴静，婉约有礼', examples: ['婉清', '静姝'] },
  { code: 'wealth', name: '富贵', feeling: '丰裕富足，前程似锦', examples: ['瑞丰', '景盛'] },
  { code: 'peace', name: '平安', feeling: '安宁顺遂，岁月静好', examples: ['安和', '静安'] },
  { code: 'talent', name: '才华', feeling: '才华横溢，文采斐然', examples: ['文采', '景行'] },
  { code: 'virtue', name: '品德', feeling: '德才兼备，品行高洁', examples: ['明德', '怀瑾'] }
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
  queryBazi,
  STYLE_OPTIONS,
  MEANING_OPTIONS,
  STYLE_EXAMPLES,
  MEANING_EXAMPLES,
  RANGE_OPTIONS,
  DEFAULT_RANGE_DAYS,
  MEANING_MAX_SELECT
}
