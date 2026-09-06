"""
请求/响应数据模型
"""

from pydantic import BaseModel, Field
from typing import Optional


class NamingRequest(BaseModel):
    """起名请求"""
    surname: str = Field(..., min_length=1, max_length=4, description="姓氏")
    gender: str = Field("male", pattern="^(male|female)$", description="性别")
    year: Optional[int] = Field(None, ge=1900, le=2100, description="出生年")
    month: Optional[int] = Field(None, ge=1, le=12, description="出生月")
    day: Optional[int] = Field(None, ge=1, le=31, description="出生日")
    hour: Optional[int] = Field(12, ge=0, le=23, description="出生时")
    minute: Optional[int] = Field(0, ge=0, le=59, description="出生分")
    name_length: int = Field(2, ge=1, le=2, description="名字字数（1或2）")
    max_results: int = Field(20, ge=1, le=50, description="最大返回数量")
    use_bazi: bool = Field(True, description="是否使用八字分析")
    use_poetry: bool = Field(True, description="是否使用诗词典故")
    style: Optional[str] = Field(None, description="风格偏好: classic|modern|grand|fresh")
    meanings: Optional[list[str]] = Field(None, max_length=3, description="期望寓意，最多3个")
    avoid_chars: Optional[list[str]] = Field(None, description="避讳字（单个汉字列表）")
    industry: Optional[str] = Field(None, description="行业 code，映射五行（P1 启用）")
    selected_chars: Optional[list[str]] = Field(None, description="用户点选的候选字（两阶段流程）")


class RecommendCharsRequest(BaseModel):
    """选字推荐请求（两阶段流程第一步）"""
    surname: str = Field(..., min_length=1, max_length=4, description="姓氏")
    gender: str = Field("male", pattern="^(male|female)$", description="性别")
    year: Optional[int] = Field(None, ge=1900, le=2100, description="出生年")
    month: Optional[int] = Field(None, ge=1, le=12, description="出生月")
    day: Optional[int] = Field(None, ge=1, le=31, description="出生日")
    hour: Optional[int] = Field(12, ge=0, le=23, description="出生时")
    minute: Optional[int] = Field(0, ge=0, le=59, description="出生分")
    style: Optional[str] = Field(None, description="风格偏好: classic|modern|grand|fresh")
    meanings: Optional[list[str]] = Field(None, max_length=3, description="期望寓意，最多3个")
    avoid_chars: Optional[list[str]] = Field(None, description="避讳字（单个汉字列表）")
    limit_per_group: int = Field(8, ge=1, le=20, description="每个五行分组返回的字数上限")


class NameAnalysisRequest(BaseModel):
    """名字解析请求"""
    full_name: str = Field(..., min_length=2, max_length=10, description="完整姓名")
    year: Optional[int] = Field(None, ge=1900, le=2100)
    month: Optional[int] = Field(None, ge=1, le=12)
    day: Optional[int] = Field(None, ge=1, le=31)
    hour: Optional[int] = Field(12, ge=0, le=23)
    minute: Optional[int] = Field(0, ge=0, le=59)
    gender: Optional[str] = Field(None, pattern="^(male|female)$")


class PrenatalRequest(BaseModel):
    """预产期起名请求（孕期参考/范围建议）"""
    due_date: str = Field(..., description="预产期 YYYY-MM-DD")
    range_days: int = Field(7, description="预产期前后浮动天数，取值 0|3|7|14")
    gender: Optional[str] = Field("male", pattern="^(male|female)$", description="性别，用于候选字推荐")
    style: Optional[str] = Field(None, description="风格偏好: classic|modern|grand|fresh")
    meanings: Optional[list[str]] = Field(None, max_length=3, description="期望寓意，最多3个")
    avoid_chars: Optional[list[str]] = Field(None, description="避讳字（单个汉字列表）")


class PrenatalResponse(BaseModel):
    """预产期起名响应"""
    due_date: str
    range_days: int
    range: dict
    certain: dict
    probabilistic: dict
    suggestion: dict


class CharInfoResponse(BaseModel):
    char: str
    pinyin: str
    wuxing: str
    kangxi_strokes: int
    meaning: str


class PoetryInfoResponse(BaseModel):
    source: str
    title: str
    author: str
    dynasty: str
    text: str


class PhoneticsResponse(BaseModel):
    pinyins: list[str]
    tones: list[int]
    tone_types: list[str]
    rhythm: str
    score: int
    description: str


