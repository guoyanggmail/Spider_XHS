package com.yangguo.xhs_android.data

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URLEncoder
import java.net.URL

class BackendClient(private val config: AppConfig) {
    class SessionExpiredException(message: String) : IllegalStateException(message)

    private fun jsonArrayToStringList(array: JSONArray?): List<String> {
        if (array == null) return emptyList()
        return List(array.length()) { index -> array.optString(index) }.filter { it.isNotBlank() }
    }

    private fun parseSearchResultItem(item: JSONObject): SearchResultItem {
        return SearchResultItem(
            postId = item.optString("post_id"),
            postUrl = item.optString("post_url"),
            title = item.optString("title"),
            authorName = item.optString("author_name"),
            authorAvatar = item.optString("author_avatar"),
            likeCount = item.optInt("like_count"),
            commentCount = item.optInt("comment_count"),
            collectCount = item.optInt("collect_count"),
            contentPreview = item.optString("content_preview"),
            content = item.optString("content"),
            noteType = item.optString("note_type"),
            topics = jsonArrayToStringList(item.optJSONArray("topics")),
            coverUrl = item.optString("cover_url"),
            imageUrls = jsonArrayToStringList(item.optJSONArray("image_urls")),
            videoUrl = item.optString("video_url"),
            videoCoverUrl = item.optString("video_cover_url"),
            publishTime = item.optString("publish_time"),
            location = item.optString("location"),
            workerCookieId = item.optString("worker_cookie_id")
        )
    }

    internal fun normalizePublishTaskTitle(item: SearchResultItem): String {
        val candidates = listOf(
            item.title,
            item.contentPreview,
            item.content,
        )
        return candidates
            .map { it.trim() }
            .firstOrNull { it.isNotBlank() && it != "无标题" }
            ?.take(120)
            ?: "笔记${item.postId.takeLast(8).ifBlank { "" }}"
    }

    internal fun buildPublishTaskMediaUrls(item: SearchResultItem): List<String> {
        if (item.videoUrl.isNotBlank()) {
            return listOf(item.videoUrl.trim())
        }
        return item.imageUrls
            .map { it.trim() }
            .filter { it.isNotBlank() }
            .ifEmpty {
                listOf(item.coverUrl.trim()).filter { it.isNotBlank() }
            }
    }

    internal fun resolvePublishTaskCoverUrl(item: SearchResultItem): String {
        return item.coverUrl
            .ifBlank { item.videoCoverUrl }
            .ifBlank { item.imageUrls.firstOrNull().orEmpty() }
            .trim()
    }

    internal fun buildPublishTaskDraft(item: SearchResultItem): PublishTaskDraft {
        val mediaUrls = buildPublishTaskMediaUrls(item)
        require(mediaUrls.isNotEmpty()) { "当前帖子没有可用的图片或视频" }
        return PublishTaskDraft(
            accountId = config.accountId,
            title = normalizePublishTaskTitle(item),
            desc = item.content.ifBlank { item.contentPreview }.trim(),
            topics = item.topics.filter { it.isNotBlank() },
            location = item.location.trim(),
            mediaType = if (item.videoUrl.isNotBlank()) "video" else "image",
            mediaUrls = mediaUrls,
            coverUrl = resolvePublishTaskCoverUrl(item),
        )
    }

    internal fun buildPublishTaskRequestBody(item: SearchResultItem): JSONObject {
        val draft = buildPublishTaskDraft(item)
        return JSONObject()
            .put("account_id", draft.accountId)
            .put("title", draft.title)
            .put("desc", draft.desc)
            .put("topics", JSONArray(draft.topics))
            .put("location", draft.location)
            .put("media_type", draft.mediaType)
            .put("media_urls", JSONArray(draft.mediaUrls))
            .put("cover_url", draft.coverUrl)
            .put("review_status", draft.reviewStatus)
            .put("max_retry", draft.maxRetry)
    }

    fun requestSmsCode(phone: String): SmsCodeSession {
        require(phone.isNotBlank()) { "请先填写手机号" }
        val body = JSONObject()
            .put("phone", phone.trim())
            .put("zone", "86")
        val response = JSONObject(request("POST", "/api/app/auth/request-sms-code", body))
        return SmsCodeSession(
            loginSessionId = response.optString("login_session_id"),
            expiresInSeconds = response.optInt("expires_in_seconds")
        )
    }

    fun loginWithSmsCode(phone: String, code: String, loginSessionId: String): Pair<AccountSummary, String> {
        require(phone.isNotBlank()) { "请先填写手机号" }
        require(code.isNotBlank()) { "请先填写验证码" }
        require(loginSessionId.isNotBlank()) { "请先获取验证码" }
        val body = JSONObject()
            .put("login_session_id", loginSessionId)
            .put("phone", phone.trim())
            .put("code", code.trim())
            .put("zone", "86")
            .put("account_id", config.accountId)
            .put("device_id", config.deviceId)
        val response = JSONObject(request("POST", "/api/app/auth/login-with-sms", body))
        return parseAccountSummary(response.getJSONObject("account_summary")) to response.optString("cookies")
    }

