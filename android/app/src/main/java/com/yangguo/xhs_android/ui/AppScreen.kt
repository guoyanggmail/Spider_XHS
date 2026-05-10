package com.yangguo.xhs_android.ui

import android.os.Handler
import android.os.Looper
import androidx.annotation.StringRes
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import com.yangguo.xhs_android.R
import com.yangguo.xhs_android.data.AppConfigStore
import com.yangguo.xhs_android.data.AppStatus
import com.yangguo.xhs_android.data.AppTask
import com.yangguo.xhs_android.data.BackendClient
import com.yangguo.xhs_android.data.PublishReportDraft
import com.yangguo.xhs_android.data.SearchResultItem
import kotlin.concurrent.thread

@Composable
fun AppScreen(configStore: AppConfigStore) {
    val context = LocalContext.current
    val mainHandler = remember { Handler(Looper.getMainLooper()) }
    var config by remember { mutableStateOf(configStore.load()) }
    var baseUrl by remember { mutableStateOf(config.baseUrl) }
    var phone by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var keyword by remember { mutableStateOf("") }
    var requireNumText by remember { mutableStateOf("20") }
    var publishDraft by remember { mutableStateOf(PublishReportDraft()) }
    var status by remember { mutableStateOf(AppStatus(message = context.getString(R.string.status_idle))) }
    var currentTab by remember { mutableStateOf(HomeTab.PUBLISH) }
    var selectedSearchItem by remember { mutableStateOf<SearchResultItem?>(null) }

    fun text(@StringRes id: Int, vararg args: Any): String = context.getString(id, *args)

    fun ensureLoginReady(): Boolean {
        if (config.accountId.isBlank()) {
            status = status.copy(message = text(R.string.error_login_first))
            return false
        }
        if (status.requiresRelogin) {
            status = status.copy(message = text(R.string.error_cookie_invalid))
            return false
        }
        return true
    }

    fun runAction(successMessage: String? = null, block: () -> Unit) {
        status = status.copy(isLoading = true)
        thread {
            val result = runCatching(block)
            mainHandler.post {
                status = status.copy(
                    message = result.exceptionOrNull()?.message ?: successMessage ?: context.getString(R.string.status_idle),
                    isLoading = false
                )
            }
        }
    }

    fun runTaskAction(block: () -> AppTask?) {
        if (!ensureLoginReady()) return
        status = status.copy(isLoading = true)
        thread {
            val result = runCatching(block)
            mainHandler.post {
                val task = result.getOrNull()
                if (task != null && task.taskType == "publish") {
                    publishDraft = publishDraft.copy(status = "published", postId = "", postUrl = "", errorMessage = "")
                }
                status = status.copy(
                    message = result.exceptionOrNull()?.message ?: if (task == null) text(R.string.status_no_task) else text(R.string.status_task_claimed, task.taskType),
                    latestTask = task,
                    isLoading = false
                )
            }
        }
    }

    fun runSearchListAction() {
        if (!ensureLoginReady()) return
        status = status.copy(isLoading = true)
        selectedSearchItem = null
        thread {
            val result = runCatching { BackendClient(config).listSearchTasks() }
            mainHandler.post {
                status = status.copy(
                    message = result.exceptionOrNull()?.message ?: text(R.string.status_loading_search_task),
                    searchTasks = result.getOrDefault(emptyList()),
                    isLoading = false
                )
            }
        }
    }

    fun runSearchDetailAction(taskId: String) {
        if (!ensureLoginReady()) return
        status = status.copy(isLoading = true)
        selectedSearchItem = null
        thread {
            val result = runCatching { BackendClient(config).fetchSearchTaskDetail(taskId) }
            mainHandler.post {
                status = status.copy(
                    message = result.exceptionOrNull()?.message ?: text(R.string.status_loading_task_detail),
                    searchTaskDetail = result.getOrNull(),
                    isLoading = false
                )
            }
        }
    }

    fun runDirectSearchAction() {
        if (!ensureLoginReady()) return
        status = status.copy(isLoading = true)
        selectedSearchItem = null
        thread {
            val result = runCatching {
                BackendClient(config).searchPreview(
                    keyword = keyword,
                    requireNum = requireNumText.toIntOrNull() ?: 20
                )
            }
            mainHandler.post {
                status = status.copy(
                    message = result.exceptionOrNull()?.message ?: text(R.string.status_search_result),
                    searchTaskDetail = result.getOrNull(),
                    isLoading = false
                )
            }
        }
    }

    fun runSearchPostDetailAction(item: SearchResultItem) {
        if (!ensureLoginReady()) return
        status = status.copy(isLoading = true)
        thread {
            val result = runCatching {
                if (item.postUrl.isBlank()) item else BackendClient(config).fetchSearchPostDetail(item.postUrl)
            }
            mainHandler.post {
                selectedSearchItem = result.getOrNull()
                status = status.copy(
                    message = result.exceptionOrNull()?.message ?: text(R.string.status_loading_post_detail),
                    isLoading = false
                )
            }
        }
    }

    fun runAccountSummaryAction() {
        if (!ensureLoginReady()) return
        status = status.copy(isLoading = true)
        thread {
            val result = runCatching { BackendClient(config).fetchAccountSummary() }
            mainHandler.post {
                status = status.copy(
                    message = result.exceptionOrNull()?.message ?: text(R.string.status_loading_account),
                    accountSummary = result.getOrNull(),
                    isLoading = false
                )
            }
        }
    }

    fun runAccountCheckAction(silent: Boolean = false) {
        if (!silent) {
            status = status.copy(isLoading = true)
        }
        thread {
            val result = runCatching { BackendClient(config).checkAccountStatus() }
            mainHandler.post {
                val check = result.getOrNull()
                if (check != null) {
                    val invalid = !check.success || check.account.status == "invalid"
                    if (invalid) {
                        config = configStore.clearLoginState()
                    }
                    status = status.copy(
                        message = if (invalid) text(R.string.status_login_expired) else text(R.string.status_account_valid),
                        accountSummary = check.account,
                        requiresRelogin = invalid,
                        smsCodeSession = if (invalid) null else status.smsCodeSession,
                        isLoading = false
                    )
                } else {
                    status = status.copy(
                        message = result.exceptionOrNull()?.message ?: text(R.string.section_status),
                        isLoading = false
                    )
                }
            }
        }
    }

    fun runRequestSmsCodeAction() {
        status = status.copy(isLoading = true)
        thread {
            val result = runCatching { BackendClient(config).requestSmsCode(phone) }
            mainHandler.post {
                val session = result.getOrNull()
                status = status.copy(
                    message = result.exceptionOrNull()?.message ?: text(R.string.status_code_sent),
                    smsCodeSession = session,
                    isLoading = false
                )
            }
        }
    }

    fun runCreateSearchTaskAction() {
        if (!ensureLoginReady()) return
        status = status.copy(isLoading = true)
        thread {
            val result = runCatching {
                BackendClient(config).createSearchTask(keyword = keyword, requireNum = requireNumText.toIntOrNull() ?: 20)
            }
            val listResult = if (result.isSuccess) runCatching { BackendClient(config).listSearchTasks() } else null
            mainHandler.post {
                if (result.isSuccess) {
                    keyword = ""
                }
                status = status.copy(
                    message = result.exceptionOrNull()?.message ?: result.getOrNull() ?: text(R.string.section_search_form),
                    searchTasks = listResult?.getOrDefault(status.searchTasks) ?: status.searchTasks,
                    isLoading = false
                )
            }
        }
    }

    fun runLoginWithSmsAction() {
        status = status.copy(isLoading = true)
        thread {
            val result = runCatching {
                BackendClient(config).loginWithSmsCode(
                    phone = phone,
                    code = code,
                    loginSessionId = status.smsCodeSession?.loginSessionId.orEmpty()
                )
            }
            mainHandler.post {
                val loginResult = result.getOrNull()
                if (loginResult != null) {
                    val (summary, cookies) = loginResult
                    config = configStore.saveLoginState(summary.accountId, cookies)
                    currentTab = HomeTab.PUBLISH
                    status = status.copy(
                        message = text(R.string.status_login_success),
                        accountSummary = summary,
                        requiresRelogin = false,
                        smsCodeSession = null,
                        isLoading = false
                    )
                } else {
                    status = status.copy(
                        message = result.exceptionOrNull()?.message ?: text(R.string.page_login),
                        isLoading = false
                    )
                }
            }
        }
    }

    fun runPublishResultAction() {
        val task = status.latestTask ?: return
        runAction(successMessage = text(R.string.status_publish_reported, task.taskId)) {
            BackendClient(config).reportPublishResult(
                task = task,
                status = publishDraft.status,
                postId = publishDraft.postId,
                postUrl = publishDraft.postUrl,
                errorMessage = publishDraft.errorMessage
            )
        }
    }

    LaunchedEffect(config.accountId) {
        if (config.accountId.isNotBlank() && status.accountSummary == null) {
            runAccountCheckAction(silent = true)
        }
    }

    val isLoggedIn = config.accountId.isNotBlank() && !status.requiresRelogin

    if (!isLoggedIn) {
        LoginScreen(
            baseUrl = baseUrl,
            phone = phone,
            code = code,
            smsCodeHint = status.smsCodeSession?.let { text(R.string.sms_session_hint, it.expiresInSeconds) }.orEmpty(),
            requiresRelogin = status.requiresRelogin,
            status = status,
            onBaseUrlChange = { baseUrl = it },
            onPhoneChange = { phone = it.filter(Char::isDigit).take(11) },
            onCodeChange = { code = it.filter(Char::isDigit).take(6) },
            onSaveBaseUrl = {
                config = configStore.save(baseUrl, config.accountId)
                status = status.copy(message = text(R.string.status_config_saved))
            },
            onRequestCode = { runRequestSmsCodeAction() },
            onLogin = { runLoginWithSmsAction() }
        )
        return
    }

    if (currentTab == HomeTab.SEARCH && selectedSearchItem != null) {
        SearchDetailScreen(
            item = selectedSearchItem!!,
            status = status,
            onBack = { selectedSearchItem = null }
        )
        return
    }

    HomeScreen(
        currentTab = currentTab,
        status = status,
        onTabChange = { currentTab = it }
    ) {
        when (currentTab) {
            HomeTab.PUBLISH -> PublishModule(
                latestTask = status.latestTask,
                draft = publishDraft,
                onFetchTask = { runTaskAction { BackendClient(config).fetchNextTask() } },
                onDraftChange = { publishDraft = it },
                onReportResult = { runPublishResultAction() },
                onReportMockResult = {
                    status.latestTask?.let { task ->
                        runAction(successMessage = text(R.string.status_task_reported, task.taskType, task.taskId)) {
                            BackendClient(config).reportMockResult(task)
                        }
                    }
                },
            )
            HomeTab.SEARCH -> SearchModule(
                keyword = keyword,
                requireNumText = requireNumText,
                tasks = status.searchTasks,
                detail = status.searchTaskDetail,
                onKeywordChange = { keyword = it },
                onRequireNumChange = { requireNumText = it.filter(Char::isDigit).take(3) },
                onDirectSearch = { runDirectSearchAction() },
                onCreateTask = { runCreateSearchTaskAction() },
                onLoadTasks = { runSearchListAction() },
                onOpenTask = { runSearchDetailAction(it) },
                onOpenItem = { runSearchPostDetailAction(it) }
            )
            HomeTab.PROFILE -> ProfileModule(
                config = config,
                accountSummary = status.accountSummary,
                requiresRelogin = status.requiresRelogin,
                baseUrl = baseUrl,
                onBaseUrlChange = { baseUrl = it },
                onSaveBaseUrl = {
                    config = configStore.save(baseUrl, config.accountId)
                    status = status.copy(message = text(R.string.status_config_saved))
                },
                onLoadSummary = { runAccountSummaryAction() },
                onCheckStatus = { runAccountCheckAction() },
                onLogout = {
                    config = configStore.clearLoginState()
                    status = status.copy(
                        message = text(R.string.status_logged_out),
                        accountSummary = null,
                        smsCodeSession = null,
                        requiresRelogin = false,
                        latestTask = null,
                        searchTaskDetail = null
                    )
                    selectedSearchItem = null
                },
                onLanguageChange = { languageCode ->
                    config = configStore.saveLanguage(languageCode)
                    status = status.copy(message = text(R.string.status_config_saved))
                }
            )
        }
    }
}
