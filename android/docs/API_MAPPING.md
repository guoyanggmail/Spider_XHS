# Android 接口映射

## 配置

| 字段 | 来源 |
|---|---|
| `base_url` | App 设置页手动填写 |
| `account_id` | Web 管理后台创建主账号后复制到 App |
| `device_id` | Android ID |
| `app_instance_id` | App 首次启动生成 UUID 后持久化 |

## 接口

### 设备心跳

```http
POST /api/app/heartbeat
```

```json
{
  "device_id": "android-id",
  "app_instance_id": "uuid",
  "app_version": "1.0",
  "device_name": "Pixel 8"
}
```

### 同步主 Cookie

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
