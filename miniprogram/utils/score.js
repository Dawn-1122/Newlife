/**
 * 推荐值 · 展示刻度换算
 *
 * ── 为什么需要这个文件 ──
 * 后端返回的 `scores.overall` 是「韵味分」，量表满分 100。但其中有两个维度
 * 让它拿不满，也有一个维度白送，结果整个分布被挤在一条窄带里
 * （1362 个真实候选实测，见 scripts/diag_score_scale.py）：
 *
 *   维度          满分   实测均值   得满率
 *   出处 P          35     30.5     65%
 *   意象 I          25     11.7      0%   命中 1 个意象词才 +4，一条出处通常只标 1~3 个
 *   余味 L          15     15.0    100%   义项数 ×4 封顶 15，几乎人人拿满
 *   呼应 C          10      4.4     39%
 *   姓氏 S          15      0.6      0%   要「姓+名」在原文里连成词，李/王/张/陈基本不可能
 *
 * 合计实际可达上限 ≈ 85（实测最高 85），中位数 62。于是用户看到的推荐结果
 * 几乎全是 58~77 分 —— 不是名字差，是量表的天花板缺了一块。
 *
 * ── 这里做什么 ──
 * 把韵味分折算到「实际可达满分」上，得到 0~100 的推荐值：
 *
 *     推荐值 = round(韵味分 ÷ 85 × 100)，封顶 99
 *
 * 62 分 → 73，77 分 → 91。
 *
 * ── 边界 ──
 * 1. **只影响展示。** 排序、筛选、门槛仍用 `scores.yunwei`（原分），后端一个字没改。
 * 2. 折算是线性、单调的：谁比谁高不会变，只是刻度换了；把 CEIL 改成 100 即退回原刻度。
 * 3. 换算放在前端而不是后端，是为了**旧数据一致**：名字本里已收藏的记录只存了
 *    `overall` 原分，前端换算能让新旧记录显示同一把尺子，不必做数据迁移。
 */

// 实测可达满分（韵味的理论上限 100 减去恒空的姓氏协调 15 分）
var CEIL = 85
// 不显示满分：99 是「几乎无可挑剔」的惯用写法，100 反而像凑数
var MAX_SHOWN = 99

/**
 * 韵味原分 → 推荐值（0~99）
 * @param {number} raw scores.overall
 */
function recommend(raw) {
  var v = Number(raw)
  if (!v || v <= 0) return 0
  var out = Math.round((v * 100) / CEIL)
  return out > MAX_SHOWN ? MAX_SHOWN : out
}

/**
 * 徽章档位（朱砂 / 墨 / 灰）：按推荐值分，88 以上强推，75 以上可用。
 * 阈值随刻度一起换 —— 原刻度是 85 / 70，折算后等价于 100 / 82，
 * 但那样几乎没人进「强推」，故按实际分布下调到 88 / 75。
 */
function tier(rec) {
  if (rec >= 88) return 'score-high'
  if (rec >= 75) return 'score-mid'
  return 'score-low'
}

/** 一次拿到展示所需的两个字段：{ recommend, tier } */
function badge(raw) {
  var rec = recommend(raw)
  return { recommend: rec, tier: tier(rec) }
}

module.exports = {
  recommend: recommend,
  tier: tier,
  badge: badge,
  CEIL: CEIL
}
