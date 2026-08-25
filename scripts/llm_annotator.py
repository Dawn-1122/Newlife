"""
T3 · LLM 批量标注流水线

逐条调用 LLM，为 raw_corpus.jsonl 中的摘句输出起名标注：
{recommend_chars, emotion, gender, imagery, scene}

特性：
- asyncio + Semaphore 并发（默认 4）
- 断点续跑（done_ids.json）
- 指数退避重试（1s/2s/4s/8s，最多 5 次）
- 失败写 failed.jsonl（含原始输入 + 错误信息）
- 结果写 annotated.jsonl（以 id 幂等，可重跑覆盖）

用法：
    venv/bin/python scripts/llm_annotator.py --input data/poetry/raw_corpus.jsonl --limit 50 --balanced
    venv/bin/python scripts/llm_annotator.py --limit 50 --balanced --concurrency 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from app.services.llm_service import LLMService, LLMError  # noqa: E402
from prompts.annotate_prompt import (  # noqa: E402
    SYSTEM_PROMPT, build_user_prompt, FUNCTION_WORDS,
)
from poetry_utils import load_char_map, load_blacklist  # noqa: E402

DEFAULT_INPUT = PROJECT_ROOT / "data" / "poetry" / "raw_corpus.jsonl"
DEFAULT_ANNOTATED = PROJECT_ROOT / "data" / "poetry" / "annotated.jsonl"
DEFAULT_FAILED = PROJECT_ROOT / "data" / "poetry" / "failed.jsonl"
DEFAULT_DONE = PROJECT_ROOT / "data" / "poetry" / "done_ids.json"

EMOTION_ENUM = {"喜庆", "中性", "哀伤"}
GENDER_ENUM = {"男", "女", "中"}


def is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def build_candidates(text: str, char_map: dict, blacklist: set) -> list[dict]:
    """预筛可用字候选集：字库 luck=吉 且 出现在诗句中 且 非黑名单 且 非功能字。"""
    seen: set[str] = set()
    result: list[dict] = []
    for ch in text:
        if ch in seen or not is_cjk(ch):
            continue
        seen.add(ch)
        info = char_map.get(ch)
        if not info:
            continue
        if info.get("luck") != "吉":
            continue
        if ch in blacklist:
            continue
        if ch in FUNCTION_WORDS:
            continue
        result.append(info)
    return result


def normalize_result(raw: dict, candidate_chars: set[str]) -> dict:
    """把 LLM 输出规整为合法结构（字必须 ∈ 候选集）。"""
    rec = raw.get("recommend_chars", [])
    if not isinstance(rec, list):
        rec = []
    cleaned: list[str] = []
    for item in rec:
        if isinstance(item, str):
            # 单个字或多字串都拆成单字处理
            for ch in item:
                if ch in candidate_chars and ch not in cleaned:
                    cleaned.append(ch)
    # 后置过滤：剔除功能字（双保险，即使 LLM 忽略提示词约束也不入库）
    cleaned = [ch for ch in cleaned if ch not in FUNCTION_WORDS]
    cleaned = cleaned[:5]

    emotion = raw.get("emotion", "中性")
    if emotion not in EMOTION_ENUM:
        emotion = "中性"
    if emotion == "哀伤":
        cleaned = []

    gender = raw.get("gender", "中")
    if gender not in GENDER_ENUM:
        gender = "中"

    imagery = raw.get("imagery", [])
    if not isinstance(imagery, list):
        imagery = []
    imagery = [str(i) for i in imagery if isinstance(i, str)][:4]

    scene = raw.get("scene", "")
    if not isinstance(scene, str):
        scene = ""

    return {
        "recommend_chars": cleaned,
        "emotion": emotion,
        "gender": gender,
        "imagery": imagery,
        "scene": scene,
    }


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def load_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return set(data)
    return set(data.get("ids", []))


def save_done(path: Path, ids: set[str]) -> None:
    path.write_text(
        json.dumps(sorted(ids), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def select_entries(entries: list[dict], limit: int, balanced: bool) -> list[dict]:
    """选取待标注条目（balanced=True 时跨来源轮询取，保证 6 大类覆盖）。"""
    if limit and limit > 0:
        entries = entries[: limit * 10] if balanced else entries[:limit]
    if not balanced:
        return entries[:limit] if limit else entries

    by_source: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_source[e["source"]].append(e)

    result: list[dict] = []
    sources = sorted(by_source.keys())
    row = 0
    while (not limit) or len(result) < limit:
        added = False
        for s in sources:
            if row < len(by_source[s]):
                result.append(by_source[s][row])
                added = True
                if limit and len(result) >= limit:
                    break
        if not added:
            break
        row += 1
    return result


async def annotate_one(
    sem: asyncio.Semaphore,
    llm: LLMService,
    entry: dict,
    char_map: dict,
    blacklist: set,
    delay: float,
) -> dict:
    """标注单条（含重试）。失败抛 LLMError。"""
    candidate_chars = build_candidates(entry["text"], char_map, blacklist)
    candidate_set = {c["char"] for c in candidate_chars}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(entry, candidate_chars)},
    ]

    last_err: Exception | None = None
    for attempt in range(1, 6):
        try:
            async with sem:
                if delay > 0:
                    await asyncio.sleep(delay)
                raw = await llm.chat(
                    messages=messages,
                    temperature=0.2,
                    max_tokens=600,
                    json_mode=True,
                )
            return normalize_result(raw, candidate_set)
        except LLMError as e:
            last_err = e
            backoff = 2 ** (attempt - 1)  # 1s/2s/4s/8s
            print(f"  [retry] {entry['id']} 第{attempt}次失败: {e}，{backoff}s 后重试")
            await asyncio.sleep(backoff)
    raise LLMError(f"重试 5 次仍失败: {last_err}")


async def run(
    entries: list[dict],
    done_ids: set[str],
    llm: LLMService,
    char_map: dict,
    blacklist: set,
    concurrency: int,
    delay: float,
    annotated_path: Path,
    failed_path: Path,
    done_path: Path,
) -> tuple[int, int]:
    """并发标注，写 annotated.jsonl / failed.jsonl / done_ids.json。"""
    sem = asyncio.Semaphore(concurrency)
    annotated_f = open(annotated_path, "a", encoding="utf-8")
    failed_f = open(failed_path, "a", encoding="utf-8")
    success = 0
    failed = 0

    async def worker(entry: dict):
        nonlocal success, failed
        if entry["id"] in done_ids:
            return
        try:
            result = await annotate_one(sem, llm, entry, char_map, blacklist, delay)
            record = {"id": entry["id"], **result}
            annotated_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            annotated_f.flush()
            done_ids.add(entry["id"])
            save_done(done_path, done_ids)
            success += 1
            emo = result["emotion"]
            print(f"  [ok] {entry['id']} {entry['title'][:16]} → {result['recommend_chars']} ({emo})")
        except Exception as e:
            failed += 1
            failed_f.write(json.dumps({
                "id": entry["id"],
                "source": entry.get("source", ""),
                "title": entry.get("title", ""),
                "text": entry.get("text", ""),
                "error": str(e),
            }, ensure_ascii=False) + "\n")
            failed_f.flush()
            print(f"  [fail] {entry['id']} {entry['title'][:16]} → {e}")

    # 逐个调度（Semaphore 控制并发）
    for entry in entries:
        await worker(entry)

    annotated_f.close()
    failed_f.close()
    return success, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 批量标注诗词")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--annotated", default=str(DEFAULT_ANNOTATED))
    parser.add_argument("--failed", default=str(DEFAULT_FAILED))
    parser.add_argument("--done", default=str(DEFAULT_DONE))
    parser.add_argument("--limit", type=int, default=0, help="最多标注条数（0=全部）")
    parser.add_argument("--balanced", action="store_true", help="跨 6 大类轮询取，保证覆盖")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.2, help="每次请求间隔秒数")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    entries = load_jsonl(Path(args.input))
    if not entries:
        print(f"[annotator] 输入为空: {args.input}")
        sys.exit(1)

    selected = select_entries(entries, args.limit, args.balanced)
    done_ids = load_done(Path(args.done))
    pending = [e for e in selected if e["id"] not in done_ids]
    print(f"[annotator] 输入 {len(entries)} 条，本次选取 {len(selected)} 条，"
          f"已完成 {len(selected) - len(pending)} 条，待标注 {len(pending)} 条")

    if not pending:
        print("[annotator] 没有待标注条目")
        return

    llm = LLMService(
        provider=args.provider,
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
    )
    print(f"[annotator] LLM: {llm.provider} / {llm.model} / {llm.base_url}")

    char_map = load_char_map()
    blacklist = load_blacklist()

    success, failed = asyncio.run(
        run(
            entries=pending,
            done_ids=done_ids,
            llm=llm,
            char_map=char_map,
            blacklist=blacklist,
            concurrency=args.concurrency,
            delay=args.delay,
            annotated_path=Path(args.annotated),
            failed_path=Path(args.failed),
            done_path=Path(args.done),
        )
    )

    print(f"[annotator] 完成：成功 {success}，失败 {failed}，累计完成 {len(done_ids)}")


if __name__ == "__main__":
    main()
