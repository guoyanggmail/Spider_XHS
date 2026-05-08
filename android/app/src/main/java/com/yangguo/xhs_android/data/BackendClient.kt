package com.yangguo.xhs_android.data

import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URLEncoder
import java.net.URL

class BackendClient(private val config: AppConfig) {
    fun heartbeat(): String {
        val body = JSONObject()
            .put("device_id", config.deviceId)
            .put("app_instance_id", config.appInstanceId)
            .put("app_version", config.appVersion)
            .put("device_name", config.deviceName)
        request("POST", "/api/app/heartbeat", body)
        return "设备心跳已上报"
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
