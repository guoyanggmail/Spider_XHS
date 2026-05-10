package com.yangguo.xhs_android.data

data class AppConfig(
    val baseUrl: String = "http://10.0.2.2:8000",
    val accountId: String = "",
    val primaryCookie: String = "",
    val languageCode: String = "",
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

data class PublishTaskDetail(
    val taskId: String,
    val title: String,
    val content: String,
    val topics: List<String>,
    val location: String,
    val mediaType: String,
    val mediaUrls: List<String>,
    val coverUrl: String,
    val taskStatus: String,
    val lastError: String,
    val publishedPostUrl: String
)

data class PublishTaskDraft(
    val accountId: String,
    val title: String,
    val desc: String,
    val topics: List<String>,
    val location: String,
    val mediaType: String,
    val mediaUrls: List<String>,
    val coverUrl: String,
    val reviewStatus: String = "pending",
    val maxRetry: Int = 1
)

data class SearchTaskSummary(
    val taskId: String,
    val keyword: String,
    val status: String,
    val postCount: Int,
    val requireNum: Int,
    val rawJson: String
)

data class SearchResultItem(
    val postId: String,
    val postUrl: String,
    val title: String,
    val authorName: String,
    val authorAvatar: String,
    val likeCount: Int,
    val commentCount: Int,
    val collectCount: Int,
    val contentPreview: String,
    val content: String,
    val noteType: String,
    val topics: List<String>,
    val coverUrl: String,
    val imageUrls: List<String>,
    val videoUrl: String,
    val videoCoverUrl: String,
    val publishTime: String,
    val location: String,
    val workerCookieId: String
)

data class SearchTaskDetail(
    val taskId: String,
    val keyword: String,
    val postCount: Int,
    val results: List<SearchResultItem>
)

data class AccountSummary(
    val accountId: String,
    val name: String,
    val nickname: String,
    val status: String,
    val cookiePreview: String,
    val failureCount: Int,
    val remark: String,
    val avatar: String,
    val followingCount: Int,
    val followerCount: Int,
    val likedCount: Int,
    val publishedNotes: List<SearchResultItem>
)

data class AccountCheckResult(
    val success: Boolean,
    val message: String,
    val account: AccountSummary
)

data class SmsCodeSession(
    val loginSessionId: String,
    val expiresInSeconds: Int
)

data class AppStatus(
    val message: String = "未连接",
    val latestTask: AppTask? = null,
    val accountSummary: AccountSummary? = null,
    val smsCodeSession: SmsCodeSession? = null,
    val searchTasks: List<SearchTaskSummary> = emptyList(),
    val searchTaskDetail: SearchTaskDetail? = null,
    val requiresRelogin: Boolean = false,
    val isLoading: Boolean = false
)
