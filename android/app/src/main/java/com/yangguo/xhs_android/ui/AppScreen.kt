package com.yangguo.xhs_android.ui

import android.os.Handler
import android.os.Looper
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.yangguo.xhs_android.data.AppConfig
import com.yangguo.xhs_android.data.AppConfigStore
import com.yangguo.xhs_android.data.AppStatus
import com.yangguo.xhs_android.data.AppTask
import com.yangguo.xhs_android.data.BackendClient
import com.yangguo.xhs_android.xhs.XhsAutomation
import kotlin.concurrent.thread

@Composable
fun AppScreen(configStore: AppConfigStore) {
    val context = LocalContext.current
    val mainHandler = remember { Handler(Looper.getMainLooper()) }
    var config by remember { mutableStateOf(configStore.load()) }
    var baseUrl by remember { mutableStateOf(config.baseUrl) }
    var accountId by remember { mutableStateOf(config.accountId) }
    var cookie by remember { mutableStateOf("") }
    var status by remember { mutableStateOf(AppStatus()) }

    fun runAction(block: () -> String) {
        status = status.copy(isLoading = true)
        thread {
            val result = runCatching(block)
            mainHandler.post {
                status = status.copy(
                    message = result.getOrNull() ?: result.exceptionOrNull()?.message ?: "操作失败",
                    isLoading = false
                )
            }
        }
    }

    fun runTaskAction(block: () -> AppTask?) {
        status = status.copy(isLoading = true)
        thread {
            val result = runCatching(block)
            mainHandler.post {
                val task = result.getOrNull()
                status = AppStatus(
                    message = result.exceptionOrNull()?.message ?: if (task == null) "暂无可领取任务" else "已领取任务：${task.taskType}",
                    latestTask = task,
                    isLoading = false
                )
            }
        }
    }

    Scaffold { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(20.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Text("XHS Android 执行端", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text("先完成后台连接、任务拉取和结果回传。真实小红书 UI 操作会接到执行器里。")

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("后台配置", fontWeight = FontWeight.Bold)
                    OutlinedTextField(
                        value = baseUrl,
                        onValueChange = { baseUrl = it },
                        label = { Text("后台地址") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = accountId,
                        onValueChange = { accountId = it },
                        label = { Text("主账号 ID") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    Button(onClick = {
                        config = configStore.save(baseUrl, accountId)
                        status = status.copy(message = "配置已保存")
                    }) {
                        Text("保存配置")
                    }
                }
            }

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("设备信息", fontWeight = FontWeight.Bold)
                    Text("device_id: ${config.deviceId}")
                    Text("app_instance_id: ${config.appInstanceId}")
                    Text("device_name: ${config.deviceName}")
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Button(onClick = { runAction { BackendClient(config).heartbeat() } }) {
                            Text("上报心跳")
                        }
                        Button(onClick = {
                            val opened = XhsAutomation(context).openXhsApp()
                            status = status.copy(message = if (opened) "已打开小红书" else "未安装小红书")
                        }) {
                            Text("打开小红书")
                        }
                    }
                }
            }

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("主 Cookie 同步", fontWeight = FontWeight.Bold)
                    OutlinedTextField(
                        value = cookie,
                        onValueChange = { cookie = it },
                        label = { Text("主 Cookie") },
                        modifier = Modifier.fillMaxWidth(),
                        minLines = 3
                    )
                    Button(onClick = {
                        runAction {
                            BackendClient(config).syncPrimaryCookie(cookie)
                        }
                    }) {
                        Text("同步主 Cookie")
                    }
                }
            }

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("任务调试", fontWeight = FontWeight.Bold)
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Button(onClick = { runTaskAction { BackendClient(config).fetchNextTask() } }) {
                            Text("拉取任务")
                        }
                        Button(
                            enabled = status.latestTask != null,
                            onClick = {
                                val task = status.latestTask ?: return@Button
                                runAction { BackendClient(config).reportMockResult(task) }
                            }
                        ) {
                            Text("回传模拟结果")
                        }
                    }
                    status.latestTask?.let { TaskPanel(it) }
                }
            }

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("状态", fontWeight = FontWeight.Bold)
                    if (status.isLoading) {
                        CircularProgressIndicator()
                    }
                    Text(status.message)
                }
            }

            Spacer(modifier = Modifier.height(24.dp))
        }
    }
}

@Composable
private fun TaskPanel(task: AppTask) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("任务类型：${task.taskType}")
        Text("任务 ID：${task.taskId}")
        Text("标题：${task.title}")
        Text(task.rawJson, style = MaterialTheme.typography.bodySmall)
    }
}
