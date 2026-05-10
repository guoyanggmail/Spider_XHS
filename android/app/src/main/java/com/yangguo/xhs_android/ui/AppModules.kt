package com.yangguo.xhs_android.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.unit.dp
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import coil.compose.AsyncImage
import com.yangguo.xhs_android.R
import com.yangguo.xhs_android.data.AccountSummary
import com.yangguo.xhs_android.data.AppConfig
import com.yangguo.xhs_android.data.AppStatus
import com.yangguo.xhs_android.data.AppTask
import com.yangguo.xhs_android.data.PublishReportDraft
import com.yangguo.xhs_android.data.SearchTaskDetail
import com.yangguo.xhs_android.data.SearchResultItem
import com.yangguo.xhs_android.data.SearchTaskSummary
import com.yangguo.xhs_android.ui.theme.BorderSoft
import com.yangguo.xhs_android.ui.theme.BrandRed
import com.yangguo.xhs_android.ui.theme.TextSecondary
import com.yangguo.xhs_android.ui.theme.WarmBackground
import com.yangguo.xhs_android.ui.theme.WarmSurface
import com.yangguo.xhs_android.ui.theme.WarmSurfaceAlt

enum class HomeTab(val titleRes: Int, val shortLabel: String) {
    PUBLISH(R.string.tab_publish, "P"),
    SEARCH(R.string.tab_search, "S"),
    PROFILE(R.string.tab_profile, "M"),
}

@Composable
private fun AppCard(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = WarmSurface),
        elevation = CardDefaults.cardElevation(defaultElevation = 3.dp),
        shape = RoundedCornerShape(24.dp)
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            content = content
        )
    }
}

@Composable
private fun PrimaryButton(text: String, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = BrandRed,
            contentColor = WarmSurface,
            disabledContainerColor = BrandRed.copy(alpha = 0.35f)
        )
    ) {
        Text(text)
    }
}

@Composable
private fun SecondaryButton(text: String, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = WarmSurfaceAlt,
            contentColor = MaterialTheme.colorScheme.onSurface,
            disabledContainerColor = WarmSurfaceAlt.copy(alpha = 0.5f)
        )
    ) {
        Text(text)
    }
}

@Composable
private fun AppTextField(
    value: String,
    onValueChange: (String) -> Unit,
    labelRes: Int,
    singleLine: Boolean = true,
    minLines: Int = 1,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(stringResource(labelRes)) },
        modifier = Modifier.fillMaxWidth(),
        singleLine = singleLine,
        minLines = minLines,
        shape = RoundedCornerShape(18.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedContainerColor = WarmSurface,
            unfocusedContainerColor = WarmSurface,
            focusedBorderColor = BrandRed,
            unfocusedBorderColor = BorderSoft,
            cursorColor = BrandRed
        )
    )
}

@Composable
fun LoginScreen(
    baseUrl: String,
    phone: String,
    code: String,
    smsCodeHint: String,
    requiresRelogin: Boolean,
    status: AppStatus,
    onBaseUrlChange: (String) -> Unit,
    onPhoneChange: (String) -> Unit,
    onCodeChange: (String) -> Unit,
    onSaveBaseUrl: () -> Unit,
    onRequestCode: () -> Unit,
    onLogin: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(WarmBackground)
            .padding(20.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.brand_title), style = MaterialTheme.typography.headlineLarge)
            Text(
                stringResource(R.string.brand_subtitle),
                style = MaterialTheme.typography.bodyLarge,
                color = TextSecondary
            )
        }
        AppCard {
            Text(stringResource(R.string.page_login), style = MaterialTheme.typography.titleLarge)
            Text(
                stringResource(R.string.login_intro),
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondary
            )
            AppTextField(
                value = phone,
                onValueChange = onPhoneChange,
                labelRes = R.string.phone_label
            )
            AppTextField(
                value = code,
                onValueChange = onCodeChange,
                labelRes = R.string.code_label
            )
            if (smsCodeHint.isNotBlank()) {
                Text(smsCodeHint, style = MaterialTheme.typography.bodySmall, color = TextSecondary)
            }
            if (requiresRelogin) {
                Text(stringResource(R.string.login_invalid_hint), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                SecondaryButton(
                    text = stringResource(R.string.request_code),
                    onClick = onRequestCode,
                    modifier = Modifier.weight(1f)
                )
                PrimaryButton(
                    text = stringResource(R.string.login_action),
                    onClick = onLogin,
                    modifier = Modifier.weight(1f)
                )
            }
        }
        AppCard {
            Text(stringResource(R.string.section_connection), style = MaterialTheme.typography.titleMedium)
            AppTextField(
                value = baseUrl,
                onValueChange = onBaseUrlChange,
                labelRes = R.string.backend_url_label
            )
            SecondaryButton(
                text = stringResource(R.string.save_address),
                onClick = onSaveBaseUrl
            )
        }
        StatusPanel(status = status)
    }
}

