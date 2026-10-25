"""
起名核心引擎

整合八字引擎 + 字库 + 诗词库 + 字源库 + 音律评分 + 五格数理 + 韵味评分，
生成完整的名字候选列表。

评分架构（重构后）：
- 硬过滤层（安全底线）：负面字黑名单 + 用户避讳字 + luck=凶 ∪ blacklist.json
- 第一层门槛（只排除、不打分）：音律严重拗口 / 五格人格总格双凶 / 八字全忌神
- 第二层排序：韵味（出处/意象/余味/名内呼应/姓氏协调）——决定谁排前面
    - 韵味同分 tie-break：喜用神命中数 → 寓意命中数 → 风格命中数
    - _diversify 多样性重排 → 截取 max_results

scores.overall 语义变更 = 韵味分（主排序依据）；scores.phonetics/wuge/bazi 退化为展示值。
"""

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Optional
from app.services.bazi_engine import BaziEngine
from app.services.char_database import CharDatabase
from app.services.poetry_database import PoetryDatabase
from app.services.source_database import SourceDatabase
from app.services.surname_database import SurnameDatabase
from app.services.phonetics import PhoneticsScorer
from app.services.wuge import WugeScorer
from app.services.yunwei_scorer import YunWeiScorer
from app.services.llm_service import LLMService
from app.services.meaning_cache import MeaningCache
from app.services.surname_fit import SurnameFit
from app.services.char_sense_database import CharSenseDatabase
from app.core.constants import (
    NEGATIVE_CHARS, EMOTIONAL_CHARS, SAD_POETRY_TITLES, COMPOUND_SURNAMES, WUXING_LIST,
    IMAGERY_FAMILY_PRIORITY, build_radical_family_map,
)
from app.core.naming_options import (
    STYLE_OPTIONS,
    MEANING_OPTIONS,
    STYLE_TIER_A_WEIGHT,
    MEANING_KEYWORD_WEIGHT,
    IMAGERY_WEIGHT,
    TARGET_MIN,
    COHESION_RANK,
)

# 康熙部首异体归一化（单字名「说文解字」出处的 title 用主部首名，如 氵→水）。
# 与 scripts/expand_source_shuowen.py 的 RADICAL_ALIAS 保持一致。
_RADICAL_TITLE_ALIAS = {
    "氵": "水", "艸": "艹", "钅": "金", "釒": "金", "灬": "火",
    "忄": "心", "扌": "手", "亻": "人", "纟": "糸", "糹": "糸",
    "讠": "言", "王": "玉", "罒": "网",
}