    fun syncPrimaryCookie(cookie: String): String {
        require(config.accountId.isNotBlank()) { "请先填写主账号 ID" }
        val body = JSONObject()
            .put("account_id", config.accountId)
            .put("cookies", cookie.trim())
            .put("source", "android_app")
        request("POST", "/api/app/auth/sync-cookie", body)
        return "主 Cookie 已同步"
    }

    fun fetchAccountSummary(): AccountSummary {
        require(config.accountId.isNotBlank()) { "请先填写主账号 ID" }
        val response = JSONObject(request("GET", "/api/app/accounts/${config.accountId}/summary"))
        val account = response.getJSONObject("account")
        return parseAccountSummary(account)
    }

    fun checkAccountStatus(): AccountCheckResult {
        require(config.accountId.isNotBlank()) { "请先填写主账号 ID" }
        val response = JSONObject(request("POST", "/api/app/accounts/${config.accountId}/check", JSONObject()))
        return AccountCheckResult(
            success = response.optBoolean("success"),
            message = response.optString("message"),
            account = parseAccountSummary(response.getJSONObject("account"))
        )
    }

    private fun parseAccountSummary(account: JSONObject): AccountSummary {
        val publishedNotes = account.optJSONArray("published_notes") ?: JSONArray()
        return AccountSummary(
            accountId = account.optString("id"),
            name = account.optString("name"),
            nickname = account.optString("nickname"),
            status = account.optString("status"),
            cookiePreview = account.optString("cookie_preview"),
            failureCount = account.optInt("failure_count"),
            remark = account.optString("remark"),
            avatar = account.optString("avatar"),
            followingCount = account.optInt("following_count"),
            followerCount = account.optInt("follower_count"),
            likedCount = account.optInt("liked_count"),
            publishedNotes = List(publishedNotes.length()) { index ->
                parseSearchResultItem(publishedNotes.getJSONObject(index))
            }
        )
    }

    fun createSearchTask(keyword: String, requireNum: Int): String {
        require(keyword.isNotBlank()) { "请填写关键词" }
        val body = JSONObject()
            .put("keyword", keyword.trim())
            .put("require_num", requireNum.coerceIn(1, 100))
            .put("interval_minutes", 120)
            .put("sort_type", "general")
            .put("note_type", "all")
            .put("time_range", "all")
            .put("enabled", true)
            .put("device_id", config.deviceId)
            .put("app_instance_id", config.appInstanceId)
        val response = JSONObject(request("POST", "/api/app/search-tasks", body))
        val task = response.getJSONObject("task")
        return "关键词任务已创建：${task.optString("keyword")}"
    }

    fun createPublishTaskFromPost(item: SearchResultItem): String {
        require(config.accountId.isNotBlank()) { "请先完成登录" }
        val body = buildPublishTaskRequestBody(item)
        val response = JSONObject(request("POST", "/api/publish-tasks", body))
        val task = response.getJSONObject("task")
        return task.optString("id")
    }

    fun searchPreview(keyword: String, requireNum: Int): SearchTaskDetail {
        require(config.accountId.isNotBlank()) { "请先完成登录" }
        require(keyword.isNotBlank()) { "请填写关键词" }
        val body = JSONObject()
            .put("account_id", config.accountId)
            .put("keyword", keyword.trim())
            .put("require_num", requireNum.coerceIn(1, 20))
            .put("sort_type", "general")
            .put("note_type", "all")
            .put("time_range", "all")
        val response = JSONObject(request("POST", "/api/app/search-preview", body))
        val results = response.optJSONArray("results") ?: JSONArray()
        return SearchTaskDetail(
            taskId = "",
            keyword = response.optString("keyword"),
            postCount = response.optInt("post_count"),
            results = List(results.length()) { index -> parseSearchResultItem(results.getJSONObject(index)) }
        )
    }

    fun fetchSearchPostDetail(postUrl: String): SearchResultItem {
        require(config.accountId.isNotBlank()) { "请先完成登录" }
        require(postUrl.isNotBlank()) { "帖子链接为空" }
        val body = JSONObject()
            .put("account_id", config.accountId)
            .put("post_url", postUrl.trim())
        val response = JSONObject(request("POST", "/api/app/search-post-detail", body))
        return parseSearchResultItem(response.getJSONObject("detail"))
    }

    fun fetchSearchPostDetail(item: SearchResultItem): SearchResultItem {
        require(config.accountId.isNotBlank()) { "请先完成登录" }
        require(item.postUrl.isNotBlank()) { "帖子链接为空" }
        val body = JSONObject()
            .put("account_id", config.accountId)
            .put("post_url", item.postUrl.trim())
            .put("worker_cookie_id", item.workerCookieId)
        val response = JSONObject(request("POST", "/api/app/search-post-detail", body))
        return parseSearchResultItem(response.getJSONObject("detail"))
    }

