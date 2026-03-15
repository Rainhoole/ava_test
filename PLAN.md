# Plan: Fix OpenAI Mandate + Error Observability

基于反馈的改动计划，分为 **5 个部分**。

---

## Part 1: 移除 Claude 引擎选项，只保留 OpenAI

### 涉及文件
- `research_agent_cowork/web_server.py`
- `research_agent_cowork/task_manager.py`

### 改动点

**web_server.py:**
1. `ResearchRequest` (L132): `engine` 字段默认改 `"openai"`，描述改为只支持 openai
2. `ConfigResponse` (L177): `available_engines` 改为 `["openai"]`
3. `create_research` (L585-592): engine 验证只允许 `"openai"`，传 `"claude"` 返回 400
4. `run_research_task` (L356-365): 移除 Claude 分支，只走 OpenAI 路径
5. `TaskResponse` (L144): `engine` 默认改 `"openai"`
6. 各处 `getattr(t, 'engine', 'claude') or 'claude'` fallback 改为 `'openai'`

**task_manager.py:**
7. `Task` dataclass (L50): `engine` 默认改 `"openai"`
8. `create_task` (L185): `engine` 参数默认改 `"openai"`
9. 旧数据中 engine=claude 的记录不动

---

## Part 2: Mandate 必填

### 涉及文件
- `research_agent_cowork/web_server.py`

### 改动点

1. `ResearchRequest` (L134): `mandate_id` 从 `Optional[str]` 改为 `str`（必填）
2. `create_research`: 加校验——空 mandate_id 返回 400:
   ```
   "mandate_id is required. Create a payment mandate before submitting research."
   ```
3. `run_research_task` (L396-400): 移除 "No mandate → skip payment" 的分支（mandate 一定存在）

---

## Part 3: 结构化失败信息（failure_stage / failure_code / retryable）

### 涉及文件
- `research_agent_cowork/web_server.py`
- `research_agent_cowork/task_manager.py`

### 新增字段

**TaskResponse / Task / DB 新增:**
```python
failure_stage: Optional[str] = None    # provider_auth | provider_quota | provider_runtime | tool_runtime | internal
failure_code: Optional[str] = None     # 机器可读错误码
retryable: Optional[bool] = None       # 客户端是否应重试
```

### 错误分类逻辑

新增 helper `classify_failure(error: str) -> (stage, code, retryable)`:

| 错误模式 | failure_stage | failure_code | retryable |
|---------|--------------|-------------|-----------|
| `Credit balance is too low` | `provider_quota` | `billing_insufficient_credit` | `false` |
| `API_KEY not set` | `provider_auth` | `provider_key_missing` | `false` |
| `401` / `Unauthorized` | `provider_auth` | `provider_auth_failed` | `false` |
| `429` / `Rate limit` | `provider_runtime` | `provider_rate_limited` | `true` |
| `5xx` / OpenAI generic error | `provider_runtime` | `provider_internal_error` | `true` |
| `timeout` / `Connection` | `provider_runtime` | `provider_timeout` | `true` |
| Tool/MCP 错误 | `tool_runtime` | `tool_execution_failed` | `true` |
| 其他 | `internal` | `internal_error` | `false` |

---

## Part 4: OpenAI 错误可观测性

### 涉及文件
- `research_agent_cowork/agent_runner.py` (AgentRunnerOpenAI)
- `research_agent_cowork/web_server.py`
- `research_agent_cowork/task_manager.py`

### 改动点

**AgentRunnerOpenAI 异常处理增强:**
- catch 块中提取 OpenAI 错误细节: `status_code`, `request_id`, `error_type`
- 写入 JSONL error entry 时包含 `detail` 对象（provider, model, endpoint, upstream_status_code, upstream_request_id）
- session_end entry 也写入 error detail

**TaskResponse / Task / DB 新增:**
```python
upstream_request_id: Optional[str] = None
```

**run_research_task:**
- task 失败时从 error 中提取 `req_` 开头的 request_id，存入 DB

---

## Part 5: 更新 skill.md 文档

### 涉及文件
- `/home/user/ava_production_fluxa/skill.md`
- `/home/user/ava_production_fluxa/research_agent_cowork/research-frontend/public/skill.md`

### 改动点

1. **Step 2**: 移除 engine 选项说明（只有 openai），mandate 变必填说明
2. **Step 5 Request body**: engine 默认改 `"openai"`，mandate_id 改 **Required**
3. **新增: Preflight Checklist**:
   - mandate 已创建并签名
   - JWT 未过期
   - budget 足够
4. **新增: Error Matrix**:
   - 400 mandate_id missing → 创建 mandate
   - 401 → refresh JWT
   - provider_quota → 充值
   - provider_runtime → 重试 + 报 upstream_request_id
   - 新增字段 failure_stage / failure_code / retryable 说明
5. **新增: Observability / Troubleshooting**:
   - 排障流程: /research/{id} → /log → /payment
   - 最小排障命令集
6. **Cost Model**: "Claude API usage" → "OpenAI API usage"

---

## 实施顺序

1. Part 1 → 移除 Claude 引擎
2. Part 2 → Mandate 必填
3. Part 3 → 结构化失败信息
4. Part 4 → OpenAI 可观测性
5. Part 5 → 更新 skill.md

## 不改动的部分

- **保留** `AgentRunnerV1`/`AgentRunnerV3`/`get_agent_runner` 代码（防回退），只是 web_server 不再路由
- **不动** 历史数据（engine=claude 的旧记录保持原样）
- **不动** Fluxa payment 逻辑
- **不动** MCP server mount 逻辑
