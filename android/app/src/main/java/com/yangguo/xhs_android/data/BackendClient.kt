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
            publishTime = item.optString("publish_time")
        )
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
        val response = JSONObject(request("POST", "/api/app/auth/login-with-sms", body))
        val account = response.getJSONObject("account_summary")
        return AccountSummary(
            accountId = account.optString("id"),
            name = account.optString("name"),
            nickname = account.optString("nickname"),
            status = account.optString("status"),
            cookiePreview = account.optString("cookie_preview"),
            failureCount = account.optInt("failure_count"),
            remark = account.optString("remark")
        ) to response.optString("cookies")
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
        return AccountSummary(
            accountId = account.optString("id"),
            name = account.optString("name"),
            nickname = account.optString("nickname"),
            status = account.optString("status"),
            cookiePreview = account.optString("cookie_preview"),
            failureCount = account.optInt("failure_count"),
            remark = account.optString("remark")
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

    fun reportMockResult(task: AppTask): String {
        val body = when (task.taskType) {
            "publish" -> publishResult(task)
            "search" -> searchResult(task)
            "analytics" -> analyticsResult(task)
            else -> error("未知任务类型：${task.taskType}")
        }
        request("POST", "/api/app/tasks/${task.taskType}/${task.taskId}/result", body)
        return "任务结果已回传：${task.taskType}/${task.taskId}"
    }

    fun reportPublishResult(
        task: AppTask,
        status: String,
        postId: String,
        postUrl: String,
        errorMessage: String,
    ): String {
        require(task.taskType == "publish") { "当前任务不是发帖任务" }
        val body = baseResult(status)
            .put("post_id", postId.trim())
            .put("post_url", postUrl.trim())
            .put("error_message", errorMessage.trim())
        request("POST", "/api/app/tasks/${task.taskType}/${task.taskId}/result", body)
        return "发帖结果已回传：${task.taskId}"
    }

    private fun publishResult(task: AppTask): JSONObject {
        return baseResult("published")
            .put("post_id", "mock-${task.taskId}")
            .put("post_url", "https://www.xiaohongshu.com/explore/mock-${task.taskId}")
    }

    private fun searchResult(task: AppTask): JSONObject {
        return baseResult("success")
            .put("worker_cookie_id", JSONObject(task.rawJson).optString("worker_cookie_id"))
            .put("partial_success", false)
            .put("items", org.json.JSONArray())
    }

    private fun analyticsResult(task: AppTask): JSONObject {
        val accountId = JSONObject(task.rawJson).optString("account_id", config.accountId)
        val snapshot = JSONObject()
            .put("account_id", accountId)
            .put("nickname", "")
            .put("follower_count", 0)
            .put("liked_count", 0)
            .put("post_count", 0)
            .put("collected_total", 0)
            .put("posts", org.json.JSONArray())
        return baseResult("success")
            .put("worker_cookie_id", JSONObject(task.rawJson).optString("worker_cookie_id"))
            .put("snapshot", snapshot)
    }

    private fun baseResult(status: String): JSONObject {
        return JSONObject()
            .put("device_id", config.deviceId)
            .put("app_instance_id", config.appInstanceId)
            .put("result_id", "${System.currentTimeMillis()}-${config.appInstanceId.take(8)}")
            .put("status", status)
            .put("error_message", "")
            .put("duration_seconds", 0)
    }

    private fun request(method: String, path: String, body: JSONObject? = null): String {
        val url = URL("${config.baseUrl.trimEnd('/')}$path")
        val connection = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 8000
            readTimeout = 12000
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
            throw IllegalStateException("HTTP $responseCode: $response")
        }
        return response
    }

    private fun Map<String, String>.toQueryString(): String {
        return entries.joinToString("&") { (key, value) ->
            "${key.urlEncode()}=${value.urlEncode()}"
        }
    }

    private fun String.urlEncode(): String = URLEncoder.encode(this, "UTF-8")
}
