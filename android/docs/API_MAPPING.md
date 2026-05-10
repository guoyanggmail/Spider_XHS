# Android 接口映射

## 配置

| 字段 | 来源 |
|---|---|
| `base_url` | App 设置页手动填写 |
| `account_id` | Web 管理后台创建主账号后复制到 App |
| `device_id` | Android ID，用于任务领取和结果排查 |
| `app_instance_id` | App 首次启动生成 UUID 后持久化 |

## 接口

### 设备心跳

首期不需要单独调用心跳接口。App 在创建搜索任务、拉取发帖任务、回传结果时携带 `device_id` 和 `app_instance_id`。

### 手机号验证码登录

```http
POST /api/app/auth/request-sms-code
POST /api/app/auth/login-with-sms
```

`request-sms-code` 用于发送验证码并返回 `login_session_id`。  
`login-with-sms` 用于验证码登录，成功后返回主账号 Cookie、账号摘要和后台 `account_id`。

### 校验主账号状态

```http
POST /api/app/accounts/{account_id}/check
```

用于 App 启动时或用户手动触发时校验后台记录的主账号 Cookie 状态。  
当接口返回失效状态时，App 清空本地登录态，并要求重新获取验证码登录。

### 保存主账号 Cookie

```http
POST /api/app/auth/sync-cookie
```

```json
{
  "account_id": "primary_account_id",
  "cookies": "cookie string",
  "source": "android_app"
}
```

### 查看主账号摘要

```http
GET /api/app/accounts/{account_id}/summary
```

用于账号模块展示昵称、状态、Cookie 脱敏预览和失败次数。

### 统一拉取任务

```http
GET /api/app/tasks/next?device_id=android-id&app_instance_id=uuid&app_version=1.0&device_name=Pixel
```

返回：

```json
{
  "task_type": "publish",
  "task": {}
}
```

### App 创建关键词搜索任务

```http
POST /api/app/search-tasks
```

```json
{
  "keyword": "新加坡酒店",
  "require_num": 20,
  "sort_type": "general",
  "note_type": "all",
  "time_range": "all",
  "enabled": true,
  "device_id": "android-id",
  "app_instance_id": "uuid"
}
```

### App 查看关键词任务列表

```http
GET /api/app/search-tasks
```

返回任务状态和 `post_count`。

### App 查看关键词任务详情

```http
GET /api/app/search-tasks/{task_id}
```

返回 `task`、`post_count` 和 `results`。`results` 除基础摘要外，还会尽量包含：

- `content`
- `topics`
- `image_urls`
- `video_url`
- `video_cover_url`
- `note_type`

### App 即时搜索

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

用于 Android 先直接执行搜索并返回帖子列表，不依赖先创建任务。

返回的每条帖子结果同时作为详情页数据源。App 点击帖子项后，直接展示正文、话题、图片链接、视频链接和帖子链接，不额外发起详情请求。

当前改为：

```http
POST /api/app/search-post-detail
```

App 点击帖子项后，使用 `post_url` 拉取单条帖子详情，加载正文、话题、图片和视频。这样可以避免搜索列表字段不全的问题。

### 统一回传结果

```http
POST /api/app/tasks/{task_type}/{task_id}/result
```

| `task_type` | 回传内容 |
|---|---|
| `publish` | 发帖结果、帖子 ID、帖子 URL |
| `search` | 搜索采集结果列表、部分成功标记 |
| `analytics` | 账号数据快照、帖子指标 |

## 本地开发地址

Android 模拟器访问电脑本机后端：

```text
http://10.0.2.2:8000
```

真机访问电脑后端：

```text
http://电脑局域网IP:8000
```
