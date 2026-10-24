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

// 寓意枚举（与后端 MEANING_OPTIONS 镜像；code + name + group）
// name 是给用户看的标签（贴近父母话术，非字典词）；group 归入 MEANING_GROUPS 的期许方向。
const MEANING_OPTIONS = [
  { code: 'wisdom', name: '聪慧睿智', group: 'intellect' },
  { code: 'health', name: '健康长寿', group: 'wellbeing' },
  { code: 'bravery', name: '坚毅勇敢', group: 'fortitude' },
  { code: 'gentle', name: '温婉娴静', group: 'temperament' },
  { code: 'wealth', name: '富贵荣华', group: 'achievement' },
  { code: 'peace', name: '平安康泰', group: 'wellbeing' },
  { code: 'talent', name: '才情出众', group: 'intellect' },
  { code: 'virtue', name: '仁厚善良', group: 'character' },
  { code: 'beauty', name: '俊美清雅', group: 'temperament' },
  { code: 'loyal', name: '忠义赤诚', group: 'character' },
  { code: 'patriotic', name: '志向远大', group: 'achievement' },
  { code: 'tranquil', name: '宁静致远', group: 'mindset' },
  { code: 'resilient', name: '坚韧不拔', group: 'fortitude' },
  { code: 'optimistic', name: '乐观豁达', group: 'mindset' }
]

// 期许方向（分组）：与后端 MEANING_GROUPS 镜像。前端按此顺序分块渲染：
// 每块 = 一句人话（subtitle）+ 该组下的寓意标签，像小红书画像一样点选。
const MEANING_GROUPS = [
  { code: 'character', title: '品行', subtitle: '正直善良，心存仁厚' },
  { code: 'intellect', title: '才识', subtitle: '聪慧灵秀，才情出众' },
  { code: 'wellbeing', title: '康宁', subtitle: '平安健康，顺遂无忧' },
  { code: 'achievement', title: '前程', subtitle: '志向远大，前程似锦' },
  { code: 'temperament', title: '性情', subtitle: '温润得体，仪态大方' },
  { code: 'fortitude', title: '风骨', subtitle: '坚毅有担当，扛得住事' },
  { code: 'mindset', title: '心境', subtitle: '豁达从容，想得开' }
]

// ── 偏好选择（气质 8 + 期许 14）──
//
// 设计意图：用户不想先回答「寓意优先还是八字优先」这类算法口径问题，
// 只想从一片标签里挑出自己要的那几个感觉——像 B 站/小红书的兴趣画像一样。
//
// 两个维度的**作用域各不相同**，不要混着理解：
//   气质（STYLE_OPTIONS，单选）  → 后端 style 参数：来源偏好 + 意象关键词 + 选字倾向
//   期许（MEANING_OPTIONS，≤3）  → 后端 meanings 参数：选字硬前置 + 排序，按 MEANING_GROUPS 分块
//
// 意象（字形部首族：草木/水/玉/金…）**不再作为用户输入**：它是名字被读出来之后
// 用户「感受到」的画面与余味，属于产出侧——挂在字卡与名字详情上展示，不让父母
// 一开始就去勾「我要草木字」（没人会这么想）。后端仍会返回每个字的 family 标签。
//
// 旧版「感觉卡」FEELING_CARDS（1 风格 + 2 寓意打包成 8 张卡）已废除：
// 它把气质与期待绑死成一对一，用户想「温润 + 勇敢」时无路可走。

// 期许最多选几个（与后端 MEANING_MAX_SELECT 镜像）
const MEANING_MAX_SELECT = 3

// 出处类目（与后端 SOURCE_CLASSES 镜像）——「先出处后字」路径的 8 个选项，
// 也是 /generate 的 source_classes 合法取值。字源 4 部典籍（周易/山海经/
// 本草纲目/神农本草经）归入「经史子集」，选它会一并纳入。
const SOURCE_CLASSES = [
  '诗经', '楚辞', '汉魏古诗', '唐诗', '五代词', '宋词', '清词', '经史子集'
]

