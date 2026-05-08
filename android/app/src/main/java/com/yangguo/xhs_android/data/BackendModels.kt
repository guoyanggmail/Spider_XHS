package com.yangguo.xhs_android.data

data class AppConfig(
    val baseUrl: String = "http://10.0.2.2:8000",
    val accountId: String = "",
    val deviceId: String = "",
    val appInstanceId: String = "",
    val deviceName: String = "",
    val appVersion: String = "1.0"
)

data class AppTask(
    val taskType: String,
    val taskId: String,
    val title: String,
    val rawJson: String
)

data class AppStatus(
    val message: String = "未连接",
    val latestTask: AppTask? = null,
    val isLoading: Boolean = false
)
