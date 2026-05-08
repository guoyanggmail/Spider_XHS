# XHS Android App

Android 自动化执行端项目目录。

## 功能范围

当前已实现首期 App 骨架：

| 功能 | 说明 |
|---|---|
| 后台配置 | 支持配置后台 Base URL 和主账号 ID |
| 设备心跳 | 调用 `/api/app/heartbeat` 注册和刷新设备 |
| 主 Cookie 同步 | 手动粘贴 Cookie 后调用 `/api/app/auth/sync-cookie` |
| 拉取任务 | 调用 `/api/app/tasks/next` 获取一个任务 |
| 回传结果 | 调用 `/api/app/tasks/{type}/{id}/result` 回传模拟结果 |
| 打开小红书 | 检查并启动小红书 App |

真实发帖、搜索采集、账号监控还未接无障碍执行器，当前先打通后台接口链路。

## 打开方式

用 Android Studio 打开当前目录：

```text
/Users/guoyang/AIProjects/Spider_XHS/android
```

不要打开上一级 `Spider_XHS` 作为 Android 项目，避免 Gradle、`.idea`、`.gradle` 文件再次写到后端项目根目录。

## 命令行

```bash
cd android
./gradlew tasks
```

`local.properties`、`.gradle/`、`.idea/` 和构建产物已由根目录 `.gitignore` 忽略。

## 文档

- [需求](docs/REQUIREMENTS.md)
- [接口映射](docs/API_MAPPING.md)
- [技术方案](docs/TECHNICAL_DESIGN.md)