// 预产期浮动档位（与后端 RANGE_OPTIONS 镜像）
const RANGE_OPTIONS = [0, 3, 7, 14]
const DEFAULT_RANGE_DAYS = 7

// ── 后端基址解析 ──
//
// 预览（浏览器）、开发者工具、真机跑在三套不同的网络口径里，写死一个基址必然有场景连不上：
//   - 预览器在本机跑，后端就是 localhost:8000
//   - 真机必须走局域网 IP（手机与电脑同一 WiFi）
//   - 沙箱里 192.168.x.x 与 127.0.0.1 都可能不可达
// 故先探一次 /health，选第一个真的应答的，并记进本地缓存供下次先用。
//
// ⚠️ 探活不能只看状态码。这台机器上 127.0.0.1 会被代理拦成**空响应**，
//    状态码仍然是 200 —— 只看 200 就会错锁到它，之后每条业务请求都拿到空 body，
//    报出来的错和真实原因毫无关系。所以必须校验响应体里确实有 status: ok。
const API_LOCAL_BASE = 'http://localhost:8000/api/v1'
const API_LOOPBACK_BASES = [
  'http://127.0.0.1:8000/api/v1',
  'http://host.docker.internal:8000/api/v1'
]

// 单条候选的等待上限。wx.request 的 timeout 在部分宿主里不生效（预览器的
// fetch 替身就不带超时），被代理挂住的连接会一直不回来，故自己兜一层。
const API_PROBE_TIMEOUT = 1500

const API_BASE_CACHE_KEY = 'api_base'

let baseReady = null

function isHealthy(data) {
  return !!(data && data.status === 'ok')
}

function probeApiBase() {
  if (baseReady) return baseReady

  const app = getApp()
  const candidates = []
  const push = function (base) {
    if (base && candidates.indexOf(base) === -1) candidates.push(base)
  }
  push(wx.getStorageSync(API_BASE_CACHE_KEY))
  // localhost 排在配置值之前：预览环境里配置值已被预览器改写成 127.0.0.1，
  // 而真机上 localhost 会立刻被拒（不等超时），不会拖慢流程。
  push(API_LOCAL_BASE)
  push(app.globalData.apiBase)
  API_LOOPBACK_BASES.forEach(push)

  baseReady = new Promise(function (resolve) {
    let i = 0
    let settled = false
    let timer = null

    const finish = function (base) {
      if (settled) return
      settled = true
      if (timer) {
        clearTimeout(timer)
        timer = null
      }
      if (base) {
        app.globalData.apiBase = base
        try {
          wx.setStorageSync(API_BASE_CACHE_KEY, base)
        } catch (e) {
          // 存不下不影响本次使用
        }
        console.log('[api] 后端基址 = ' + base)
      }
      // 全都不通：保留配置值，让真正的业务请求去暴露具体错误
      resolve(app.globalData.apiBase)
    }

    const next = function () {
      if (timer) {
        clearTimeout(timer)
        timer = null
      }
      if (settled) return
      if (i >= candidates.length) {
        finish(null)
        return
      }
      const base = candidates[i++]
      timer = setTimeout(function () {
        timer = null
        next()
      }, API_PROBE_TIMEOUT)
      wx.request({
        url: base + '/health',
        method: 'GET',
        timeout: API_PROBE_TIMEOUT,
        success: function (res) {
          if (res.statusCode === 200 && isHealthy(res.data)) finish(base)
          else next()
        },
        fail: function () {
          next()
        }
      })
    }

    next()
  })

  return baseReady
}

