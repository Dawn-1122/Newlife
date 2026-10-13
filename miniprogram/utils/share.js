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

module.exports = {
  HOME_PATH,
  HOME_TITLE,
  defaultShare,
  defaultTimeline
}
