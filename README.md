# 名堂 · 有据可循的起名工具

> 微信小程序 + FastAPI 后端。以**诗词出处的含义与意象**为核心，音律/五格/八字作为筛选门槛
> （漏斗式筛选，非加权平均）。产品定位：名字含义 > 命理。

## 快速开始

项目根目录即 `Newlife/`（不再是历史文档里的 `naming-app/`）。

### 1. 后端

```bash
./dev.sh          # 激活 venv → 校验数据 → 检查 git 同步 → 启动 uvicorn
```

手动方式：

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/api/v1/health>

### 2. 小程序

1. 微信开发者工具 → 导入项目，目录选 **`miniprogram/`**（appid 见 `miniprogram/project.config.json`）
2. 改 `miniprogram/app.js` 的 `globalData.apiBase` 为后端地址（真机调试填局域网 IP）
3. 运行

### 3. 测试

```bash
venv/bin/python -m pytest --basetemp=.pytest_tmp/run
```

> 沙箱/受限环境下**必须显式给 `--basetemp`**，否则 pytest 默认 `tmp_path` 会报 EEXIST。

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/health` | GET | 健康检查 |
| `/api/v1/generate` | POST | 生成名字（已出生，精确生辰） |
| `/api/v1/prenatal` | POST | 预产期范围起名（孕期参考） |
| `/api/v1/analyze` | POST | 名字测评（用字/音律/五格/八字匹配/出处） |
| `/api/v1/name/meaning` | POST | 深度寓意解读（多层余味，LLM） |
| `/api/v1/bazi` | GET | 八字排盘查询 |
| `/api/v1/recommend-chars` | POST | 按五行分组推荐选字 |
| `/api/v1/recommend-sources` | POST | 推荐意境来源（**前端已不再调用**，后端保留） |
| `/api/v1/source-chars` | POST | 在选定来源内推荐字（**同上，保留**） |
| `/api/v1/chars` | GET | 查询字库 |
| `/api/v1/poetry` | GET | 查询诗词库 |

## 项目结构

```
.
├── app/                        # FastAPI 后端
│   ├── api/routes.py           # 路由
│   ├── core/
│   │   ├── config.py           # 配置（LLM provider / key）
│   │   ├── constants.py        # 天干地支、负面字表
│   │   └── naming_options.py   # 风格 / 寓意枚举（单一事实来源）
│   ├── schemas/schemas.py      # 数据模型
│   └── services/
│       ├── naming_engine.py        # 起名核心（分层抽样 + 语义字对）
│       ├── yunwei_scorer.py        # 韵味评分（主排序键）
│       ├── poetry_database.py      # 诗词库 / 字对索引
│       ├── char_database.py        # 字库
│       ├── char_sense_database.py  # 语境字义
│       ├── bazi_engine.py          # 八字排盘与喜用神
│       ├── prenatal_engine.py      # 预产期引擎
│       ├── surname_fit.py          # 姓名搭配（谐音/声调）
│       ├── phonetics.py / wuge.py  # 音律 / 五格
│       └── llm_service.py          # LLM 寓意解读
├── data/
│   ├── dict/                   # 字库 chars.json（6492 字）+ 黑名单 + 康熙笔画
│   ├── poetry/                 # 诗词库 poetry.json + 字对 name_pairs.json
│   └── sense/                  # 语境义项 char_senses.json
├── miniprogram/                # 微信小程序
│   ├── app.wxss                # 设计令牌（改视觉只改这里）
│   ├── utils/api.js            # API + 前端枚举镜像
│   ├── utils/share.js          # 统一分享实现
│   └── pages/                  # home / name / wizard / result / detail / analyze …
├── scripts/                    # 数据管线、探针、评估脚本（见下）
├── docs/                       # 规范与设计文档
└── tests/                      # pytest（含前端镜像 / 命名判定 / 分享 / 视觉令牌门禁）
```

## 数据现状

| 项 | 量 |
| --- | --- |
| 字库 | 6492 字（康熙笔画/五行/吉凶） |
| 候选展示字池 | 714 字（= 出处推荐字 ∪ 字对用字） |
| 诗词库 | **873 首**，其中默认可用 **700 首**（173 首含哀伤者默认过滤） |
| 出处分布 | 宋词 268 / 五代词 150 / 诗经 104 / 唐诗 103 / 经史子集 98 / 清词 60 / 楚辞 52 / 汉魏 38 |
| 宜作名字对 | 699 条出处 → 829 对（529 条有字对） |
| 性别倾向 | 男 131 / 女 262 / 中 480 |

## 文档

| 文档 | 内容 |
| --- | --- |
| `docs/naming_direction.md` | 起名算法方向、历次整改与实测验收 |
| `docs/name_policy.md` | 「什么样的词适合做名字」判定标准与事故记录 |
| `docs/visual_system.md` | 视觉系统（山水泼墨）：令牌、四条硬规则、迁移对照 |
| `docs/ui_assets.md` | 配图资源清单（自行出图后交付替换） |
| `docs/system_design*.md` | 系统设计（含历史重构方案） |

## 常用脚本

```bash
venv/bin/python scripts/enrich_rare_chars.py --report      # 字库字义缺口统计
venv/bin/python scripts/enrich_rare_chars.py --pool-only --limit 40   # 补候选池字义（试点）
venv/bin/python scripts/eval_naming.py                     # 起名质量/多样性评估
venv/bin/python scripts/diag_luming.py                     # 任意词可达性分层探针
venv/bin/python scripts/pair_review.py --blocklist-only    # 应用人工黑名单（幂等，不调 LLM）
```

## 已知待优化项

1. **字库字义缺口**：候选池 714 字中约 76% 的字义/说文/字源为空 → 用字解析显示空白，且拿不到义项加分。
   正在用 `scripts/enrich_rare_chars.py` 补齐（`--pool-only` 只补用户可见的字）。
2. **命名标准场景分级**：当前所有场景共用一套「像不像正式姓名」标准；网名/笔名/小说角色名应放宽。见 `docs/name_policy.md` 第五节。
3. **多样性与质量互斥**：Top30 无弱名与「高频名重复少」不可兼得，唯一出路是继续扩源数据（加诗句）。
4. **性别标签失衡**：「中」占 55% 且大量实为男性观感 → 女性请求仍会出偏男性观感的名字。根治要审校标注，不是改算法。
5. 五格数理中复姓笔画计算需校验；八字立春/节气精确时刻需查表。
6. 名字故事卡（分享图生成）未做。

## 开发约定

- Git 用户 `Dawn-1122`。**Mac 上必须走 SSH**（HTTPS 443 不通）：`git@github.com:Dawn-1122/Newlife.git`。
- 两端互通：云端改 → `git pull origin main`；本地改 → `git add -A && git commit -m "..." && git push origin main`。**不要两端同时改再 push。**
- 改动偏好枚举 / 命名判定规则 / 视觉令牌后，跑一次 `pytest` —— 相关不变量已由测试门禁。
