# 美名集 · 有据可循的起名工具

> 微信小程序 + FastAPI 后端，混合架构起名应用

## 快速开始

### 1. 后端启动

```bash
cd naming-app

# 安装依赖
pip install -r requirements.txt

# 生成数据库
python3 scripts/generate_char_db.py
python3 scripts/generate_poetry_db.py

# 启动服务
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 `http://localhost:8000/docs` 查看API文档。

### 2. 小程序启动

1. 打开微信开发者工具
2. 导入项目，目录选择 `naming-app/miniprogram`
3. 在 `app.js` 中修改 `apiBase` 为后端地址
4. 运行

### 3. LLM 对比测试

```bash
# 设置环境变量
export DEEPSEEK_API_KEY=sk-xxx
export QWEN_API_KEY=sk-xxx
export ZHIPU_API_KEY=sk-xxx

# 运行测试
python3 scripts/llm_benchmark.py
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/generate` | POST | 生成名字 |
| `/api/v1/analyze` | POST | 解析名字 |
| `/api/v1/chars` | GET | 查询字库 |
| `/api/v1/poetry` | GET | 查询诗词库 |
| `/api/v1/bazi` | GET | 八字排盘 |
| `/api/v1/health` | GET | 健康检查 |

## 项目结构

```
naming-app/
├── app/                    # 后端应用
│   ├── api/routes.py       # API路由
│   ├── core/
│   │   ├── config.py       # 配置
│   │   └── constants.py    # 天干地支常量
│   ├── services/
│   │   ├── bazi_engine.py  # 八字排盘引擎
│   │   ├── char_database.py # 字库服务
│   │   ├── poetry_database.py # 诗词库服务
│   │   ├── phonetics.py    # 音律评分
│   │   ├── wuge.py         # 五格数理
│   │   ├── naming_engine.py # 起名核心引擎
│   │   └── llm_service.py  # LLM寓意解读
│   ├── schemas/schemas.py  # 数据模型
│   └── main.py             # 入口
├── data/
│   ├── dict/chars.json     # 字库数据（148字）
│   └── poetry/poetry.json  # 诗词库（42条）
├── miniprogram/            # 微信小程序
│   ├── pages/
│   │   ├── index/          # 起名输入页
│   │   ├── result/         # 结果列表页
│   │   └── detail/         # 名字详情页
│   └── utils/api.js        # API调用
├── scripts/
│   ├── generate_char_db.py # 字库生成
│   ├── generate_poetry_db.py # 诗词库生成
│   └── llm_benchmark.py    # LLM对比测试
├── tests/test_core.py      # 核心测试
└── requirements.txt
```

## 技术栈

- 后端：Python FastAPI
- 前端：微信小程序原生框架
- 数据：康熙字典字库 + 诗经/楚辞/唐诗/宋词典故库
- AI：LLM（DeepSeek/通义千问/智谱，待对比测试后选定）

## 已知待优化项

1. [ ] 字库扩充至7000+常用字
2. [ ] 诗词库扩充至500+条
3. [ ] 五格数理中复姓笔画计算需校验
4. [ ] 八字立春/节气精确时刻需查表
5. [ ] 名字组合算法需优化（避免"张清水"这类搭配）
6. [ ] 名字故事卡（分享图生成）
7. [ ] LLM对比测试报告
