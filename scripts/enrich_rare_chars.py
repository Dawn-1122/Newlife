"""
生僻字 LLM 批量标注（补 meaning/detail/shuowen/imagery）

复用 llm_annotator 模式（asyncio + Semaphore + 指数退避重试 + 断点续跑），
为字库中 meaning 为空的新扩充字批量补释义。这是「放开生僻字」的落地前提——
生僻字必须带齐意象/出处数据，否则会因「数据贫乏」而非「生僻」被韵味排低。

⚠️ 费用控制：先做小规模试点（约 50 字）验证流程与数据质量，报告确认后再全量。

用法：
    # 试点 50 字（只输出 JSONL，不写回 chars.json）
    venv/bin/python scripts/enrich_rare_chars.py --limit 50

    # 试点 50 字并合并写回 chars.json
    venv/bin/python scripts/enrich_rare_chars.py --limit 50 --merge

    # 全量（谨慎，预算确认后）
    venv/bin/python scripts/enrich_rare_chars.py --merge
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.llm_service import LLMService, LLMError  # noqa: E402

CHARS_PATH = PROJECT_ROOT / "data" / "dict" / "chars.json"
DEFAULT_OUT = PROJECT_ROOT / "data" / "dict" / "rare_enriched.jsonl"
DEFAULT_DONE = PROJECT_ROOT / "data" / "dict" / "rare_enriched_done.json"

SYSTEM_PROMPT = (
    "你是一位精通《说文解字》《康熙字典》与汉字字源学的专家。"
    "请为给定汉字生成起名用途的精简标注，严格基于字源与常见用法，不得编造。"
)


def build_user_prompt(info: dict) -> str:
    radical = info.get("radical", "") or "未知"
    wuxing = info.get("wuxing", "") or "未知"
    strokes = info.get("kangxi_strokes", "")
    return (
        f"汉字：{info['char']}\n"
        f"部首：{radical}\n"
        f"五行：{wuxing}\n"
        f"康熙笔画：{strokes}\n\n"
        "请输出 JSON（不要代码块）：\n"
        "{\n"
        '  "meaning": "2~4 个义项，用中文顿号「、」分隔，如「香草、清雅、高洁」",\n'
        '  "shuowen": "《说文解字》原文（仅在你确定时填写，否则填空字符串）",\n'
        '  "detail": "1~2 句话，字源本义 + 引申义 + 起名寓意",\n'
        '  "imagery": ["2~4 个意象标签"]\n'
        "}\n\n"
        "要求：\n"
        "1. meaning 义项要贴合起名场景、积极正面，不堆砌\n"
        "2. shuowen 不确定就填空字符串，禁止编造古籍原文\n"
        "3. 若该字含负面义（病丧凶恶等），imagery 置空、meaning 首项注明「慎用」\n"
        "4. 语言典雅但可读"
    )


def normalize_result(raw: dict, char: str) -> dict:
    """规整 LLM 输出为合法结构。"""
    meaning = raw.get("meaning", "")
    if not isinstance(meaning, str):
        meaning = ""
    meaning = re.sub(r"\s+", "", meaning)

    shuowen = raw.get("shuowen", "")
    if not isinstance(shuowen, str):
        shuowen = ""

    detail = raw.get("detail", "")
    if not isinstance(detail, str):
        detail = ""

    imagery = raw.get("imagery", [])
    if not isinstance(imagery, list):
        imagery = []
    imagery = [str(i) for i in imagery if isinstance(i, str)][:4]

    return {
        "char": char,
        "meaning": meaning,
        "shuowen": shuowen,
        "detail": detail,
        "imagery": imagery,
    }


def load_chars() -> dict:
    with open(CHARS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def select_candidates(data: dict, limit: int) -> list[dict]:
    """选取 meaning 为空的新扩充字（level=二/扩展 优先，其次一级空义项字）。"""
    chars = data["chars"]
    order = {"扩展": 0, "二": 1, "一": 2}
    candidates = [
        c for c in chars if not (c.get("meaning") or "").strip()
    ]
    candidates.sort(key=lambda c: (order.get(c.get("level", "一"), 9), c["char"]))
    if limit and limit > 0:
        return candidates[:limit]
    return candidates


def load_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if isinstance(data, list):
        return set(data)
    return set(data.get("chars", []))


def save_done(path: Path, chars: set[str]) -> None:
    path.write_text(
        json.dumps(sorted(chars), ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def enrich_one(
    sem: asyncio.Semaphore,
    llm: LLMService,
    info: dict,
    delay: float,
) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(info)},
    ]
    last_err: Exception | None = None
    for attempt in range(1, 6):
        try:
            async with sem:
                if delay > 0:
                    await asyncio.sleep(delay)
                raw = await llm.chat(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=400,
                    json_mode=True,
                )
            return normalize_result(raw, info["char"])
        except LLMError as e:
            last_err = e
            backoff = 2 ** (attempt - 1)
            print(f"  [retry] {info['char']} 第{attempt}次失败: {e}，{backoff}s 后重试")
            await asyncio.sleep(backoff)
    raise LLMError(f"重试 5 次仍失败: {last_err}")


async def run(
    candidates: list[dict],
    done: set[str],
    llm: LLMService,
    concurrency: int,
    delay: float,
    out_path: Path,
    done_path: Path,
) -> tuple[int, int]:
    sem = asyncio.Semaphore(concurrency)
    out_f = open(out_path, "a", encoding="utf-8")
    success = 0
    failed = 0

    for info in candidates:
        ch = info["char"]
        if ch in done:
            continue
        try:
            result = await enrich_one(sem, llm, info, delay)
            out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
            out_f.flush()
            done.add(ch)
            save_done(done_path, done)
            success += 1
            print(f"  [ok] {ch} → {result['meaning'][:24]} | {result['imagery']}")
        except Exception as e:
            failed += 1
            print(f"  [fail] {ch} → {e}")

    out_f.close()
    return success, failed


def merge_back(data: dict, out_path: Path) -> int:
    """把标注结果合并写回 chars.json。"""
    if not out_path.exists():
        return 0
    enriched: dict[str, dict] = {}
    with open(out_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            enriched[rec["char"]] = rec

    merged = 0
    for c in data["chars"]:
        rec = enriched.get(c["char"])
        if not rec:
            continue
        c["meaning"] = rec.get("meaning", "")
        c["shuowen"] = rec.get("shuowen", "")
        c["detail"] = rec.get("detail", "")
        c["imagery"] = rec.get("imagery", [])
        merged += 1

    data["version"] = "4.1"
    with open(CHARS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 批量标注生僻字")
    parser.add_argument("--limit", type=int, default=0, help="最多标注字数（0=全部，试点建议 50）")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--done", default=str(DEFAULT_DONE))
    parser.add_argument("--merge", action="store_true", help="标注后合并写回 chars.json")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    data = load_chars()
    candidates = select_candidates(data, args.limit)
    done = load_done(Path(args.done))
    pending = [c for c in candidates if c["char"] not in done]
    print(f"[enrich] 候选 {len(candidates)} 字，已完成 {len(candidates) - len(pending)}，待标注 {len(pending)}")

    if not pending:
        print("[enrich] 没有待标注字")
        if args.merge:
            merged = merge_back(data, Path(args.out))
            print(f"[enrich] 合并写回 {merged} 字")
        return

    llm = LLMService(
        provider=args.provider,
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
    )
    print(f"[enrich] LLM: {llm.provider} / {llm.model} / {llm.base_url}")

    success, failed = asyncio.run(
        run(
            candidates=pending,
            done=done,
            llm=llm,
            concurrency=args.concurrency,
            delay=args.delay,
            out_path=Path(args.out),
            done_path=Path(args.done),
        )
    )

    print(f"[enrich] 完成：成功 {success}，失败 {failed}，累计 {len(done)}")

    if args.merge:
        merged = merge_back(data, Path(args.out))
        print(f"[enrich] 合并写回 {merged} 字")


if __name__ == "__main__":
    main()
