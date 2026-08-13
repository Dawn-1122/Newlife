#!/bin/bash
# 本地开发启动脚本
# 用法: ./dev.sh

cd "$(dirname "$0")"

echo "=============================="
echo "  美名集 · 本地开发环境"
echo "=============================="
echo ""

# 激活虚拟环境
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "[OK] 虚拟环境已激活"
else
    echo "[!] 未找到 venv，正在创建..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    echo "[OK] 虚拟环境已创建并安装依赖"
fi

# 检查数据文件
if [ ! -f "data/dict/chars.json" ] || [ ! -f "data/poetry/poetry.json" ]; then
    echo "[!] 数据文件缺失，正在生成..."
    python3 scripts/generate_char_db.py
    python3 scripts/generate_poetry_db.py
    echo "[OK] 数据文件已生成"
else
    echo "[OK] 数据文件就绪"
fi

# 检查 git 状态
echo ""
echo "--- Git 同步状态 ---"
git fetch origin 2>/dev/null
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main 2>/dev/null)
if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[OK] 本地与云端同步"
else
    AHEAD=$(git rev-list origin/main..HEAD --count 2>/dev/null)
    BEHIND=$(git rev-list HEAD..origin/main --count 2>/dev/null)
    if [ "$AHEAD" -gt "0" ]; then
        echo "[!] 本地领先云端 $AHEAD 个提交 (用 git push origin main 推送)"
    fi
    if [ "$BEHIND" -gt "0" ]; then
        echo "[!] 本地落后云端 $BEHIND 个提交 (用 git pull origin main 拉取)"
    fi
fi

# 启动后端
echo ""
echo "--- 启动后端服务 ---"
echo "API文档: http://localhost:8000/docs"
echo "健康检查: http://localhost:8000/api/v1/health"
echo "按 Ctrl+C 停止"
echo ""

PYTHONPATH=. python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
