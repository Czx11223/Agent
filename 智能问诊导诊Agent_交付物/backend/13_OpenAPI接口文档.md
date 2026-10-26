# FastAPI 后端 OpenAPI 接口文档

- 版本：V1.0.0　·　基础路径：`https://<host>/api/v1`（生产必须走 HTTPS 终截）
- 认证方式：绝大多数接口需 `Authorization: Bearer <token>`（登录接口获取）
- 统一响应结构：成功 `{"code":0,"message":"ok","data":...}`；失败 `{"code":<非0>,"message":"...","data":null}`

---

## 0. 统一错误码

| code | 含义 | 建议处理 |
| --- | --- | --- |
| 0 | 成功 | — |
| 4001 | 参数错误 | 检查入参 |
| 4002 | 账号或密码错误 | 提示重新登录 |
| 4003 | 未登录 / 令牌失效 / 过期 | 跳转登录或刷新令牌 |
| 4004 | 越权访问他人资源 | 提示无权访问 |
| 4005 | 资源不存在 | 提示 |
| 4006 | 数据冲突（用户已存在） | 提示更换 |
| 4007 | 检测到提示词注入，已拦截 | 提示输入包含敏感指令 |
| 5000 | 服务器内部错误 | 提示稍后重试 |
| 5001 | 大模型调用失败 | 提示服务繁忙 |
| 5002 | 数据库异常 | 提示稍后重试 |

---

## 1. 注册用户

- **POST** `/api/v1/auth/register`

请求体：

```json
{
  "username": "chenzx",
  "password": "P@ssw0rd123",
  "phone": "13800000000"
}
```

返回示例（成功）：

```json
{
  "code": 0,
  "message": "ok",
  "data": { "user_id": 1, "username": "chenzx" }
}
```

返回示例（用户名已存在 `4006`）：

```json
{ "code": 4006, "message": "用户名或手机号已存在", "data": null }
```

---

## 2. 用户登录

- **POST** `/api/v1/auth/login`

请求体：

```json
{ "account": "chenzx", "password": "P@ssw0rd123" }
```

返回示例（成功）：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xxx.yyy",
    "user": { "id": 1, "username": "chenzx", "role": "patient" }
  }
}
```

返回示例（失败 `4002`）：`{ "code": 4002, "message": "账号或密码错误", "data": null }`

---

## 3. 获取会话列表

- **GET** `/api/v1/conversations`
- **Header**: `Authorization: Bearer <token>`

返回示例（成功）：

```json
{
  "code": 0,
  "message": "ok",
  "data": [
    {
      "id": 1,
      "code": "C20261008001",
      "user_id": 1,
      "title": "咳嗽三天",
      "status": "diagnosing",
      "started_at": "2026-10-08T09:00:00+00:00",
      "ended_at": null,
      "slot_state": "{\"main_symptom\":\"咳嗽\",\"duration\":\"三天\"}",
      "ask_progress": "{}",
      "emergency_flag": 0,
      "deleted": 0,
      "created_at": "2026-10-08T09:00:00+00:00",
      "updated_at": "2026-10-08T09:00:00+00:00"
    }
  ]
}
```

---

## 4. 新建会话

- **POST** `/api/v1/conversations`
- **Header**: `Authorization: Bearer <token>`

请求体：

```json
{ "title": "新问诊" }
```

返回示例（成功）：

```json
{ "code": 0, "message": "ok", "data": { "conversation_id": 2 } }
```

---

## 5. SSE 流式对话（核心接口）

- **POST** `/api/v1/chat/stream`
- **Header**: `Authorization: Bearer <token>`
- **Content-Type**: `application/json`；**响应**: `text/event-stream`

请求体：

```json
{ "conversation_id": 1, "content": "我胸口疼三天了" }
```

响应（SSE，逐事件）示例：

```text
event: slot
data: {"type":"slot","updates":{"main_symptom":"胸痛","body_part":"胸口","duration":"三天"}}

event: comfort
data: {"type":"comfort","emotion":"pain","text":"听上去确实很难受，辛苦了。"}