@Composable
fun HomeScreen(
    currentTab: HomeTab,
    status: AppStatus,
    onTabChange: (HomeTab) -> Unit,
    content: @Composable () -> Unit,
) {
    Scaffold(
        containerColor = WarmBackground,
        bottomBar = {
            NavigationBar(containerColor = WarmSurface) {
                HomeTab.entries.forEach { tab ->
                    NavigationBarItem(
                        selected = currentTab == tab,
                        onClick = { onTabChange(tab) },
                        icon = {
                            Box(
                                modifier = Modifier
                                    .size(28.dp)
                                    .background(
                                        color = if (currentTab == tab) BrandRed.copy(alpha = 0.14f) else WarmSurfaceAlt,
                                        shape = CircleShape
                                    ),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    tab.shortLabel,
                                    color = if (currentTab == tab) BrandRed else TextSecondary,
                                    style = MaterialTheme.typography.labelMedium
                                )
                            }
                        },
                        label = {
                            Text(
                                stringResource(tab.titleRes),
                                color = if (currentTab == tab) BrandRed else TextSecondary
                            )
                        }
                    )
                }
            }
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .background(WarmBackground)
                .padding(20.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            content()
            StatusPanel(status = status)
        }
    }
}

@Composable
fun SearchModule(
    keyword: String,
    requireNumText: String,
    tasks: List<SearchTaskSummary>,
    detail: SearchTaskDetail?,
    onKeywordChange: (String) -> Unit,
    onRequireNumChange: (String) -> Unit,
    onDirectSearch: () -> Unit,
    onCreateTask: () -> Unit,
    onLoadTasks: () -> Unit,
    onOpenTask: (String) -> Unit,
    onOpenItem: (SearchResultItem) -> Unit,
) {
    Text(stringResource(R.string.search_page_title), style = MaterialTheme.typography.headlineSmall)
    AppCard {
        Text(stringResource(R.string.section_search_form), style = MaterialTheme.typography.titleMedium)
        AppTextField(keyword, onKeywordChange, R.string.keyword_label)
        AppTextField(requireNumText, onRequireNumChange, R.string.post_count_label)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            PrimaryButton(stringResource(R.string.search_now), onDirectSearch, modifier = Modifier.weight(1f))
            SecondaryButton(stringResource(R.string.create_task), onCreateTask, modifier = Modifier.weight(1f))
        }
        SecondaryButton(stringResource(R.string.refresh_task), onLoadTasks)
    }
    if (tasks.isNotEmpty()) {
        AppCard {
            Text(stringResource(R.string.section_task_list), style = MaterialTheme.typography.titleMedium)
            tasks.forEach { task ->
                SecondaryButton(
                    text = stringResource(R.string.task_item_summary, task.keyword, task.requireNum, task.postCount),
                    onClick = { onOpenTask(task.taskId) },
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }
    }
    detail?.let { taskDetail ->
        AppCard {
            Text(
                stringResource(if (taskDetail.taskId.isBlank()) R.string.section_search_result else R.string.section_task_detail),
                style = MaterialTheme.typography.titleMedium
            )
            Text(
                stringResource(R.string.detail_count_summary, taskDetail.keyword, taskDetail.postCount),
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondary
            )
            taskDetail.results.forEach { item ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = WarmSurfaceAlt),
                    shape = RoundedCornerShape(20.dp)
                ) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(item.title.ifBlank { item.postId }, style = MaterialTheme.typography.titleMedium)
                        Text(
                            stringResource(R.string.author_name, item.authorName.ifBlank { stringResource(R.string.empty_author) }),
                            style = MaterialTheme.typography.bodySmall,
                            color = TextSecondary
                        )
                        Text(
                            stringResource(R.string.engagement_summary, item.likeCount, item.commentCount, item.collectCount),
                            style = MaterialTheme.typography.bodySmall,
                            color = TextSecondary
                        )
                        if (item.contentPreview.isNotBlank()) {
                            Text(item.contentPreview, style = MaterialTheme.typography.bodyMedium)
                        }
                        SecondaryButton(
                            text = stringResource(R.string.view_post_detail),
                            onClick = { onOpenItem(item) }
                        )
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SearchDetailScreen(
    item: SearchResultItem,
    status: AppStatus,
    onBack: () -> Unit,
) {
    Scaffold(
        containerColor = WarmBackground,
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.section_post_detail)) },
                navigationIcon = {
                    SecondaryButton(
                        text = stringResource(R.string.back_to_results),
                        onClick = onBack,
                        modifier = Modifier.padding(start = 12.dp)
                    )
                }
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .background(WarmBackground)
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            AppCard {
                Text(item.title.ifBlank { item.postId }, style = MaterialTheme.typography.headlineSmall)
                Text(
                    stringResource(R.string.author_name, item.authorName.ifBlank { stringResource(R.string.empty_author) }),
                    style = MaterialTheme.typography.bodySmall,
                    color = TextSecondary
                )
                if (item.noteType.isNotBlank()) {
                    Text(stringResource(R.string.note_type_value, item.noteType), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                }
                if (item.publishTime.isNotBlank()) {
                    Text(stringResource(R.string.publish_time_value, item.publishTime), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                }
                Text(
                    stringResource(R.string.engagement_summary, item.likeCount, item.commentCount, item.collectCount),
                    style = MaterialTheme.typography.bodySmall,
                    color = TextSecondary
                )
                if (item.content.isNotBlank()) {
                    Text(stringResource(R.string.post_content_label), style = MaterialTheme.typography.labelLarge)
                    Text(item.content, style = MaterialTheme.typography.bodyLarge)
                }
                if (item.topics.isNotEmpty()) {
                    Text(stringResource(R.string.post_topics_label), style = MaterialTheme.typography.labelLarge)
                    Text(item.topics.joinToString(" ") { "#$it" }, style = MaterialTheme.typography.bodyMedium, color = BrandRed)
                }
            }
            if (item.imageUrls.isNotEmpty()) {
                AppCard {
                    Text(stringResource(R.string.post_images_label), style = MaterialTheme.typography.titleMedium)
                    item.imageUrls.forEach { imageUrl ->
                        AsyncImage(
                            model = imageUrl,
                            contentDescription = null,
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(240.dp),
                            contentScale = ContentScale.Crop
                        )
                    }
                }
            }
            if (item.videoUrl.isNotBlank()) {
                AppCard {
                    Text(stringResource(R.string.post_video_label), style = MaterialTheme.typography.titleMedium)
                    VideoPlayer(url = item.videoUrl)
                    if (item.videoCoverUrl.isNotBlank()) {
                        Text(stringResource(R.string.video_cover_value, item.videoCoverUrl), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                    }
                }
            }
            if (item.postUrl.isNotBlank()) {
                AppCard {
                    Text(stringResource(R.string.post_url_value, item.postUrl), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                }
            }
            StatusPanel(status = status)
        }
    }
}

@Composable
private fun VideoPlayer(url: String) {
    val context = LocalContext.current
    val player = remember(url) {
        ExoPlayer.Builder(context).build().apply {
            setMediaItem(MediaItem.fromUri(url))
            prepare()
        }
    }
    DisposableEffect(player) {
        onDispose { player.release() }
    }
    AndroidView(
        factory = {
            PlayerView(it).apply {
                this.player = player
                useController = true
            }
        },
        modifier = Modifier
            .fillMaxWidth()
            .height(240.dp)
    )
}

@Composable
fun PublishModule(
    latestTask: AppTask?,
    draft: PublishReportDraft,
    onFetchTask: () -> Unit,
    onDraftChange: (PublishReportDraft) -> Unit,
    onReportResult: () -> Unit,
    onReportMockResult: () -> Unit,
) {
    Text(stringResource(R.string.publish_page_title), style = MaterialTheme.typography.headlineSmall)
    AppCard {
        Text(stringResource(R.string.section_publish_task), style = MaterialTheme.typography.titleMedium)
        Text(stringResource(R.string.publish_intro), style = MaterialTheme.typography.bodyMedium, color = TextSecondary)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            PrimaryButton(
                text = stringResource(R.string.fetch_task),
                onClick = onFetchTask,
                modifier = Modifier.weight(1f)
            )
            SecondaryButton(
                text = stringResource(R.string.report_result),
                onClick = onReportResult,
                enabled = latestTask != null,
                modifier = Modifier.weight(1f)
            )
        }
        SecondaryButton(
            text = stringResource(R.string.report_mock),
            onClick = onReportMockResult,
            enabled = latestTask != null
        )
        latestTask?.let { task ->
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = WarmSurfaceAlt),
                shape = RoundedCornerShape(20.dp)
            ) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(stringResource(R.string.task_type, task.taskType), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                    Text(stringResource(R.string.task_title, task.title), style = MaterialTheme.typography.titleMedium)
                    Text(stringResource(R.string.task_id, task.taskId), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(18.dp), modifier = Modifier.fillMaxWidth()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(
                        selected = draft.status == "published",
                        onClick = { onDraftChange(draft.copy(status = "published")) },
                        colors = RadioButtonDefaults.colors(selectedColor = BrandRed)
                    )
                    Text(stringResource(R.string.success_label))
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(
                        selected = draft.status == "failed",
                        onClick = { onDraftChange(draft.copy(status = "failed")) },
                        colors = RadioButtonDefaults.colors(selectedColor = BrandRed)
                    )
                    Text(stringResource(R.string.failed_label))
                }
            }
            AppTextField(draft.postId, { onDraftChange(draft.copy(postId = it)) }, R.string.post_id_label)
            AppTextField(draft.postUrl, { onDraftChange(draft.copy(postUrl = it)) }, R.string.post_url_label)
            AppTextField(
                value = draft.errorMessage,
                onValueChange = { onDraftChange(draft.copy(errorMessage = it)) },
                labelRes = R.string.error_reason_label,
                singleLine = false,
                minLines = 3
            )
        }
    }
}

