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
  RANGE_OPTIONS,
  DEFAULT_RANGE_DAYS,
  MEANING_MAX_SELECT
}
