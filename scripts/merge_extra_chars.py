"""
合并补充字库数据到 chars.json

读取 scripts/extra_chars_data.py 的 EXTRA_CHARS，
用 pypinyin 自动生成拼音和声调，合并进 data/dict/chars.json（自动去重）。

用法：
    python scripts/merge_extra_chars.py
"""

import json
import re
from pathlib import Path
from pypinyin import pinyin, Style

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
CHARS_PATH = ROOT / "data" / "dict" / "chars.json"

# 导入补充数据
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from extra_chars_data import EXTRA_CHARS


def gen_pinyin_and_tone(char: str):
    """用 pypinyin 生成拼音（无声调）和声调数字"""
    normal = pinyin(char, style=Style.NORMAL)
    tone3 = pinyin(char, style=Style.TONE3)
    py = normal[0][0] if normal else ""
    t = 0
    if tone3 and tone3[0]:
        m = re.search(r"(\d)$", tone3[0][0])
        if m:
            t = int(m.group(1))
    return py, t


def main():
    with open(CHARS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    existing = {c["char"] for c in data["chars"]}
    added = 0
    skipped = 0

    for item in EXTRA_CHARS:
        ch = item["char"]
        if ch in existing:
            skipped += 1
            continue

        py, tone = gen_pinyin_and_tone(ch)
        entry = {
            "char": ch,
            "pinyin": py,
            "tone": tone,
            "radical": item["radical"],
            "kangxi_strokes": item["kangxi_strokes"],
            "simplified_strokes": item["simplified_strokes"],
            "wuxing": item["wuxing"],
            "luck": item["luck"],
            "gender": item["gender"],
            "meaning": item["meaning"],
            "shuowen": item["shuowen"],
            "detail": item["detail"],
        }
        data["chars"].append(entry)
        existing.add(ch)
        added += 1

    data["total"] = len(data["chars"])
    # 版本升级到 2.1
    data["version"] = "2.1"

    with open(CHARS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"新增 {added} 字，跳过(已存在) {skipped} 字，字库总数 {data['total']}，版本 {data['version']}")


if __name__ == "__main__":
    main()
