# XHS Android App

Android 自动化执行端项目目录。

## 功能范围

当前已实现首期 App 骨架：

| 功能 | 说明 |
|---|---|
| 接口地址 | 支持配置后台 Base URL 和主账号 ID |
| 手机号验证码登录 | 调用 `/api/app/auth/request-sms-code` 和 `/api/app/auth/login-with-sms` |
| 主 Cookie 保存 | 登录成功后自动返回并本地保存，`/api/app/auth/sync-cookie` 仅保留为兼容接口 |
| Cookie 状态校验 | 调用 `/api/app/accounts/{account_id}/check`，失效后清空本地登录态并要求重新登录 |
| 发帖任务拉取 | 调用 `/api/app/tasks/next` 获取后台创建的发帖任务 |
| 发帖执行 | 调用 `/api/app/publish-tasks/{task_id}/execute` 由后台直接执行发布 |
| 关键词任务 | 调用 `/api/app/search-tasks` 创建任务，并查看任务详情和帖子数量 |

当前已打通手机号验证码登录、Cookie 保存、Cookie 状态校验、发帖任务拉取、后台直连发布执行、搜索预览、帖子详情页一键创建发帖任务和账号查询链路。

当前页面结构：

| 页面/模块 | 说明 |
|---|---|
| 登录页 | 进入 App 先判断登录状态，未登录或失效时跳到手机号验证码登录页 |
| 首页 | 登录成功后进入首页，底部三个 Tab：发帖、搜索、我的 |
| 发帖 Tab | 拉取后台任务后，直接调用后台发布接口完成发帖 |
| 搜索 Tab | 支持立即搜索、创建关键词任务、查看任务详情和帖子列表 |
| 我的 Tab | 查看账号详情、校验状态、切换中英文、保存后台地址、退出登录 |

当前 Android 视觉风格使用“轻拟态借鉴小红书”的内容产品风格，后续新增页面默认遵循 [UI Style Guide](docs/UI_STYLE_GUIDE.md)。

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
- [UI 风格](docs/UI_STYLE_GUIDE.md)