class WugeResponse(BaseModel):
    tian_ge: dict
    ren_ge: dict
    di_ge: dict
    wai_ge: dict
    zong_ge: dict
    total_score: int
    description: str


class NameResult(BaseModel):
    full_name: str
    given_name: str
    chars_info: list[dict]
    poetry: Optional[dict] = None
    phonetics: dict
    wuge: dict
    scores: dict
    meaning: str


class NamingResponse(BaseModel):
    """起名响应"""
    bazi: Optional[dict] = None
    names: list[NameResult]
    total: int
    fallback_note: Optional[str] = None


class ApiResponse(BaseModel):
    """通用API响应"""
    success: bool = True
    data: dict = None
    message: str = ""


class MeaningRequest(BaseModel):
    """名字寓意懒加载请求（详情页）"""
    full_name: str = Field(..., min_length=2, max_length=10, description="完整姓名")
    gender: str = Field("male", pattern="^(male|female)$", description="性别")
    year: Optional[int] = Field(None, ge=1900, le=2100, description="出生年")
    month: Optional[int] = Field(None, ge=1, le=12, description="出生月")
    day: Optional[int] = Field(None, ge=1, le=31, description="出生日")
    hour: Optional[int] = Field(12, ge=0, le=23, description="出生时")
    minute: Optional[int] = Field(0, ge=0, le=59, description="出生分")


class MeaningResponse(BaseModel):
    """名字寓意懒加载响应（多层余味）"""
    full_name: str
    given_name: Optional[str] = None
    surname: Optional[str] = None
    citation: Optional[str] = None
    layers: list[dict] = Field(default_factory=list, description="多层余味（字面/出处/余味）")
    meaning: str
    poetry_note: Optional[str] = None
    wuxing_note: Optional[str] = None
    overall_note: Optional[str] = None
    meaning_source: str = "template"
    provider: Optional[str] = None
    model: Optional[str] = None


class RecommendCharsResponse(BaseModel):
    """选字推荐响应（两阶段流程第一步）"""
    bazi: Optional[dict] = None
    groups: list[dict] = Field(default_factory=list, description="按五行分组的推荐字")
    total: int = 0


class RecommendSourcesRequest(BaseModel):
    """来源推荐请求（寓意优先/命格优先 两模式流程第一步）"""
    surname: str = Field(..., min_length=1, max_length=4, description="姓氏")
    gender: str = Field("male", pattern="^(male|female)$", description="性别")
    year: Optional[int] = Field(None, ge=1900, le=2100, description="出生年")
    month: Optional[int] = Field(None, ge=1, le=12, description="出生月")
    day: Optional[int] = Field(None, ge=1, le=31, description="出生日")
    hour: Optional[int] = Field(12, ge=0, le=23, description="出生时")
    minute: Optional[int] = Field(0, ge=0, le=59, description="出生分")
    mode: str = Field("bazi_first", pattern="^(meaning_first|bazi_first)$",
                      description="寓意优先/命格优先")
    meanings: Optional[list[str]] = Field(None, max_length=3, description="期望寓意（寓意优先时用）")
    avoid_chars: Optional[list[str]] = Field(None, description="避讳字")
    limit: int = Field(20, ge=1, le=50, description="返回来源数量上限")


class RecommendSourcesResponse(BaseModel):
    """来源推荐响应"""
    mode: str = "bazi_first"
    bazi: Optional[dict] = None
    bazi_explanation: Optional[dict] = None
    sources: list[dict] = Field(default_factory=list, description="来源列表（诗句/古文）")
    total: int = 0


class SourceCharsRequest(BaseModel):
    """来源内选字请求（两模式流程第二步）"""
    surname: str = Field(..., min_length=1, max_length=4, description="姓氏")
    gender: str = Field("male", pattern="^(male|female)$", description="性别")
    year: Optional[int] = Field(None, ge=1900, le=2100, description="出生年")
    month: Optional[int] = Field(None, ge=1, le=12, description="出生月")
    day: Optional[int] = Field(None, ge=1, le=31, description="出生日")
    hour: Optional[int] = Field(12, ge=0, le=23, description="出生时")
    minute: Optional[int] = Field(0, ge=0, le=59, description="出生分")
    source_ids: list[str] = Field(..., description="用户选定的来源 id 列表")
    limit_per_source: int = Field(8, ge=1, le=20, description="每个来源返回的字数上限")


class SourceCharsResponse(BaseModel):
    """来源内选字响应"""
    bazi: Optional[dict] = None
    sources: list[dict] = Field(default_factory=list, description="各来源内的推荐字")
    total: int = 0
