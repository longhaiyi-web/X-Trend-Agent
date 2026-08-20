# 每日热点到候选内容池 Agent

这是一个可在 Windows 本地运行的 Streamlit Demo。它从真实公开信息源抓取科技、AI 与开发者生态信息，把原始记录聚合成热点事件，再通过可解释的规则完成优先级排序、X 账号跟进判断、英文候选文案生成、人工审核和本地反馈学习。

项目不调用 X API、付费 API 或 LLM API，也不使用模拟数据填充 Agent 结果。每个事件和候选内容都保留真实原文链接。

## 当前能力

### 第一阶段：真实公开来源

| 来源 | 类型 | 公开入口 | 用途 |
| --- | --- | --- | --- |
| DEV Community Articles API | 开发者社区 API | `https://dev.to/api/articles` | 最近 7 天的 AI 热门文章 |
| GitHub Search REST API | 开源趋势 API | `https://api.github.com/search/repositories` | 最近 7 天新建仓库按 Star 排序 |
| npm Registry Search API | 软件包生态 API | `https://registry.npmjs.org/-/v1/search` | AI 关键词相关软件包发布与更新 |
| Lobsters RSS | 科技社区 RSS | `https://lobste.rs/rss` | 程序员社区提交的科技新闻与工程话题 |

单个来源失败不会阻断整个流程，页面会显示失败原因，并继续处理其他来源返回的真实数据。

### 第二阶段：核心 Agent

- **事件聚合去重**：综合原文 URL、标题/描述相似度和同一软件包家族的集中发布，将相关原始记录合并成热点事件。聚合后保留全部原始链接。
- **可解释优先级**：最终分数由时效性（25）、趋势形成信号（20）、行业相关度（25）、可讨论性（20）、内容价值（10）和历史偏好调整（±10）组成；页面逐项显示得分原因。
- **分层行业相关度**：结合标题、描述和主题标签判断高相关、中相关、低相关或无关。单独出现 `AI` 不会直接得到 25 分；AI Agent、LLM、模型能力、AI 开发工具与基础设施等具体信号才会进入高相关层级。
- **趋势形成信号**：多条原始记录、多个独立来源或多种来源类型会明显加分。同源软件包家族集中更新可形成发布簇，但分数仍低于跨来源交叉印证。
- **动态 X 跟进判断**：每个事件按阈值输出“建议跟进 / 观察 / 不建议跟进”，没有固定推荐条数。单一 GitHub 仓库需要同时满足高行业价值、强时效、讨论性和内容价值，stars 与 AI 关键词不能单独触发推荐。
- **事件类型与候选内容**：识别产品/工具发布、开源项目、生态集中更新、行业新闻、技术观点、开发者经验、研究进展 7 类事件，分别生成内容角度与英文 Hook。候选文案不复制原始描述，并限制在 280 字符以内。
- **待审核内容池**：候选内容由用户主动加入，随后可以采用或驳回。
- **本地反馈持久化**：审核池与历史记录保存在 `data/review_state.json`。采用/驳回会影响同主题事件的后续评分，页面明确列出使用了哪些历史记录和加减分。

## Windows 本地运行

需要 Python 3.10 或更高版本。在 PowerShell 中执行：

```powershell
cd D:\X-Trend-Agent
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run.ps1
```

如果虚拟环境和依赖已经安装，直接运行：

```powershell
cd D:\X-Trend-Agent
.\run.ps1
```

默认访问地址：`http://localhost:8501`

## 验收脚本

验证真实来源：

```powershell
.\.venv\Scripts\python.exe scripts\check_sources.py
```

验证“真实来源 → 聚合 → 排序 → 跟进判断 → 候选内容”链路：

```powershell
.\.venv\Scripts\python.exe scripts\check_agent.py
```

## 项目结构

```text
X-Trend-Agent/
├─ app.py                         # Streamlit 主页面与审核交互
├─ data/
│  └─ review_state.json           # 待审核内容与采用/驳回历史
├─ scripts/
│  ├─ check_sources.py            # 真实来源验收
│  └─ check_agent.py              # 核心 Agent 链路验收
└─ src/
   ├─ models.py                   # 原始信息统一模型
   ├─ pipeline.py                 # 公开来源抓取与失败隔离
   ├─ review_store.py             # 本地审核池与反馈偏好
   ├─ agent/
   │  ├─ aggregation.py           # 事件级聚合去重
   │  ├─ scoring.py               # 评分、排序与跟进判断
   │  ├─ content.py               # 内容角度与候选文案
   │  └─ pipeline.py              # Agent 总流程
   └─ fetchers/                   # 四个现有公开来源适配器
```

## 反馈调整规则

每个历史记录保留事件主题、候选文案、来源、动作和时间。对某个主题：

1. 每次采用计 `+1.5`，每次驳回计 `-1.5`。
2. 同主题连续采用或连续驳回达到 2 次后，增加同方向的 streak 权重。
3. 单主题权重限制在 `-8` 到 `+8`，单个事件最终历史偏好调整限制在 `-10` 到 `+10`。
4. 页面会显示采用数、驳回数、连续动作、实际调整分和最近使用的历史事件；不会笼统宣称“AI 自动学习”。

## Demo 评分规则说明

当前分项权重、相关度词表和跟进阈值都是透明、确定性的 Demo 规则，用于展示 Agent 如何筛选而非替代编辑判断。真实业务中可根据账号定位、来源覆盖、审核采用率和内容表现持续校准这些规则；调整时仍应保留分项依据、原始链接与人工审核闭环。

## 边界

当前 Agent 是本地、确定性、可解释的规则系统，适合实战题 Demo 和人工审核工作流。它没有调用 LLM，因此摘要和候选文案采用来源文本与模板生成。后续若接入 LLM，也应继续保留现有聚合依据、分项评分、原始链接和人工审核记录。
