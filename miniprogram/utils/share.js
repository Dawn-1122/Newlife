/**
 * 统一分享文案
 *
 * 为什么要有这个文件：
 * 1. 微信要求 `onShareAppMessage` **必须定义在页面里**，右上角菜单才会出现「转发」。
 *    此前只有 home / wizard / result / detail 四个页面定义过，其余 7 个页面
 *    （more / name / analyze / analyze-result / bazi / prenatal-result / index）
 *    用户**根本无法转发** —— 分享入口不该按页面随机缺失。
 * 2. 11 个页面各写一遍同样的 title/path 必然漂移，故抽到这里，页面里挂上即可。
 *
 * ⚠️ 铁律：本文件的返回值**只能**包含官方支持的字段
 *    （title / path / imageUrl / promise；onShareTimeline 无 path）。
 *    平台**不提供**「分享成功」回调 —— 写 success 字段会被静默忽略，不报错、不崩，
 *    只是那段逻辑永远不执行（detail 页的分享解锁就是这么失效的）。
 *    该约束由 `tests/test_share_policy.py` 自动门禁。
 */

const HOME_PATH = '/pages/home/home'
const HOME_TITLE = '名堂 · 有据可循的起名工具'

// 名字分享的落地页：必须能用 URL 参数重建内容
//（detail 依赖 globalData.selectedName，好友冷启动点开时并不存在）
const NAME_PATH = '/pages/share/share'
const NAMING_PATH = '/pages/name/name'

// 分享路径长度上限（query 部分）。微信未公开具体限制，按经验留足余量。
const MAX_QUERY_LEN = 560

// 转发给好友 / 群
function defaultShare() {
  return {
    title: HOME_TITLE,
    path: HOME_PATH
  }
}

// 分享到朋友圈（该场景不支持自定义 path，只能带 query）
function defaultTimeline() {
  return {
    title: HOME_TITLE
  }
}

// ── 单个名字的分享 ──
//
// 为什么把出处整条塞进链接，而不是让落地页按名字重新解析：
//   生成器给名字配出处，用的是「本次生成上下文里的那一条」；落地页只有名字，
//   重新解析可能落到另一首同样含名字用字的诗 —— 分享卡写着「出自《山鬼》」，
//   点开却是另一首，「有据可循」这块牌子就砸了。
//
// 参数含义见 pages/share/share.js 顶部注释。
function nameShareQuery(fullName, poem, gender) {
  const parts = ['n=' + encodeURIComponent(fullName || '')]

  if (poem) {
    if (poem.citation) parts.push('c=' + encodeURIComponent(poem.citation))
    if (poem.text) parts.push('x=' + encodeURIComponent(poem.text))
    if (poem.author) parts.push('a=' + encodeURIComponent(poem.author))
    if (poem.dynasty) parts.push('d=' + encodeURIComponent(poem.dynasty))
  }

  parts.push('g=' + (gender === 'female' ? 'female' : 'male'))
  parts.push('from=card')

  let query = parts.join('&')

  // 意境句属于锦上添花：路径过长时先丢它，别为一句文案把整条分享挤坏
  if (poem && poem.scene) {
    const withScene = query + '&s=' + encodeURIComponent(poem.scene)
    if (withScene.length <= MAX_QUERY_LEN) query = withScene
  }

  return query
}

function nameShareTitle(fullName, poem) {
  if (!fullName) return HOME_TITLE
  if (poem && poem.citation) return '「' + fullName + '」· 出自' + poem.citation
  return '「' + fullName + '」· 名堂'
}

/**
 * 单个名字的转发
 * @param {string} fullName 完整姓名
 * @param {object} poem     出处（citation/text/author/dynasty/scene）
 * @param {string} gender   male | female
 */
function nameShare(fullName, poem, gender) {
  if (!fullName) return defaultShare()
  return {
    title: nameShareTitle(fullName, poem),
    path: NAME_PATH + '?' + nameShareQuery(fullName, poem, gender)
  }
}

// 单个名字分享到朋友圈（无 path，只带 query）
function nameTimeline(fullName, poem, gender) {
  if (!fullName) return defaultTimeline()
  return {
    title: nameShareTitle(fullName, poem),
    query: nameShareQuery(fullName, poem, gender)
  }
}

// 起名入口的转发：结果页是一批名字，分享其中单个会以偏概全
function namingShare() {
  return {
    title: '我在名堂给孩子起名：每个名字，都查得到出处',
    path: NAMING_PATH
  }
}

function namingTimeline() {
  return {
    title: '我在名堂给孩子起名：每个名字，都查得到出处'
  }
}

module.exports = {
  HOME_PATH,
  HOME_TITLE,
  NAME_PATH,
  NAMING_PATH,
  defaultShare,
  defaultTimeline,
  nameShare,
  nameTimeline,
  nameShareTitle,
  nameShareQuery,
  namingShare,
  namingTimeline
}