    fun listSearchTasks(): List<SearchTaskSummary> {
        val response = JSONObject(request("GET", "/api/app/search-tasks"))
        val tasks = response.optJSONArray("tasks") ?: JSONArray()
        return List(tasks.length()) { index ->
            val task = tasks.getJSONObject(index)
            SearchTaskSummary(
                taskId = task.optString("id"),
                keyword = task.optString("keyword"),
                status = task.optString("task_status"),
                postCount = task.optInt("post_count"),
                requireNum = task.optInt("require_num"),
                rawJson = task.toString(2)
            )
        }
    }

    fun fetchSearchTaskDetail(taskId: String): SearchTaskDetail {
        require(taskId.isNotBlank()) { "任务 ID 为空" }
        val response = JSONObject(request("GET", "/api/app/search-tasks/$taskId"))
        val task = response.getJSONObject("task")
        val results = response.optJSONArray("results") ?: JSONArray()
        return SearchTaskDetail(
            taskId = task.optString("id"),
            keyword = task.optString("keyword"),
            postCount = response.optInt("post_count"),
            results = List(results.length()) { index -> parseSearchResultItem(results.getJSONObject(index)) }
        )
    }

    fun fetchNextTask(): AppTask? {
        val query = mapOf(
            "device_id" to config.deviceId,
            "app_instance_id" to config.appInstanceId,
            "app_version" to config.appVersion,
            "device_name" to config.deviceName
        ).toQueryString()
        val response = JSONObject(request("GET", "/api/app/tasks/next?$query"))
        if (response.isNull("task")) return null

        val taskType = response.optString("task_type")
        val task = response.getJSONObject("task")
        val taskId = task.optString("id")
        val title = when (taskType) {
            "publish" -> task.optString("title", taskId)
            "search" -> task.optString("keyword", taskId)
            "analytics" -> task.optString("account_id", taskId)
            else -> taskId
        }
        return AppTask(taskType = taskType, taskId = taskId, title = title, rawJson = task.toString(2))
    }

    fun fetchNextPublishTask(): AppTask? {
        val query = mapOf(
            "device_id" to config.deviceId,
            "app_instance_id" to config.appInstanceId,
            "app_version" to config.appVersion,
            "device_name" to config.deviceName
        ).toQueryString()
        val response = JSONObject(request("GET", "/api/app/publish-tasks/next?$query"))
        if (response.isNull("task")) return null
        val task = response.getJSONObject("task")
        val taskId = task.optString("id")
        return AppTask(
            taskType = "publish",
            taskId = taskId,
            title = task.optString("title", taskId),
            rawJson = task.toString(2)
        )
    }

    fun executePublishTask(task: AppTask): String {
        require(task.taskType == "publish") { "当前任务不是发帖任务" }
        val body = JSONObject()
            .put("device_id", config.deviceId)
            .put("app_instance_id", config.appInstanceId)
        val response = JSONObject(
            request(
                method = "POST",
                path = "/api/app/publish-tasks/${task.taskId}/execute",
                body = body,
                readTimeoutMillis = 180000,
            )
        )
        val taskJson = response.getJSONObject("task")
        val taskStatus = taskJson.optString("task_status")
        val postId = taskJson.optString("published_post_id")
        return if (taskStatus == "success") {
            if (postId.isBlank()) "发帖成功：${task.taskId}" else "发帖成功：$postId"
        } else {
            throw IllegalStateException(taskJson.optString("last_error").ifBlank { "发布失败" })
        }
    }

    private fun request(
        method: String,
        path: String,
        body: JSONObject? = null,
        connectTimeoutMillis: Int = 8000,
        readTimeoutMillis: Int = 12000,
    ): String {
        val url = URL("${config.baseUrl.trimEnd('/')}$path")
        val connection = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = connectTimeoutMillis
            readTimeout = readTimeoutMillis
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Accept", "application/json")
            if (body != null) {
                doOutput = true
            }
        }
        if (body != null) {
            OutputStreamWriter(connection.outputStream, Charsets.UTF_8).use { writer ->
                writer.write(body.toString())
            }
        }

        val responseCode = connection.responseCode
        val stream = if (responseCode in 200..299) connection.inputStream else connection.errorStream
        val response = BufferedReader(InputStreamReader(stream, Charsets.UTF_8)).use { reader ->
            reader.readText()
        }
        connection.disconnect()
        if (responseCode !in 200..299) {
            val detail = runCatching {
                JSONObject(response).optString("detail").ifBlank { response }
            }.getOrElse { response }
            if (responseCode == 401 || isSessionExpiredMessage(detail)) {
                throw SessionExpiredException(detail.ifBlank { "登录已失效，请重新登录" })
            }
            throw IllegalStateException("HTTP $responseCode: ${detail.ifBlank { response }}")
        }
        return response
    }

    private fun isSessionExpiredMessage(message: String): Boolean {
        val lowered = message.lowercase()
        return "登录已失效" in message ||
            "重新登录" in message ||
            "cookie" in lowered && ("失效" in message || "invalid" in lowered || "expired" in lowered)
    }

    private fun Map<String, String>.toQueryString(): String {
        return entries.joinToString("&") { (key, value) ->
            "${key.urlEncode()}=${value.urlEncode()}"
        }
    }

    private fun String.urlEncode(): String = URLEncoder.encode(this, "UTF-8")
}
