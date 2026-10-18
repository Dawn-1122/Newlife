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
    style: Optional[str] = Field(None, description="风格偏好: classic|modern|grand|fresh|warm|elegant|plain|zen")
    meanings: Optional[list[str]] = Field(None, max_length=3, description="期望寓意（code 见 /chars 的 meanings 字段），最多3个，取值: wisdom|health|bravery|gentle|wealth|peace|talent|virtue|beauty|loyal|patriotic|tranquil|resilient|optimistic")
    avoid_chars: Optional[list[str]] = Field(None, description="避讳字（单个汉字列表）")
    industry: Optional[str] = Field(None, description="行业 code，映射五行（**商业起名**纵向使用；宝宝起名主流程不再暴露该字段，此处仅作透传位）")
    selected_chars: Optional[list[str]] = Field(None, description="用户点选的候选字（先字后出处）：语义为「名字必须含所选字」（任一位置）")
    source_classes: Optional[list[str]] = Field(None, description="出处类目限定（先出处后字），可多选: 诗经|楚辞|汉魏古诗|唐诗|五代词|宋词|清词|经史子集（字源 4 部典籍归入经史子集）")
    generational_char: Optional[str] = Field(None, max_length=1, description="字辈（可选，仅双字名生效）：固定出现在名字第二个字，硬约束")


class RecommendCharsRequest(BaseModel):
    """选字推荐请求（两阶段流程第一步）"""
    surname: str = Field(..., min_length=1, max_length=4, description="姓氏")
    gender: str = Field("male", pattern="^(male|female)$", description="性别")
    year: Optional[int] = Field(None, ge=1900, le=2100, description="出生年")
    month: Optional[int] = Field(None, ge=1, le=12, description="出生月")
    day: Optional[int] = Field(None, ge=1, le=31, description="出生日")
    hour: Optional[int] = Field(12, ge=0, le=23, description="出生时")
    minute: Optional[int] = Field(0, ge=0, le=59, description="出生分")
    style: Optional[str] = Field(None, description="风格偏好: classic|modern|grand|fresh|warm|elegant|plain|zen")
    meanings: Optional[list[str]] = Field(None, max_length=3, description="期望寓意（code 见 /chars 的 meanings 字段），最多3个，取值: wisdom|health|bravery|gentle|wealth|peace|talent|virtue|beauty|loyal|patriotic|tranquil|resilient|optimistic")
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
    style: Optional[str] = Field(None, description="风格偏好: classic|modern|grand|fresh|warm|elegant|plain|zen")
    meanings: Optional[list[str]] = Field(None, max_length=3, description="期望寓意（code 见 /chars 的 meanings 字段），最多3个，取值: wisdom|health|bravery|gentle|wealth|peace|talent|virtue|beauty|loyal|patriotic|tranquil|resilient|optimistic")
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
    context_senses: list[dict] = Field(
        default_factory=list,
        description='各字在本出处语境下的取义 [{"char":"清","senses":["清朗"],"general":"水清"}]',
    )
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
    context_senses: list[dict] = Field(
        default_factory=list,
        description='逐字语境义项 [{"char":"清","senses":["清朗","高远"],"general":"水清"}]',
    )
    meaning_source: str = "template"
    provider: Optional[str] = None
    model: Optional[str] = None


class RecommendCharsResponse(BaseModel):
    """选字推荐响应（两阶段流程第一步）"""
    bazi: Optional[dict] = None
    groups: list[dict] = Field(default_factory=list, description="按五行分组的推荐字")
    total: int = 0


class PickableCharsRequest(BaseModel):
    """可选字表请求（「先字后出处」路径：用户在字表里点选候选字）"""
    surname: str = Field(..., min_length=1, max_length=4, description="姓氏")
    gender: str = Field("female", pattern="^(male|female)$", description="性别")
    year: Optional[int] = Field(None, ge=1900, le=2100, description="出生年")
    month: Optional[int] = Field(None, ge=1, le=12, description="出生月")
    day: Optional[int] = Field(None, ge=1, le=31, description="出生日")
    hour: Optional[int] = Field(12, ge=0, le=23, description="出生时")
    minute: Optional[int] = Field(0, ge=0, le=59, description="出生分")
    use_bazi: bool = Field(False, description="是否使用八字分析")
    name_length: int = Field(2, ge=1, le=2, description="名字字数（1或2，决定门槛口径）")
    style: Optional[str] = Field(None, description="风格偏好: classic|modern|grand|fresh|warm|elegant|plain|zen")
    meanings: Optional[list[str]] = Field(None, max_length=3, description="期望寓意（code 见 /chars 的 meanings 字段），最多3个")
    imagery_families: Optional[list[str]] = Field(
        None,
        description="字形意象族（排序用，不作硬过滤）: 日月星辰|草木|水|玉|金|火|土",
    )
    avoid_chars: Optional[list[str]] = Field(None, description="避讳字（单个汉字列表）")
    source_classes: Optional[list[str]] = Field(None, description="出处类目限定（可选），可多选: 诗经|楚辞|汉魏古诗|唐诗|五代词|宋词|清词|经史子集（字源 4 部典籍归入经史子集）")
    generational_char: Optional[str] = Field(None, max_length=1, description="字辈（可选，仅双字名生效）：固定出现在名字第二个字，硬约束")
    limit: int = Field(400, ge=1, le=400, description="返回字数上限")


