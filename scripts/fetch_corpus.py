"""
T1 · 语料接入：拉取 chinese-poetry 开源语料库

将 chinese-poetry 仓库浅克隆到项目外的 .corpus 目录（已加入 .gitignore，不提交进 git）。
只做「获取」，不做清洗/筛选（清洗见 normalize_corpus.py）。

用法：
    venv/bin/python scripts/fetch_corpus.py
    venv/bin/python scripts/fetch_corpus.py --repo git@github.com:chinese-poetry/chinese-poetry.git
    venv/bin/python scripts/fetch_corpus.py --force   # 强制重新克隆
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# 项目根目录（scripts/ 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = PROJECT_ROOT / ".corpus"

# 默认 HTTPS 地址（可被 --repo 覆盖为 SSH 地址）
DEFAULT_REPO = "https://github.com/chinese-poetry/chinese-poetry.git"

# 需要的子目录/文件（用于克隆后的完整性自检）
REQUIRED_PATHS = [
    "shijing/shijing.json",   # 诗经 305 篇
    "chuci/chuci.json",       # 楚辞 19 篇
    "json",                   # 唐诗/宋诗等（poet.tang.*.json）
    "ci",                     # 宋词（ci.song.*.json）
    "lunyu",                  # 论语
    "sishuwujing",            # 四书五经（周易/大学/中庸/孟子等）
]


def run(cmd: list[str]) -> None:
    """执行命令并透传输出，失败即退出。"""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"[fetch_corpus] 命令执行失败: {' '.join(cmd)}", file=sys.stderr)
        sys.exit(result.returncode)


def corpus_ready() -> bool:
    """检查语料库是否已就绪。"""
    if not CORPUS_DIR.exists():
        return False
    for rel in REQUIRED_PATHS:
        if not (CORPUS_DIR / rel).exists():
            return False
    return True


def fetch(repo: str, force: bool) -> None:
    """克隆或更新语料库。"""
    if corpus_ready() and not force:
        print(f"[fetch_corpus] 语料库已就绪: {CORPUS_DIR}")
        return

    if CORPUS_DIR.exists() and force:
        print(f"[fetch_corpus] 强制重建，删除旧目录 {CORPUS_DIR}")
        shutil.rmtree(CORPUS_DIR)

    if not CORPUS_DIR.exists():
        # 浅克隆（只取最新快照，不拉全历史，减小体积与耗时）
        run(["git", "clone", "--depth", "1", repo, str(CORPUS_DIR)])
    else:
        # 已存在但不完整时，尝试增量拉取
        run(["git", "-C", str(CORPUS_DIR), "pull", "--depth", "1"])

    if not corpus_ready():
        print("[fetch_corpus] 克隆完成但缺少必要文件，请检查仓库结构", file=sys.stderr)
        sys.exit(1)

    print(f"[fetch_corpus] 语料库就绪: {CORPUS_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description="拉取 chinese-poetry 语料库")
    parser.add_argument("--repo", default=DEFAULT_REPO,
                        help="仓库地址（支持 SSH，如 git@github.com:chinese-poetry/chinese-poetry.git）")
    parser.add_argument("--force", action="store_true", help="强制重新克隆")
    args = parser.parse_args()

    fetch(args.repo, args.force)


if __name__ == "__main__":
    main()
