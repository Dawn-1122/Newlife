"""「宜作名字对」批量标注流水线

遍历 data/poetry/poetry.json，对每条出处调 LLM 挑出可直接作为双字名的两字组合，
产出 data/poetry/name_pairs.json。

为什么需要（背景）：
诗词标注产出的是「一袋好字」（recommend_chars 2~5 个），组合层再用 C(n,2)
全交叉造配对。实测 3378 个配对里 65.5% 的两字在原文中分处不同分句（机械拼接）；
而「圣人」「教多」「用财」这类虽在原句同句，却不成意象、不宜作名。
前者由 pair_cohesion 判定，后者只能靠语义判断 —— 即本脚本。

输入：data/poetry/poetry.json
输出：data/poetry/name_pairs.json      {"entry_id": [["婵","娟"], ...], ...}
      data/poetry/pairs_done.json      已完成 entry_id 列表（断点续跑）
      data/poetry/pairs_failed.jsonl   失败记录

服务端校验（normalize_pairs，与提示词并列的第二道闸）：
  字必须在原文中 + 两字必须同分句（相邻或同句）+ 非功能字 + 两字不同。
即使 LLM 越界造字或跨句凑对，也会在此被丢弃。

三种模式：
  默认          断点续跑，只处理还没标注过的条目
  --only-empty  补标注：只重跑「标注跑过但字对被复核清空」的条目（带黑名单重试）
  --topup       增补：保留已通过复核的字对，另请 LLM 追加新字对

⚠️ --topup 实测局限（2026-09-22）：小批 20 条产出 2.2 倍字对，但**约 75% 是凑数**
（城隅/嘉宾/鼓瑟/雉鸠），因为一句话里的好字对本就有上限 —— 实测 699 条出处平均
仅 1.56 对，远低于提示词允许的 4。即**字对库存受语料封顶，不能靠追问扩充**；
要提升候选多样性只能扩源数据（加诗句），而不是加字对。故 --topup 仅用于
「补回历史遗漏」，且**必须**随后跑 pair_review.py 复核。

用法：
    venv/bin/python scripts/pair_annotator.py --limit 20     # 小批试跑
    venv/bin/python scripts/pair_annotator.py                # 全量（断点续跑）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from app.services.llm_service import LLMService, LLMError  # noqa: E402
from app.services.yunwei_scorer import pair_cohesion  # noqa: E402
from prompts.annotate_prompt import FUNCTION_WORDS  # noqa: E402
from prompts.pair_prompt import SYSTEM_PROMPT, build_user_prompt  # noqa: E402

DEFAULT_POETRY = PROJECT_ROOT / "data" / "poetry" / "poetry.json"
DEFAULT_OUT = PROJECT_ROOT / "data" / "poetry" / "name_pairs.json"
DEFAULT_DONE = PROJECT_ROOT / "data" / "poetry" / "pairs_done.json"
DEFAULT_FAILED = PROJECT_ROOT / "data" / "poetry" / "pairs_failed.jsonl"

MAX_PAIRS = 4
PAIRED_KINDS = ("adjacent", "same_clause")


def normalize_pairs(
    raw: dict, text: str, banned: set[str] | None = None
) -> list[list[str]]:
    """服务端校验：只保留「字在原文 + 同分句 + 非功能字」的两字组合。

    期望格式为扁平字符串数组 ["婵娟", "清扬"]；同时兼容异常输出
    （嵌套数组、单字串），凡无法还原成「恰好两个汉字」的一律丢弃。
    banned 给定时，命中复核黑名单的组合一并丢弃（补标注时的硬闸）。
    """
    words: list[str] = []

    def absorb(item) -> None:
        if isinstance(item, str):
            words.append(item.strip())
        elif isinstance(item, (list, tuple)):
            parts = [str(x).strip() for x in item]
            if len(parts) == 2 and all(len(x) == 1 for x in parts):
                words.append("".join(parts))
            else:
                words.extend(parts)

    for item in (raw.get("pairs") or []):
        absorb(item)

    out: list[list[str]] = []
    seen: set[str] = set()
    for word in words:
        if len(word) != 2:
            continue
        a, b = word[0], word[1]
        if a == b or a in FUNCTION_WORDS or b in FUNCTION_WORDS:
            continue
        if a not in text or b not in text:
            continue
        if banned and (a + b) in banned:
            continue
        if pair_cohesion(a, b, text) not in PAIRED_KINDS:
            continue
        key = "".join(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        out.append([a, b])
    return out[:MAX_PAIRS]


def _atomic_write_json(path: Path, obj, indent: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


async def annotate_one(
    sem: asyncio.Semaphore,
    llm: LLMService,
    entry: dict,
    delay: float,
    banned: set[str] | None = None,
    retry_hint: bool = False,
    existing: list[str] | None = None,
) -> list[list[str]]:
    text = entry.get("text") or ""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(entry, banned, existing)},
    ]
    last_err: Exception | None = None
    for attempt in range(1, 6):
        try:
            async with sem:
                if delay > 0:
                    await asyncio.sleep(delay)
                raw = await llm.chat(
                    messages=messages, temperature=0.3, max_tokens=400, json_mode=True
                )
            pairs = normalize_pairs(raw, text, banned)
            if pairs or not retry_hint:
                return pairs
            # 补空条目时：第一轮没挑出可用字对 → 追加一次「换一批」的提示再试
            pairs = await _retry_with_hint(sem, llm, entry, banned, text, delay)
            return pairs
        except LLMError as e:
            last_err = e
            backoff = 2 ** (attempt - 1)
            print(f"  [retry] {entry.get('id')} 第{attempt}次失败: {e}，{backoff}s 后重试")
            await asyncio.sleep(backoff)
    raise LLMError(f"重试 5 次仍失败: {last_err}")


async def _retry_with_hint(
    sem: asyncio.Semaphore,
    llm: LLMService,
    entry: dict,
    banned: set[str] | None,
    text: str,
    delay: float,
) -> list[list[str]]:
    """第一轮空手而归时的第二次尝试：明确告知「上一轮全部不合规」，要求换字对。"""
    hint = (
        "上一轮你给出的组合经复核**全部不适合做人名**（或为空）。请重新从原句中"
        "另选 1~3 组更雅正的字对：优先原句中**相邻成词**的字（如「婵娟」「清扬」），"
        "并从原句里换其他位置的字，不要重复上一轮的选择。"
        "若整句确实没有适合作名的字对，返回空数组 []。"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(entry, banned)},
        {"role": "assistant", "content": '{"pairs": [], "note": "不符合} '},
        {"role": "user", "content": hint},
    ]
    try:
        async with sem:
            if delay > 0:
                await asyncio.sleep(delay)
            raw = await llm.chat(
                messages=messages, temperature=0.5, max_tokens=400, json_mode=True
            )
        return normalize_pairs(raw, text, banned)
    except LLMError:
        return []


async def run(
    entries: list[dict],
    done_ids: set[str],
    llm: LLMService,
    concurrency: int,
    delay: float,
    out_path: Path,
    done_path: Path,
    failed_path: Path,
    banned: set[str] | None = None,
    retry_hint: bool = False,
    topup: bool = False,
) -> tuple[int, int]:
    sem = asyncio.Semaphore(concurrency)
    results: dict[str, list] = {}
    if out_path.exists():
        try:
            results = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            results = {}

    failed_f = open(failed_path, "a", encoding="utf-8")
    success = failed = 0
    lock = asyncio.Lock()

    async def worker(entry: dict) -> None:
        nonlocal success, failed
        eid = entry.get("id")
        if not eid:
            return
        if topup:
            existing = [
                "".join(p) for p in (results.get(eid) or []) if len(p) == 2
            ]
        else:
            if eid in done_ids:
                return
            existing = None
        try:
            pairs = await annotate_one(
                sem, llm, entry, delay, banned=banned,
                retry_hint=retry_hint, existing=existing,
            )
        except LLMError as e:
            failed += 1
            failed_f.write(json.dumps({"id": eid, "error": str(e)}, ensure_ascii=False) + "\n")
            failed_f.flush()
            return
        if topup:
            # 增补模式：保留已复核通过的旧字对，只追加新字对（review 会再筛一遍）
            old = results.get(eid) or []
            seen = {"".join(sorted(p)) for p in old if len(p) == 2}
            for p in pairs:
                key = "".join(sorted(p))
                if key not in seen:
                    seen.add(key)
                    old.append(p)
            pairs = old
        async with lock:
            results[eid] = pairs
            done_ids.add(eid)
            success += 1
            if success % 25 == 0:
                _atomic_write_json(out_path, results)
                _atomic_write_json(done_path, sorted(done_ids))
                with_pairs = sum(1 for v in results.values() if v)
                print(f"  ...已处理 {success}，其中有可用字对 {with_pairs}")

    await asyncio.gather(*[worker(e) for e in entries])
    failed_f.close()
    _atomic_write_json(out_path, results)
    _atomic_write_json(done_path, sorted(done_ids))
    return success, failed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--poetry", default=str(DEFAULT_POETRY))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--done", default=str(DEFAULT_DONE))
    ap.add_argument("--failed", default=str(DEFAULT_FAILED))
    ap.add_argument("--limit", type=int, default=0, help="本次最多标注多少条")
    ap.add_argument(
        "--only-empty",
        action="store_true",
        help="补标注模式：只重跑「已标注但字对被复核清空」的条目（配合 --banned 使用）",
    )
    ap.add_argument(
        "--topup",
        action="store_true",
        help="增补模式：保留已通过复核的字对，另请 LLM 追加新字对（须随后跑 pair_review.py）",
    )
    ap.add_argument(
        "--banned",
        default=str(PROJECT_ROOT / "data" / "poetry" / "pairs_review.json"),
        help="复核黑名单来源（--only-empty 时作为硬排除传入）",
    )
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--delay", type=float, default=0.0)
    ap.add_argument("--provider", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    data = json.loads(Path(args.poetry).read_text(encoding="utf-8"))
    poems = data.get("poems") if isinstance(data, dict) else data
    # 只标注有推荐字的条目：空 recommend_chars 说明标注时已判为不宜起名（哀伤句等）
    entries = [p for p in poems if p.get("recommend_chars")]

    done_path = Path(args.done)
    done_ids: set[str] = set()
    if done_path.exists():
        try:
            done_ids = set(json.loads(done_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            done_ids = set()

    banned: set[str] = set()
    out_path = Path(args.out)
    current: dict[str, list] = {}
    if out_path.exists():
        try:
            current = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}

    # 黑名单（复核剔除清单）——三种模式都作为硬排除传入；但保护名单必须扣掉，
    # 否则「窈窕」这类被误杀的词会被自己的黑名单永久挡住。
    bp = Path(args.banned)
    if bp.exists():
        try:
            banned = set(json.loads(bp.read_text(encoding="utf-8")).get("unsuitable") or [])
        except json.JSONDecodeError:
            banned = set()
    try:
        from pair_review import PROTECTED as _PROTECTED

        banned -= _PROTECTED
    except ImportError:
        pass

    if args.topup:
        pending = list(entries)
        done_ids = set()
    elif args.only_empty:
        # 已标注但字对为空 → 复核把它们全剔了，这批条目的出处「白白浪费」；
        # 带黑名单重跑一轮，能救回一部分（救不回的仍保持空，引擎侧不再退回全交叉）。
        empty_ids = {eid for eid, v in current.items() if not v}
        pending = [e for e in entries if e.get("id") in empty_ids]
        # 补跑不受断点文件阻挡
        done_ids = {i for i in done_ids if i not in empty_ids}
    else:
        pending = [e for e in entries if e.get("id") not in done_ids]

    if args.limit and args.limit > 0:
        pending = pending[: args.limit]

    print(f"[pairs] 条目 {len(entries)} 条（有推荐字），已完成 {len(done_ids)}，"
          f"本次待标注 {len(pending)}"
          + (f"（补空条目，黑名单 {len(banned)} 词）" if args.only_empty else "")
          + (f"（增补模式，黑名单 {len(banned)} 词）" if args.topup else ""))
    if not pending:
        print("[pairs] 没有待标注任务")
        return

    llm = LLMService(
        provider=args.provider, api_key=args.api_key,
        base_url=args.base_url, model=args.model,
    )
    print(f"[pairs] LLM: {llm.provider} / {llm.model}")

    success, failed = asyncio.run(run(
        entries=pending, done_ids=done_ids, llm=llm, concurrency=args.concurrency,
        delay=args.delay, out_path=out_path, done_path=done_path,
        failed_path=Path(args.failed),
        banned=banned, retry_hint=args.only_empty, topup=args.topup,
    ))
    results = json.loads(out_path.read_text(encoding="utf-8"))
    with_pairs = sum(1 for v in results.values() if v)
    total_pairs = sum(len(v) for v in results.values())
    print(f"[pairs] 完成：成功 {success}，失败 {failed}")
    print(f"[pairs] 累计 {len(results)} 条已标注，其中 {with_pairs} 条有可用字对"
          f"（{with_pairs / max(1, len(results)):.0%}），共 {total_pairs} 个字对")


if __name__ == "__main__":
    main()
