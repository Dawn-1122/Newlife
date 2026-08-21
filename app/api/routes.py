"""
API 路由

提供起名、名字解析、字库查询、诗词查询等接口
"""

from fastapi import APIRouter, HTTPException
from app.schemas.schemas import (
    NamingRequest, NamingResponse,
    NameAnalysisRequest, ApiResponse,
    PrenatalRequest, PrenatalResponse,
)
from app.services.naming_engine import NamingEngine
from app.services.char_database import CharDatabase
from app.services.poetry_database import PoetryDatabase
from app.services.bazi_engine import BaziEngine
from app.services.phonetics import PhoneticsScorer
from app.services.wuge import WugeScorer
from app.services.prenatal_engine import PrenatalEngine
from app.core.constants import RANGE_OPTIONS

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "美名集 API"}


@router.post("/generate", response_model=NamingResponse)
async def generate_names(request: NamingRequest):
    """
    生成名字

    输入姓氏、性别、生辰（可选），返回候选名字列表。
    每个名字包含八字分析、诗词出处、音律评分、五格数理。
    """
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
    )

    return NamingResponse(**result)


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
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return PrenatalResponse(**result)


@router.post("/analyze")
async def analyze_name(request: NameAnalysisRequest):
    """
    名字解析

    输入完整姓名，返回五行、音律、五格、寓意等分析。
    如提供生辰，还会分析八字匹配度。
    """
    full_name = request.full_name.strip()
    if len(full_name) < 2:
        raise HTTPException(status_code=400, detail="姓名至少2个字")

    # 拆分姓和名
    # 简化处理：第一个字为姓，其余为名
    # 实际应考虑复姓
    compound_surnames = ["欧阳", "司马", "上官", "诸葛", "皇甫", "令狐", "慕容", "公孙", "尉迟"]
    surname = ""
    given_name = ""
    for cs in compound_surnames:
        if full_name.startswith(cs):
            surname = cs
            given_name = full_name[len(cs):]
            break
    if not surname:
        surname = full_name[0]
        given_name = full_name[1:]

    char_db = CharDatabase()
    phonetics = PhoneticsScorer()
    wuge_scorer = WugeScorer()

    # 字信息
    chars_info = []
    for c in given_name:
        info = char_db.get_char(c)
        if info:
            chars_info.append({
                "char": info["char"],
                "pinyin": info["pinyin"],
                "wuxing": info["wuxing"],
                "kangxi_strokes": info["kangxi_strokes"],
                "meaning": info["meaning"],
                "shuowen": info.get("shuowen", ""),
                "detail": info.get("detail", ""),
            })
        else:
            chars_info.append({
                "char": c,
                "pinyin": "",
                "wuxing": "未知",
                "kangxi_strokes": 0,
                "meaning": "字库中暂无此字信息",
            })

    # 音律
    phonetics_result = phonetics.analyze(full_name)

    # 五格
    try:
        wuge_result = wuge_scorer.calculate(surname, given_name)
    except Exception:
        wuge_result = {"total_score": 0, "description": "数理计算异常"}

    # 八字匹配（如提供生辰）
    bazi_match = None
    if request.year and request.month and request.day:
        bazi = BaziEngine.generate_bazi(
            request.year, request.month, request.day,
            request.hour if request.hour is not None else 12,
            request.minute if request.minute is not None else 0,
            request.gender or "male"
        )
        xiyong = bazi["xiyong"]["xi_wuxing"]
        matched = sum(1 for ci in chars_info if ci.get("wuxing") in xiyong)
        bazi_match = {
            "bazi": bazi,
            "match_score": 60 + int(matched / max(len(chars_info), 1) * 40),
            "matched_wuxing": [ci["wuxing"] for ci in chars_info if ci.get("wuxing") in xiyong],
        }

    # 诗词出处
    poetry_db = PoetryDatabase()
    poetry_matches = []
    for ci in chars_info:
        poems = poetry_db.get_by_char(ci["char"])
        for p in poems:
            if p not in poetry_matches:
                poetry_matches.append(p)

    return {
        "full_name": full_name,
        "surname": surname,
        "given_name": given_name,
        "chars_info": chars_info,
        "phonetics": phonetics_result,
        "wuge": wuge_result,
        "bazi_match": bazi_match,
        "poetry": poetry_matches[0] if poetry_matches else None,
        "poetry_list": poetry_matches[:3],
    }


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