@Composable
fun ProfileModule(
    config: AppConfig,
    accountSummary: AccountSummary?,
    requiresRelogin: Boolean,
    baseUrl: String,
    onBaseUrlChange: (String) -> Unit,
    onSaveBaseUrl: () -> Unit,
    onLoadSummary: () -> Unit,
    onCheckStatus: () -> Unit,
    onLogout: () -> Unit,
    onLanguageChange: (String) -> Unit,
) {
    Text(stringResource(R.string.profile_page_title), style = MaterialTheme.typography.headlineSmall)
    AppCard {
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(52.dp)
                    .background(BrandRed.copy(alpha = 0.14f), CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Text("ME", color = BrandRed, style = MaterialTheme.typography.labelLarge)
            }
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    accountSummary?.nickname?.ifBlank { accountSummary.name } ?: stringResource(R.string.profile_page_title),
                    style = MaterialTheme.typography.titleLarge
                )
                Text(stringResource(R.string.current_account_id, config.accountId), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
            }
        }
        if (requiresRelogin) {
            Text(stringResource(R.string.relogin_hint), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            SecondaryButton(stringResource(R.string.view_detail), onLoadSummary, modifier = Modifier.weight(1f))
            SecondaryButton(stringResource(R.string.check_status), onCheckStatus, modifier = Modifier.weight(1f))
        }
        PrimaryButton(stringResource(R.string.logout_action), onLogout)
        accountSummary?.let { summary ->
            AccountSummaryCard(summary)
        }
    }
    AppCard {
        Text(stringResource(R.string.section_language), style = MaterialTheme.typography.titleMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            SecondaryButton(stringResource(R.string.language_zh), { onLanguageChange("zh") }, modifier = Modifier.weight(1f))
            SecondaryButton(stringResource(R.string.language_en), { onLanguageChange("en") }, modifier = Modifier.weight(1f))
        }
    }
    AppCard {
        Text(stringResource(R.string.section_connection), style = MaterialTheme.typography.titleMedium)
        AppTextField(baseUrl, onBaseUrlChange, R.string.backend_url_label)
        Text(stringResource(R.string.device_id_value, config.deviceId), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
        Text(stringResource(R.string.app_instance_id_value, config.appInstanceId), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
        SecondaryButton(stringResource(R.string.save_settings), onSaveBaseUrl)
    }
}

@Composable
private fun AccountSummaryCard(summary: AccountSummary) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = WarmSurfaceAlt),
        shape = RoundedCornerShape(20.dp)
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(summary.nickname.ifBlank { summary.name.ifBlank { summary.accountId } }, style = MaterialTheme.typography.titleMedium)
            Text(stringResource(R.string.account_status, summary.status), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
            Text(stringResource(R.string.account_cookie, summary.cookiePreview), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
            Text(stringResource(R.string.account_failure_count, summary.failureCount), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
            if (summary.remark.isNotBlank()) {
                Text(stringResource(R.string.account_remark, summary.remark), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
            }
        }
    }
}

@Composable
fun StatusPanel(status: AppStatus) {
    val isIdle = status.message.isBlank() || status.message == stringResource(R.string.status_idle)
    if (isIdle && !status.isLoading) return

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, BorderSoft, RoundedCornerShape(18.dp))
            .background(WarmSurface, RoundedCornerShape(18.dp))
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        if (status.isLoading) {
            CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp, color = BrandRed)
        } else {
            Box(
                modifier = Modifier
                    .size(10.dp)
                    .background(BrandRed, CircleShape)
            )
        }
        Text(status.message, style = MaterialTheme.typography.bodySmall, textAlign = TextAlign.Start)
    }
}
