# 后台接口设计

## 1. 约定

- 所有接口仅供本机或可信内网使用。
- 所有返回结构统一包含业务主体字段，错误使用 HTTP 状态码和 `detail`。
- 发帖任务使用主 Cookie。
- 关键词搜索任务由 App 创建，App 可查看任务详情、帖子数量、帖子列表和帖子详情。
- 搜索默认使用 App 当前登录账号 Cookie；后端不把小号 Cookie 分配作为首期必需能力。
- App 回传接口统一要求带 `device_id`、`app_instance_id`、`result_id`。
- App 结果回传以 `task_id + result_id` 作为幂等键。
- App 推荐优先接统一拉取/统一回传接口；分类型接口保留用于调试和兼容。

## 2. 账号与 Cookie 池

### 2.1 获取账号与 Cookie 概览

```http
GET /api/accounts
```

返回：

```json
{
  "primary_accounts": [],
  "worker_cookies": []
}
```

### 2.2 新增主账号

```http
POST /api/accounts/primary
Content-Type: application/json
```

```json
{
  "name": "品牌主号",
  "cookies": "cookie string"
}
```

### 2.3 App 更新主 Cookie

```http
POST /api/app/auth/sync-cookie
Content-Type: application/json
```

```json
{
  "account_id": "primary_account_id",
  "cookies": "cookie string",
  "source": "android_app"
}
```

### 2.3.1 App 获取主账号摘要

```http
GET /api/app/accounts/{account_id}/summary
```

返回：

```json
{
  "account": {
    "id": "primary_account_id",
    "name": "品牌主号",
    "nickname": "品牌号",
    "status": "active",
    "cookie_preview": "abcd1234...efgh5678",
    "failure_count": 0
  }
}
```

### 2.3.2 手机号验证码登录接口现状

App 现在可用以下接口：

```http
POST /api/app/auth/request-sms-code
POST /api/app/auth/login-with-sms
```

`POST /api/app/auth/request-sms-code`

```json
{
  "phone": "13800138000",
  "zone": "86"
}
```

返回：

```json
{
  "success": true,
  "message": "验证码已发送",
  "login_session_id": "session_id",
  "expires_in_seconds": 600
}
```

`POST /api/app/auth/login-with-sms`

```json
{
  "login_session_id": "session_id",
  "phone": "13800138000",
  "code": "123456",
  "zone": "86",
  "account_id": ""
}
```

返回：

```json
{
  "success": true,
  "message": "登录成功",
  "cookies": "a1=...; web_session=...",
  "account": {},
  "account_summary": {}
}
```

`POST /api/app/auth/sync-cookie` 仍保留为过渡接口，用于 App 已经拿到主账号 Cookie 后手动同步到后台。

### 2.3.3 App 即时搜索

```http
POST /api/app/search-preview
```

```json
{
  "account_id": "primary_account_id",
  "keyword": "新加坡酒店",
  "require_num": 10,
  "sort_type": "general",
  "note_type": "all",
  "time_range": "all"
}
```

返回：

```json
{
  "keyword": "新加坡酒店",
  "post_count": 2,
  "results": []
}
```

说明：该接口直接使用当前主账号 Cookie 执行一次搜索，立即返回帖子列表，不依赖先创建任务。

### 2.4 新增小号 Cookie

```http
POST /api/cookie-workers
Content-Type: application/json
```

```json
{
  "name": "采集小号01",
  "cookies": "cookie string",
  "remark": "搜索池A",
  "usage_tags": ["worker_search"],
  "group_name": "brand_a"
}
```

### 2.5 小号扫码/验证码登录

Web 管理台现在支持三种小号录入方式：

- 直接粘贴 Cookie
- 手机号 + 短信验证码登录
- 扫码登录

短信验证码接口：

```http
POST /api/cookie-workers/auth/request-sms-code
POST /api/cookie-workers/auth/login-with-sms
```

扫码接口：

```http
POST /api/cookie-workers/auth/request-qrcode
POST /api/cookie-workers/auth/check-qrcode
```

`POST /api/cookie-workers/auth/request-qrcode` 返回示例：

```json
{
  "success": true,
  "message": "二维码已生成",
  "login_session_id": "session_id",
  "expires_in_seconds": 600,
  "qr_url": "https://...",
  "qr_data_url": "data:image/svg+xml;base64,..."
}
```

### 2.6 获取小号 Cookie 池

```http
GET /api/cookie-workers
```

### 2.7 更新小号状态

```http
PATCH /api/cookie-workers/{worker_id}
Content-Type: application/json
```