function request(url, method = 'GET', data = {}) {
  const app = getApp()
  return probeApiBase().then(function () {
    return new Promise((resolve, reject) => {
      wx.request({
        url: app.globalData.apiBase + url,
        method: method,
        data: data,
        timeout: 30000,
        header: {
          'Content-Type': 'application/json'
        },
        success(res) {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(res.data)
          } else {
            const detail = res.data && (res.data.detail || res.data.message)
            reject({
              message: typeof detail === 'string' ? detail : '请求失败（' + res.statusCode + '）',
              statusCode: res.statusCode
            })
          }
        },
        fail(err) {
          // 预览器的 wx.request 替身把非 2xx 也走 fail，并带上 statusCode / data；
          // 真机则是 errMsg。两条都要能读出有用的原因，否则只剩一句「网络错误」。
          const code = err && err.statusCode
          if (code) {
            const detail = err.data && (err.data.detail || err.data.message)
            reject({
              message: typeof detail === 'string' ? detail : '请求失败（' + code + '）',
              statusCode: code
            })
            return
          }
          // 把平台给的 errMsg 原样透出：是「域名不在白名单」还是「连不上」，
          // 只有这条信息能区分，笼统的「网络错误」等于没说。
          const raw = (err && err.errMsg) || ''
          reject({
            message: raw ? '连接失败：' + raw : '连接失败：后端未启动或地址不通'
          })
        }
      })
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
 * 解析名字（释名）
 */
function analyzeName(params) {
  return request('/analyze', 'POST', params)
}

/**
 * 批量释名（测候选名 / 双名对比）
 *
 * 与 analyzeName 走后端同一条解析路径，同一个名字两处得分完全一致。
 * 单项不合法不会整批失败：非法项进 rejected 并带原因，其余照常返回。
 */
function analyzeBatch(params) {
  return request('/analyze/batch', 'POST', params)
}

/**
 * 创意起名（网名昵称 / 宠物 / 商业）
 *
 * kind 枚举与后端 CREATIVE_KINDS 镜像：
 *   platform 平台名称 / game 游戏昵称 / role 虚构角色 / pet 宠物 / business 商业名称
 */
const CREATIVE_KINDS = ['platform', 'game', 'role', 'pet', 'business']

// 各 kind 的中文名（前端标题/副标题，与后端 KIND_NAMES 镜像）
const CREATIVE_KIND_NAMES = {
  platform: '平台名称',
  game: '游戏昵称',
  role: '虚构角色',
  pet: '宠物起名',
  business: '商业名称'
}

function creativeGenerate(params) {
  return request('/creative/generate', 'POST', params)
}

// 小说类型枚举（与后端 NOVEL_GENRES 镜像；code + name，虚拟人物起名用）
const NOVEL_GENRES = [
  { code: 'xuanhuan', name: '玄幻' },
  { code: 'xianxia', name: '仙侠' },
  { code: 'wuxia', name: '武侠' },
  { code: 'dushi', name: '都市' },
  { code: 'kehuan', name: '科幻' },
  { code: 'lishi', name: '历史' },
  { code: 'junshi', name: '军事' },
  { code: 'xuanyi', name: '悬疑灵异' },
  { code: 'youxi', name: '游戏竞技' },
  { code: 'erciyuan', name: '二次元' },
  { code: 'yanqing', name: '言情' },
  { code: 'qihuan', name: '奇幻' },
  { code: 'moshi', name: '末世' }
]

// 性格特征枚举（与后端 CHARACTER_TRAITS 镜像；code + name，虚拟人物起名用）
const CHARACTER_TRAITS = [
  { code: 'qingleng', name: '清冷' },
  { code: 'wenrun', name: '温润' },
  { code: 'fuhei', name: '腹黑' },
  { code: 'aojiao', name: '傲娇' },
  { code: 'yangguang', name: '阳光' },
  { code: 'lengjun', name: '冷峻' },
  { code: 'wenrou', name: '温柔' },
  { code: 'satuo', name: '洒脱' },
  { code: 'guao', name: '孤傲' },
  { code: 'chenwen', name: '沉稳' },
  { code: 'rexue', name: '热血' },
  { code: 'jiaoxie', name: '狡黠' },
  { code: 'jianyi', name: '坚毅' },
  { code: 'lanyang', name: '慵懒' },
  { code: 'shenmi', name: '神秘' }
]

// 平台名称枚举（与后端 PLATFORM_TYPES 镜像；code + name，平台名称起名用）
const PLATFORM_TYPES = [
  { code: 'xiaohongshu', name: '小红书' },
  { code: 'zhihu', name: '知乎' },
  { code: 'douyin', name: '抖音' },
  { code: 'bilibili', name: 'B站' },
  { code: 'wechat', name: '微信' }
]

// 游戏类型枚举（与后端 GAME_TYPES 镜像；code + name，游戏昵称起名用）
const GAME_TYPES = [
  { code: 'fantasy', name: '仙侠奇幻' },
  { code: 'scifi', name: '科幻' },
  { code: 'tactical', name: '硬核战术' },
  { code: 'casual', name: '休闲经营' }
]

// 激励视频广告位（配置驱动）：填入微信小程序流量主的广告位 ID 后，
// 「看广告解锁 AI 生成」才生效；留空表示未配置，前端提示「广告位未配置」。
const REWARDED_AD_UNIT_ID = ''

/**
 * 创意起名 · AI 生成（虚拟人物自定义描述，看广告解锁后调用）
 *
 * 后端 LLM 未配置时会降级本地词库（source="local"），并附 fallback_note。
 */
function llmGenerate(params) {
  return request('/creative/llm', 'POST', params)
}

// 行业枚举（与后端 INDUSTRY_WUXING 镜像，商业起名 picker 用；code 即后端行业 code）
const INDUSTRY_OPTIONS = [
  { code: 'tech', name: '互联网 / 科技' },
  { code: 'media', name: '传媒 / 文创' },
  { code: 'catering', name: '餐饮' },
  { code: 'energy', name: '能源' },
  { code: 'finance', name: '金融 / 财会' },
  { code: 'law', name: '法律' },
  { code: 'manufacturing', name: '制造 / 工业' },
  { code: 'education', name: '教育 / 文化' },
  { code: 'medical', name: '医疗 / 健康' },
  { code: 'art', name: '艺术' },
  { code: 'agriculture', name: '农业' },
  { code: 'realestate', name: '地产 / 建筑' },
  { code: 'trade', name: '贸易 / 物流' },
  { code: 'tourism', name: '旅游 / 服务' }
]

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
 * 分享页小程序码（PNG）
 *
 * 返回本地临时文件路径，供 <image src> 直接使用。
 * 后端未配置 WX_APPID / WX_SECRET 时返回 501，这里按失败处理 ——
 * 调用方（分享页）显示占位印即可，属于开发期的正常状态，不是故障。
 */
function shareQrcode() {
  return probeApiBase().then(function () {
    const app = getApp()
    return new Promise((resolve, reject) => {
      wx.downloadFile({
        url: app.globalData.apiBase + '/share/qrcode',
        success(res) {
          if (res.statusCode >= 200 && res.statusCode < 300 && res.tempFilePath) {
            resolve(res.tempFilePath)
          } else {
            reject({ message: '小程序码未启用' })
          }
        },
        fail() {
          reject({ message: '小程序码获取失败' })
        }
      })
    })
  })
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
  analyzeBatch,
  creativeGenerate,
  llmGenerate,
  recommendChars,
  pickableChars,
  recommendSources,
  sourceChars,
  nameMeaning,
  shareQrcode,
  queryBazi,
  STYLE_OPTIONS,
  SOURCE_STYLE_MAP,
  getStyleCodes,
  MEANING_OPTIONS,
  MEANING_GROUPS,
  MEANING_MAX_SELECT,
  SOURCE_CLASSES,
  RANGE_OPTIONS,
  DEFAULT_RANGE_DAYS,
  CREATIVE_KINDS,
  CREATIVE_KIND_NAMES,
  INDUSTRY_OPTIONS,
  NOVEL_GENRES,
  CHARACTER_TRAITS,
  PLATFORM_TYPES,
  GAME_TYPES,
  REWARDED_AD_UNIT_ID
}