class NamingEngine:
    """起名核心引擎"""

    # ── 分层抽样可调参数（P3 主排序改造） ──
    # 层内抽样温度：越大越均匀（多样性↑、「高频常客」↓），越小越偏高分。
    # 职责分离：质量底线交给 STRATIFY_QUALITY_BAND，温度只负责多样性，
    # 故可放宽到 36（实测 T>36 多样性收益递减，且八字匹配度开始下滑）。
    STRATIFY_TEMPERATURE = 36.0
    # 全喜神层配额占比（其余给「含非喜用神字」层）。忌神为喜神补集，不存在中性层。
    STRATIFY_FULL_RATIO = 0.8
    # 层内权重里「含用神字」的加分（用神随生日变化 → 抽样结果随输入变化）。
    # 实测 60 会让抽样在「带宽后仅剩百来个候选」的层内极度集中到双用神字子集上
    # （换一批重合 33%→20% 靠它下调）；而降为 20 对八字匹配度无影响（该指标由
    # 分层配额独立保证，恒 90%），故取小值保留「用神进入主排序权重」的设计意图。
    STRATIFY_YONG_BONUS = 20.0
    # 层内权重里「覆盖喜神五行个数」的加分（实测无稳定收益，保留开关）
    STRATIFY_COVER_BONUS = 0.0
    # 组合阶段候选池规模：池太小（原 120）会让「高频常客」不可避免——
    # 实测池 ≈970 是质量/多样/耗时（≈0.23s）的最佳平衡点。
    COMPOSE_CAP_FACTOR = 40      # cap = max_results × factor
    COMPOSE_CAP_MIN = 600
    RANDOM_BUDGET_FACTOR = 20    # 随机组合名额 = max_results × factor
    # 分层抽样时每层可参与抽样的候选上限（越大越不易出现跨输入「常客」）
    STRATIFY_POOL_FACTOR = 25
    STRATIFY_POOL_MIN = 800
    # 质量带宽：抽样窗口内只保留「韵味分 ≥ 窗口最高分 − 带宽」的名字。
    # 候选池实测呈双峰：同源名（双字同出一源，P=35）均分 63~64，单字名（P=20）
    # 均分仅 44~47 且占池一半——尾部弱名全部来自后者。带宽 18 正好卡在两峰之间，
    # 效果（18 组 × Top30 = 540 名，T=36/YONG=20）：
    #   韵味 min 28→58、中位 52→66、低于 50 分 235→0 条、双字同源 40%→96%。
    # 代价：高频常客 3→4~5、换一批重合 3%→17~27%（仍远低于 <90% 目标）。
    # 该代价无法靠调参消除——同源名池被源数据硬顶在 326~459 条/生日，
    # 组合预算翻 8 倍也不增长（多出来的全是单字名）。要同时提质量与多样性，
    # 必须扩源数据（更多诗词/条目 → 更大的同源池）。设 0 关闭带宽。
    STRATIFY_QUALITY_BAND = 18.0
    # 带宽生效的最小窗口规模（带宽后候选不足 n×该系数时逐档放宽带宽，见
    # _banded_window）。取 3：实测 2/3 质量完全相同（min 58 / 中位 66 / 0 条 <50），
    # 但 3 的「高频常客」更稳（多轮 5/5/5 vs 5/5/6）。
    STRATIFY_BAND_MIN_FACTOR = 3

    # ── 偏好层参数（用户明确选了寓意/风格时，见 _stratified_sample 步骤 1） ──
    # 为什么偏好层要单独一套：通用层温度 36 是为「没选偏好时也要每批不同」而调的，
    # 但用户一旦选了寓意/风格，意图就是「给我贴合这个风格的」——此时还按近均匀
    # 抽样，结果就成了「换了 6 个碰巧命中偏好的随机名」，用户体感「选不选差不多」。
    # 另外原实现里 pref_pool 先按命中数排序，进 take() 又被 -韵味 重排，
    # 命中 1 项与命中 4 项待遇相同 —— 偏好只剩「过滤器」作用，没有被「优先」。
    # 故：层内权重 = 韵味 + 命中数 × PREF_HIT_BONUS，温度降到 PREF_TEMPERATURE。
    # 取值来自配对实测（同一随机种子，4 组输入 × 12 批 × 6 名，只改这两个参数）：
    #   旧 0/36 → 新 6/28：命中 ≥2 项的占比 53/72/81% → 64/81/92%，
    #   命中 ≤1 项（「跟没选一样」的体感来源）47/28/19% → 36/19/8%；
    #   代价是批间不同名比例 0.50/0.38/0.56 → 0.44/0.36/0.44（换一批重合 +6pt）。
    # 再压温度（T=24）命中率只涨 2~3pt 而重合度继续升，故取 28。
    # 注：寓意/风格命中判定本身是字面匹配（出处 imagery/scene 文本），
    # 区分度有限——「李」这类姓氏的池子偏窄，效果最弱（53%→50%），
    # 要再往上只能靠标注数据，不是调参能解决的。
    PREF_HIT_BONUS = 6.0
    PREF_TEMPERATURE = 28.0

    # 组合成立度门槛：抽样前先把窗口收窄到「两字在原文中成对」的同源名。
    # 出处的推荐字是「一袋好字」，两字组合由全交叉产生，实测 65% 的配对在原诗中
    # 分处不同分句——即「只是从同一句里抠了两个不相干的字」（萸橘/红黄式）。
    # 这类名字看起来有出处、实则配对是假的，且评分器对它失明，是用户
    # 「不像名字」体感的根源。故在质量带宽之前先按成立度收窄；
    # 成对候选不足 k × 该系数时才放开到跨句拼接与单字出处。
    # 取 2：实测成对候选 97~134 条（k=30 时门槛 60），有足够余量；
    # 取 1 会因池太窄把常客推高。
    COHESION_MIN_FACTOR = 2
    # 「成对」的成立度档位（相邻 = 原句成词，同句 = 同分句内可解释，
    # annotated = LLM 判定宜作名的字对）
    COHESION_PAIRED_KINDS = ("annotated", "adjacent", "same_clause")

    def __init__(self):
        self.char_db = CharDatabase()
        self.poetry_db = PoetryDatabase()
        self.source_db = SourceDatabase()
        self.surname_db = SurnameDatabase()
        self.yunwei = YunWeiScorer(
            surname_db=self.surname_db,
            source_db=self.source_db,
            poetry_db=self.poetry_db,
        )
        self.phonetics = PhoneticsScorer()
        self.wuge = WugeScorer()
        self.bazi = BaziEngine()
        self.llm = LLMService()
        self.cache = MeaningCache()
        self.surname_fit = SurnameFit()
        self.sense_db = CharSenseDatabase()
        # 出处推荐字白名单缓存（懒加载）
        self._provenance_char_set: Optional[set[str]] = None
        # 字 → 该字「有语境义项」的最佳出处（回退用，与输入无关）
        self._sense_entry_cache: dict[str, Optional[dict]] = {}
        # 字对「名字感」分级（人工审定，见 scripts/pair_taste.py）
        self.pair_taste = self._load_pair_taste()
        # 单字名的名字感分级（同一份文件的 single 段，判据见 _char_taste）
        self.char_taste = self._load_char_taste()

    # ── 名字感分级（第三道闸，数据在 data/poetry/pair_taste.json） ──
    # 前两道闸（pair_annotator / pair_review）判的是「像不像诗里的好词」，
    # 取向是古典雅正——pair_review 甚至把「银河/雪海/青天/暗香/花月」写进保护名单，
    # 而这正是用户觉得「土」的那一批。第三道闸改判「愿不愿意写在出生证明上」：
    #   5 = 优先（静姝/望舒/清扬）  4 = 可用（素月/幽意）
    #   3 = 兜底（清溪/月霜这类景物直取）  1 = 屏蔽（春风/明月/翠凤/瑞祥）
    # 1 分在组合阶段直接不出；5/4 分在抽样权重里加分，让默认结果先给好名字。
    # 文件缺失时整体降级为「不分级」（全部按 3 分），不影响出名字。
    TASTE_BONUS = 4.0          # 抽样权重里每档名字感的加分（5 分比 3 分高 8）
    # 同一批里同一个字最多出现几次。语料里「清」系字对密集，不设限时一批 6 个能出
    # 三个「清」；设 2 之后仍保留「清扬/清浅」这类正常重复，只掐掉明显堆叠。
    CHAR_REPEAT_CAP = 2
    # 偏好命中池最多占整批的份额。窄风格下命中池常常只有七八个名字，全给它就等于
    # 每次「换一批」都在同一小撮里排列组合（见 take 处的注释）。
    PREF_QUOTA_RATIO = 0.65
    # 选了气质（style）时，整批里**至少**这个比例的名字要出自该气质的典籍。
    #
    # 为什么要设名额而不是只调权重：实测（林/男/1990-05-20）选「古风雅致」，
    # 结果里出自诗经/楚辞/汉魏/五代词的比例是 49%，而**不选时是 58%** ——
    # 气质偏好不但没起作用，还偏低。原因是 style 只在选池阶段做 tier 排序
    # （_rank_poems），到最终分层抽样时又被韵味分与用神配额压平了。
    # 用户点「古风雅致」的意图是「给我这个味道的名字」，不是「排序时偏一点」，
    # 所以这里改成硬名额：先按出处取够一半，剩下的再交给用神与韵味。
    STYLE_SOURCE_RATIO = 0.5
    _TASTE_FILE = Path(__file__).resolve().parents[2] / "data" / "poetry" / "pair_taste.json"

    @classmethod
    def _load_pair_taste(cls) -> dict[str, int]:
        try:
            raw = json.loads(cls._TASTE_FILE.read_text(encoding="utf-8"))
            scores = raw.get("scores") or {}
            return {k: int(v) for k, v in scores.items() if isinstance(v, (int, float))}
        except (OSError, ValueError, TypeError):
            return {}

    @classmethod
    def _load_char_taste(cls) -> dict[str, int]:
        """单字档位。文件里没有 `single` 段时返回空 dict（`_char_taste` 会降级为 3）。"""
        try:
            raw = json.loads(cls._TASTE_FILE.read_text(encoding="utf-8"))
            single = raw.get("single") or {}
            return {k: int(v) for k, v in single.items() if isinstance(v, (int, float))}
        except (OSError, ValueError, TypeError):
            return {}

    def _pair_taste(self, a: str, b: str) -> int:
        """字对名字感（**语序敏感**）。

        「幽韵」可用不代表「韵幽」可用——原句语序与倒序分别定级，否则倒序白拿
        正序的分数（实测漏出过「韵幽」「标清」「汉星」）。倒序未单独定级即按屏蔽
        处理；正序仍可出，不伤产能。

        分级文件缺失时降级为 3（不分级），而不是让整个引擎哑掉。
        """
        if not self.pair_taste:
            return 3
        return self.pair_taste.get(a + b, 1)

    def _char_taste(self, ch: str) -> int:
        """单字名的名字感（`single` 表）。

        单字原先没有过闸：`_pair_taste` 只认两个字，单字路径直接给默认 3 分，于是
        「瑰/甘/垂/蓬/汗/鸦」这类不是名字的字能直接出（实测 350 个可生成单字名里
        约四成不该出）。单字判据与字对略有不同——**一个字要独自立得住**，不能靠
        搭档衬托，所以是独立的一张表，不共用字对分数。

        表缺失时降级为 3，与 `_pair_taste` 同策。
        """
        if not self.char_taste:
            return 3
        return self.char_taste.get(ch, 1)

    def generate_names(
        self,
        surname: str,
        gender: str = "male",
        year: int = None,
        month: int = None,
        day: int = None,
        hour: int = 12,
        minute: int = 0,
        name_length: int = 2,
        max_results: int = 30,
        use_bazi: bool = True,
        use_poetry: bool = True,
        style: Optional[str] = None,
        meanings: Optional[list[str]] = None,
        avoid_chars: Optional[list[str]] = None,
        industry: Optional[str] = None,
        target_min: int = TARGET_MIN,
        selected_chars: Optional[list[str]] = None,
        source_classes: Optional[list[str]] = None,
        generational_char: Optional[str] = None,
        exclude_names: Optional[list[str]] = None,
        shuffle: bool = False,
    ) -> dict:
        """
        生成名字候选列表

        Args:
            surname: 姓氏
            gender: male / female
            year/month/day/hour/minute: 出生时间（可选，不提供则不做八字分析）
            name_length: 名字字数（1或2，不含姓）
            max_results: 最大返回数量
            use_bazi: 是否使用八字分析
            use_poetry: 是否使用诗词典故
            style: 风格偏好 code（选池偏置 + 末级 tie-break，不再强加权压过韵味）
            meanings: 期望寓意 code 列表（选字硬前置 + 二级 tie-break）
            avoid_chars: 避讳字列表，硬剔除
            industry: 行业 code，P0 仅透传不参与打分
            target_min: 同源组名目标最小数量
            selected_chars: 用户点选的候选字（两阶段流程「先字后出处」）。
                            语义 = **名字必须含所选字**（任一位置），不是「名字只用所选字」——
                            后者对单个字必然 0 结果（一个字无法自成字对），已废弃。
                            搭档仍取「已批准字对」（语义层），空白处由语料覆盖情况决定。
            source_classes: 出处类目限定（两阶段流程「先出处后字」）。
                            取值为诗词 source（诗经/楚辞/唐诗/宋词/五代词/清词/汉魏古诗/经史子集）
                            或 source_class（同左，字源 4 部典籍归入「经史子集」）。
            generational_char: 字辈（可选，仅双字名生效）：固定出现在名字第二个字，硬约束。
            exclude_names: 已展示过的名字（不含姓），「换一批」用：命中的名字硬剔除。
                           没有它时「换一批」等同于重新掷一次骰子，高分池只有二三十个，
                           连翻三批必然把同一批高分名字再抽回来（实测顾/男 elegant 三批
                           里「清浅/素秋/清秋」各出现三次）。
            shuffle: 最终摆盘顺序是否打乱（默认 False = 韵味降序，供脚本/评测使用）。
                     **只改顺序，不改选谁**：门槛、分层配额、抽样权重全部照旧，
                     所以「打乱」不会让弱名漏进来，只是不再把高分名字排在前面。
                     API 侧默认 True（产品要抽卡感，见 NamingRequest.shuffle）。

        Returns:
            {"bazi": {...}, "names": [...], "total": int, "fallback_note": str|None}
        """
        bazi_result, names = self._build_names(
            surname=surname, gender=gender, year=year, month=month, day=day,
            hour=hour, minute=minute, name_length=name_length,
            max_results=max_results, use_bazi=use_bazi, use_poetry=use_poetry,
            style=style, meanings=meanings, avoid_chars=avoid_chars,
            target_min=target_min, selected_chars=selected_chars,
            source_classes=source_classes, generational_char=generational_char,
            exclude_names=exclude_names, shuffle=shuffle,
        )

        fallback_note = None
        if (style or meanings) and len(names) < target_min and len(names) < max_results:
            _, fallback_names = self._build_names(
                surname=surname, gender=gender, year=year, month=month, day=day,
                hour=hour, minute=minute, name_length=name_length,
                max_results=max_results, use_bazi=use_bazi, use_poetry=use_poetry,
                style=None, meanings=None, avoid_chars=avoid_chars,
                target_min=target_min, selected_chars=selected_chars,
                source_classes=source_classes, generational_char=generational_char,
                exclude_names=exclude_names, shuffle=shuffle,
            )
            if len(fallback_names) > len(names):
                names = fallback_names
                fallback_note = "已尽量贴合偏好，其余按韵味评分补充"

        # 先出处模式的空结果兜底：先前这里会返回 0 个名字且 fallback_note 仍是 None，
        # 前端只能显示一句「暂无结果」，用户根本不知道是类目选得不对、还是条件太窄。
        # 类目没材料是硬原因，优先于「翻完了」——后者会把原因误判成翻页翻过头。
        source_note = None
        if not names and source_classes and not selected_chars:
            source_note = self._source_classes_note(source_classes, gender)

        if source_note:
            fallback_note = source_note
        elif not names and exclude_names and not selected_chars:
            # 排除名单把池子掏空：如实说「翻完了」，不要悄悄回退到已展示过的名字。
            # 前端据此引导用户换风格/放宽偏好，比再给一遍同样的名字体面。
            fallback_note = "这一批已经把合适的名字翻完了，换个风格或放宽偏好再试试"

        if selected_chars and not names:
            # 先字模式的显式降级，区分两种情况（前端据此给不同引导）：
            # ① 该字全局没有已批准搭档 → 死胡同，必须换字；
            # ② 有搭档但与本姓氏/性别条件组合不出（三连同调、谐音、五格等门槛拦下）
            #    → 换字或改用「直接推荐」。正常流程不会走到这里——
            #    字表由 scripts/diag_selected_chars.py 的覆盖/可行性表预先筛过。
            no_partner = [
                ch for ch in selected_chars
                if not self.poetry_db.approved_partners(ch)
            ]
            if no_partner:
                fallback_note = f"「{no_partner[0]}」没有可组名的搭档字，换一个字试试"
            else:
                fallback_note = "所选字与当前姓氏条件组合不出合适的名字，换一个字或直接推荐试试"

        return {
            "bazi": bazi_result,
            "names": names,
            "total": len(names),
            "fallback_note": fallback_note,
        }

    def _source_classes_note(self, source_classes: list[str], gender: str) -> str:
        """先出处模式返回 0 个名字时的说明。

        先前该模式下空结果一律给 `fallback_note=None`，前端只剩一句「暂无结果」，
        用户既不知道这类典故本来就少，也不知道该动类目还是动姓氏。这里按材料量分三种
        说清楚下一步该动什么：

        ① 这一类一条可作名字的典故都没有 —— 收录缺口；
        ② 有收录，但适合作名字的条目对本性别为零 —— 性别口径不合；
        ③ 有可用条目，仍一个名字都没组出来 —— 字句本身不合用（名字感屏蔽档、
           谐音、三连同调等门槛拦下）。此档**不把锅甩给姓氏**：实测「五代词」
           150 条里字对多为闺阁套语，属语料性质问题，与姓氏无关。

        Args:
            source_classes: 用户限定的类目（可多选，来自请求体）。
            gender: male / female，用于复现生成时真正采用的性别口径。

        Returns:
            直接可展示给用户的中文说明（永不为 None，调用方已确认结果为空）。
        """
        wanted = set(source_classes)
        label = "、".join(source_classes)

        def count(entries: list[dict]) -> int:
            """数「本类目里、有推荐字、且非哀伤」的条目。"""
            n = 0
            for entry in entries:
                if not (
                    entry.get("source") in wanted
                    or entry.get("source_class") in wanted
                ):
                    continue
                if not entry.get("recommend_chars"):
                    continue
                if NamingEngine._is_sad_poem(entry):
                    continue
                n += 1
            return n

        total = count(
            list(self.poetry_db.get_all()) + list(self.source_db.get_all())
        )
        usable = count(
            list(self.poetry_db.get_by_gender(gender))
            + list(self.source_db.get_by_gender(gender))
        )

        if not total:
            return f"还没有收录「{label}」里可作名字的典故，换一类试试"
        if not usable:
            return f"「{label}」里还没有适合作名字的典故，换一类试试"
        return (
            f"「{label}」里的字句没能组出合适的名字，"
            "换一类，或改用直接推荐"
        )

    def _build_names(
        self,
        surname: str,
        gender: str,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int,
        name_length: int,
        max_results: int,
        use_bazi: bool,
        use_poetry: bool,
        style: Optional[str],
        meanings: Optional[list[str]],
        avoid_chars: Optional[list[str]],
        target_min: int,
        selected_chars: Optional[list[str]] = None,
        source_classes: Optional[list[str]] = None,
        generational_char: Optional[str] = None,
        exclude_names: Optional[list[str]] = None,
        shuffle: bool = False,
    ) -> tuple:
        """核心起名流程（八字 → 候选字 → 出处匹配 → 组名 → 门槛/韵味 → 排序/多样性/截取）。"""
        # 1. 八字分析（如提供生辰）
        bazi_result = None
        xiyong_wuxing = None
        yong_wuxing = None
        ji_wuxing = None
        if use_bazi and year and month and day:
            bazi_result = self.bazi.generate_bazi(
                year, month, day, hour, minute, gender
            )
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]
            yong_wuxing = bazi_result["xiyong"]["yong_wuxing"]
            ji_wuxing = bazi_result["xiyong"]["ji_wuxing"]

        # 0. 会话黑名单 = 负面字 + 用户避讳字（硬过滤）
        blacklist = set(NEGATIVE_CHARS)
        if avoid_chars:
            for item in avoid_chars:
                if item:
                    blacklist.update(list(item))

        # 2. 候选字筛选
        candidate_chars = self._select_candidate_chars(
            xiyong_wuxing, gender, name_length, blacklist, meanings
        )

        # 2.5 先字模式（用户点选候选字）：语义 = 「名字必须含所选字」（任一位置）。
        #     关键：**不把 candidate_chars 缩成所选字**。缩池是旧实现，对单个字必然 0 结果
        #     （一个字无法自成字对），实测「清/月/秋」等常用字全部空手。
        #     此处只做「池外所选字补齐」（让随机组合路径也能拿到该字），
        #     真正的「含所选字」约束在 _compose_names 内执行，两条路径都过语义层。
        if selected_chars:
            have = {c["char"] for c in candidate_chars}
            for ch in set(selected_chars) - have:
                info = self.char_db.get_char(ch)
                if info and info["char"] not in blacklist:
                    candidate_chars.append(info)

        # 3. 出处匹配（诗词 + 字源，统一出处抽象）
        provenance_matches = self._match_provenance(
            xiyong_wuxing, gender, style, meanings, blacklist,
            use_poetry=use_poetry, source_classes=source_classes,
        )

        # 4. 生成名字组合
        #    「换一批」的排除名单在 emit() 里硬剔除（与 seen_names 同一处收口），
        #    **不放大候选池**：放大是「先算完再剔」的补丁，而 cap 随 pool_size 线性
        #    增长——实测 exclude=120 时延迟从 109ms 涨到 893ms（cap 600 → 5040）。
        #    改为组合时跳过之后，cap 恒为 600，延迟不随排除名单长度变化。
        skip = {x for x in (exclude_names or []) if x}
        names = self._compose_names(
            surname, candidate_chars, provenance_matches,
            gender, name_length, bazi_result, blacklist, meanings,
            target_min=target_min, pool_size=max_results,
            selected_chars=selected_chars, source_classes=source_classes,
            generational_char=generational_char, exclude_given=skip,
        )
        if skip:
            # emit() 已剔除；这里再滤一次是双保险，防止将来新增路径绕过 emit。
            names = [n for n in names if n.get("given_name") not in skip]

        # 5. 韵味排序（韵味降序 → 喜用神 → 寓意 → 风格 tie-break）
        #    → 多样性重排 → 分层抽样（八字分层配额 + 偏好硬分流）→ 剥离内部标记
        names = self._rank_by_yunwei(names, xiyong_wuxing, meanings, style)
        names = self._diversify(names, max_same_char=2)
        names = self._stratified_sample(
            names, max_results,
            yong_wuxing=yong_wuxing, xi_wuxing=xiyong_wuxing,
            meanings=meanings, style=style, shuffle=shuffle,
        )
        for n in names:
            n.pop("_tier", None)
            n.pop("_selected_hits", None)

        return bazi_result, names

    @staticmethod
    def _diversify(names: list[dict], max_same_char: int = 2) -> list[dict]:
        """
        多样性重排：限制同一个字（尤其名字首字）在结果中反复出现。

        贪心策略——按韵味分降序遍历（调用方已排序），维护每个字已出现次数：
        - 首字出现 >= max_same_char 次则暂缓放入 deferred；
        - 否则纳入，并累加该名字所有字的出现次数。
        被跳过的 deferred 仍按韵味分降序补到末尾。不删除任何名字。
        """
        if not names or max_same_char < 1:
            return names

        counts: dict[str, int] = {}
        kept: list[dict] = []
        deferred: list[dict] = []

        for name in names:
            given_name = name.get("given_name", "")
            first_char = given_name[0] if given_name else ""

            if first_char and counts.get(first_char, 0) >= max_same_char:
                deferred.append(name)
                continue

            kept.append(name)
            for ch in given_name:
                counts[ch] = counts.get(ch, 0) + 1

        deferred.sort(key=lambda n: n["scores"]["yunwei"], reverse=True)
        return kept + deferred

    @staticmethod
    def _weighted_pick(
        pool: list[dict],
        n: int,
        temperature: float = 10.0,
        weight_of=None,
    ) -> list[dict]:
        """从候选池按权重软加权不放回抽取 n 个（高分概率更高，结果随机）。

        weight_of 可覆盖默认权重（默认取 scores.yunwei）；调用方可借此混入
        与用户输入相关的加分（如「含用神字」），让抽样结果随输入变化。
        调用方需保证 pool 已按展示优先级降序；返回结果未排序。
        """
        import math

        if n <= 0 or not pool:
            return []
        if len(pool) <= n:
            picked = list(pool)
            random.shuffle(picked)
            return picked

        if weight_of is None:
            weights = [math.exp(x["scores"]["yunwei"] / temperature) for x in pool]
        else:
            weights = [math.exp(weight_of(x) / temperature) for x in pool]
        indices = list(range(len(pool)))
        total = sum(weights)
        picked: list[dict] = []
        for _ in range(n):
            if not indices or total <= 0:
                break
            r = random.random() * total
            cum = 0.0
            chosen = indices[-1]
            for idx in indices:
                cum += weights[idx]
                if r <= cum:
                    chosen = idx
                    break
            picked.append(pool[chosen])
            indices.remove(chosen)
            total -= weights[chosen]
        return picked

    @staticmethod
    def _weighted_sample(
        names: list[dict],
        k: int,
        temperature: float = 10.0,
    ) -> list[dict]:
        """
        加权随机采样（整体池，保留旧语义：无分层时使用）。

        从韵味分降序的候选里取前若干高分做软加权不放回抽样，抽出 k 个：
        高分名字被抽中概率更高（质量下限）+ 每次结果不同（随机性），
        结果按韵味分降序返回。
        """
        if not names:
            return names
        if len(names) <= k:
            sampled = list(names)
            random.shuffle(sampled)
            return sampled

        pool_size = max(4 * k, 60)
        picked = NamingEngine._weighted_pick(list(names[:pool_size]), k, temperature)
        picked.sort(key=lambda n: -n["scores"]["yunwei"])
        return picked

    @staticmethod
    def _wuxing_layer(
        name: dict,
        yong_wuxing: Optional[str],
        xi_wuxing: Optional[list[str]],
    ) -> str:
        """按八字喜忌给名字分层。

        - full：名字用字全部命中喜神（八字最优）
        - partial：含至少一个非喜用神（即忌神）字

        注意：`BaziEngine` 里忌神恒为喜神的补集，所以不存在「既非喜神又非忌神」的中性字，
        原先的 yong/xi/neutral 三层里 neutral 恒为空。此处按「命中比例」重构为两层，
        用神命中改为同层内的权重加分（见 STRATIFY_YONG_BONUS）。
        """
        if not xi_wuxing:
            return "full"
        wuxings = [c.get("wuxing") for c in name.get("chars_info", [])]
        if wuxings and all(w in xi_wuxing for w in wuxings):
            return "full"
        return "partial"

    @staticmethod
    def _pref_hits(
        name: dict,
        meanings: Optional[list[str]],
        style: Optional[str],
    ) -> int:
        """名字的偏好命中数（寓意命中 + 风格命中），用于偏好硬分流。"""
        entry = name.get("poetry") or {}
        imagery = " ".join(entry.get("imagery", []) or [])
        scene = entry.get("scene", "") or ""
        text = entry.get("text", "") or ""

        hits = 0
        if meanings:
            char_text = "".join(
                (c.get("meaning") or "") for c in name.get("chars_info", [])
            )
            hits += NamingEngine._meanings_match_score(
                f"{char_text} {imagery} {scene}", meanings
            )
        if style and style in STYLE_OPTIONS:
            hits += NamingEngine._keyword_hits(
                f"{imagery} {scene} {text}",
                STYLE_OPTIONS[style].get("imagery_keywords", []),
            )
        return hits

    def _banded_window(self, window: list[dict], n: int) -> list[dict]:
        """对抽样窗口做质量带宽过滤（只保留「韵味 ≥ 窗口最高分 − 带宽」的名字）。

        ｜为什么要「逐步放宽」而不是「不够就放弃」：
        女性路径的同源名池只有约 186 条（男性 242），每层带宽后候选常常不足
        n × STRATIFY_BAND_MIN_FACTOR。原实现此时**整体放弃带宽**，于是又退回
        无过滤状态、让 40 分级弱名漏进 TopN —— 正是「女性结果尾部偏差」的机制。
        现在改为**按 1.5 倍逐档放宽带宽**，在候选天生偏少的输入上也能兜到
        尽可能高的质量底线，而不是二元地「要么全过滤、要么不过滤」。
        """
        band = self.STRATIFY_QUALITY_BAND
        if not band or len(window) <= n:
            return window
        scores = [x["scores"]["yunwei"] for x in window]
        top, lowest = max(scores), min(scores)
        span = top - lowest
        if span <= band:
            return window  # 整个窗口都在带宽内，无需过滤
        need = n * self.STRATIFY_BAND_MIN_FACTOR
        b = band
        while b < span:
            kept = [x for x in window if x["scores"]["yunwei"] >= top - b]
            if len(kept) >= need:
                return kept
            b *= 1.5
        return window  # 放宽到全窗口仍不足 need，只能不过滤

    def _cohesion_window(self, names: list[dict], k: int) -> list[dict]:
        """组合成立度门槛：优先只用「两字在原文中成对」的同源名。

        为什么单独做成一道门槛而不是并进韵味分：
        韵味分是「相对带宽 + 加权采样」，只能表达「这个比那个高几分」，
        无法表达「整类不要」。实测把跨句同源从 35 压到 22 分后，
        它与单字出处（20 分）几乎持平，反而丢掉区分度、让单字弱名漏进 Top。
        成对/不成对是**类别差异**，就该用类别门槛表达。

        成对候选不足 k × COHESION_MIN_FACTOR 时退回全集——
        宁可出几个跨句拼接，也不要让用户拿到不足数的结果。
        """
        paired = [
            x for x in names
            if (x.get("scores", {}).get("yunwei_detail") or {}).get("cohesion")
            in self.COHESION_PAIRED_KINDS
        ]
        if len(paired) >= k * self.COHESION_MIN_FACTOR:
            return paired
        return names

    @staticmethod
    def _dedupe_reverse_pairs(names: list[dict]) -> list[dict]:
        """去掉「同字对反序」的重复名（杨柳 / 柳杨），保留韵味分更高的那个语序。

        两字不同而出处不同时，`_order_two_chars` 会分别按各自原文语序输出，
        导致「杨柳」与「柳杨」同时上榜 —— 对用户是明显的重复感。
        单字名与叠字名不受影响。
        """
        out: list[dict] = []
        seen: dict[frozenset, int] = {}
        for n in names:
            given = n.get("given_name") or ""
            if len(given) != 2 or given[0] == given[1]:
                out.append(n)
                continue
            key = frozenset(given)
            idx = seen.get(key)
            if idx is None:
                seen[key] = len(out)
                out.append(n)
            elif n["scores"]["yunwei"] > out[idx]["scores"]["yunwei"]:
                out[idx] = n
        return out

    def _stratified_sample(
        self,
        names: list[dict],
        k: int,
        yong_wuxing: Optional[str] = None,
        xi_wuxing: Optional[list[str]] = None,
        meanings: Optional[list[str]] = None,
        style: Optional[str] = None,
        temperature: Optional[float] = None,
        shuffle: bool = False,
    ) -> list[dict]:
        """分层抽样（最终截取阶段；P3 主排序改造，替代整体加权采样）。

        目的：让「八字 + 偏好」真正改变输出形态，而不是只在同分时做 tie-break。

        规则：
        1) 偏好硬分流：给了寓意/风格时，先按偏好命中取 pref_quota
           （= min(k, TARGET_MIN)，若存在命中者）席位，保证偏好真正生效。
        2) 八字分层配额：其余名额按 全喜神层 : 含非喜用神层 = 8 : 2 分配。
        3) 层内权重 = 韵味分 + 用神命中加分（随八字变化）→ 兼顾质量、多样、抗常客。
        4) 某层不足时名额顺延给其余层；无八字信息时退化为单一池加权采样。

        返回顺序：
        - shuffle=False（默认）：韵味分降序（脚本/评测要可复现的榜单）。
        - shuffle=True：打乱。**抽到什么排什么**——产品要的是抽卡感，
          按分数排队等于每次都在告诉用户「后面几个是将就的」，
          而后面的名字其实同样过了全部门槛。见 `generate_names` 同名参数说明。
        """
        if not names:
            return names
        # 同字对反序去重（杨柳 / 柳杨）：同一对字不应在榜单里出现两次，观感像 bug
        names = self._dedupe_reverse_pairs(names)
        # 组合成立度门槛（先于质量带宽）：只看「原文成对」的同源名，
        # 不足时才放开到跨句拼接 / 单字出处。
        names = self._cohesion_window(names, k)
        if len(names) <= k:
            sampled = list(names)
            if shuffle:
                random.shuffle(sampled)
            return sampled

        k = min(k, len(names))
        temp = self.STRATIFY_TEMPERATURE if temperature is None else temperature
        picked: list[dict] = []
        picked_ids: set[int] = set()

        def yong_bonus(n: dict) -> float:
            """含用神字的加权加分（用神随生日变化 → 抽样结果随输入变化）。"""
            if not yong_wuxing or not self.STRATIFY_YONG_BONUS:
                return 0.0
            return self.STRATIFY_YONG_BONUS * sum(
                1 for c in n.get("chars_info", []) if c.get("wuxing") == yong_wuxing
            )

        def weight_of(n: dict) -> float:
            """层内抽样权重 = 韵味分 + 八字相关加分（随输入变化 → 抗常客）。"""
            w = n["scores"]["yunwei"] + yong_bonus(n)
            # 名字感：5 分比 3 分高 2×TASTE_BONUS（默认 16），让好名字先浮上来；
            # 1 分已在组合阶段屏蔽，这里只需处理 3/4/5 三档
            w += self.TASTE_BONUS * (n.get("_taste", 3) - 3)
            if self.STRATIFY_COVER_BONUS and xi_wuxing:
                covered = {
                    c.get("wuxing") for c in n.get("chars_info", [])
                    if c.get("wuxing") in xi_wuxing
                }
                w += self.STRATIFY_COVER_BONUS * len(covered)
            return w

        def take(
            pool: list[dict],
            n: int,
            weight=None,
            temperature: Optional[float] = None,
        ) -> None:
            if n <= 0:
                return
            avail = [x for x in pool if id(x) not in picked_ids]
            if not avail:
                return
            w = weight or weight_of
            t = temp if temperature is None else temperature
            cap = max(
                int(k * self.STRATIFY_POOL_FACTOR), self.STRATIFY_POOL_MIN
            )  # 扩大参与抽样的候选池，避免总是同样的高分区

            # 同批用字去重：语料里「清」系字对特别多（清扬/清浅/清润/清晓…），不加
            # 约束时一批 6 个能出三个「清」，观感像系统只会拼一个字。约束必须**逐字
            # 施加**——先筛一遍再由 _weighted_pick 一次选 n 个是无效的（窗口里两个
            # 「清」各自只占 1 次，选完就变 3 次）。
            used: dict[str, int] = defaultdict(int)
            for p in picked:
                for ch in (p.get("given_name") or ""):
                    used[ch] += 1
            target = len(picked) + n
            while len(picked) < target:
                cands = [
                    x for x in avail
                    if id(x) not in picked_ids
                    and all(
                        used[ch] < self.CHAR_REPEAT_CAP
                        for ch in (x.get("given_name") or "")
                    )
                ]
                if not cands:
                    break
                cands.sort(key=lambda x: -w(x))
                g = NamingEngine._weighted_pick(
                    # 带宽必须按「本批要几个」算，不能按 1 算：_banded_window 的
                    # need = n × STRATIFY_BAND_MIN_FACTOR，n=1 会把窗口压到最高分
                    # 那几名，于是每次换一批都回到同一批名字（实测唯一名 32→20）。
                    self._banded_window(cands[:cap], n), 1, t, weight_of=w
                )[0]
                picked_ids.add(id(g))
                picked.append(g)
                for ch in (g.get("given_name") or ""):
                    used[ch] += 1

        # 1) 偏好硬分流
        has_pref = bool(meanings or (style and style in STYLE_OPTIONS))
        if has_pref:
            hits_of = {id(n): self._pref_hits(n, meanings, style) for n in names}
            pref_pool = [n for n in names if hits_of[id(n)] > 0]
            pref_pool.sort(
                key=lambda n: (-hits_of[id(n)], -n["scores"]["yunwei"])
            )
            if pref_pool:
                def pref_weight(n: dict) -> float:
                    """偏好层权重：韵味 + 命中项数加成（命中越多越靠前）。"""
                    return weight_of(n) + self.PREF_HIT_BONUS * hits_of[id(n)]

                # 偏好池**不许吃满整批**：命中池可能只有七八个名字（风格越窄越小），
                # 若把 k 个名额全给它，每次「换一批」就是这七八个的排列组合，
                # 扩库进来的名字永远轮不到（实测某输入连翻 12 批只出 14 个）。
                # 留两三席给非命中池，偏好照样看得见，池子也能转动。
                quota = max(2, round(k * self.PREF_QUOTA_RATIO))
                take(
                    pref_pool,
                    min(k, quota, TARGET_MIN),
                    weight=pref_weight,
                    temperature=self.PREF_TEMPERATURE,
                )

        # 1.5) 气质出处层：选了气质，就先按该气质的典籍取够一半名额。
        # 只调权重不够 —— 到这一步排序已被韵味分与用神配额压平，实测选「古风」
        # 反而比不选更少出古典出处（见 STYLE_SOURCE_RATIO 处的实测记录）。
        remaining = k - len(picked)
        if remaining > 0 and style and style in STYLE_OPTIONS:
            prefs = set(STYLE_OPTIONS[style].get("source_preference") or [])
            style_pool = [
                n for n in names
                if (n.get("poetry") or {}).get("source") in prefs
            ]
            q_style = max(2, round(k * self.STYLE_SOURCE_RATIO))
            if style_pool:
                take(style_pool, min(remaining, q_style))

        # 2) 八字分层配额
        remaining = k - len(picked)
        if remaining > 0 and (yong_wuxing or xi_wuxing):
            layers: dict[str, list[dict]] = {"full": [], "partial": []}
            for n in names:
                if id(n) in picked_ids:
                    continue
                layers[self._wuxing_layer(n, yong_wuxing, xi_wuxing)].append(n)
            q_full = round(k * self.STRATIFY_FULL_RATIO)
            for layer, quota in (("full", q_full), ("partial", k - q_full)):
                if remaining <= 0:
                    break
                take(layers[layer], min(quota, remaining))
                remaining = k - len(picked)
            if remaining > 0:  # 层不足 → 顺延
                take(names, remaining)
        elif remaining > 0:
            take(names, remaining)

        # 3) 兜底（理论不会触达）
        if len(picked) < k:
            for n in names:
                if len(picked) >= k:
                    break
                if id(n) not in picked_ids:
                    picked_ids.add(id(n))
                    picked.append(n)

        # 4) 摆盘：默认按韵味降序（榜单语义）；shuffle 时打乱，只改顺序不改选谁
        if shuffle:
            random.shuffle(picked)
        else:
            picked.sort(key=lambda n: -n["scores"]["yunwei"])
        return picked

    def _rank_by_yunwei(
        self,
        names: list[dict],
        xiyong_wuxing: Optional[list[str]],
        meanings: Optional[list[str]],
        style: Optional[str],
    ) -> list[dict]:
        """韵味降序排序，同分依次按喜用神命中数 → 寓意命中数 → 风格命中数 tie-break。"""

        def xiyong_hits(n: dict) -> int:
            if not xiyong_wuxing:
                return 0
            return sum(
                1 for c in n.get("chars_info", [])
                if c.get("wuxing") in xiyong_wuxing
            )

        def meaning_hits(n: dict) -> int:
            if not meanings:
                return 0
            text = "".join(
                (c.get("meaning") or "") for c in n.get("chars_info", [])
            )
            return NamingEngine._meanings_match_score(text, meanings)

        def style_hits(n: dict) -> int:
            if not style or style not in STYLE_OPTIONS:
                return 0
            entry = n.get("poetry") or {}
            blob = " ".join(entry.get("imagery", []) or []) + " "
            blob += (entry.get("scene", "") or "") + " "
            blob += (entry.get("text", "") or "")
            return NamingEngine._keyword_hits(
                blob, STYLE_OPTIONS[style].get("imagery_keywords", [])
            )

        names.sort(
            key=lambda n: (
                -n["scores"]["yunwei"],
                # 先字模式：含更多所选字的组合优先（用户点选即意图，强于八字/寓意 tie-break）
                -n.get("_selected_hits", 0),
                -xiyong_hits(n),
                -meaning_hits(n),
                -style_hits(n),
            )
        )
        return names

    def _select_candidate_chars(
        self,
        xiyong_wuxing: list[str] = None,
        gender: str = "male",
        name_length: int = 2,
        blacklist: set = None,
        meanings: Optional[list[str]] = None,
        ji_wuxing: Optional[list[str]] = None,
    ) -> list[dict]:
        """筛选候选字（黑名单硬过滤 + 出处白名单 + 寓意关键词硬前置）。

        出处白名单（关键质量闸门）：候选字必须来自「诗词/古文出处推荐过的字」并集，
        否则会出现「订/切/叫/口/轧」这类无出处、无字义的字被按笔画归入某五行后混进名字。
        产品定位是「有据可循」——每个名字用字都应有出处与语境义项。
        例外：情绪字（哀悲愁怨恨怒）按用户的「分级放开」决定仍进候选池，
        由 `_evaluate_name` 的软门槛（须有出处 + 非全情绪字）把关。

        3a：提供 ji_wuxing 时，混入「非喜用神字」按约 3:7 稀释（用户已确认接受）。
        注意：`BaziEngine` 中忌神恒为喜神的补集，因此「非喜用神字」== 「忌神字」，
        不存在既非喜神又非忌神的中性字。混入后由 `_pass_gate` 保证不会出现「全忌神」名字。
        代价：八字匹配度由「全部满分」降为「大部分高分」。
        """
        blacklist = blacklist or set()
        provenance = self._provenance_chars()
        if xiyong_wuxing:
            chars = []
            for wx in xiyong_wuxing:
                chars.extend(self.char_db.get_by_wuxing(wx, gender))
            # 3a：混入非喜用神字（忌神行），稀释「候选池全是喜用神字」
            if ji_wuxing:
                xi_set = set(xiyong_wuxing)
                extra = [
                    c for c in self.char_db.filter(gender=gender)
                    if c["wuxing"] in set(ji_wuxing) and c["wuxing"] not in xi_set
                    and c["char"] in provenance
                ]
                n_extra = min(len(extra), max(12, len(chars) * 3 // 7))
                if n_extra > 0:
                    chars.extend(random.sample(extra, n_extra))
            if len(chars) < 20:
                all_chars = self.char_db.get_all()
                for c in all_chars:
                    if c not in chars:
                        if gender == "male":
                            if c["gender"] in ("男", "中"):
                                chars.append(c)
                        elif gender == "female":
                            if c["gender"] in ("女", "中"):
                                chars.append(c)
                        else:
                            chars.append(c)
        else:
            chars = self.char_db.filter(gender=gender)

        chars = [
            c for c in chars
            if c["char"] not in blacklist
            and (c["char"] in provenance or c["char"] in EMOTIONAL_CHARS)
        ]

        if meanings:
            chars.sort(
                key=lambda c: 0
                if self._meanings_match_score(c.get("meaning", ""), meanings) > 0
                else 1
            )

        return chars

    def _provenance_chars(self) -> set[str]:
        """全部出处（诗词 + 字源）推荐过的字并集——「有据可循」的用字白名单。

        只有这些字自带出处与语境义项，才允许进入候选字池。
        """
        if self._provenance_char_set is None:
            chars: set[str] = set()
            for entry in self.poetry_db.get_all(include_sad=True):
                chars.update(entry.get("recommend_chars") or [])
            for entry in self.source_db.get_all(include_sad=True):
                chars.update(entry.get("recommend_chars") or [])
            self._provenance_char_set = chars
        return self._provenance_char_set

    def _shuowen_entry_for(self, ci: dict) -> Optional[dict]:
        """单字名的「说文解字」出处（字有《说文》本义时优先使用）。

        单字名讲不了「成句/成对」的诗词叙事，用字源讲「本义」更贴切。
        构造一个轻量「说文解字·某部」条目（text=该字本义），优先于诗词出处展示。
        """
        shuowen = (ci.get("shuowen") or "").strip()
        if not shuowen:
            return None
        raw_radical = ci.get("radical", "") or ""
        radical = _RADICAL_TITLE_ALIAS.get(raw_radical, raw_radical) or "某"
        fam = build_radical_family_map().get(raw_radical, "")
        return {
            "id": None,
            "source": "说文解字",
            "source_class": "经史子集",
            "category": "字源",
            "title": f"{radical}部",
            "author": "许慎",
            "dynasty": "东汉",
            "text": shuowen,
            "original_text": shuowen,
            "citation": f"《说文解字·{radical}部》",
            "recommend_chars": [ci["char"]],
            "imagery": [fam] if fam else [],
            "scene": "",
            "emotion": "中性",
            "gender": "中",
        }

    def _char_affinity(
        self,
        surname: str,
        char_info: dict,
        meanings: Optional[list[str]] = None,
    ) -> float:
        """
        单字亲和分（组合阶段软加权）：姓氏意象呼应 + 寓意偏好命中。

        用于候选字排序/随机加权，让不同姓氏、不同偏好在组合阶段就产生差异。
        分数只影响选字优先级，不进入韵味评分、不做硬过滤。
        """
        score = 0.0
        surname_info = self.surname_db.get_surname(surname)
        if surname_info:
            tags = [t for t in (surname_info.get("imagery") or []) if t]
            text = " ".join(filter(None, [
                char_info.get("meaning", ""),
                char_info.get("detail", ""),
                char_info.get("shuowen", ""),
            ]))
            for tag in tags:
                if tag and tag in text:
                    score += 3.0
                    break
        if meanings:
            score += self._meanings_match_score(
                char_info.get("meaning", ""), meanings
            ) * 2.0
        return score

    @staticmethod
    def _weighted_char_choice(chars: list[dict], top_n: int = 80) -> dict:
        """从候选字前 top_n（已按亲和分降序）里随机选一个，偏向姓氏/偏好匹配的字。"""
        pool = chars[:top_n]
        return random.choice(pool)

    def _same_source_partner(
        self, c1: dict, candidate_chars: list[dict]
    ) -> Optional[dict]:
        """从 c1 的**已批准字对**搭档里挑一个（语义层，取代旧的「推荐字共现」）。

        旧实现取「出现在同一条出处推荐字里的字」——那正是「一袋好字」的旧机制，
        会拼出「圣人」「荔枝」这类同源但不宜作名的组合，是用户体感「只是抠了两个字」的来源。
        现改为只认 `name_pairs`（LLM 判定宜作名 + 复核通过的组合）：
        取不到搭档时返回 None，调用方跳过该次尝试，不再退回机械拼接。
        """
        char = c1["char"]
        partners = [
            p for p in self.poetry_db.approved_partners(char)
            if self._pair_taste(char, p) > 1     # 屏蔽档不值得占一次尝试
        ]
        if not partners:
            return None
        allowed = {c["char"]: c for c in candidate_chars}
        usable = [allowed[ch] for ch in partners if ch in allowed and ch != char]
        if not usable:
            return None
        return random.choice(usable)

    def _pair_entry(
        self,
        a: str,
        b: str,
        gender: Optional[str] = None,
        source_classes: Optional[list[str]] = None,
    ) -> Optional[dict]:
        """取「已批准字对 (a,b)」所属的出处（性别口径内择优，取不到退回全集）。

        随机组合必须挂**字对真正被批准的那条出处**，否则详情页显示的出处里
        两字并不成对（cohesion 会退化成 same_clause/cross_clause），又回到旧问题。
        source_classes 给定时（先出处模式）只在所选类目内取，避免挂到别的典籍上。
        """
        entries = self.poetry_db.entries_for_pair(a, b)
        if not entries:
            return None
        if source_classes:
            wanted = set(source_classes)
            entries = [
                e for e in entries
                if e.get("source") in wanted or e.get("source_class") in wanted
            ]
            if not entries:
                return None
        scoped = self._filter_by_gender(entries, gender) if gender else entries
        return (scoped or entries)[0]

    def recommend_chars(
        self,
        surname: str,
        gender: str = "male",
        year: int = None,
        month: int = None,
        day: int = None,
        hour: int = 12,
        minute: int = 0,
        style: Optional[str] = None,
        meanings: Optional[list[str]] = None,
        avoid_chars: Optional[list[str]] = None,
        limit_per_group: int = 8,
    ) -> dict:
        """
        两阶段流程第一步：根据用户信息推荐选字范围（按五行分组，喜用神优先）。

        Returns:
            {"bazi": {...}|None,
             "groups": [{"wuxing": str, "is_xiyong": bool,
                         "total": int, "chars": [字摘要...]}],
             "total": int}
        """
        # 1. 八字（如提供生辰）
        bazi_result = None
        xiyong_wuxing = None
        if year and month and day:
            bazi_result = self.bazi.generate_bazi(year, month, day, hour, minute, gender)
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]

        # 2. 会话黑名单
        blacklist = set(NEGATIVE_CHARS)
        if avoid_chars:
            for item in avoid_chars:
                if item:
                    blacklist.update(list(item))

        # 3. 候选字（喜用神优先）
        candidate_chars = self._select_candidate_chars(
            xiyong_wuxing, gender, 2, blacklist, meanings
        )

        # 4. 姓氏结合预筛：剔除谐音歧义 / 本义冲突的字
        def fits_surname(c: dict) -> bool:
            taboo, _ = self.surname_fit.is_homophone_taboo(surname, c["char"])
            if taboo:
                return False
            conflict, _ = self.surname_fit.is_meaning_conflict(surname, c["char"])
            return not conflict

        candidate_chars = [c for c in candidate_chars if fits_surname(c)]

        # 5. 按五行分组，喜用神优先，每组取 top N
        xiyong_set = set(xiyong_wuxing or [])
        wuxing_order = list(xiyong_set) + [w for w in WUXING_LIST if w not in xiyong_set]
        groups = []
        for wx in wuxing_order:
            chars = [c for c in candidate_chars if c["wuxing"] == wx]
            if not chars:
                continue
            groups.append({
                "wuxing": wx,
                "is_xiyong": wx in xiyong_set,
                "total": len(chars),
                "chars": [self._char_brief(c) for c in chars[:limit_per_group]],
            })

        return {
            "bazi": bazi_result,
            "groups": groups,
            "total": sum(g["total"] for g in groups),
        }

    # ── 先字模式：可选字表（意象族 + 门槛感知可行性） ──

    def pickable_chars(
        self,
        surname: str,
        gender: str = "female",
        year: int = None,
        month: int = None,
        day: int = None,
        hour: int = 12,
        minute: int = 0,
        use_bazi: bool = False,
        name_length: int = 2,
        style: Optional[str] = None,
        meanings: Optional[list[str]] = None,
        imagery_families: Optional[list[str]] = None,
        avoid_chars: Optional[list[str]] = None,
        source_classes: Optional[list[str]] = None,
        generational_char: Optional[str] = None,
        limit: int = 400,
    ) -> dict:
        """「先字后出处」的可选字表：哪些字真的能组出名字，以及按什么顺序摆。

        为什么需要它（而不是让前端按字库直接铺满）：
        先字模式的产能 = 「该字在已批准字对里的搭档数」，语料标注量决定供给上限。
        池内 553 字里只有约一半出得来名字，且**与姓氏强相关**（姓「林」时名字两字
        全平触发三连同调，整类字全灭）。前端若把 0 覆盖的字也铺出来，用户点到就是
        「系统坏了」的体感。故字表必须由本接口按「门槛感知可行性」筛过。

        可行性镜像引擎的两条供给路径（与 scripts/diag_selected_chars.py 对拍零偏差）：
        A. 出处组合路径：出处须过 `_match_provenance` 可用性过滤；有标注出处只产标注
           字对，标注跑过但为空则不产双字名，从未标注才退回全交叉。
        B. 随机组合路径：搭档 =「已批准字对 ∩ 候选池」，音韵同分时两序都试。

        意象族（radical → 7 族）**只用于排序与分组，不作硬过滤**：实测 7 族仅覆盖
        池内 35%（196/553，金族仅 4 字），硬过滤会砍掉 65% 的好字（诗/思/安/宜
        这类无族属的字）。族的真实作用域是「字表怎么摆」——用户在格子里的选择
        （selected_chars）才是硬约束。

        Returns:
            {"bazi", "total", "feasible", "returned", "truncated",
             "families": [{"family", "count", "total", "selected", "sample"}],
             "no_family": int,
             "chars": [{"char","pinyin","wuxing","family","partner_count",
                        "name_hits","match","xiyong","sample","meaning"}]}

        契约（由 tests/test_pickable_chars.py 与 live 对拍强制）：
        chars 里每个字都能真的出名字；chars 之外的字一个都出不来。
        partner_count 只作展示（「组合力」），不参与入选判定。
        """
        # 0. 会话黑名单 = 负面字 + 用户避讳字（硬过滤）
        blacklist = set(NEGATIVE_CHARS)
        for item in (avoid_chars or []):
            if item:
                blacklist.update(list(item))

        # 1. 八字（可选）：喜用神用于标记，忌神用于门槛（名字全忌神硬排除）
        bazi_result = None
        xiyong_wuxing = None
        gate_bazi = None
        if use_bazi and year and month and day:
            bazi_result = self.bazi.generate_bazi(
                year, month, day, hour, minute, gender
            )
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]
            gate_bazi = {"xiyong": {"ji_wuxing": bazi_result["xiyong"]["ji_wuxing"]}}

        # 2. 候选池（出处白名单 + 性别 + 非黑名单）
        pool = {
            c["char"]: c
            for c in self._select_candidate_chars(
                xiyong_wuxing, gender, name_length, blacklist, meanings
            )
        }
        partner_index = {
            ch: {
                p for p in self.poetry_db.approved_partners(ch)
                if p in pool and self._pair_taste(ch, p) > 1
            }
            for ch in pool
        }

        # 3. 门槛层（与 _pass_gate 同源）：三连同调 + 音律 + 五格 + 姓氏谐音/本义 + 忌神
        def gate_ok(chars_info: list[dict]) -> Optional[str]:
            gn = "".join(c["char"] for c in chars_info)
            if self.surname_fit.tri_tone_conflict(
                surname, [c["char"] for c in chars_info]
            ):
                return None
            ph = self.phonetics.analyze(surname + gn)
            try:
                wg = self.wuge.calculate(surname, gn)
            except Exception:
                wg = {"total_score": 60}
            if not self._pass_gate(surname, gn, ph, wg, gate_bazi, chars_info):
                return None
            return gn

        hits: dict[str, list[str]] = defaultdict(list)
        seen: dict[str, set] = defaultdict(set)

        def record(chars: list[str], gn: str) -> None:
            for ch in chars:
                if gn not in seen[ch]:
                    seen[ch].add(gn)
                    hits[ch].append(gn)

        if name_length == 1:
            # 单字名没有「搭档」概念，只问该字本身过不过门槛
            for ch, ci in pool.items():
                if gate_ok([ci]):
                    record([ch], ch)
        elif generational_char:
            # ── 字辈模式：辈字固定第二个字 ──
            # 可选字 = 「与辈字能组成合格名字」的第一个字。辈字本身不放进字表
            # （它已由家族字辈锁定，不是用户要挑的），第一个字才是要挑的。
            gen_ci = self.char_db.get_char(generational_char)
            if gen_ci and generational_char not in blacklist:
                for ch, ci in pool.items():
                    if ch == generational_char:
                        continue
                    if gate_ok([ci, gen_ci]):
                        record([ch], ch + generational_char)
        else:
            # ── 供给 A：出处组合路径 ──
            for entry, _tier in self._match_provenance(
                xiyong_wuxing, gender, style, meanings, blacklist,
                source_classes=source_classes,
            ):
                by_char = {
                    c["char"]: c for c in self._get_valid_poem_chars(
                        entry, gender, xiyong_wuxing, blacklist, meanings
                    )
                }
                # 标注字对可能用到 recommend_chars 之外的字，一并补进可用字
                for pair in (entry.get("name_pairs") or []):
                    for ch in pair:
                        if ch in by_char or ch in blacklist:
                            continue
                        ci = self.char_db.get_char(ch)
                        if not ci:
                            continue
                        if gender == "male" and ci["gender"] not in ("男", "中"):
                            continue
                        if gender == "female" and ci["gender"] not in ("女", "中"):
                            continue
                        by_char[ch] = ci
                annotated = entry.get("name_pairs") or []
                known = entry.get("name_pairs_known", bool(annotated))
                # 与 _compose_names 同源：先按出处/音韵定字序，再判名字感。
                # 表里说「这个字出得来名字」，实际生成就必须出得来——所以这里不能
                # 只查正序，而要复现生成时真正采用的那一序。
                def pair_ok(a: str, b: str) -> bool:
                    first, second = self._order_two_chars(entry, by_char[a], by_char[b])
                    return self._pair_taste(first["char"], second["char"]) > 1

                if annotated:
                    pair_list = [
                        tuple(p) for p in annotated
                        if all(ch in by_char for ch in p) and pair_ok(p[0], p[1])
                    ]
                elif known:
                    pair_list = []      # 语义层已判定此出处无宜作名的组合
                else:
                    chars = list(by_char)
                    pair_list = [
                        (a, b)
                        for i, a in enumerate(chars) for b in chars[i + 1:]
                        if pair_ok(a, b)
                    ]
                for a, b in pair_list:
                    first, second = self._order_two_chars(entry, by_char[a], by_char[b])
                    gn = gate_ok([first, second])
                    if gn:
                        record([a, b], gn)

            # ── 供给 B：随机组合路径 ──
            for ch, ci in pool.items():
                for p in sorted(partner_index[ch]):
                    if p == ch:
                        continue
                    for first, second in self._order_candidates(ci, pool[p]):
                        # 与随机组合路径同源：屏蔽档不许占位。缺这一步时「云汉」的
                        # 搭档会以「汉云」（未定级=屏蔽）的语序记进字表，用户点到
                        # 「云」却拿不到名字。
                        if self._pair_taste(first["char"], second["char"]) <= 1:
                            continue
                        gn = gate_ok([first, second])
                        if gn:
                            record([ch, p], gn)
                            break

        # 4. 组装字表（族归属 + 偏好命中排序键）
        fam_map = build_radical_family_map()
        fam_selected = set(imagery_families or [])
        style_kws = (
            STYLE_OPTIONS[style].get("imagery_keywords", [])
            if style in STYLE_OPTIONS else []
        )
        rows = []
        for ch, ci in pool.items():
            names = sorted(set(hits.get(ch, [])))
            partners = partner_index[ch]
            # 入选门槛 = **真的出得来名字**，不是「有搭档字」。
            # 反例（实测）：姓林 + 「情」有 4 个已批准搭档（中/凝/兰/深），
            # 但 8 种字序全部三连同调全灭 → 用户点到就是空结果。
            # 只按搭档数入选会把这类字放进表里，正是要避免的「系统坏了」体感。
            if not names:
                continue
            family = fam_map.get(ci.get("radical", ""), "")
            meaning_hit = NamingEngine._meanings_match_score(
                f'{ci.get("meaning") or ""} {ci.get("detail") or ""}', meanings
            )
            style_hit = NamingEngine._keyword_hits(
                f'{" ".join(ci.get("imagery") or [])} {ci.get("meaning") or ""}',
                style_kws,
            )
            xi_hit = 1 if (xiyong_wuxing and ci.get("wuxing") in xiyong_wuxing) else 0
            rows.append({
                "char": ch,
                "pinyin": ci.get("pinyin", ""),
                "wuxing": ci.get("wuxing", ""),
                "family": family,
                "partner_count": len(partners),
                "name_hits": len(names),
                "match": (4 if (family and family in fam_selected) else 0)
                         + meaning_hit * 2 + style_hit + xi_hit * 2,
                "xiyong": bool(xi_hit),
                "sample": names[:3],
                "meaning": (ci.get("meaning") or "")[:50],
            })

        def row_key(r: dict) -> tuple:
            """排序：偏好命中 → 真能出多少名字 → 搭档数 → 字（稳定收尾）。"""
            return (-r["match"], -r["name_hits"], -r["partner_count"], r["char"])

        rows.sort(key=row_key)

        # 5. 截断（默认 400 已覆盖实测全员；若超限，保证每族至少留 2 字，
        #    否则用户点「金」筛选时会看到空表——金族全池仅 4 字，按名次必被截掉）
        limit = max(1, min(int(limit or 400), 400))
        chars = rows[:limit]
        kept = {r["char"] for r in chars}
        backup: list[dict] = []
        by_family: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            if r["family"]:
                by_family[r["family"]].append(r)
        for family in IMAGERY_FAMILY_PRIORITY:
            present = sum(1 for r in chars if r["family"] == family)
            for r in by_family.get(family, [])[: max(0, 2 - present)]:
                if r["char"] not in kept:
                    backup.append(r)
                    kept.add(r["char"])
        if backup:
            chars = sorted(chars + backup, key=row_key)

        return {
            "bazi": bazi_result,
            "total": len(pool),          # 池内字数（有出处、性别相符、非黑名单）
            "feasible": len(rows),       # 真出得来名字的字数（字表实际可选范围）
            "returned": len(chars),
            "truncated": len(chars) < len(rows),
            "no_family": sum(1 for r in chars if not r["family"]),
            "families": [
                {
                    "family": family,
                    "count": sum(1 for r in chars if r["family"] == family),
                    "total": len(by_family.get(family, [])),
                    "selected": family in fam_selected,
                    "sample": [r["char"] for r in by_family.get(family, [])[:6]],
                }
                for family in IMAGERY_FAMILY_PRIORITY
            ],
            "chars": chars,
        }

    @staticmethod
    def _char_brief(c: dict) -> dict:
        """字摘要（选字推荐用，精简字段）。"""
        return {
            "char": c.get("char", ""),
            "pinyin": c.get("pinyin", ""),
            "wuxing": c.get("wuxing", ""),
            "kangxi_strokes": c.get("kangxi_strokes", 0),
            "gender": c.get("gender", "中"),
            "meaning": c.get("meaning", ""),
        }

    # ── 来源推荐（寓意优先 / 命格优先 两模式流程） ──

    def _source_wuxing_tendency(self, entry: dict) -> dict:
        """计算一条来源（诗词/字源）的五行倾向：基于推荐字的五行分布。"""
        dist: dict[str, int] = {}
        for ch in entry.get("recommend_chars", []):
            ci = self.char_db.get_char(ch)
            if not ci:
                continue
            wx = ci.get("wuxing", "")
            if wx:
                dist[wx] = dist.get(wx, 0) + 1
        if not dist:
            return {"wuxing_dist": {}, "tendency": [], "dominant": ""}
        max_cnt = max(dist.values())
        tendency = sorted(w for w, c in dist.items() if c == max_cnt)
        return {
            "wuxing_dist": dist,
            "tendency": tendency,
            "dominant": tendency[0],
        }

    @staticmethod
    def _entry_key(entry: dict) -> tuple:
        """出处条目的去重键 —— 按 id，**不按 (source, title)**。

        一个篇目可以合法地贡献多个短句单元：《离骚》14 条、《浣溪沙》57 条、
        《水调歌头》12 条，都是同篇下的不同句子，各有自己的推荐字与字对。
        按篇名去重会把它们当成重复整条丢掉——实测全库 1233 条里有 654 条
        （53%）从未进入候选，其中五代词 57 首《浣溪沙》只剩 1 首可出。
        「五代词出不了名字」的真正原因在这里，而不是语料性质。

        真正需要防的只有「同一条目被加载两次」，那用 id 就够。
        """
        return (entry.get("id") or "", entry.get("source"), entry.get("title"))

    def _available_source_entries(self, gender: str, blacklist: set) -> list[dict]:
        """收集所有可用来源（诗词 + 字源，排除哀伤、无可用推荐字）。"""
        entries: list[dict] = []
        entries.extend(self.poetry_db.get_by_gender(gender))
        entries.extend(self.source_db.get_by_gender(gender))
        blacklist = blacklist or set()
        seen: set = set()
        result: list[dict] = []
        for entry in entries:
            key = NamingEngine._entry_key(entry)
            if key in seen:
                continue
            seen.add(key)
            if self._is_sad_poem(entry):
                continue
            available = [
                c for c in entry.get("recommend_chars", [])
                if self.char_db.get_char(c) and c not in blacklist
            ]
            if not available:
                continue
            result.append(entry)
        return result

    def _find_source_by_id(self, source_id: str) -> Optional[dict]:
        """按 id 定位来源（诗词或字源）。"""
        for entry in self.poetry_db.get_all(include_sad=True):
            if entry.get("id") == source_id:
                return entry
        for entry in self.source_db.get_all(include_sad=True):
            if entry.get("id") == source_id:
                return entry
        return None

    @staticmethod
    def _bazi_explanation(bazi_result: Optional[dict]) -> Optional[dict]:
        """命格优先：把八字结果包装成人话解释 + 起名方向建议。"""
        if not bazi_result:
            return None
        xiyong = bazi_result.get("xiyong") or {}
        xi = xiyong.get("xi_wuxing", [])
        ji = xiyong.get("ji_wuxing", [])
        return {
            "day_master": xiyong.get("day_master", ""),
            "day_master_wuxing": xiyong.get("day_master_wuxing", ""),
            "strength_label": xiyong.get("strength_label", ""),
            "xi_wuxing": xi,
            "yong_wuxing": xiyong.get("yong_wuxing", ""),
            "ji_wuxing": ji,
            "suggestion": (
                f"命格{xiyong.get('strength_label', '')}，喜用神为"
                f"{'、'.join(xi) or '—'}，建议名字用{'、'.join(xi) or '喜用'}行字，"
                f"避开{'、'.join(ji) or '忌神'}行字。"
            ),
            "detail": xiyong.get("explanation", ""),
        }

    def recommend_sources(
        self,
        surname: str,
        gender: str = "male",
        year: int = None,
        month: int = None,
        day: int = None,
        hour: int = 12,
        minute: int = 0,
        mode: str = "bazi_first",
        meanings: Optional[list[str]] = None,
        avoid_chars: Optional[list[str]] = None,
        limit: int = 20,
    ) -> dict:
        """
        两模式流程第一步：推荐「来源」（诗句/古文），先不确定字。

        - mode="meaning_first"：按寓意匹配度排序（八字仅作忌神避让提示）
        - mode="bazi_first"：先给八字解释 + 方向，来源按喜用神倾向排序

        Returns:
            {"mode", "bazi", "bazi_explanation", "sources": [...], "total"}
        """
        bazi_result = None
        xiyong_wuxing: list[str] = []
        ji_wuxing: list[str] = []
        if year and month and day:
            bazi_result = self.bazi.generate_bazi(year, month, day, hour, minute, gender)
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]
            ji_wuxing = bazi_result["xiyong"]["ji_wuxing"]

        blacklist = set(NEGATIVE_CHARS)
        if avoid_chars:
            for item in avoid_chars:
                if item:
                    blacklist.update(list(item))

        entries = self._available_source_entries(gender, blacklist)

        xi_set = set(xiyong_wuxing)
        ji_set = set(ji_wuxing)

        decorated = []
        for entry in entries:
            tendency = self._source_wuxing_tendency(entry)
            blob = " ".join(entry.get("imagery", []) or []) + " "
            blob += (entry.get("scene", "") or "") + " "
            blob += (entry.get("text", "") or "")
            meaning_score = (
                self._meanings_match_score(blob, meanings) if meanings else 0
            )
            dom = tendency["dominant"]
            if dom and dom in xi_set:
                bazi_flag = "xiyong"
            elif dom and dom in ji_set:
                bazi_flag = "ji"
            else:
                bazi_flag = "neutral"
            decorated.append((entry, tendency, meaning_score, bazi_flag))

        def sort_key(item):
            _e, _t, m_score, flag = item
            flag_rank = {"xiyong": 0, "neutral": 1, "ji": 2}
            if mode == "bazi_first":
                return (flag_rank[flag], -m_score)
            # 寓意优先：寓意分降序，忌神倾向在同分内排后
            return (-m_score, flag_rank[flag])

        decorated.sort(key=sort_key)

        # 分层洗牌：按「命中强度」分档（而非只分命中/未命中），档内随机打乱
        #   → 换一批有变化；强命中档优先占据名额 → 不同偏好给出不同来源
        def bucket(item):
            _e, _t, m_score, flag = item
            if mode == "bazi_first":
                if flag == "xiyong":
                    return 0 if m_score >= 2 else (1 if m_score == 1 else 2)
                if flag == "neutral":
                    return 3 if m_score > 0 else 4
                return 5
            # 寓意优先：寓意是核心，八字只做「忌神避让」——
            #   故偏好命中优先于忌神避让，忌神仅在同强度内退后（避让提示由 reason 承载）。
            #   强命中 → 强命中(忌) → 弱命中 → 弱命中(忌) → 未命中(非忌) → 忌神兜底
            if m_score >= 2:
                return 0 if flag != "ji" else 1
            if m_score == 1:
                return 2 if flag != "ji" else 3
            return 4 if flag != "ji" else 5

        buckets: dict[int, list] = {}
        for item in decorated:
            buckets.setdefault(bucket(item), []).append(item)
        ordered = []
        for b in sorted(buckets):
            group = buckets[b]
            random.shuffle(group)
            ordered.extend(group)
        decorated = ordered

        sources = []
        for entry, tendency, m_score, flag in decorated:
            sources.append(
                self._source_brief(entry, tendency, flag, m_score, meanings)
            )
            if len(sources) >= limit:
                break

        return {
            "mode": mode,
            "bazi": bazi_result,
            "bazi_explanation": self._bazi_explanation(bazi_result),
            "sources": sources,
            "total": len(sources),
        }

    def _source_brief(
        self,
        entry: dict,
        tendency: dict,
        flag: str,
        m_score: int,
        meanings: Optional[list[str]],
    ) -> dict:
        """来源摘要（来源推荐用）。"""
        reason = ""
        if flag == "xiyong":
            reason = f"意境偏{tendency['dominant']}，契合命格喜用神"
        elif flag == "ji":
            reason = f"意境偏{tendency['dominant']}，与命格忌神相冲，建议避开"
        if m_score > 0 and meanings:
            names = [MEANING_OPTIONS[m].get("name", m) for m in meanings]
            reason = (reason + "；" if reason else "") + "契合寓意「" + "、".join(names) + "」"
        if not reason:
            reason = "意境中正，可供参考"
        return {
            "id": entry.get("id", ""),
            "source": entry.get("source", ""),
            "source_class": entry.get("source_class", entry.get("source", "")),
            "title": entry.get("title", ""),
            "author": entry.get("author", "佚名"),
            "dynasty": entry.get("dynasty", ""),
            "text": entry.get("text", ""),
            "citation": entry.get("citation", ""),
            "imagery": entry.get("imagery", []),
            "scene": entry.get("scene", ""),
            "recommend_chars": entry.get("recommend_chars", []),
            "wuxing_tendency": tendency["dominant"],
            "wuxing_dist": tendency["wuxing_dist"],
            "bazi_flag": flag,
            "match_reason": reason,
        }

    def source_chars(
        self,
        surname: str,
        gender: str = "male",
        year: int = None,
        month: int = None,
        day: int = None,
        hour: int = 12,
        minute: int = 0,
        source_ids: Optional[list[str]] = None,
        limit_per_source: int = 8,
    ) -> dict:
        """
        两模式流程第二步：用户选定来源后，在该来源内按八字喜用神推荐字。

        Returns:
            {"bazi", "sources": [{"id", "source", "title", "text",
                                  "wuxing_tendency", "chars": [...]}], "total"}
        """
        bazi_result = None
        xiyong_wuxing: list[str] = []
        ji_wuxing: list[str] = []
        if year and month and day:
            bazi_result = self.bazi.generate_bazi(year, month, day, hour, minute, gender)
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]
            ji_wuxing = bazi_result["xiyong"]["ji_wuxing"]

        blacklist = set(NEGATIVE_CHARS)
        xi_set = set(xiyong_wuxing)
        ji_set = set(ji_wuxing)

        result_sources = []
        for sid in (source_ids or []):
            entry = self._find_source_by_id(sid)
            if not entry:
                continue
            valid_chars = self._get_valid_poem_chars(
                entry, gender, xiyong_wuxing, blacklist, None
            )

            def rank(c):
                wx = c["wuxing"]
                if xi_set and wx in xi_set:
                    return 0
                if ji_set and wx in ji_set:
                    return 2
                return 1

            valid_chars.sort(key=rank)
            tendency = self._source_wuxing_tendency(entry)
            result_sources.append({
                "id": entry.get("id", ""),
                "source": entry.get("source", ""),
                "title": entry.get("title", ""),
                "text": entry.get("text", ""),
                "wuxing_tendency": tendency["dominant"],
                "chars": [
                    self._source_char_brief(c, xi_set, ji_set)
                    for c in valid_chars[:limit_per_source]
                ],
            })

        return {
            "bazi": bazi_result,
            "sources": result_sources,
            "total": sum(len(s["chars"]) for s in result_sources),
        }

    @staticmethod
    def _source_char_brief(c: dict, xi_set: set, ji_set: set) -> dict:
        """来源内选字摘要（含喜用神/忌神标记）。"""
        wx = c.get("wuxing", "")
        if wx in xi_set:
            flag = "xiyong"
        elif wx in ji_set:
            flag = "ji"
        else:
            flag = "neutral"
        return {
            "char": c.get("char", ""),
            "pinyin": c.get("pinyin", ""),
            "wuxing": wx,
            "kangxi_strokes": c.get("kangxi_strokes", 0),
            "gender": c.get("gender", "中"),
            "meaning": c.get("meaning", ""),
            "bazi_flag": flag,
        }

    def _match_provenance(
        self,
        xiyong_wuxing: list[str] = None,
        gender: str = "male",
        style: Optional[str] = None,
        meanings: Optional[list[str]] = None,
        blacklist: set = None,
        use_poetry: bool = True,
        source_classes: Optional[list[str]] = None,
    ) -> list[tuple]:
        """
        统一出处匹配：合并诗词库 + 字源库条目，返回 [(entry, tier), ...]。

        去重后保留所有有可用推荐字的条目，tier ∈ {A, B, C} 仅用于候选池预算式引入顺序，
        不再决定最终排序（最终排序由韵味分决定）。

        source_classes（先出处后字）：按「source 或 source_class ∈ 给定集合」硬过滤。
        诗词库两类字段同值（诗经/楚辞/唐诗/宋词/五代词/清词/汉魏古诗/经史子集），
        字源 4 部典籍 source_class 统一为「经史子集」，故选「经史子集」会同时纳入它们。
        """
        entries = []
        if use_poetry:
            entries.extend(self.poetry_db.get_by_gender(gender))
        entries.extend(self.source_db.get_by_gender(gender))

        if source_classes:
            wanted = set(source_classes)
            entries = [
                e for e in entries
                if e.get("source") in wanted or e.get("source_class") in wanted
            ]

        blacklist = blacklist or set()
        matched = []
        seen = set()
        for entry in entries:
            key = NamingEngine._entry_key(entry)
            if key in seen:
                continue
            seen.add(key)

            if NamingEngine._is_sad_poem(entry):
                continue

            available = [
                c for c in entry["recommend_chars"]
                if self.char_db.get_char(c) and c not in blacklist
            ]
            if not available:
                continue

            matched.append(entry)

        return self._rank_poems(matched, style, meanings)

    @staticmethod
    def _rank_poems(
        entries: list[dict],
        style: Optional[str] = None,
        meanings: Optional[list[str]] = None,
    ) -> list[tuple]:
        """
        分层打分 + tier 标记（仅影响选池引入顺序，不决定最终排序）。

        - Tier A：source 或 source_class 命中该风格的 source_preference
        - Tier B：非 A 但 imagery_keywords 命中
        - Tier C：其余（兜底）
        """
        if not style and not meanings:
            return [(e, "C") for e in entries]

        tier_rank = {"A": 0, "B": 1, "C": 2}

        def blob_of(entry: dict) -> str:
            imagery = " ".join(entry.get("imagery", []) or [])
            scene = entry.get("scene", "") or ""
            text = entry.get("text", "") or ""
            return f"{imagery} {scene} {text}"

        def tier_of(entry: dict) -> str:
            if style and style in STYLE_OPTIONS:
                opt = STYLE_OPTIONS[style]
                prefs = opt.get("source_preference", [])
                # 字源 source_class 归入「经史子集」，与诗词 source 统一命中
                if (entry.get("source", "") in prefs
                        or entry.get("source_class", "") in prefs):
                    return "A"
                blob = blob_of(entry)
                if any(kw in blob for kw in opt.get("imagery_keywords", [])):
                    return "B"
            # 寓意命中：诗词 imagery/scene/text 命中寓意词族 → 提升为 tier A（软加权优先引入）
            if meanings:
                blob = blob_of(entry)
                if NamingEngine._meanings_match_score(blob, meanings) > 0:
                    return "A"
            return "C"

        def score_of(entry: dict) -> int:
            total = 0
            blob = blob_of(entry)
            if style and style in STYLE_OPTIONS:
                opt = STYLE_OPTIONS[style]
                prefs = opt.get("source_preference", [])
                if (entry.get("source", "") in prefs
                        or entry.get("source_class", "") in prefs):
                    total += STYLE_TIER_A_WEIGHT
                for kw in opt.get("imagery_keywords", []):
                    if kw in blob:
                        total += IMAGERY_WEIGHT
            if meanings:
                for m in meanings:
                    opt = MEANING_OPTIONS.get(m)
                    if not opt:
                        continue
                    for kw in opt.get("keywords", []) + opt.get("imagery_words", []):
                        if kw in blob:
                            total += MEANING_KEYWORD_WEIGHT
            return total

        decorated = [(tier_of(e), score_of(e), e) for e in entries]
        decorated.sort(key=lambda x: (tier_rank[x[0]], -x[1]))
        return [(e, t) for t, _score, e in decorated]

    @staticmethod
    def _is_sad_poem(poem: dict) -> bool:
        """判断出处是否为哀伤类（标题命中黑名单；字源条目 emotion 已由读层过滤）。"""
        title = poem.get("title", "")
        source_title = f'{poem.get("source", "")}·{title}'
        for sad in SAD_POETRY_TITLES:
            if sad in title or sad in source_title:
                return True
        return False

    @staticmethod
    def _meanings_match_score(text: str, meanings: Optional[list[str]]) -> int:
        """
        计算文本命中寓意词族的次数（用于候选字/出处软排序与 tie-break）。

        词族 = keywords（字面词）+ imagery_words（意象词族），
        让偏好匹配能覆盖 data 里 900+ 个意象标签，命中率从个位数提到几十上百条。
        """
        if not meanings or not text:
            return 0
        score = 0
        for m in meanings:
            opt = MEANING_OPTIONS.get(m)
            if not opt:
                continue
            for kw in opt.get("keywords", []) + opt.get("imagery_words", []):
                if kw in text:
                    score += 1
        return score

    @staticmethod
    def _keyword_hits(text: str, keywords: Optional[list[str]]) -> int:
        """裸关键词命中数（用于风格意象词——它不是寓意 code，不能走 _meanings_match_score）。

        修复背景：`_rank_by_yunwei.style_hits` 与 `_pref_hits` 原先把 STYLE_OPTIONS 的
        `imagery_keywords`（如「清雅」「壮阔」）当成 MEANING_OPTIONS 的 code 去查表，
        `MEANING_OPTIONS.get("清雅")` 恒为 None → 风格命中**恒为 0**。风格偏好实际只
        通过 source_preference（出处大类）起作用，意象关键词那一半是死代码。
        """
        if not keywords or not text:
            return 0
        return sum(1 for kw in keywords if kw and kw in text)

    def _get_valid_poem_chars(
        self,
        poem: dict,
        gender: str,
        xiyong_wuxing: list[str] = None,
        blacklist: set = None,
        meanings: Optional[list[str]] = None,
    ) -> list[dict]:
        """从一条出处条目（诗词/字源）的推荐字里筛出可用字（字库存在 + 性别 + 非黑名单）。"""
        blacklist = set(NEGATIVE_CHARS) if blacklist is None else set(blacklist)
        valid = []
        for char in poem["recommend_chars"]:
            ci = self.char_db.get_char(char)
            if not ci:
                continue
            if ci["char"] in blacklist:
                continue
            if gender == "male" and ci["gender"] not in ("男", "中"):
                continue
            if gender == "female" and ci["gender"] not in ("女", "中"):
                continue
            valid.append(ci)

        def sort_key(c: dict) -> tuple:
            meaning_hit = 0 if (
                meanings
                and NamingEngine._meanings_match_score(c.get("meaning", ""), meanings) > 0
            ) else 1
            xiyong_rank = 0 if (xiyong_wuxing and c["wuxing"] in xiyong_wuxing) else 1
            return (meaning_hit, xiyong_rank)

        valid.sort(key=sort_key)
        return valid

    def _entry_fit_score(self, entry: dict, char: str) -> float:
        """评估出处条目对某字的「贴合度」，用于多出处时择优（替代盲目取第 0 条）。

        维度（降序）：该字在本出处有语境义项 > 字出现在原文 > 字出现在意象标签。
        同分时优先推荐字更少的条目（该字更核心、语境更聚焦）。
        """
        score = 0.0
        entry_id = entry.get("id")
        if entry_id and self.sense_db.get_senses(char, entry_id):
            score += 3.0
        text = entry.get("text", "") or ""
        if char in text:
            score += 2.0
        imagery = " ".join(entry.get("imagery", []) or [])
        if char in imagery:
            score += 1.0
        return score

    @staticmethod
    def _gender_tag(gender: Optional[str]) -> Optional[str]:
        """把 male/female 归一为库内性别标签；返回 None 表示不限制。"""
        tag = {"male": "男", "female": "女"}.get(gender or "", gender)
        return tag if tag in ("男", "女") else None

    def _filter_by_gender(self, entries: list[dict], gender: Optional[str]) -> list[dict]:
        """按性别口径收窄候选出处：只保留「本性别 + 中性」条目。

        注意：这是「择优时优先」而非硬堵——若收窄后为空，调用方应退回全集，
        避免冷门字因性别标签缺失而挂不上出处。
        """
        tag = self._gender_tag(gender)
        if tag is None:
            return entries
        return [e for e in entries if e.get("gender") in (tag, "中")]

    def _pick_entry_for_char(self, char: str, entries: list[dict]) -> Optional[dict]:
        """从某字的所有出处（已按库内顺序）里择优：贴合度高者优先，同分取库内靠前者。"""
        if not entries:
            return None
        return max(
            entries,
            key=lambda e: (self._entry_fit_score(e, char), -len(e.get("recommend_chars") or [])),
        )

    def _find_entry_for_char(self, char: str, gender: Optional[str] = None) -> Optional[dict]:
        """按字查找贴合的出处条目（优先诗词，其次字源；多条时按贴合度择优）。

        gender 给定时先在本性别口径内择优，取不到再退回全集。
        """
        for db in (self.poetry_db, self.source_db):
            entries = db.get_by_char(char)
            if not entries:
                continue
            scoped = self._filter_by_gender(entries, gender)
            picked = self._pick_entry_for_char(char, scoped or entries)
            if picked:
                return picked
        return None

    @staticmethod
    def _order_phonetic_better(c1: dict, c2: dict) -> bool:
        """比较 c1+c2 与 c2+c1 的音韵，返回 True 表示 c1 在前更顺口。

        只做「顺序敏感」的声调评价（姓的衔接不因名内两字交换而变，故不纳入）：
        - 末字平声（1/2 声）收尾更响亮悠长；
        - 两字声调起伏（不同优于相同）；
        - 上声/去声连续拗口，额外扣分。
        """
        def _score(chars):
            tones = [PhoneticsScorer.get_pinyin(ch)[1] for ch in chars]
            s = 0.0
            if len(tones) == 2:
                if tones[1] in (1, 2):
                    s += 3.0  # 末字平声收尾
                if len(set(tones)) >= 2:
                    s += 2.0  # 声调起伏
                if tones[0] == tones[1] and tones[0] in (3, 4):
                    s -= 2.0  # 上上/去去连续拗口
            return s
        return _score([c1["char"], c2["char"]]) >= _score([c2["char"], c1["char"]])

    def _order_candidates(self, c1: dict, c2: dict) -> list[tuple]:
        """随机组合的字序候选（无固定出处时）。

        音韵优劣明确 → 只给更顺的一种序；
        音韵同分 → **两序都作为候选**：此时字序本来就是自由的，交给门槛层筛。
        旧实现同分时固定保留输入序，实测约 3% 的先字组合因此被无谓丢掉
        （「宁耕」五格凶、同分的「耕宁」五格吉，整条路径空手）。
        """
        better = self._order_phonetic_better(c1, c2)
        better_rev = self._order_phonetic_better(c2, c1)
        if better and better_rev:
            return [(c1, c2), (c2, c1)]
        return [(c1, c2)] if better else [(c2, c1)]

    def _order_two_chars(self, entry: dict, c1: dict, c2: dict) -> tuple:
        """决定两字的最终前后顺序：原文成词语序 > 原文出现先后 > 音韵。

        原文成词：两字在 text 中相邻 → 按词序（「婵娟」不得倒成「娟婵」）。
        否则按首次出现先后；字不在原文则退回音韵优选。
        """
        text = (entry or {}).get("text") or ""
        a, b = c1["char"], c2["char"]
        if (a + b) in text and (b + a) not in text:
            return (c1, c2)
        if (b + a) in text and (a + b) not in text:
            return (c2, c1)
        p1 = text.find(a)
        p2 = text.find(b)
        if p1 >= 0 and p2 >= 0 and p1 != p2:
            return (c1, c2) if p1 < p2 else (c2, c1)
        if self._order_phonetic_better(c1, c2):
            return (c1, c2)
        return (c2, c1)

    def _compose_names(
        self,
        surname: str,
        candidate_chars: list[dict],
        provenance_matches: list[tuple],
        gender: str,
        name_length: int,
        bazi_result: dict = None,
        blacklist: set = None,
        meanings: Optional[list[str]] = None,
        target_min: int = TARGET_MIN,
        pool_size: int = 30,
        selected_chars: Optional[list[str]] = None,
        source_classes: Optional[list[str]] = None,
        generational_char: Optional[str] = None,
        exclude_given: Optional[set] = None,
    ) -> list[dict]:
        """组合生成名字（预算式 + tier 标记）。"""
        names = []
        seen_names = set()
        exclude_given = exclude_given or set()
        blacklist = blacklist or set()
        selected_set = set(selected_chars) if selected_chars else None
        source_wanted = set(source_classes) if source_classes else None
        # 字辈：仅双字名生效，固定第二个字（辈字 == given_name 最后一个字符）
        gen_char = generational_char if (name_length == 2 and generational_char) else None

        xiyong_wuxing = None
        if bazi_result:
            xiyong_wuxing = bazi_result["xiyong"]["xi_wuxing"]

        candidate_chars = [
            c for c in candidate_chars if c["char"] not in blacklist
        ]

        # 候选字按「姓氏意象呼应 + 偏好命中」亲和分降序（稳定排序，喜用神优先顺序作 tie-break）
        candidate_chars = sorted(
            candidate_chars,
            key=lambda c: -self._char_affinity(surname, c, meanings),
        )

        def emit(name_data: dict, tier: str) -> None:
            """入库：打 tier + 先字命中数（让「含更多所选字」的名字在同分时靠前）。"""
            given = name_data.get("given_name") or ""
            # 「换一批」的排除名单在这里收口：所有产出路径（同源/随机/单字/字辈）
            # 都要经过 emit，在这一处剔除比在调用方逐路过滤可靠。
            if given in exclude_given:
                return
            name_data["_tier"] = tier
            if "_taste" not in name_data:
                # 字辈 / 随机组合 / 单字名等未显式标注的路径统一在这里兜底。
                # 单字走 _char_taste：先前一律给 3 分，等于单字名整条路径不过闸。
                name_data["_taste"] = (
                    self._pair_taste(given[0], given[1]) if len(given) >= 2
                    else self._char_taste(given)
                )
            if selected_set:
                name_data["_selected_hits"] = sum(
                    1 for ch in name_data["given_name"] if ch in selected_set
                )
            names.append(name_data)

        def pair_allowed(a: str, b: str) -> bool:
            """先字模式：字对必须含所选字（任一位置）；非先字模式恒通过。"""
            return not selected_set or a in selected_set or b in selected_set

        # ── 字辈模式（双字名，辈字固定第二字）────────────────────────
        # 家族字辈是硬规矩：名字 = 「有出处的第一个字」 + 辈字。这里不再走
        # 同源名 / 随机组合的「诗词字对」逻辑——辈字组合不是诗词成对
        # （「张志远」≠「婵娟」），只需第一个字有出处 + 整名过门槛（音律/五格/
        # 谐音/忌神），故单独横扫候选字，早退。
        if gen_char:
            gen_ci = self.char_db.get_char(gen_char)
            if gen_ci and gen_char not in blacklist:
                rows = []
                for ci in candidate_chars:
                    ch = ci["char"]
                    if ch == gen_char:
                        continue
                    # 先字 + 字辈叠加：第一个字还须是用户点选的
                    if selected_set and ch not in selected_set:
                        continue
                    if self.surname_fit.tri_tone_conflict(surname, [ch, gen_char]):
                        continue
                    given_name = ch + gen_char
                    if given_name in seen_names:
                        continue
                    seen_names.add(given_name)
                    chars_info = [ci, gen_ci]
                    entry = self._find_best_entry(given_name, chars_info, gender)
                    if entry is None:
                        entry = self._find_entry_for_char(ch, gender)
                    name_data = self._evaluate_name(
                        surname, given_name, chars_info, entry, bazi_result
                    )
                    if name_data:
                        rows.append(name_data)
                # 名字感闸门在字辈模式下**软执行**：辈字由家族锁定，用户无从换字，
                # 若把屏蔽档全砍掉可能一个字都不剩（该模式整块失效）。故只在一批里
                # 还有可用项时才丢弃屏蔽档，全灭时退回全量。
                keep = [n for n in rows if self._pair_taste(*n["given_name"]) > 1]
                for name_data in (keep or rows):
                    emit(name_data, "R")
            return names

        def compose_from_entry(entry: dict, tier: str) -> None:
            """从单条出处的推荐字里生成同源名字。"""
            valid_chars = self._get_valid_poem_chars(
                entry, gender, xiyong_wuxing, blacklist, meanings
            )
            # 标注字对（name_pairs）可能用到 recommend_chars 之外的字（如「修远」的「远」
            # 取自「路漫漫其修远兮」却没进推荐字），故把这些字一并补进可用字。
            by_char = {c["char"]: c for c in valid_chars}
            for pair in (entry.get("name_pairs") or []):
                for ch in pair:
                    if ch in by_char or ch in blacklist:
                        continue
                    ci = self.char_db.get_char(ch)
                    if not ci:
                        continue
                    if gender == "male" and ci["gender"] not in ("男", "中"):
                        continue
                    if gender == "female" and ci["gender"] not in ("女", "中"):
                        continue
                    by_char[ch] = ci
            valid_chars = list(by_char.values())
            # 姓氏参与：同源字按姓氏亲和分排序，让不同姓氏优先取不同字
            valid_chars = sorted(
                valid_chars,
                key=lambda c: -self._char_affinity(surname, c, meanings),
            )
            # 先字模式（selected_chars = 名字必须含所选字）：
            # 单字名 → 该字本身须是所选字（此时「含」即「等于」）；
            # 双字名 → **不收窄 valid_chars**（收窄会让单个所选字无法成对），
            #          改为在下方字对筛选处只保留「含任一所选字」的字对。
            if selected_set and name_length == 1:
                valid_chars = [c for c in valid_chars if c["char"] in selected_set]
            index_of = {c["char"]: i for i, c in enumerate(valid_chars)}

            if name_length == 1:
                # 单字名过第三道闸：屏蔽档直接不出（「瑰/甘/垂/蓬」这类不是名字的字
                # 先前能一路出到结果页）。此处**不做兜底**——出处的推荐字若全被屏蔽，
                # 就让这条出处不出单字名，由别的出处补；否则兜底会把屏蔽档又放回来。
                gated = [c for c in valid_chars if self._char_taste(c["char"]) > 1]
                for ci in gated:
                    given_name = ci["char"]
                    if given_name in seen_names:
                        continue
                    seen_names.add(given_name)
                    # 单字名出处优先「说文解字」：字有《说文》本义时用字源本义作出处
                    # （比硬套诗词更贴切），否则退回原诗词/字源条目。
                    # 先出处模式（source_classes）下尊重用户指定，不强行覆盖。
                    entry_for_name = entry
                    if not source_wanted:
                        entry_for_name = self._shuowen_entry_for(ci) or entry
                    name_data = self._evaluate_name(
                        surname, given_name, [ci], entry_for_name, bazi_result
                    )
                    if name_data:
                        emit(name_data, tier)
            else:
                # 组合优先序：先出「LLM 判定宜作名的字对」，再出原文相邻/同句的两字，
                # 最后才是跨句拼接。出处的推荐字是「一袋好字」，全交叉会产生大量
                # 原诗中并不成对的配对（「萸橘」式）以及「成对但不宜作名」的配对
                # （圣人/教多用财式），这两类正是用户体感「只是抠了两个字」的来源。
                # 注意：此处只决定「入库顺序」，最终排序仍由韵味分（含组合成立度）决定。
                #
                # 分两路，这是「不要单纯抠两个字」的关键：
                # ① 该出处有「宜作名字对」标注（name_pairs）→ **只产出标注字对**。
                #    全交叉必须放弃，否则「圣人」「壮心」「呦鹿」这类「原句成词但不宜作名」
                #    的配对还会从交叉里漏出来 —— 语义判断只有标注能提供。
                # ② 标注跑过但字对为空（复核判定该出处无可作名组合）→ **不产出双字名**。
                #    退回全交叉会把「荔枝」「长安」这类被复核剔除的组合重新漏出。
                # ③ 从未标注的出处（新增语料尚未补标）→ 退回按成立度排序的全交叉，不降级。
                annotated = entry.get("name_pairs") or []
                annotated_known = entry.get(
                    "name_pairs_known", bool(annotated)
                )
                pairs = []
                if annotated:
                    for pair in annotated:
                        # index_of 判断是索引安全网：字对含性别不符/黑名单字时不能索引
                        # （这些字没进 valid_chars）。
                        if not all(ch in index_of for ch in pair):
                            continue
                        # 先字模式：字对须含所选字（任一位置）——「修远」式成对关系不因
                        # 只选了其中一个字而作废。
                        if not pair_allowed(pair[0], pair[1]):
                            continue
                        i, j = index_of[pair[0]], index_of[pair[1]]
                        pairs.append((
                            -self._pair_taste(pair[0], pair[1]),   # 名字感优先
                            COHESION_RANK.get("annotated", 0), min(i, j), max(i, j),
                        ))
                elif annotated_known:
                    # 语义层已判定「此出处无适合作名的两字组合」——尊重判断，不机械拼接
                    pairs = []
                else:
                    for i in range(len(valid_chars)):
                        for j in range(i + 1, len(valid_chars)):
                            if not pair_allowed(valid_chars[i]["char"], valid_chars[j]["char"]):
                                continue
                            kind = self.yunwei._cohesion_kind(
                                valid_chars[i]["char"], valid_chars[j]["char"], entry
                            )
                            pairs.append((
                                -self._pair_taste(valid_chars[i]["char"], valid_chars[j]["char"]),
                                COHESION_RANK.get(kind, 9), i, j,
                            ))
                pairs.sort(key=lambda t: (t[0], t[1], t[2], t[3]))

                for _, _, i, j in pairs:
                    c1, c2 = valid_chars[i], valid_chars[j]
                    # 字序决定：原文语序优先，其次音韵（治「颠倒一下更好」）
                    first, second = self._order_two_chars(entry, c1, c2)
                    # 名字感屏蔽档：春风/明月/翠凤/瑞祥 这类，组合阶段就不出
                    taste = self._pair_taste(first["char"], second["char"])
                    if taste <= 1:
                        continue
                    # 姓氏结合：三连同调（全平/全仄）提前跳过
                    if self.surname_fit.tri_tone_conflict(
                        surname, [first["char"], second["char"]]
                    ):
                        continue
                    given_name = first["char"] + second["char"]
                    if given_name in seen_names:
                        continue
                    seen_names.add(given_name)
                    name_data = self._evaluate_name(
                        surname, given_name, [first, second], entry, bazi_result
                    )
                    if name_data:
                        name_data["_taste"] = taste
                        emit(name_data, tier)

        # 策略1：同源组名，按 tier 预算式（A → B → C），tier 内随机 shuffle + 总量封顶
        tier_groups: dict[str, list[dict]] = {"A": [], "B": [], "C": []}
        for entry, tier in provenance_matches:
            tier_groups.setdefault(tier, []).append(entry)

        # tier 内随机打乱诗词顺序，让每次调用的同源组合不同（解决「换一批不变」）
        for tier in ("A", "B", "C"):
            random.shuffle(tier_groups.get(tier, []))

        has_preference_tiers = bool(tier_groups.get("A") or tier_groups.get("B"))
        cap = max(pool_size * self.COMPOSE_CAP_FACTOR, self.COMPOSE_CAP_MIN)

        for tier in ("A", "B", "C"):
            if len(names) >= cap:
                break
            for entry in tier_groups.get(tier, []):
                compose_from_entry(entry, tier)
                # 有偏好时，命中偏好的 A/B 组合达到 target_min 即截断（C 仍兜底）
                if has_preference_tiers and tier != "C" and len(names) >= target_min:
                    break
                if len(names) >= cap:
                    break

        # 策略2：随机组合（始终参与，补充多样性 + 姓氏/偏好引导）
        if candidate_chars:
            # 先字模式：随机路径同样必须「含所选字」——起始字只从所选字里取
            # （双字名再配已批准搭档，单字名即该字本身）。无可用所选字则跳过随机路径。
            base_pool = (
                [c for c in candidate_chars if c["char"] in selected_set]
                if selected_set else candidate_chars
            )
            if name_length == 1:
                # 单字名的随机路径也要过闸，否则屏蔽档会从这条路人字形回来
                # （策略 1 已过滤，但两条路各自独立取字）。同样不做兜底：
                # 池子滤空就不走随机路径，宁可少几个名字也不放回屏蔽字。
                base_pool = [c for c in base_pool if self._char_taste(c["char"]) > 1]
            budget = max(pool_size * self.RANDOM_BUDGET_FACTOR, 120)
            max_attempts = budget * 10
            attempts = 0
            random_count = 0
            while base_pool and random_count < budget and attempts < max_attempts:
                attempts += 1
                if name_length == 1:
                    ci = self._weighted_char_choice(base_pool)
                    cands = [(ci, ci, ci["char"])]
                else:
                    c1 = self._weighted_char_choice(base_pool)
                    # 搭档只从「已批准字对」里取（语义层）；取不到就跳过，不退回机械拼接
                    c2 = self._same_source_partner(c1, candidate_chars)
                    if c2 is None:
                        continue
                    # 字序决定（随机组合无固定出处）：音韵优选；同分时两序均为候选
                    cands = []
                    for first, second in self._order_candidates(c1, c2):
                        # 姓氏结合：三连同调（全平/全仄）跳过
                        if self.surname_fit.tri_tone_conflict(
                            surname, [first["char"], second["char"]]
                        ):
                            continue
                        cands.append((first, second, first["char"] + second["char"]))
                    if not cands:
                        continue

                # 同一次尝试：主序优先；主序被重复/门槛挡住时，再试同分的另一序
                for first, second, given_name in cands:
                    if given_name in seen_names:
                        continue
                    # 名字感屏蔽档：随机组合路径也要拦（否则「凤翠」「彩金」会绕过字对闸门）
                    if name_length == 2 and self._pair_taste(
                        first["char"], second["char"]
                    ) <= 1:
                        continue
                    seen_names.add(given_name)

                    chars_info = []
                    for c in given_name:
                        ci = self.char_db.get_char(c)
                        if ci:
                            chars_info.append(ci)

                    # 出处择优：优先挂「该字对真正被批准」的那条出处（保证详情页里两字成对），
                    # 其次才退回「推荐字含全部名字用字」的通用择优。
                    entry = (
                        self._pair_entry(first["char"], second["char"], gender, source_wanted)
                        if name_length == 2
                        else None
                    )
                    if entry is None:
                        # 单字名：无先出处约束时，优先「说文解字」字源（字有《说文》本义更贴切）
                        if name_length == 1 and not source_wanted and chars_info:
                            entry = self._shuowen_entry_for(chars_info[0])
                    if entry is None:
                        entry = self._find_best_entry(given_name, chars_info, gender)
                    if entry is None and chars_info:
                        entry = self._find_entry_for_char(chars_info[0]["char"], gender)

                    # 先出处模式兜底：出处必须落在所选类目内（通用择优可能取到别的典籍），
                    # 否则跳过本次尝试——「有据可循」承诺的出处不能张冠李戴。
                    if source_wanted:
                        if not entry or not (
                            entry.get("source") in source_wanted
                            or entry.get("source_class") in source_wanted
                        ):
                            continue

                    name_data = self._evaluate_name(
                        surname, given_name, chars_info, entry, bazi_result
                    )
                    if name_data:
                        emit(name_data, "R")
                        random_count += 1
                        break

        # 先字模式契约兜底：所有产出必须含所选字（两条路径均已约束，此处保底，
        # 防止未来新增路径漏出不符合用户点选的组合）。
        if selected_set:
            names = [n for n in names if n.get("_selected_hits")]

        return names

    def _pass_gate(
        self,
        surname: str,
        given_name: str,
        phonetics: dict,
        wuge: dict,
        bazi_result: Optional[dict],
        chars_info: list[dict],
    ) -> bool:
        """
        第一层门槛：只排除、不打分。

        - 音律严重拗口（全平/全仄 或 score<55）
        - 五格人格、总格双凶
        - 八字全忌神（名字所有字五行都在忌神）
        - 姓氏谐音歧义（杜子腾/吴德/杨伟 类，安全底线）
        - 姓氏本义冲突（朱+红 重复、白+云 贬义）
        """
        if self.phonetics.is_cacophonous(phonetics):
            return False
        if self.wuge.is_bad(wuge):
            return False
        if bazi_result:
            ji_wuxing = bazi_result["xiyong"]["ji_wuxing"]
            name_wuxing = [c["wuxing"] for c in chars_info]
            if name_wuxing and BaziEngine.is_ji_wuxing_conflict(name_wuxing, ji_wuxing):
                return False
        # 姓氏结合：谐音歧义 / 本义冲突（硬排除，安全底线）
        taboo, _ = self.surname_fit.is_homophone_taboo(surname, given_name)
        if taboo:
            return False
        conflict, _ = self.surname_fit.is_meaning_conflict(surname, given_name)
        if conflict:
            return False
        return True

    def _evaluate_name(
        self,
        surname: str,
        given_name: str,
        chars_info: list[dict],
        entry: dict = None,
        bazi_result: dict = None,
    ) -> Optional[dict]:
        """评估单个名字：过门槛 → 韵味评分 → 组装返回。"""
        full_name = surname + given_name

        phonetics = self.phonetics.analyze(full_name)

        try:
            wuge = self.wuge.calculate(surname, given_name)
        except Exception:
            wuge = {"total_score": 60, "description": "数理计算异常"}

        # 门槛：任一不通过 → 丢弃（不进候选）
        if not self._pass_gate(surname, given_name, phonetics, wuge, bazi_result, chars_info):
            return None

        # 情绪字软门槛（分级放开）：含负面情绪字的名字须「该字本身有出处 + 名内非全情绪字」。
        # 「有出处」按本字是否出现在某条出处的推荐字里判定，而不是名字整体有出处——
        # 否则情绪字会搭同名中另一个有出处字的便车混进结果（数据中情绪字均无出处，故实际不出现）。
        emotional_hit = [c["char"] for c in chars_info if c["char"] in EMOTIONAL_CHARS]
        has_emotional = bool(emotional_hit)
        if has_emotional:
            if not entry or len(emotional_hit) == len(chars_info):
                return None
            if not all(ch in self._provenance_chars() for ch in emotional_hit):
                return None

        # 八字匹配展示值（不再参与主排序）
        bazi_score = 70
        if bazi_result and chars_info:
            xiyong = bazi_result["xiyong"]["xi_wuxing"]
            matched = sum(1 for ci in chars_info if ci["wuxing"] in xiyong)
            bazi_score = 60 + int(matched / len(chars_info) * 40)

        # 韵味评分（含 S 姓氏协调）
        yunwei_detail = self.yunwei.score(surname, chars_info, entry, self.sense_db)
        yunwei_total = yunwei_detail["total"]

        meaning = self._generate_meaning(chars_info, entry)

        return {
            "full_name": full_name,
            "given_name": given_name,
            "emotional": has_emotional,
            "chars_info": [
                {
                    "char": ci["char"],
                    "pinyin": ci.get("pinyin", ""),
                    "wuxing": ci.get("wuxing", ""),
                    "kangxi_strokes": ci.get("kangxi_strokes", 0),
                    "meaning": ci.get("meaning", ""),
                    "shuowen": ci.get("shuowen", ""),
                    "detail": ci.get("detail", ""),
                    "radical": ci.get("radical", ""),
                    "imagery": ci.get("imagery", []),
                    "level": ci.get("level", "一"),
                }
                for ci in chars_info
            ],
            "poetry": {
                "source": entry["source"],
                "title": entry["title"],
                "author": entry.get("author", "佚名"),
                "dynasty": entry.get("dynasty", ""),
                "text": entry.get("text", ""),
                # 原文段落（三级溯源第二层用）：完整原诗/原文，缺字段时退回 text
                "original_text": entry.get("original_text") or entry.get("text", ""),
                "citation": entry.get("citation", ""),
                "source_class": entry.get("source_class", entry.get("source", "")),
                "imagery": entry.get("imagery", []),
                "scene": entry.get("scene", ""),
            } if entry else None,
            # 语境义项（免费展示）：各字在本出处语境下的取义，供详情页「按语境释义」
            "context_senses": self._context_senses(chars_info, entry),
            "phonetics": phonetics,
            "wuge": wuge,
            "scores": {
                "phonetics": phonetics["score"],
                "wuge": wuge.get("total_score", 60),
                "bazi": bazi_score,
                "overall": yunwei_total,
                "yunwei": yunwei_total,
                "yunwei_detail": yunwei_detail,
            },
            "meaning": meaning,
        }

    @staticmethod
    def _generate_meaning(chars_info: list[dict], entry: dict = None) -> str:
        """生成寓意简述（模板兜底，LLM 懒加载见 generate_meaning_detail）。"""
        meanings = [ci.get("meaning", "") for ci in chars_info if ci.get("meaning")]

        if entry:
            source = f"「{entry['source']}·{entry['title']}」"
            text = entry.get("text", "")
            char_meanings = "，".join(meanings)
            return f"出自{source}「{text}」。{char_meanings}。"
        return "，".join(meanings) + "。"

    # ── LLM 寓意懒加载（详情页） ──

    @staticmethod
    def _split_name(full_name: str) -> tuple[str, str]:
        """拆分姓与名（兼容复姓）。"""
        for cs in COMPOUND_SURNAMES:
            if full_name.startswith(cs):
                return cs, full_name[len(cs):]
        return full_name[0], full_name[1:]

    def _lookup_chars(self, given_name: str) -> list[dict]:
        """按名字用字查字库，缺失字兜底。"""
        chars_info = []
        for c in given_name:
            info = self.char_db.get_char(c)
            if info:
                chars_info.append(info)
            else:
                chars_info.append({
                    "char": c,
                    "pinyin": "",
                    "wuxing": "未知",
                    "kangxi_strokes": 0,
                    "meaning": "字库中暂无此字信息",
                    "shuowen": "",
                    "detail": "",
                    "radical": "",
                    "imagery": [],
                    "level": "扩展",
                })
        return chars_info

    def _find_best_entry(
        self,
        given_name: str,
        chars_info: list[dict],
        gender: Optional[str] = None,
    ) -> Optional[dict]:
        """为名字查找最佳出处条目（优先「含全部名字用字」的同源条目，其次单字出处）。

        同源候选有多条时，按「原文含名字用字个数 + 各字语境义项贴合度」择优，
        避免固定取第一条导致详情页出处与语境义不匹配。

        gender 给定时，只在「本性别 + 中性」的出处里择优——否则女性请求会被挂上
        男性向出处（性别标签不一致，且出处的意象/场景会污染偏好匹配与韵味分）。
        收窄后为空时退回全集。
        """
        name_chars = [c["char"] for c in chars_info]
        if not name_chars:
            return None

        def text_hits(entry: dict) -> int:
            text = entry.get("text", "") or ""
            return sum(1 for c in name_chars if c in text)

        # 同源优先：收集所有「推荐字含全部名字用字」的条目
        same_source: list[dict] = []
        seen_ids: set = set()
        for db in (self.source_db, self.poetry_db):
            for ch in name_chars:
                for entry in db.get_by_char(ch):
                    eid = entry.get("id")
                    if eid in seen_ids:
                        continue
                    if all(x in (entry.get("recommend_chars") or []) for x in name_chars):
                        seen_ids.add(eid)
                        same_source.append(entry)
        if same_source:
            scoped = self._filter_by_gender(same_source, gender) or same_source
            return max(
                scoped,
                key=lambda e: (
                    text_hits(e),
                    sum(self._entry_fit_score(e, c) for c in name_chars),
                    -len(e.get("recommend_chars") or []),
                ),
            )

        # 单字出处兜底：逐字择优（保持原顺序：字源优先，其次诗词）
        for ch in name_chars:
            for db in (self.source_db, self.poetry_db):
                entries = db.get_by_char(ch)
                if not entries:
                    continue
                scoped = self._filter_by_gender(entries, gender) or entries
                picked = self._pick_entry_for_char(ch, scoped)
                if picked:
                    return picked
        return None

    def _entry_with_senses(self, char: str) -> Optional[dict]:
        """找该字「有语境义项」的最佳出处（主出处未收录该字时的回退）。

        结果与用户输入无关，故按字缓存。
        """
        if char in self._sense_entry_cache:
            return self._sense_entry_cache[char]
        best = None
        best_key = None
        for db in (self.poetry_db, self.source_db):
            for entry in db.get_by_char(char):
                eid = entry.get("id")
                if not eid or not self.sense_db.get_senses(char, eid):
                    continue
                key = (
                    self._entry_fit_score(entry, char),
                    -len(entry.get("recommend_chars") or []),
                )
                if best_key is None or key > best_key:
                    best_key = key
                    best = entry
        self._sense_entry_cache[char] = best
        return best

    @staticmethod
    def _wuxing_note(chars_info: list[dict]) -> str:
        """模板兜底：名字五行说明。"""
        if not chars_info:
            return ""
        parts = [f"{c['char']}属{c.get('wuxing', '未知')}" for c in chars_info]
        return "、".join(parts) + "，五行搭配"

    async def generate_meaning_detail(
        self,
        full_name: str,
        gender: str = "male",
        year: int = None,
        month: int = None,
        day: int = None,
        hour: int = 12,
        minute: int = 0,
    ) -> dict:
        """
        详情页懒加载：为单个名字生成「多层余味」寓意。

        LLM 成功 → 多层 layers + meaning_source="llm"；失败 → 模板兜底 + meaning_source="template"。
        结果写入缓存（key = full_name + gender + 生辰签名 + citation）。
        """
        surname, given_name = self._split_name(full_name)
        chars_info = self._lookup_chars(given_name)
        entry = self._find_best_entry(given_name, chars_info, gender)

        # 语境义项：逐字取「在本出处语境下的取义」，供详情页按语境释义 + 供 LLM 在正确语境下解读
        context_senses = self._context_senses(chars_info, entry)
        sense_map = {s["char"]: s["senses"] for s in context_senses if s.get("senses")}
        for ci in chars_info:
            if sense_map.get(ci["char"]):
                ci["context_senses"] = sense_map[ci["char"]]

        bazi_data = None
        bazi_signature = None
        if year and month and day:
            bazi_data = self.bazi.generate_bazi(
                year, month, day, hour, minute, gender
            )
            bazi_signature = f"{year}-{month}-{day}-{hour}-{minute}"

        citation = (entry or {}).get("citation", "")
        key = self.cache.build_key(full_name, gender, bazi_signature, citation)
        cached = self.cache.get(key)
        if cached:
            if "context_senses" not in cached:
                cached["context_senses"] = context_senses
            return cached

        result = await self.llm.generate_meaning(
            full_name, chars_info, entry, bazi_data, gender
        )

        if result.get("error") or not result.get("layers"):
            fallback = {
                "full_name": full_name,
                "given_name": given_name,
                "surname": surname,
                "citation": citation,
                "layers": self._fallback_layers(chars_info, entry),
                "meaning": self._generate_meaning(chars_info, entry),
                "poetry_note": (
                    f"出自{citation}" if citation else "名字用字自有其文化意蕴"
                ),
                "wuxing_note": self._wuxing_note(chars_info),
                "overall_note": self._generate_meaning(chars_info, entry),
                "context_senses": context_senses,
                "meaning_source": "template",
            }
            self.cache.set(key, fallback)
            return fallback

        result["full_name"] = full_name
        result["given_name"] = given_name
        result["surname"] = surname
        result["citation"] = citation
        result["context_senses"] = context_senses
        result["meaning_source"] = "llm"
        self.cache.set(key, result)
        return result

    def _context_senses(
        self,
        chars_info: list[dict],
        entry: Optional[dict],
    ) -> list[dict]:
        """逐字输出「在本出处语境下的义项」，供详情页按语境释义展示。

        返回 [{"char": "清", "senses": ["清朗", "高远"], "general": "水清，清澈"}]。
        无出处 / 无标注时 senses 为空列表（前端回退到通用字义 general）。
        """
        entry_id = (entry or {}).get("id")
        recommend = set((entry or {}).get("recommend_chars") or [])
        out: list[dict] = []
        for c in chars_info:
            ch = c.get("char", "")
            senses = self.sense_db.get_senses(ch, entry_id) if entry_id else []
            from_main = True
            if not senses and ch not in recommend:
                # 主出处未收录该字（随机组合的两字可能无共同出处）→
                # 退回该字自身最有据的一句，保证仍能按语境释义。
                own = self._entry_with_senses(ch)
                if own is not None and own.get("id") != entry_id:
                    senses = self.sense_db.get_senses(ch, own["id"])
                    from_main = False
            out.append({
                "char": ch,
                "senses": senses,
                "general": c.get("meaning") or c.get("detail") or "",
                "from_main": from_main,
            })
        return out

    @staticmethod
    def _fallback_layers(chars_info: list[dict], entry: Optional[dict]) -> list[dict]:
        """模板兜底的三层余味结构。"""
        literal = "、".join(
            (c.get("meaning") or "未收录") for c in chars_info
        )
        layers = [{"level": "字面", "text": f"名字用字取义：{literal}"}]
        if entry:
            layers.append({
                "level": "出处",
                "text": f"出自{entry.get('citation', '')}「{entry.get('text', '')}」",
            })
        layers.append({
            "level": "余味",
            "text": "名字自有其深意，可细细品味其文化意蕴",
        })
        return layers
