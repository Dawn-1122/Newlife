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
    result = await llm.generate_meaning(
        full_name="王鑫瑞",
        chars_info=[...],
        poetry_data={...},
        bazi_data={...},
    )
"""

import httpx
import json
from typing import Optional
from app.core.config import settings


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

    def __init__(self, provider: str = None, api_key: str = None):
        self.provider = provider or settings.LLM_PROVIDER
        self.api_key = api_key or settings.LLM_API_KEY
        self.config = self.PROVIDERS.get(self.provider, self.PROVIDERS["deepseek"])
        self.base_url = self.config["base_url"]
        self.model = self.config["model"]

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

        response = await self._call_llm(prompt)

        return {
            **response,
            "provider": self.provider,
            "model": self.model,
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
请为以下{gender_text}的名字生成一份寓意解读。

【名字】{full_name}

【名字用字信息】
{chars_desc}

{poetry_desc}

{bazi_desc}

请按以下格式输出（用JSON格式，不要用代码块包裹）：

{{
  "meaning": "用2-3句话解读这个名字的整体寓意，要言之有物，不要空泛",
  "poetry_note": "如果有诗词出处，分析原诗意境与名字的关联；如果没有诗词出处，说明名字用字本身的文化意蕴",
  "wuxing_note": "分析名字用字五行与八字喜用神的匹配情况（如无八字信息则只分析名字五行搭配）",
  "overall_note": "一句话总结点评，要有文采"
}}

注意：
1. 如果有诗词出处，必须基于原文分析，不要编造不存在的诗句或出处
2. 语言要典雅但不晦涩，普通家长能看懂
3. 不要出现"算命""命运""预测"等词汇，用"传统文化""五行搭配"等表述
4. 寓意要积极正面，但不要过度夸大
"""

        return prompt

    async def _call_llm(self, prompt: str) -> dict:
        """调用LLM API（OpenAI兼容格式）"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一位中国传统文化和姓名学专家。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 1000,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]

                # 尝试解析JSON
                try:
                    # 去除可能的markdown代码块标记
                    content = content.strip()
                    if content.startswith("```"):
                        content = content.split("\n", 1)[1] if "\n" in content else content
                        content = content.rsplit("```", 1)[0]
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {
                        "meaning": content,
                        "poetry_note": "",
                        "wuxing_note": "",
                        "overall_note": "",
                    }
        except Exception as e:
            return {
                "meaning": f"解读生成失败: {str(e)}",
                "poetry_note": "",
                "wuxing_note": "",
                "overall_note": "",
                "error": str(e),
            }
