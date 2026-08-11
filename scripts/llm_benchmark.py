"""
LLM 对比测试方案

对 DeepSeek / 通义千问 / 智谱GLM 三家模型进行寓意解读效果对比。

评测维度：
1. 寓意质量（是否言之有物、有深度）
2. 诗词准确性（是否正确引用、不编造）
3. 响应速度（API延迟）
4. 成本（token单价 × 实际token数）

使用方式：
    1. 在环境变量或 .env 文件中设置各家的 API Key：
       DEEPSEEK_API_KEY=sk-xxx
       QWEN_API_KEY=sk-xxx
       ZHIPU_API_KEY=sk-xxx

    2. 运行测试：
       python3 scripts/llm_benchmark.py

    3. 查看报告：
       output/llm_benchmark_report.json
"""

import asyncio
import time
import json
import os
from pathlib import Path
from app.services.llm_service import LLMService

# 测试用例
TEST_CASES = [
    {
        "name": "王鑫瑞",
        "gender": "male",
        "chars_info": [
            {"char": "鑫", "pinyin": "xin", "wuxing": "金", "kangxi_strokes": 24, "meaning": "财富兴盛，多金多福"},
            {"char": "瑞", "pinyin": "rui", "wuxing": "金", "kangxi_strokes": 14, "meaning": "祥瑞、瑞气、吉兆"},
        ],
        "poetry": None,
        "bazi": {
            "day_master": "癸",
            "day_master_wuxing": "水",
            "xiyong": {
                "strength_label": "身弱",
                "xi_wuxing": ["金", "水"],
                "yong_wuxing": "金",
            },
        },
    },
    {
        "name": "李清照",
        "gender": "female",
        "chars_info": [
            {"char": "清", "pinyin": "qing", "wuxing": "水", "kangxi_strokes": 12, "meaning": "清澈、清正、清风明月"},
            {"char": "照", "pinyin": "zhao", "wuxing": "火", "kangxi_strokes": 13, "meaning": "照耀、明照、日照"},
        ],
        "poetry": {
            "source": "唐诗",
            "title": "山居秋暝",
            "author": "王维",
            "dynasty": "唐",
            "text": "明月松间照，清泉石上流",
        },
        "bazi": None,
    },
    {
        "name": "张子轩",
        "gender": "male",
        "chars_info": [
            {"char": "子", "pinyin": "zi", "wuxing": "水", "kangxi_strokes": 3, "meaning": "君子、学子、有学问的人"},
            {"char": "轩", "pinyin": "xuan", "wuxing": "土", "kangxi_strokes": 10, "meaning": "气宇轩昂、轩窗、轩昂"},
        ],
        "poetry": None,
        "bazi": {
            "day_master": "甲",
            "day_master_wuxing": "木",
            "xiyong": {
                "strength_label": "身弱",
                "xi_wuxing": ["水", "木"],
                "yong_wuxing": "水",
            },
        },
    },
    {
        "name": "陈芷萱",
        "gender": "female",
        "chars_info": [
            {"char": "芷", "pinyin": "zhi", "wuxing": "木", "kangxi_strokes": 10, "meaning": "白芷、香草、品行高洁"},
            {"char": "萱", "pinyin": "xuan", "wuxing": "木", "kangxi_strokes": 15, "meaning": "萱草、忘忧、母亲花"},
        ],
        "poetry": {
            "source": "楚辞",
            "title": "九歌·湘夫人",
            "author": "屈原",
            "dynasty": "战国",
            "text": "沅有芷兮澧有兰，思公子兮未敢言",
        },
        "bazi": None,
    },
    {
        "name": "刘浩然",
        "gender": "male",
        "chars_info": [
            {"char": "浩", "pinyin": "hao", "wuxing": "水", "kangxi_strokes": 11, "meaning": "浩大、浩然、浩气长存"},
            {"char": "然", "pinyin": "ran", "wuxing": "金", "kangxi_strokes": 12, "meaning": "自然、坦然、理所当然"},
        ],
        "poetry": None,
        "bazi": {
            "day_master": "丙",
            "day_master_wuxing": "火",
            "xiyong": {
                "strength_label": "身强",
                "xi_wuxing": ["土", "金", "水"],
                "yong_wuxing": "土",
            },
        },
    },
]

# 各提供商API Key（从环境变量读取）
PROVIDERS = {
    "deepseek": os.environ.get("DEEPSEEK_API_KEY", ""),
    "qwen": os.environ.get("QWEN_API_KEY", ""),
    "zhipu": os.environ.get("ZHIPU_API_KEY", ""),
}


async def run_single_test(provider: str, api_key: str, case: dict) -> dict:
    """运行单个测试用例"""
    llm = LLMService(provider=provider, api_key=api_key)

    start_time = time.time()
    result = await llm.generate_meaning(
        full_name=case["name"],
        chars_info=case["chars_info"],
        poetry_data=case.get("poetry"),
        bazi_data=case.get("bazi"),
        gender=case["gender"],
    )
    elapsed = time.time() - start_time

    return {
        "name": case["name"],
        "gender": case["gender"],
        "has_poetry": case.get("poetry") is not None,
        "has_bazi": case.get("bazi") is not None,
        "result": result,
        "elapsed_seconds": round(elapsed, 2),
        "has_error": "error" in result,
    }


async def run_benchmark():
    """运行完整对比测试"""
    print("=" * 70)
    print("LLM 寓意解读对比测试")
    print("=" * 70)

    all_results = {}

    for provider, api_key in PROVIDERS.items():
        provider_name = LLMService.PROVIDERS[provider]["name"]
        model = LLMService.PROVIDERS[provider]["model"]

        if not api_key:
            print(f"\n⚠ {provider_name} ({model}): 未配置API Key，跳过")
            all_results[provider] = {
                "provider": provider,
                "name": provider_name,
                "model": model,
                "status": "skipped",
                "reason": "未配置API Key",
            }
            continue

        print(f"\n▶ 测试 {provider_name} ({model})...")

        provider_results = []
        for case in TEST_CASES:
            print(f"  - 测试用例: {case['name']}...", end=" ")
            result = await run_single_test(provider, api_key, case)
            provider_results.append(result)
            if result["has_error"]:
                print(f"失败 ({result['elapsed_seconds']}s)")
            else:
                print(f"完成 ({result['elapsed_seconds']}s)")

        # 统计
        valid_results = [r for r in provider_results if not r["has_error"]]
        avg_time = (
            sum(r["elapsed_seconds"] for r in valid_results) / len(valid_results)
            if valid_results else 0
        )

        all_results[provider] = {
            "provider": provider,
            "name": provider_name,
            "model": model,
            "status": "completed",
            "total_cases": len(TEST_CASES),
            "success_cases": len(valid_results),
            "avg_response_time": round(avg_time, 2),
            "results": provider_results,
        }

        print(f"  → 成功 {len(valid_results)}/{len(TEST_CASES)}, 平均耗时 {avg_time:.2f}s")

    # 输出报告
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "llm_benchmark_report.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 70}")
    print(f"测试报告已保存: {output_path}")
    print(f"{'=' * 70}")

    # 打印摘要
    print("\n📊 测试摘要:")
    for provider, data in all_results.items():
        if data["status"] == "skipped":
            print(f"  {data['name']}: 跳过（{data['reason']}）")
        else:
            print(
                f"  {data['name']} ({data['model']}): "
                f"成功 {data['success_cases']}/{data['total_cases']}, "
                f"平均耗时 {data['avg_response_time']}s"
            )


if __name__ == "__main__":
    asyncio.run(run_benchmark())