event: token
data: {"type":"token","delta":"请问"}

event: token
data: {"type":"token","delta":"这种情况持续多久了？"}

event: question
data: {"type":"question","missing":"duration","text":"这种情况持续多久了？"}

event: done
data: {"type":"done","next":"asking"}
```

急重症命中示例：

```text
event: emergency
data: {"type":"emergency","flag":true}
data: {"type":"done","next":"emergency","text":"【急重症提示】……请您立即前往医院急诊科，或尽快拨打120急救电话，切勿耽搁。"}
```

错误（提示词注入 `4007`）示例：

```text
event: error
data: {"code":4007,"message":"检测到可疑指令注入,已拦截"}
```

> 前端使用 EventSource 或不支持时的 polyfill 解析；`done.next` 取值 `asking / report_ready / emergency / rejected`。

---

## 6. 获取会话全部历史消息

- **GET** `/api/v1/conversations/{cid}/messages`
- **Header**: `Authorization: Bearer <token>`

返回示例（成功）：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "conversation": { "id": 1, "title": "咳嗽三天", "status": "completed" },
    "messages": [
      {
        "id": 1,
        "code": "M20261008001",
        "conversation_id": 1,
        "sender": "user",
        "content": "我胸口疼三天了",
        "content_type": "text",
        "slot_delta": "{\"body_part\":\"胸口\"}",
        "emotion": null,
        "emergency_hit": 0,
        "created_at": "2026-10-08T09:00:00+00:00"
      },
      {
        "id": 2,
        "conversation_id": 1,
        "sender": "agent",
        "content": "请问这种情况持续多久了？",
        "content_type": "text",
        "slot_delta": null,
        "emotion": null,
        "emergency_hit": 0,
        "created_at": "2026-10-08T09:00:01+00:00"
      }
    ]
  }
}
```

---

## 7. 获取预问诊报告

- **GET** `/api/v1/reports/{conv_id}`
- **Header**: `Authorization: Bearer <token>`

返回示例（成功）：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "id": 1,
    "code": "R20261008001",
    "conversation_id": 1,
    "user_id": 1,
    "chief_complaint": "右侧胸肋疼痛 3 天",
    "present_illness": "……",
    "accompanying_symptom": "胸闷、气短",
    "past_history": "高血压",
    "allergy_history": "无",
    "symptom_json": "{}",
    "recommend_dept_top3": "[{\"dept\":\"心血管内科\",\"reason\":\"…\"},…]",
    "top3_accuracy": 0,
    "emergency_flag": 0,
    "disclaimer": "本报告来源于患者口述，仅供参考……",
    "status": "generated",
    "deleted": 0,
    "created_at": "2026-10-08T09:00:05+00:00",
    "updated_at": "2026-10-08T09:00:05+00:00"
  }
}
```

未生成报告（`4005`）：`{ "code": 4005, "message": "报告尚未生成", "data": null }`

---

## 8. 报告复制 / 导出

- **GET** `/api/v1/reports/{conv_id}/export`
- **Header**: `Authorization: Bearer <token>`

返回示例（成功，Markdown 文本）：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "filename": "R20261008001.md",
    "content": "# 预问诊报告\n\n## 主诉\n右侧胸肋疼痛 3 天\n\n……\n\n> 本报告来源于患者口述，仅供参考。"
  }
}
```

---

## 9. 评测数据写入

- **POST** `/api/v1/evaluation/write`
- **Header**: `Authorization: Bearer <token>`（建议 evaluator 角色）

请求体：

```json
{
  "batch_code": "EVAL_20261008",
  "test_case_id": "TC-0001",
  "input_text": "我胸口疼三天了",
  "expected_dept": "心血管内科",
  "expected_fields": "{\"main_symptom\":\"胸痛\",\"duration\":\"三天\"}"
}
```

返回示例（成功）：

```json
{ "code": 0, "message": "ok", "data": { "evaluation_id": 1 } }
```

---

## 10. 健康检查

- **GET** `/api/v1` 外的 `/health`

```json
{ "code": 0, "message": "ok", "data": { "status": "ok" } }
```