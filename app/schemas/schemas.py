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


class NameAnalysisRequest(BaseModel):
    """名字解析请求"""
    full_name: str = Field(..., min_length=2, max_length=10, description="完整姓名")
    year: Optional[int] = Field(None, ge=1900, le=2100)
    month: Optional[int] = Field(None, ge=1, le=12)
    day: Optional[int] = Field(None, ge=1, le=31)
    hour: Optional[int] = Field(12, ge=0, le=23)
    minute: Optional[int] = Field(0, ge=0, le=59)
    gender: Optional[str] = Field(None, pattern="^(male|female)$")


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


class ApiResponse(BaseModel):
    """通用API响应"""
    success: bool = True
    data: dict = None
    message: str = ""
