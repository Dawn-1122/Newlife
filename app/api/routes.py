"""
API 路由

提供起名、名字解析、字库查询、诗词查询等接口
"""

from fastapi import APIRouter, HTTPException, Response
from app.schemas.schemas import (
    NamingRequest, NamingResponse,
    NameAnalysisRequest, ApiResponse,
    BatchAnalysisRequest, BatchAnalysisResponse,
    PrenatalRequest, PrenatalResponse,
    MeaningRequest, MeaningResponse,
    RecommendCharsRequest, RecommendCharsResponse,
    RecommendSourcesRequest, RecommendSourcesResponse,
    SourceCharsRequest, SourceCharsResponse,
    PickableCharsRequest, PickableCharsResponse,
    CreativeRequest, CreativeResponse,
    CreativeLLMRequest, CreativeLLMResponse,
)
from app.core.names import is_valid_full_name
from app.services.naming_engine import NamingEngine
from app.services.char_database import CharDatabase
from app.services.poetry_database import PoetryDatabase
from app.services.bazi_engine import BaziEngine
from app.services.phonetics import PhoneticsScorer
from app.services.wuge import WugeScorer
from app.services.name_analyzer import analyze_full_name
from app.services.prenatal_engine import PrenatalEngine
from app.services.creative_service import CreativeNamingService
from app.services.wx_qrcode import (
    WxQrcodeService,
    WxQrcodeError,
    WxQrcodeNotConfigured,
)
from app.core.constants import RANGE_OPTIONS

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "名堂 API"}


@router.post("/generate", response_model=NamingResponse)
async def generate_names(request: NamingRequest):
    engine = NamingEngine()

    # 如果使用八字但未提供完整日期
    if request.use_bazi and not all([request.year, request.month, request.day]):
        raise HTTPException(
            status_code=400,
            detail="使用八字分析需要提供完整的出生日期（年月日）"
        )

    result = engine.generate_names(
        surname=request.surname,
        gender=request.gender,
        year=request.year,
        month=request.month,
        day=request.day,
        hour=request.hour if request.hour is not None else 12,
        minute=request.minute if request.minute is not None else 0,
        name_length=request.name_length,
        max_results=request.max_results,
        use_bazi=request.use_bazi,
        use_poetry=request.use_poetry,
        style=request.style,
        meanings=request.meanings,
        avoid_chars=request.avoid_chars,
        industry=request.industry,
        selected_chars=request.selected_chars,
        source_classes=request.source_classes,
        generational_char=request.generational_char,
        exclude_names=request.exclude_names,
    )

    return NamingResponse(**result)


@router.post("/recommend-chars", response_model=RecommendCharsResponse)
async def recommend_chars(request: RecommendCharsRequest):
    """
    两阶段流程第一步：推荐选字范围。

    根据生辰八字算喜用神，返回按五行分组（喜用神优先）的推荐字，
    用户点选后，将所选字作为 selected_chars 传给 /generate 生成名字。
    """
    engine = NamingEngine()
    result = engine.recommend_chars(
        surname=request.surname,
        gender=request.gender,
        year=request.year,
        month=request.month,
        day=request.day,
        hour=request.hour if request.hour is not None else 12,
        minute=request.minute if request.minute is not None else 0,
        style=request.style,
        meanings=request.meanings,
        avoid_chars=request.avoid_chars,
        limit_per_group=request.limit_per_group,
    )
    return RecommendCharsResponse(**result)


@router.post("/pickable-chars", response_model=PickableCharsResponse)
async def pickable_chars(request: PickableCharsRequest):
    """
    「先字后出处」第一步：可选字表。

    返回**真的组得出名字**的字（门槛感知可行性），而不是字库里铺满的候选。
    先字模式的产能 = 该字在已批准字对里的搭档数，且与姓氏强相关（姓「林」时
    名字两字全平触发三连同调，整类字全灭），故字表必须由后端算过再给前端。

    意象族（日月星辰/草木/水/玉/金/火/土）只用于排序与分组，不作硬过滤——
    实测 7 族仅覆盖池内约 35%，硬过滤会砍掉 65% 的好字。
    用户点选的字最终以 selected_chars 传给 /generate（硬约束）。
    """
    engine = NamingEngine()
    if request.use_bazi and not all([request.year, request.month, request.day]):
        raise HTTPException(
            status_code=400,
            detail="使用八字分析需要提供完整的出生日期（年月日）"
        )
    result = engine.pickable_chars(
        surname=request.surname,
        gender=request.gender,
        year=request.year,
        month=request.month,
        day=request.day,
        hour=request.hour if request.hour is not None else 12,
        minute=request.minute if request.minute is not None else 0,
        use_bazi=request.use_bazi,
        name_length=request.name_length,
        style=request.style,
        meanings=request.meanings,
        imagery_families=request.imagery_families,
        avoid_chars=request.avoid_chars,
        source_classes=request.source_classes,
        generational_char=request.generational_char,
        limit=request.limit,
    )
    return PickableCharsResponse(**result)


