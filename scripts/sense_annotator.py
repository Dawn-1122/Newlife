"""
语境义项批量标注流水线

遍历已有的诗词库与字源库，对每个「字 × 出处」对，调 LLM 输出该字在该出处语境中的义项，
产出 data/sense/char_senses.json。

输入：data/poetry/poetry.json、data/source/source_entries.json 的 recommend_chars
输出：data/sense/char_senses.json（list）：
    {"char":"清","entry_id":"poem_0413","source_type":"poetry",
     "senses":["清朗","高远","澄澈"],"note":"..."}

特性：
- asyncio + Semaphore 并发（默认 4）
- 断点续跑（sense_done.json）
- 指数退避重试（1s/2s/4s/8s，最多 5 次）
- 失败写 sense_failed.jsonl
- 支持 --limit 分批；--sample N 导出人工抽检清单

用法：
    venv/bin/python scripts/sense_annotator.py --limit 50
    venv/bin/python scripts/sense_annotator.py            # 全量
    venv/bin/python scripts/sense_annotator.py --sample 80
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from app.services.llm_service import LLMService, LLMError  # noqa: E402
from prompts.sense_prompt import SYSTEM_PROMPT, build_user_prompt  # noqa: E402

DEFAULT_POETRY = PROJECT_ROOT / "data" / "poetry" / "poetry.json"
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "source" / "source_entries.json"
DEFAULT_OUT = PROJECT_ROOT / "data" / "sense" / "char_senses.json"
DEFAULT_FAILED = PROJECT_ROOT / "data" / "sense" / "sense_failed.jsonl"
DEFAULT_DONE = PROJECT_ROOT / "data" / "sense" / "sense_done.json"
DEFAULT_SAMPLE = PROJECT_ROOT / "data" / "sense" / "sense_review_sample.jsonl"


def _load_list(path: Path, keys: tuple[str, ...]) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for k in keys:
            if isinstance(data.get(k), list):
                return data[k]
        for v in data.values():
            if isinstance(v, list):
                return v
        return []
    return data if isinstance(data, list) else []


def _load_name_pairs(poetry_path: Path) -> dict[str, list]:
    """读「宜作名字对」标注（与 poetry.json 同目录，独立文件）。缺失时返回空表。"""
    path = poetry_path.parent / "name_pairs.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def build_tasks(poetry_path: Path, source_path: Path) -> list[dict]:
    """构造 (char, entry) 任务列表。

    字来源 = recommend_chars ∪ name_pairs 用字。后者是「宜作名字对」标注
    （scripts/pair_annotator.py）引入的，可能用到推荐字之外的字（如「修远」的「远」），
    若不算进来，这些名字在评分时会回退到字典义、语境义项覆盖率掉档。
    """
    tasks: list[dict] = []
    seen: set[tuple[str, str]] = set()
    pairs_map = _load_name_pairs(poetry_path)

    for path, source_type, keys in (
        (poetry_path, "poetry", ("poems", "poetry", "data")),
        (source_path, "source", ("entries", "source_entries", "data")),
    ):
        for entry in _load_list(path, keys):
            entry_id = entry.get("id")
            if not entry_id:
                continue
            chars = list(entry.get("recommend_chars") or [])
            for pair in (entry.get("name_pairs") or pairs_map.get(entry_id) or []):
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    chars.extend(pair)
            for char in chars:
                key = (char, entry_id)
                if key in seen:
                    continue
                seen.add(key)
                tasks.append({
                    "char": char,
                    "entry_id": entry_id,
                    "source_type": source_type,
                    "entry": entry,
                })
    return tasks


# 元描述 / 虚词模式（LLM 偶尔输出，必须过滤）
_META_PATTERNS = (
    "虚词", "语助", "助词", "助判断", "无实义", "判断", "停顿", "语气", "结构助",
    "音节", "句末", "调节", "凑足", "衬字", "发语词", "标点",
)


def normalize_result(raw: dict) -> dict:
    """规整 LLM 输出：senses 为 1~3 字意象词组，2~4 个；过滤虚词与元描述。"""
    from prompts.annotate_prompt import FUNCTION_WORDS

    senses = raw.get("senses", [])
    if not isinstance(senses, list):
        senses = []
    cleaned: list[str] = []
    for s in senses:
        if not isinstance(s, str):
            continue
        s = s.strip()
        if not s or len(s) > 6 or s in cleaned:
            continue
        if any(p in s for p in _META_PATTERNS):
            continue
        if s in FUNCTION_WORDS:
            continue
        cleaned.append(s)
    cleaned = cleaned[:4]

    note = raw.get("note", "")
    if not isinstance(note, str):
        note = ""

    return {"senses": cleaned, "note": note}


def load_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return set(data)
    return set(data.get("ids", []))


def save_done(path: Path, ids: set[str]) -> None:
    _atomic_write_json(path, sorted(ids), indent=2)


def _atomic_write_json(path: Path, obj, indent: int = 1) -> None:
    """原子落盘：先写临时文件再 os.replace，避免并发读取到半截 JSON。"""
    import os
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8"
    )
    os.replace(tmp, path)


async def annotate_one(
    sem: asyncio.Semaphore, llm: LLMService, task: dict, delay: float
) -> dict:
    """标注单个「字×出处」对（含重试）。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(task["entry"], task["char"])},
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
                    max_tokens=300,
                    json_mode=True,
                )
            return normalize_result(raw)
        except LLMError as e:
            last_err = e
            backoff = 2 ** (attempt - 1)
            print(f"  [retry] {task['char']}@{task['entry_id']} 第{attempt}次失败: {e}，{backoff}s 后重试")
            await asyncio.sleep(backoff)
    raise LLMError(f"重试 5 次仍失败: {last_err}")


