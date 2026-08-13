"""
字库增强脚本 - 为每个汉字添加说文解字原文和详细释义

读取 data/dict/shuowen_data.json 和 data/dict/chars.json，
合并后写回 chars.json。

数据来源：
- 《说文解字》(汉·许慎) 原文
- 《康熙字典》释义
- 字源学研究成果
"""

import json
from pathlib import Path


def enrich_char_db():
    """为字库添加说文解字和详细释义"""
    base = Path(__file__).parent.parent
    chars_path = base / "data" / "dict" / "chars.json"
    shuowen_path = base / "data" / "dict" / "shuowen_data.json"

    with open(chars_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(shuowen_path, "r", encoding="utf-8") as f:
        shuowen_data = json.load(f)

    enriched = 0
    missing = []

    for char_entry in data["chars"]:
        char = char_entry["char"]
        if char in shuowen_data:
            char_entry["shuowen"] = shuowen_data[char]["shuowen"]
            char_entry["detail"] = shuowen_data[char]["detail"]
            enriched += 1
        else:
            char_entry["shuowen"] = ""
            char_entry["detail"] = char_entry.get("meaning", "")
            missing.append(char)

    data["version"] = "2.0"

    with open(chars_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"字库增强完成: {chars_path}")
    print(f"已增强: {enriched} 字")
    if missing:
        print(f"未找到说文数据: {missing}")
    else:
        print("全部字已匹配说文解字数据")


if __name__ == "__main__":
    enrich_char_db()