@router.post("/recommend-sources", response_model=RecommendSourcesResponse)
async def recommend_sources(request: RecommendSourcesRequest):
    """
    两模式流程第一步：推荐「来源」（诗句/古文），先不确定字。

    mode="meaning_first"：按寓意匹配度排序（八字仅作忌神避让提示）；
    mode="bazi_first"：先返回八字解释 + 起名方向，来源按喜用神倾向排序。
    """
    engine = NamingEngine()
    result = engine.recommend_sources(
        surname=request.surname,
        gender=request.gender,
        year=request.year,
        month=request.month,
        day=request.day,
        hour=request.hour if request.hour is not None else 12,
        minute=request.minute if request.minute is not None else 0,
        mode=request.mode,
        meanings=request.meanings,
        avoid_chars=request.avoid_chars,
        limit=request.limit,
    )
    return RecommendSourcesResponse(**result)


@router.post("/source-chars", response_model=SourceCharsResponse)
async def source_chars(request: SourceCharsRequest):
    """两模式流程第二步：用户选定来源后，在该来源内按八字喜用神推荐字。"""
    engine = NamingEngine()
    result = engine.source_chars(
        surname=request.surname,
        gender=request.gender,
        year=request.year,
        month=request.month,
        day=request.day,
        hour=request.hour if request.hour is not None else 12,
        minute=request.minute if request.minute is not None else 0,
        source_ids=request.source_ids,
        limit_per_source=request.limit_per_source,
    )
    return SourceCharsResponse(**result)


@router.post("/name/meaning", response_model=MeaningResponse)
async def name_meaning(request: MeaningRequest):
    """
    名字寓意懒加载（详情页，讲余味）

    对单个名字调一次 LLM 生成多层余味寓意（layers: 字面/出处/余味），
    LLM 失败回退模板，并标记 meaning_source=llm/template。结果带缓存。
    """
    engine = NamingEngine()
    result = await engine.generate_meaning_detail(
        full_name=request.full_name,
        gender=request.gender,
        year=request.year,
        month=request.month,
        day=request.day,
        hour=request.hour if request.hour is not None else 12,
        minute=request.minute if request.minute is not None else 0,
    )
    return MeaningResponse(**result)


