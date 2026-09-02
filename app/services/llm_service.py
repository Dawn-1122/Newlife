"""
LLM 寓意解读模块

支持多LLM提供商切换，用RAG方式检索诗词典故后让LLM生成寓意解读。
包含prompt工程，确保解读准确、有深度、不编造出处。

支持的提供商：
- DeepSeek (deepseek-chat)
- 通义千问 (qwen-plus)
- 智谱 (glm-4)

使用方式：
    from app.services.llm_service import LLMService
    llm = LLMService(provider="deepseek", api_key="sk-xxx")
    result = await llm.generate_meaning(...)

    # 通用对话（诗词批量标注也复用它）
    result = await llm.chat(
        messages=[{"role": "user", "content": "..."}],
        temperature=0.2, max_tokens=500, json_mode=True,
    )
"""

import httpx
import json
from typing import Optional
from app.core.config import settings


class LLMError(Exception):
    """LLM 调用/解析异常（供调用方重试）。"""


class LLMService:
    """LLM 寓意解读服务"""

    # 各提供商配置
    PROVIDERS = {
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "name": "DeepSeek",
        },
        "qwen": {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
            "name": "通义千问",
        },
        "zhipu": {
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4",
            "name": "智谱GLM",
        },
    }

    def __init__(self, provider: str = None, api_key: str = None,
                 base_url: str = None, model: str = None, timeout: float = 60.0):
        self.provider = provider or settings.LLM_PROVIDER
        self.api_key = api_key or settings.LLM_API_KEY
        self.config = self.PROVIDERS.get(self.provider, {})
        # 优先使用显式参数 / .env 配置的 base_url/model（支持 OpenRouter 等 OpenAI 兼容服务）
        self.base_url = (base_url or settings.LLM_BASE_URL
                         or self.config.get("base_url", ""))
        self.model = model or settings.LLM_MODEL or self.config.get("model", "")
        self.timeout = timeout

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        json_mode: bool = False,
    ) -> dict:
        """
        通用对话接口（OpenAI 兼容）。

        Args:
            messages: [{"role": "system"/"user"/"assistant", "content": "..."}]
            temperature: 采样温度
            max_tokens: 最大生成 token 数
            json_mode: 是否开启 JSON 输出模式（response_format=json_object）

        Returns:
            解析后的 dict（json_mode 或内容本身为 JSON 时）；否则 {"content": "..."}。

        Raises:
            LLMError: HTTP 错误 / JSON 解析失败（供调用方重试）。
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = e.response.text[:300]
            except Exception:
                pass
            raise LLMError(
                f"HTTP {e.response.status_code}: {detail}"
            ) from e
        except Exception as e:
            raise LLMError(str(e)) from e

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"响应结构异常: {data}") from e

        return self._parse_content(content, json_mode)

    @staticmethod
    def _parse_content(content: str, json_mode: bool) -> dict:
        """解析 LLM 返回内容：剥掉 markdown 代码块，尝试 JSON。"""
        content = (content or "").strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            if json_mode:
                raise LLMError(f"JSON 解析失败: {content[:200]}")
            return {"content": content}

    async def generate_meaning(
        self,
        full_name: str,
        chars_info: list[dict],
        poetry_data: Optional[dict] = None,
        bazi_data: Optional[dict] = None,
        gender: str = "male",
    ) -> dict:
        """
        生成名字寓意解读

        Args:
            full_name: 完整姓名
            chars_info: 名字用字信息列表
            poetry_data: 诗词出处（如有）
            bazi_data: 八字分析数据（如有）
            gender: 性别

        Returns:
            {
                "meaning": "...",      # 寓意解读
                "poetry_note": "...",  # 诗词赏析
                "wuxing_note": "...",  # 五行分析
                "overall_note": "...", # 综合点评
                "provider": "deepseek",
                "model": "deepseek-chat",
            }
        """
        prompt = self._build_prompt(
            full_name, chars_info, poetry_data, bazi_data, gender
        )

        try:
            response = await self.chat(
                messages=[
                    {"role": "system",
                     "content": "你是一位中国传统文化和姓名学专家。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=1200,
                json_mode=True,
            )
            return {
                **response,
                "provider": self.provider,
                "model": self.model,
            }
        except LLMError as e:
            return {
                "meaning": f"解读生成失败: {str(e)}",
                "poetry_note": "",
                "wuxing_note": "",
                "overall_note": "",
                "provider": self.provider,
                "model": self.model,
                "error": str(e),
            }

    def _build_prompt(
        self,
        full_name: str,
        chars_info: list[dict],
        poetry_data: Optional[dict],
        bazi_data: Optional[dict],
        gender: str,
    ) -> str:
        """构建LLM提示词"""

        gender_text = "男孩" if gender == "male" else "女孩"

        # 名字用字信息
        chars_desc = ""
        for ci in chars_info:
            chars_desc += (
                f"  - 「{ci['char']}」: 五行属{ci.get('wuxing', '未知')}, "
                f"康熙笔画{ci.get('kangxi_strokes', '?')}画, "
                f"含义: {ci.get('meaning', '未知')}\n"
            )

        # 诗词出处
        poetry_desc = ""
        if poetry_data:
            poetry_desc = (
                f"诗词出处: 「{poetry_data['source']}·{poetry_data['title']}」\n"
                f"作者: {poetry_data['author']}（{poetry_data['dynasty']}）\n"
                f"原文: {poetry_data['text']}\n"
            )
        else:
            poetry_desc = "诗词出处: 无（此名字非出自诗词典故）\n"

        # 八字信息
        bazi_desc = ""
        if bazi_data:
            wx = bazi_data.get("xiyong", {})
            bazi_desc = (
                f"八字信息:\n"
                f"  日主: {bazi_data.get('day_master', '?')}（{bazi_data.get('day_master_wuxing', '?')}）\n"
                f"  身强身弱: {wx.get('strength_label', '?')}\n"
                f"  喜用神五行: {', '.join(wx.get('xi_wuxing', []))}\n"
                f"  用神: {wx.get('yong_wuxing', '?')}\n"
            )
        else:
            bazi_desc = "八字信息: 未提供\n"

        prompt = f"""你是一位精通中国传统文化、诗词典故和姓名学的专家。