```json
{
  "status": "active",
  "remark": "恢复使用",
  "usage_tags": ["worker_search", "worker_backup"],
  "group_name": "brand_a"
}
```

### 2.8 校验 Cookie

```http
POST /api/cookie-workers/{worker_id}/check
POST /api/accounts/primary/{account_id}/check
```

## 3. 发帖任务

### 3.1 创建发帖任务

```http
POST /api/publish-tasks
Content-Type: application/json
```

```json
{
  "account_id": "primary_account_id",
  "title": "标题",
  "desc": "正文",
  "topics": ["新加坡", "酒店"],
  "location": "新加坡",
  "media_type": "image",
  "media_urls": ["https://example.com/1.jpg"],
  "cover_url": "",
  "scheduled_at": "2026-05-09T10:00:00+08:00",
  "review_status": "approved"
}
```

### 3.2 获取发帖任务列表

```http
GET /api/publish-tasks?status=pending
```

### 3.3 获取已发帖列表

```http
GET /api/publish-records
```

### 3.4 更新发帖任务

```http
PATCH /api/publish-tasks/{task_id}
Content-Type: application/json
```

```json
{
  "review_status": "approved",
  "task_status": "pending",
  "remark": "人工审核通过"
}
```

### 3.5 重新入队发帖任务

```http
POST /api/publish-tasks/{task_id}/requeue
```

### 3.6 App 拉取待执行发帖任务

```http
GET /api/app/publish-tasks/next?device_id=android-001&app_instance_id=app-instance-001
```

返回：

```json
{
  "task": {
    "id": "task_id",
    "account_id": "primary_account_id",
    "title": "标题",
    "desc": "正文",
    "topics": ["新加坡"],
    "location": "新加坡",
    "media_type": "image",
    "media_urls": ["https://example.com/1.jpg"],
    "cover_url": "",
    "claim_expires_at": "2026-05-09T10:15:00+08:00"
  }
}
```

### 3.7 App 回传发帖结果

```http
POST /api/app/publish-tasks/{task_id}/result
Content-Type: application/json
```

```json
{
  "device_id": "android-001",
  "app_instance_id": "app-instance-001",
  "result_id": "publish-result-001",
  "status": "published",
  "post_id": "xhs_post_id",
  "post_url": "https://www.xiaohongshu.com/explore/xxx",
  "error_message": "",
  "duration_seconds": 95
}
```

## 4. 关键词采集任务

### 4.1 创建关键词任务

App 创建：

```http
POST /api/app/search-tasks
Content-Type: application/json
```

```json
{
  "keyword": "新加坡 qt",
  "require_num": 20,
  "sort_type": "general",
  "note_type": "all",
  "time_range": "all",
  "enabled": true,
  "device_id": "android-001",
  "app_instance_id": "app-instance-001"
}
```

管理后台兼容接口：

```http
POST /api/search-tasks
Content-Type: application/json
```

```json
{
  "keyword": "新加坡 qt",
  "interval_minutes": 120,
  "require_num": 20,
  "sort_type": "general",
  "note_type": "all",
  "time_range": "all",
  "enabled": true,
  "group_name": "brand_a"
}
```

### 4.2 获取关键词任务列表

```http
GET /api/search-tasks
GET /api/app/search-tasks
```

App 列表返回会附带 `post_count`：

```json
{
  "tasks": [
    {
      "id": "task_id",
      "keyword": "新加坡 qt",
      "task_status": "pending",
      "post_count": 12
    }
  ]
}
```

### 4.2.1 App 查看关键词任务详情

```http
GET /api/app/search-tasks/{task_id}
```

返回：

```json
{
  "task": {
    "id": "task_id",
    "keyword": "新加坡 qt"
  },
  "post_count": 12,
  "results": [
    {
      "post_id": "xxx",
      "post_url": "https://www.xiaohongshu.com/explore/xxx",
      "title": "帖子标题",
      "author_name": "作者A",
      "author_id": "user_a",
      "content_preview": "正文摘要",
      "content": "帖子完整正文",
      "note_type": "normal",
      "topics": ["新加坡", "酒店"],
      "image_urls": ["https://cdn.example.com/1.jpg"],
      "video_url": "",
      "video_cover_url": "",
      "like_count": 12,
      "comment_count": 3,
      "collect_count": 1,
      "publish_time": "2026-05-08T10:00:00+08:00"
    }
  ]
}
```

说明：历史任务结果优先从 `raw_payload` 还原正文、话题、图片和视频字段；旧数据没有这些字段时仅返回基础摘要。

### 4.2.2 App 即时搜索

