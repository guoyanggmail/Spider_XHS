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

用于“我的”页展示：

- 主账号头像
- 昵称
- 关注数 / 粉丝数 / 获赞数
- 已发布笔记列表
- 状态、Cookie 脱敏预览和失败次数

接口策略：

- 主账号身份仍以主账号自身登录态为准
- 已发布笔记列表优先使用主账号创作者接口拉取，便于更快看到刚发布的笔记
- 已发布笔记列表和公开资料优先复用 `worker_search` 小号 Cookie 拉取
- 小号不可用时回退到后台已有快照或主账号自有资料

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

发帖 Tab 不使用这个统一入口，直接调用：

```http
GET /api/app/publish-tasks/next
```

这样可以避免把关键词搜索任务错误展示到发帖页。

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

当前搜索请求默认从小号池中选择 `worker_search` 小号 Cookie 执行，降低主账号风控风险。

返回的每条帖子结果同时作为详情页数据源，并额外携带：

- `author_avatar`
- `cover_url`
- `location`
- `worker_cookie_id`

当前改为：

```http
POST /api/app/search-post-detail
```

App 点击帖子项后，使用 `post_url + worker_cookie_id` 拉取单条帖子详情，继续复用同一小号 Cookie，加载正文、话题、图片和视频。这样可以避免搜索列表字段不全的问题。

如果 `search-preview` 或 `search-post-detail` 返回 `401`，Android 必须立即清空本地登录态并跳回手机号验证码登录页，不能继续保留失效账号停留在首页。

### App 从帖子详情创建发帖任务

```http
POST /api/publish-tasks
```

Android 在帖子详情页右上角提供“创建发帖”按钮，点击后直接复用当前详情页数据创建后台发帖任务：

- `title`: 优先使用帖子标题，缺失时回退到正文摘要
- `desc`: 使用帖子正文
- `topics`: 使用详情页话题列表
- `location`: 使用帖子地点
- `media_type`: 根据详情页判断图文或视频
- `media_urls`: 图文取 `image_urls`，视频取 `video_url`
- `cover_url`: 优先使用详情封面字段
- `review_status`: 默认写成 `pending`

这样搜索侧看到合适帖子后，可以直接转成后台待审核的发帖任务，不需要回到 Web 端重新填写素材字段。

### App 执行发帖任务

```http
POST /api/app/publish-tasks/{task_id}/execute
```

Android 领取发帖任务后，直接调用该接口。后台负责下载媒体 URL、调用内部发布接口、写回任务成功或失败状态。Android 不再打开小红书，也不再手工填写帖子 ID、帖子链接和回传结果。

补充约束：

- Android 对该接口使用更长的读取超时，避免媒体上传和发布过程较长时误报超时
- 如果后台已经成功写入任务结果，重复调用该接口会直接返回已有成功结果，不再报冲突

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
