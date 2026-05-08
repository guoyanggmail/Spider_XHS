# 后台接口设计

## 1. 约定

- 所有接口仅供本机或可信内网使用。
- 所有返回结构统一包含业务主体字段，错误使用 HTTP 状态码和 `detail`。
- 发帖任务使用主 Cookie。
- 搜索和采集任务默认由后端分配小号 Cookie。
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

### 2.5 获取小号 Cookie 池

```http
GET /api/cookie-workers
```

### 2.6 更新小号状态

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

### 2.7 校验 Cookie

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
```

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
    "worker_cookie_id": "worker_id",
    "claim_expires_at": "2026-05-09T10:15:00+08:00"
  }
}
```

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

App 正式接入建议使用该接口，后端按发帖、搜索、账号监控的顺序尝试分配任务，并同时刷新设备心跳。

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