```http
POST /api/app/search-preview
Content-Type: application/json
```

```json
{
  "account_id": "primary_account_id",
  "keyword": "新加坡酒店",
  "require_num": 10,
  "sort_type": "general",
  "note_type": "all",
  "time_range": "all"
}
```

返回：

```json
{
  "keyword": "新加坡酒店",
  "post_count": 1,
  "results": [
    {
      "post_id": "xxx",
      "post_url": "https://www.xiaohongshu.com/explore/xxx",
      "title": "帖子标题",
      "author_name": "作者A",
      "author_id": "user_a",
      "content_preview": "正文摘要",
      "content": "帖子完整正文",
      "note_type": "video",
      "topics": ["新加坡", "酒店"],
      "image_urls": ["https://cdn.example.com/1.jpg"],
      "video_url": "https://cdn.example.com/1.mp4",
      "video_cover_url": "https://cdn.example.com/cover.jpg",
      "like_count": 12,
      "comment_count": 3,
      "collect_count": 1,
      "publish_time": "2026-05-08T10:00:00+08:00"
    }
  ]
}
```

说明：当搜索结果没有单独标题时，后端会用正文前 30 个字符补标题，避免 App 列表出现空标题。

### 4.2.3 App 查看单条帖子详情

```http
POST /api/app/search-post-detail
Content-Type: application/json
```

```json
{
  "account_id": "primary_account_id",
  "post_url": "https://www.xiaohongshu.com/explore/xxx"
}
```

返回：

```json
{
  "detail": {
    "post_id": "xxx",
    "post_url": "https://www.xiaohongshu.com/explore/xxx",
    "title": "帖子标题",
    "content_preview": "正文摘要",
    "content": "帖子完整正文",
    "note_type": "video",
    "topics": ["新加坡", "酒店"],
    "image_urls": ["https://cdn.example.com/1.jpg"],
    "video_url": "https://cdn.example.com/1.mp4",
    "video_cover_url": "https://cdn.example.com/cover.jpg"
  }
}
```

说明：App 点击帖子列表项后调用该接口，避免搜索列表接口因为字段裁剪导致正文、话题、图片、视频不完整。

### 4.3 更新关键词任务

```http
PATCH /api/search-tasks/{task_id}
Content-Type: application/json
```

```json
{
  "enabled": false
}
```

### 4.4 重新入队关键词任务

```http
POST /api/search-tasks/{task_id}/requeue
```

### 4.5 App 拉取待执行采集任务

```http
GET /api/app/search-tasks/next?device_id=android-001&app_instance_id=app-instance-001
```

返回：

```json
{
  "task": {
    "id": "task_id",
    "keyword": "新加坡 qt",
    "require_num": 20,
    "sort_type": "general",
    "note_type": "all",
    "time_range": "all",
    "claim_expires_at": "2026-05-09T10:15:00+08:00"
  }
}
```

说明：首期搜索任务由 App 使用本地登录态执行，`worker_cookie_id` 仅在后续启用小号池时返回。

### 4.6 App 回传采集结果

```http
POST /api/app/search-tasks/{task_id}/result
Content-Type: application/json
```

```json
{
  "device_id": "android-001",
  "app_instance_id": "app-instance-001",
  "result_id": "search-result-001",
  "worker_cookie_id": "worker_id",
  "partial_success": true,
  "items": [
    {
      "post_id": "xxx",
      "post_url": "https://www.xiaohongshu.com/explore/xxx",
      "title": "帖子标题",
      "username": "用户A",
      "user_id": "user_a",
      "content_preview": "内容摘要",
      "like_count": 12,
      "comment_count": 3,
      "collect_count": 1,
      "publish_time": "2026-05-08T10:00:00+08:00"
    }
  ],
  "error_message": ""
}
```

`worker_cookie_id` 在首期可由后端兼容为空；如后续启用小号池，则必须回传实际使用的小号。

### 4.7 查看采集结果

```http
GET /api/search-results?task_id=task_id
```

### 4.8 更新采集结果审核状态

```http
PATCH /api/search-results/{result_id}
Content-Type: application/json
```

```json
{
  "review_status": "valid",
  "review_note": "品牌相关",
  "hidden": false
}
```

## 5. 账号数据监控

### 5.1 创建账号监控任务

```http
POST /api/analytics-tasks
Content-Type: application/json
```

```json
{
  "account_id": "primary_account_id",
  "interval_minutes": 360,
  "enabled": true,
  "group_name": "brand_a"
}
```

### 5.2 获取监控任务列表

```http
GET /api/analytics-tasks
```