请为以下{gender_text}的名字生成一份「层层递进」的寓意解读。

【名字】{full_name}

【名字用字信息】
{chars_desc}

{poetry_desc}

{bazi_desc}

请按以下 JSON 格式输出（不要用代码块包裹，必须是合法 JSON）：

{{
  "layers": [
    {{"level": "字面", "text": "第一层：从名字用字本身解释字义（一句话，言之有物）"}},
    {{"level": "出处", "text": "第二层：如有出处，讲清典故原文意境与名字的关联（一句话）"}},
    {{"level": "余味", "text": "第三层：点出意象联想与余味，讲出这个名字'藏了几层意思'（一句话）"}}
  ],
  "meaning": "用2-3句话整体解读这个名字，层层递进、不空泛",
  "poetry_note": "出处意境与名字的关联（无出处则说明名字用字本身的文化意蕴）",
  "wuxing_note": "分析名字用字五行与八字喜用神的匹配（无八字则只分析名字五行搭配）",
  "overall_note": "一句话点睛总结，要有文采"
}}

注意：
1. 严格基于给定数据，不要编造不存在的诗句或出处
2. 必须层层递进：先字面义，再典故义，最后点出意象联想与余味
3. 语言典雅但不晦涩，普通家长能看懂
4. 不要出现"算命""命运""预测"等词汇，用"传统文化""五行搭配"等表述
5. 每个 layer 一句话、言之有物、不堆砌；寓意积极正面但不夸大
"""

        return prompt