async def run(
    tasks: list[dict],
    done_ids: set[str],
    llm: LLMService,
    concurrency: int,
    delay: float,
    out_path: Path,
    failed_path: Path,
    done_path: Path,
) -> tuple[int, int]:
    sem = asyncio.Semaphore(concurrency)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 已完成的记录回填（断点续跑）
    results: list[dict] = []
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if isinstance(existing, list):
                results = existing
        except json.JSONDecodeError:
            results = []

    failed_f = open(failed_path, "a", encoding="utf-8")
    success = 0
    failed = 0

    def _done_id(task: dict) -> str:
        return f"{task['char']}@{task['entry_id']}"

    async def worker(task: dict):
        nonlocal success, failed
        did = _done_id(task)
        if did in done_ids:
            return
        try:
            result = await annotate_one(sem, llm, task, delay)
            if result["senses"]:
                results.append({
                    "char": task["char"],
                    "entry_id": task["entry_id"],
                    "source_type": task["source_type"],
                    "senses": result["senses"],
                    "note": result["note"],
                })
            done_ids.add(did)
            save_done(done_path, done_ids)
            # 原子落盘（先写临时文件再替换），避免读取方拿到半截 JSON
            _atomic_write_json(out_path, results)
            if result["senses"]:
                success += 1
                print(f"  [ok] {task['char']}@{task['entry_id']} → {result['senses']}")
            else:
                print(f"  [skip] {task['char']}@{task['entry_id']} 无实义")
        except Exception as e:
            failed += 1
            failed_f.write(json.dumps({
                "char": task["char"],
                "entry_id": task["entry_id"],
                "text": task["entry"].get("text", ""),
                "error": str(e),
            }, ensure_ascii=False) + "\n")
            failed_f.flush()
            print(f"  [fail] {task['char']}@{task['entry_id']} → {e}")

    for task in tasks:
        await worker(task)

    failed_f.close()
    return success, failed


def export_sample(out_path: Path, sample_path: Path, n: int) -> None:
    """导出随机抽检清单（人工审核用）。"""
    import random
    if not out_path.exists():
        print(f"[sense] 无产出文件可抽检: {out_path}")
        return
    data = json.loads(out_path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        print("[sense] 产出为空，无法抽检")
        return
    picked = random.sample(data, min(n, len(data)))
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    with open(sample_path, "w", encoding="utf-8") as f:
        for rec in picked:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[sense] 抽检 {len(picked)} 条 → {sample_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="语境义项批量标注")
    parser.add_argument("--poetry", default=str(DEFAULT_POETRY))
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--failed", default=str(DEFAULT_FAILED))
    parser.add_argument("--done", default=str(DEFAULT_DONE))
    parser.add_argument("--limit", type=int, default=0, help="最多标注条数（0=全部）")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--sample", type=int, default=0, help="导出 N 条人工抽检后退出")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    out_path = Path(args.out)
    if args.sample:
        export_sample(out_path, DEFAULT_SAMPLE, args.sample)
        return

    tasks = build_tasks(Path(args.poetry), Path(args.source))
    done_ids = load_done(Path(args.done))
    all_pending = [t for t in tasks if f"{t['char']}@{t['entry_id']}" not in done_ids]
    already = len(tasks) - len(all_pending)
    pending = all_pending[: args.limit] if args.limit and args.limit > 0 else all_pending
    print(f"[sense] 「字×出处」对共 {len(tasks)} 个，已完成 {already} 个，"
          f"本次待标注 {len(pending)} 个（总待 {len(all_pending)}）")

    if not pending:
        print("[sense] 没有待标注任务")
        return

    llm = LLMService(
        provider=args.provider, api_key=args.api_key,
        base_url=args.base_url, model=args.model,
    )
    print(f"[sense] LLM: {llm.provider} / {llm.model} / {llm.base_url}")

    success, failed = asyncio.run(run(
        tasks=pending, done_ids=done_ids, llm=llm,
        concurrency=args.concurrency, delay=args.delay,
        out_path=out_path, failed_path=Path(args.failed), done_path=Path(args.done),
    ))
    print(f"[sense] 完成：成功 {success}，失败 {failed}，累计完成 {len(done_ids)}")


if __name__ == "__main__":
    main()