### 5.3 更新监控任务

```http
PATCH /api/analytics-tasks/{task_id}
Content-Type: application/json
```

```json
{
  "enabled": true,
  "interval_minutes": 360,
  "group_name": "brand_a"
}
```

### 5.4 重新入队监控任务

```http
POST /api/analytics-tasks/{task_id}/requeue
```

### 5.5 App 拉取待执行监控任务

```http
GET /api/app/analytics-tasks/next?device_id=android-001&app_instance_id=app-instance-001
```

返回：

```json
{
  "task": {
    "id": "task_id",
    "account_id": "primary_account_id",
    "worker_cookie_id": "worker_id",
    "claim_expires_at": "2026-05-09T10:15:00+08:00"
  }
}
```

### 5.6 App 回传监控快照

```http
POST /api/app/analytics-tasks/{task_id}/result
Content-Type: application/json
```

```json
{
  "device_id": "android-001",
  "app_instance_id": "app-instance-001",
  "result_id": "analytics-result-001",
  "worker_cookie_id": "worker_id",
  "snapshot": {
    "account_id": "primary_account_id",
    "nickname": "品牌号",
    "follower_count": 3200,
    "liked_count": 1200,
    "post_count": 84,
    "posts": [
      {
        "post_id": "xxx",
        "title": "帖子标题",
        "like_count": 12,
        "comment_count": 3,
        "collect_count": 1
      }
    ]
  },
  "error_message": ""
}
```

### 5.7 查看监控快照

```http
GET /api/analytics-snapshots?account_id=primary_account_id
```

## 6. App 统一任务接口

### 6.1 统一拉取下一个任务

App 正式接入建议使用该接口拉取后台创建的发帖任务。搜索任务由 App 创建，也可通过分类型接口或统一接口领取执行。

```http
GET /api/app/tasks/next?device_id=android-001&app_instance_id=app-instance-001&app_version=1.0.0&device_name=Pixel
```

无任务：

```json
{
  "task_type": null,
  "task": null
}
```

有任务：

```json
{
  "task_type": "search",
  "task": {
    "id": "task_id",
    "keyword": "新加坡 qt",
    "worker_cookie_id": "worker_id",
    "claim_expires_at": "2026-05-09T10:15:00+08:00"
  }
}
```

### 6.2 统一回传任务结果

```http
POST /api/app/tasks/{task_type}/{task_id}/result
Content-Type: application/json
```

`task_type` 可选：

| 类型 | Payload |
|---|---|
| `publish` | 与发帖结果回传一致 |
| `search` | 与关键词采集结果回传一致 |
| `analytics` | 与账号监控快照回传一致 |

## 7. 运营概览、设备与日志

### 7.1 获取概览数据

```http
GET /api/ops/summary
```

### 7.2 获取操作日志

```http
GET /api/logs
```

### 7.3 App 心跳

```http
POST /api/app/heartbeat
Content-Type: application/json
```

该接口为兼容能力，不是首期 App 必需流程。App 拉取任务、创建搜索任务、回传结果时携带的 `device_id` 和 `app_instance_id` 已足够做基础追踪。

```json
{
  "device_id": "android-001",
  "app_instance_id": "app-instance-001",
  "app_version": "1.0.0",
  "device_name": "Pixel 8"
}
```

### 7.4 更新设备状态

```http
PATCH /api/devices/{device_id}
Content-Type: application/json
```

```json
{
  "status": "disabled"
}
```

## 8. 删除或废弃的旧接口

以下接口不再保留为目标能力：

| 旧接口方向 | 处理方式 |
|---|---|
| Web 直接发布 `/api/publish` | 废弃 |
| Web 直接搜索 `/api/search/notes` | 废弃 |
| 评论自动回复相关接口 | 删除 |
| 第三方扫码发布接口 | 删除 |
| 评论工作台相关接口 | 删除 |

## 9. 状态与错误建议

状态建议：

| 字段 | 可选值 |
|---|---|
| 任务状态 | `pending` `claimed` `running` `success` `failed` `cancelled` |
| Cookie 状态 | `active` `cooldown` `invalid` `disabled` |
| 审核状态 | `pending` `approved` `rejected` |
| 采集结果审核 | `pending` `valid` `rejected` |
| 设备状态 | `online` `offline` `disabled` |

错误建议：

| 场景 | HTTP 状态码 |
|---|---|
| 参数错误 | `400` |
| 资源不存在 | `404` |
| 任务冲突或重复领取 | `409` |
| 风控冷却中 | `429` |
| 上游执行异常 | `502` |