@router.post("/prenatal", response_model=PrenatalResponse)
async def prenatal(request: PrenatalRequest):
    """
    预产期起名（孕期参考 / 范围建议）

    以预产期为中心 ±range_days 采样，聚合日主/喜用神五行概率分布，
    返回确定性结果（生肖/月柱）+ 概率分布 + 起名建议（稳定五行 + 安全字）。
    """
    if request.range_days not in RANGE_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"range_days 仅支持 {RANGE_OPTIONS}",
        )

    engine = PrenatalEngine()
    try:
        result = engine.generate(
            due_date=request.due_date,
            range_days=request.range_days,
            gender=request.gender or "male",
            style=request.style,
            meanings=request.meanings,
            avoid_chars=request.avoid_chars,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return PrenatalResponse(**result)


@router.post("/analyze")
async def analyze_name(request: NameAnalysisRequest):
    """
    名字解析（释名）

    输入完整姓名，返回五行、音律、五格、寓意等分析。
    如提供生辰，还会分析八字匹配度；不提供时辰时 `hour_known=false`，
    时柱不参与展示（内部按午时排盘保证可算，但不当成用户给的事实）。
    """
    ok, reason = is_valid_full_name(request.full_name)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    # 解析逻辑全部收在 services/name_analyzer.py：
    # 批量对比接口走同一条路径，保证同一个名字两处得分一致
    return analyze_full_name(
        request.full_name,
        year=request.year,
        month=request.month,
        day=request.day,
        hour=request.hour,
        minute=request.minute,
        gender=request.gender,
    )


@router.post("/analyze/batch", response_model=BatchAnalysisResponse)
async def analyze_batch(request: BatchAnalysisRequest):
    """
    批量释名（测候选名 / 双名对比）

    一次最多 5 个姓名，逐个走与 `/analyze` 完全相同的解析。
    单项不合法只跳过那一项（进 `rejected` 并给出原因），不让整批失败 ——
    用户粘 5 个名字，不该因为第 3 个写错就什么都看不到。
    """
    items: list[dict] = []
    rejected: list[dict] = []
    seen: set[str] = set()

    for raw in request.names:
        name = (raw or "").strip()
        if not name:
            continue
        if name in seen:
            continue
        seen.add(name)

        ok, reason = is_valid_full_name(name)
        if not ok:
            rejected.append({"name": name, "reason": reason})
            continue

        items.append(analyze_full_name(
            name,
            year=request.year,
            month=request.month,
            day=request.day,
            hour=request.hour,
            minute=request.minute,
            gender=request.gender,
        ))

    return {
        "items": items,
        "rejected": rejected,
        "hour_known": request.hour is not None,
    }


@router.get("/share/qrcode")
async def share_qrcode(width: int = 430):
    """
    分享页小程序码（PNG）

    未配置 WX_APPID / WX_SECRET 时返回 501 —— 当前处于开发期（未提审），
    这是**正常状态**：前端据 501 显示占位印，不当作故障。
    配置后返回指向起名入口的小程序码（scene 不支持中文，故不指向具体名字）。
    """
    try:
        png = await WxQrcodeService.get_entry_qrcode(width)
    except WxQrcodeNotConfigured as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except WxQrcodeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # 码图不含用户隐私，可短缓存；CDN/客户端都能省一次往返
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/chars")
async def query_chars(
    wuxing: str = None,
    gender: str = None,
    min_strokes: int = None,
    max_strokes: int = None,
    limit: int = 50,
):
    """查询字库"""
    db = CharDatabase()
    chars = db.filter(
        wuxing=wuxing,
        gender=gender,
        min_strokes=min_strokes,
        max_strokes=max_strokes,
    )
    return {
        "total": len(chars),
        "chars": chars[:limit],
    }


@router.get("/poetry")
async def query_poetry(
    char: str = None,
    imagery: str = None,
    source: str = None,
    gender: str = None,
    limit: int = 20,
):
    """查询诗词典故库"""
    db = PoetryDatabase()
    poems = db.filter(
        char=char,
        imagery=imagery,
        source=source,
        gender=gender,
    )
    return {
        "total": len(poems),
        "poems": poems[:limit],
    }


@router.post("/creative/generate", response_model=CreativeResponse)
async def creative_generate(request: CreativeRequest):
    """
    创意起名（网名昵称 / 宠物 / 商业）

    覆盖 xmind「起名」大类除宝宝起名外的全部能力：
    kind=platform 平台名称 / game 游戏昵称 / role 虚构角色 / pet 宠物 / business 商业名称。
    本地词库离线生成，确定性输出；LLM 未接入时 fallback_note 会如实标注。
    """
    service = CreativeNamingService()
    try:
        result = service.generate(
            kind=request.kind,
            keywords=request.keywords,
            style=request.style,
            pet_type=request.pet_type,
            gender=request.gender,
            industry=request.industry,
            genre=request.genre,
            trait=request.trait,
            platform_type=request.platform_type,
            game_type=request.game_type,
            count=request.count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return CreativeResponse(**result)


@router.post("/creative/llm", response_model=CreativeLLMResponse)
async def creative_llm(request: CreativeLLMRequest):
    """
    创意起名 · AI 生成（虚拟人物自定义描述）

    用户输入自定义设定描述，看广告解锁后调用。调用 LLM 生成贴合设定的角色名；
    LLM 未配置（或调用失败）时降级本地词库，source="local" 并附 fallback_note。
    """
    service = CreativeNamingService()
    result = await service.generate_llm(
        description=request.description,
        genre=request.genre,
        trait=request.trait,
        gender=request.gender,
        count=request.count,
    )
    return CreativeLLMResponse(**result)


@router.get("/bazi")
async def query_bazi(
    year: int,
    month: int,
    day: int,
    hour: int = 12,
    minute: int = 0,
    gender: str = "male",
):
    """查询八字排盘"""
    result = BaziEngine.generate_bazi(year, month, day, hour, minute, gender)
    return result