class PickableCharsResponse(BaseModel):
    """可选字表响应（每个字都能真的组出名字；字表外的字一个都出不来）"""
    bazi: Optional[dict] = None
    total: int = Field(0, description="池内字数（有出处、性别相符、非黑名单）")
    feasible: int = Field(0, description="真出得来名字的字数（字表实际可选范围）")
    returned: int = 0
    truncated: bool = False
    no_family: int = Field(0, description="无意象族归属的字数（7 族只覆盖约 35%）")
    families: list[dict] = Field(
        default_factory=list,
        description='意象族概览 [{"family","count","total","selected","sample"}]',
    )
    chars: list[dict] = Field(
        default_factory=list,
        description='字表 [{"char","pinyin","wuxing","family","partner_count",'
                    '"name_hits","match","xiyong","sample","meaning"}]',
    )


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


class CreativeRequest(BaseModel):
    """创意起名请求（网名昵称 / 宠物 / 商业）"""
    kind: str = Field(..., pattern="^(platform|game|role|pet|business)$",
                      description="起名类型: platform(平台名称)|game(游戏昵称)|role(虚构角色)|pet(宠物)|business(商业名称)")
    keywords: str = Field("", max_length=100,
                          description="自由输入：身份/兴趣/关键词/设定，空格或逗号分隔")
    style: Optional[str] = Field(None, description="风格偏好（复用 STYLE_OPTIONS code，暂作透传）")
    pet_type: Optional[str] = Field(None, pattern="^(cat|dog|other)$",
                                    description="宠物种类（kind=pet 时用）: cat|dog|other")
    gender: Optional[str] = Field(None, pattern="^(male|female)$",
                                  description="性别（kind=role/pet 时用）: male|female")
    industry: Optional[str] = Field(None, description="行业 code（kind=business 时用，见 INDUSTRY_WUXING）")
    genre: Optional[str] = Field(None, description="小说类型 code（kind=role 时用，见 NOVEL_GENRES）")
    trait: Optional[str] = Field(None, description="性格特征 code（kind=role 时用，见 CHARACTER_TRAITS）")
    count: int = Field(12, ge=1, le=30, description="返回名字数量")


class CreativeNameResult(BaseModel):
    """单个创意名字"""
    name: str
    tag: str = ""
    reason: str = ""


class CreativeResponse(BaseModel):
    """创意起名响应"""
    kind: str
    total: int
    names: list[CreativeNameResult] = Field(default_factory=list)
    fallback_note: Optional[str] = None


class CreativeLLMRequest(BaseModel):
    """创意起名 LLM 请求（虚拟人物自定义描述，看广告解锁后调用）"""
    description: str = Field(..., min_length=1, max_length=300,
                             description="自定义描述：人物设定 / 世界观 / 关键词等自由文本")
    genre: Optional[str] = Field(None, description="小说类型 code（kind=role 时用，见 NOVEL_GENRES）")
    trait: Optional[str] = Field(None, description="性格特征 code（kind=role 时用，见 CHARACTER_TRAITS）")
    gender: Optional[str] = Field(None, pattern="^(male|female)$", description="角色性别")
    count: int = Field(12, ge=1, le=20, description="返回名字数量")


class CreativeLLMResponse(BaseModel):
    """创意起名 LLM 响应（source=llm 为 AI 生成，local 为本地词库降级）"""
    source: str = Field("llm", description="llm=AI 生成 / local=本地词库降级")
    total: int
    names: list[CreativeNameResult] = Field(default_factory=list)
    provider: Optional[str] = None
    model: Optional[str] = None
    fallback_note: Optional[str] = None
