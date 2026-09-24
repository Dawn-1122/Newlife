"""「宜作名字对」复核流水线（第二道闸）

第一道闸（pair_annotator.py）已保证字对「字在原文 + 同分句」，并让 LLM 做过
「像不像名字」的判断；但审计抽样仍能看到明显不宜作名的组合，主要三类：

    地名 / 专名：长安、江南、昆仑、淇奥、天门、南山
    物名 / 器物 / 药名：神药、明堂、白鹿、玉检
    称谓 / 固定语：妻子、淑女、东君

这类是**语义**问题，规则与字库都拦不住（「药」「妻」的 luck 都是吉）。
故用一次批量复核：把所有字对去重后分批送 LLM，只让它挑出「不适合做人名」的，
再从 name_pairs.json 中剔除，并输出审计报告。

用法：
    venv/bin/python scripts/pair_review.py --dry-run     # 只看会删什么
    venv/bin/python scripts/pair_review.py               # 实际剔除
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from app.services.llm_service import LLMService, LLMError  # noqa: E402

DEFAULT_IN = PROJECT_ROOT / "data" / "poetry" / "name_pairs.json"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "poetry" / "pairs_review.json"

SYSTEM_PROMPT = (
    "你是中文姓名顾问。用户给出一批两字组合，你只挑出**明确不适合做人名**的。"
    "【重要前提】中文人名本来就大量使用自然意象与雅正器物意象"
    "（玉、月、雪、霜、露、花、草、风、云、山、水、松、竹、梅、兰、秋、春、"
    "玉壶、玉堂、银河、芳草、秋风、秋菊、芦花、雪海、青天、暗香、花月、月影），"
    "这些**一律不要标**。"
    "【尤其不要标：意象＋动作/声音/色彩的组合】这是诗词起名最经典的手法，属于上等素材："
    "鹿鸣、鹤鸣、蝉鸣、莺啼、雁回、猿啸、云飞、月照、潮生、雪落、"
    "白鹿、青崖、苍松、素月、碧云、丹枫、疏影、暗香。"
    "**只看「像不像一个词组」不足以判断——「鹿鸣」出自《诗经·小雅·鹿鸣》「呦呦鹿鸣」，"
    "这类有经典出处、意象完整的组合必须保留。**"
    "只有在属于下面四类时才标："
    "① 地名 / 专名 / 人名：长安、江南、昆仑、淇奥、天门、南山、临安、新丰、潇湘、"
    "蓬莱、珠江、泰华、阴山、池边、江汉、牧野、榆关；"
    "② 称谓 / 身份 / 神话人物：妻子、淑女、东君、天子、诸侯、赤子、阿娇、孔子、"
    "文王、嫦娥、牧人；"
    "③ 成语 / 固定短语 / 动作连用 / 虚字组合：切磋、琢磨、彷徉、平时、成事、既成、"
    "维屏、维藩、在户、在野、如故、既坚、既洁、殷勤、呦鹿；"
    "④ **纯**物种名 / 器物 / 妆具 / 药名（只有物，没有意象动作）：神药、玉检、玉搔、"
    "月帔、花钿、翠钿、鸳枕、金斗、雎鸠、蜻蜓、骢马。"
    "宁漏勿滥：只要不是上面四类，或拿不准，一律保留。"
    "【最后再次强调】第 ④ 类指的是「纯物种名」，**不是**「带动物意象的词」——"
    "前面列出的鹿鸣、鹤鸣、白鹿等一律属于保留项，看到它们不要标。"
    "只输出一个合法 JSON 对象，不输出任何解释或 markdown 代码块。"
)

BATCH = 50

# 保护名单：雅正的名用词，复核不得剔除。
# 前九个来自提示词里自己举的正例（相互矛盾会让复核失去依据），其余是人工确认无争议的。
# 后补四个是**实测被误杀**的经典：《关雎》「窈窕」、《蒹葭》「伊人」、
# 《锦瑟》「锦瑟」、《长恨歌》「霓裳」——复核据「器物/称谓」规则误判，
# 但它们都是诗词里传诵千年的名用词，且实际作名观感良好。
#
# 2026-09-24 补「意象＋动作/声音/色彩」一类：用户指出「鹿鸣」这种词不该被当作
# 不适合做名字。实测确认它本就没被拦（能正常产出），但复核提示词原先把
# 「白鹿」当「动物名」反例列举、又把「锦瑟」同时列进反例（与这里自相矛盾），
# 是颗定时炸弹——一旦重跑复核就可能误杀。故显式固化，并加 tests/test_pair_policy.py
# 约束「PROTECTED 与提示词反例不得有交集」，让矛盾无法再悄悄出现。
PROTECTED = {
    "修远", "望舒", "素秋", "琼玉", "清扬", "玉瓒", "灼华", "眠云", "听雪",
    "婵娟", "静姝", "明月", "秋水", "芝英", "莺语", "松柏", "石泉", "芳草",
    "窈窕", "伊人", "锦瑟", "霓裳",
    # 意象＋动作/声音/色彩：诗词起名的经典手法，一律保留
    "鹿鸣", "鹤鸣", "蝉鸣", "莺啼", "白鹿", "青崖", "苍松", "素月",
    "疏影", "暗香", "云飞", "月照",
}

# 硬黑名单：确定不宜作名、且**实测 LLM 复核会漏判**的组合。
# 为什么需要它：LLM 复核有召回缺口 —— 2026-09-22 实测「壮心」（《龟虽寿》
# 「烈士暮年，壮心不已」）、「中立」（中天下而立）、「用明」「知己」「石上」
# 「社方」「盈岸」「新燠」全部通过了复核，直接产出「苏壮心」这类名字。
# 语义漏网无法只靠调提示词根治，故与项目既有的「事件负面字黑名单」同思路，
# 再加一道**确定性下限**：不看 LLM 脸色，命中即剔除。
BLOCKLIST = {
    # 论断 / 志向 / 评价（最像名字，也最易漏判）
    "壮心", "中立", "廉正", "固朝", "君子", "圣人", "大知", "淑女",
    # 功能 / 虚字组合
    "用明", "用恩", "用财", "教多", "在志", "里志", "有土", "社方",
    # 关系 / 称谓
    "知己", "妻子", "天子", "诸侯",
    # 物产 / 方位 / 俗语
    "荔枝", "福禄", "延寿", "年寿", "红萸", "黄橘", "石上", "盈岸",
    "新燠", "花语", "长征",
    # 跨字机械拼接（把叠词/相邻字的其中一字与后文同句字硬凑）：
    # 「呦呦鹿鸣」应取「鹿鸣」，不得取「呦鹿」「呦鸣」。
    # 「呦鹿」2026-09-22 已封；「呦鸣」是同类漏网（2026-09-24 实测仍在产出，67 分、24 次抽样出现 6 次）
    # ——同一套复核既会误杀（锦瑟）又会漏放（呦鸣），这正是「硬黑名单」存在的原因。
    "呦鹿", "呦鸣",
}


def build_user_prompt(words: list[str]) -> str:
    lines = ["下面这批两字组合，请挑出不适合做人名的："]
    lines.append("、".join(words))
    lines.append("")
    lines.append('输出 JSON：{"unsuitable": ["长安", "神药"]}（若全部适合则给空数组）')
    return "\n".join(lines)


async def review_batch(
    sem: asyncio.Semaphore, llm: LLMService, words: list[str]
) -> list[str]:
    async with sem:
        raw = await llm.chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(words)},
            ],
            temperature=0.1,
            max_tokens=1200,
            json_mode=True,
        )
    flagged = raw.get("unsuitable") or []
    if not isinstance(flagged, list):
        return []
    allowed = set(words)
    return [w for w in flagged if isinstance(w, str) and w in allowed]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(DEFAULT_IN))
    ap.add_argument("--report", default=str(DEFAULT_REPORT))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--blocklist-only",
        action="store_true",
        help="只应用人工硬黑名单（不调 LLM、结果确定），用于修补 LLM 复核的召回缺口",
    )
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--provider", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    path = Path(args.inp)
    data: dict[str, list] = json.loads(path.read_text(encoding="utf-8"))
    words = sorted({p[0] + p[1] for v in data.values() for p in v if len(p) == 2})

    if args.blocklist_only:
        # 确定性路径：不调 LLM，只剔除人工硬黑名单里的组合（幂等、无随机性）
        bad = sorted({w for w in words if w in BLOCKLIST and w not in PROTECTED})
        print(f"[review] 硬黑名单模式：命中 {len(bad)} 个 —— {'、'.join(bad) if bad else '无'}")
        print(f"[review] 条目 {len(data)} 条，去重后字对 {len(words)} 个")
        bad_set = set(bad)
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError as e:
            print(f"[review] 警告：备份失败（{e}），仍继续写入")
        removed = 0
        kept: dict[str, list] = {}
        for eid, pairs in data.items():
            survive = [p for p in pairs if (p[0] + p[1]) not in bad_set]
            removed += len(pairs) - len(survive)
            kept[eid] = survive
        path.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
        with_pairs = sum(1 for v in kept.values() if v)
        print(f"[review] 剔除 {removed} 个字对；剩余 {sum(len(v) for v in kept.values())} 个，"
              f"{with_pairs}/{len(kept)} 条仍有可用字对")
        return

    print(f"[review] 条目 {len(data)} 条，去重后字对 {len(words)} 个")

    batches = [words[i:i + BATCH] for i in range(0, len(words), BATCH)]
    llm = LLMService(
        provider=args.provider, api_key=args.api_key,
        base_url=args.base_url, model=args.model,
    )
    print(f"[review] LLM: {llm.provider} / {llm.model}，分 {len(batches)} 批")

    sem = asyncio.Semaphore(args.concurrency)

    async def safe(batch):
        try:
            return await review_batch(sem, llm, batch)
        except LLMError as e:
            print(f"  [fail] 一批复核失败: {e}")
            return []

    results = await asyncio.gather(*[safe(b) for b in batches])
    bad = sorted(
        {w for r in results for w in r if w not in PROTECTED} | BLOCKLIST
    )
    print(f"[review] 判定不适合 {len(bad)} 个（{len(bad) / max(1, len(words)):.0%}）")

    Path(args.report).write_text(
        json.dumps(
            {"total_words": len(words), "unsuitable": bad}, ensure_ascii=False, indent=1
        ),
        encoding="utf-8",
    )
    if args.dry_run:
        print("[review] dry-run，未改动 name_pairs.json。判定为不适合的：")
        print("  " + "、".join(bad))
        return

    bad_set = set(bad)
    # 先备份再原地覆盖：复核是不可逆操作，且 LLM 判定有随机性 ——
    # 2026-09-22 就因为「直接覆盖、无备份」把误杀的「窈窕」原始字对彻底丢失。
    backup = path.with_suffix(path.suffix + ".bak")
    try:
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError as e:
        print(f"[review] 警告：备份失败（{e}），仍继续写入")

    removed = 0
    kept: dict[str, list] = {}
    for eid, pairs in data.items():
        survive = [p for p in pairs if (p[0] + p[1]) not in bad_set]
        removed += len(pairs) - len(survive)
        kept[eid] = survive
    path.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")

    with_pairs = sum(1 for v in kept.values() if v)
    print(f"[review] 剔除 {removed} 个字对；剩余 {sum(len(v) for v in kept.values())} 个，"
          f"{with_pairs}/{len(kept)} 条仍有可用字对")
    print(f"[review] 覆盖前已备份到 {backup.name}（误杀可从此恢复）")


if __name__ == "__main__":
    asyncio.run(main())
