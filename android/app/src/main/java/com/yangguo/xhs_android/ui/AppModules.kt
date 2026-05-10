package com.yangguo.xhs_android.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.ExperimentalFoundationApi
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
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
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
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
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
import com.yangguo.xhs_android.data.PublishTaskDetail
import com.yangguo.xhs_android.data.SearchTaskDetail
import com.yangguo.xhs_android.data.SearchResultItem
import com.yangguo.xhs_android.data.SearchTaskSummary
import org.json.JSONArray
import org.json.JSONObject
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
        }
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            taskDetail.results.forEach { item ->
                SearchPostCard(item = item, onClick = { onOpenItem(item) })
            }
        }
    }
}

@Composable
fun SearchDetailScreen(
    item: SearchResultItem,
    status: AppStatus,
    onBack: () -> Unit,
    onCreatePublishTask: (() -> Unit)? = null,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(WarmBackground)
    ) {
        SearchDetailTopBar(
            item = item,
            onBack = onBack,
            onCreatePublishTask = onCreatePublishTask,
            modifier = Modifier.statusBarsPadding()
        )
        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
        ) {
            PostMediaGallery(item = item)
            Column(
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 18.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                val displayTitle = displayPostTitle(item.title)
                if (displayTitle.isNotBlank()) {
                    Text(displayTitle, style = MaterialTheme.typography.titleLarge)
                }
                if (item.topics.isNotEmpty()) {
                    Text(item.topics.joinToString(" ") { "#$it" }, style = MaterialTheme.typography.bodyLarge, color = BrandRed)
                }
                if (item.content.isNotBlank()) {
                    Text(item.content, style = MaterialTheme.typography.bodyLarge)
                }
                val metaParts = listOf(item.publishTime, item.location).filter { it.isNotBlank() }
                if (metaParts.isNotEmpty()) {
                    Text(metaParts.joinToString(" "), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                }
            }
        }
        PostDetailActionBar(item = item)
        StatusPanel(status = status)
    }
}

@Composable
private fun SearchPostCard(item: SearchResultItem, onClick: () -> Unit) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(22.dp))
            .clickable(onClick = onClick),
        color = WarmSurface,
        shadowElevation = 2.dp
    ) {
        Column {
            AsyncImage(
                model = displayCoverUrl(item),
                contentDescription = null,
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(1f),
                contentScale = ContentScale.Crop
            )
            Column(
                modifier = Modifier.padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                val displayTitle = displayPostTitle(item.title)
                if (displayTitle.isNotBlank()) {
                    Text(
                        displayTitle,
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    PostAuthorInfo(
                        avatarUrl = item.authorAvatar,
                        authorName = item.authorName.ifBlank { stringResource(R.string.empty_author) },
                    )
                    Text(
                        stringResource(R.string.search_card_metrics, item.likeCount, item.commentCount),
                        style = MaterialTheme.typography.bodySmall,
                        color = TextSecondary
                    )
                }
            }
        }
    }
}

@Composable
private fun PostAuthorInfo(avatarUrl: String, authorName: String, modifier: Modifier = Modifier) {
    Row(modifier = modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        AvatarImage(avatarUrl = avatarUrl, authorName = authorName)
        Text(authorName, style = MaterialTheme.typography.bodyMedium, color = TextSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun AvatarImage(avatarUrl: String, authorName: String, modifier: Modifier = Modifier) {
    if (avatarUrl.isNotBlank()) {
        AsyncImage(
            model = avatarUrl,
            contentDescription = null,
            modifier = modifier
                .size(30.dp)
                .clip(CircleShape),
            contentScale = ContentScale.Crop
        )
    } else {
        Box(
            modifier = modifier
                .size(30.dp)
                .background(BrandRed.copy(alpha = 0.12f), CircleShape),
            contentAlignment = Alignment.Center
        ) {
            Text(authorName.take(1).ifBlank { "?" }, color = BrandRed, style = MaterialTheme.typography.labelMedium)
        }
    }
}

@Composable
private fun SearchDetailTopBar(
    item: SearchResultItem,
    onBack: () -> Unit,
    onCreatePublishTask: (() -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(WarmSurface)
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Surface(
                modifier = Modifier.size(36.dp).clickable(onClick = onBack),
                shape = CircleShape,
                color = WarmSurfaceAlt
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text("‹", style = MaterialTheme.typography.titleLarge, color = TextSecondary)
                }
            }
            PostAuthorInfo(
                avatarUrl = item.authorAvatar,
                authorName = item.authorName.ifBlank { stringResource(R.string.empty_author) }
            )
        }
        if (onCreatePublishTask != null) {
            Surface(
                modifier = Modifier
                    .clip(RoundedCornerShape(16.dp))
                    .clickable(onClick = onCreatePublishTask),
                shape = RoundedCornerShape(16.dp),
                color = WarmSurfaceAlt
            ) {
                Text(
                    stringResource(R.string.create_publish_task),
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                    style = MaterialTheme.typography.labelLarge,
                    color = BrandRed
                )
            }
        } else {
            Spacer(modifier = Modifier.width(36.dp))
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun PostMediaGallery(item: SearchResultItem) {
    val mediaItems = item.imageUrls.filter { it.isNotBlank() }
    when {
        item.videoUrl.isNotBlank() -> {
            Box(modifier = Modifier.fillMaxWidth().aspectRatio(1f).background(WarmSurface)) {
                VideoPlayer(url = item.videoUrl, modifier = Modifier.fillMaxSize())
            }
        }
        mediaItems.isNotEmpty() -> {
            val pagerState = rememberPagerState(pageCount = { mediaItems.size })
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                HorizontalPager(
                    state = pagerState,
                    modifier = Modifier
                        .fillMaxWidth()
                        .aspectRatio(1f)
                ) { page ->
                    AsyncImage(
                        model = mediaItems[page],
                        contentDescription = null,
                        modifier = Modifier.fillMaxSize(),
                        contentScale = ContentScale.Crop
                    )
                }
                if (mediaItems.size > 1) {
                    Row(
                        modifier = Modifier.padding(top = 12.dp),
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        repeat(mediaItems.size) { index ->
                            Box(
                                modifier = Modifier
                                    .size(if (index == pagerState.currentPage) 8.dp else 6.dp)
                                    .background(
                                        if (index == pagerState.currentPage) BrandRed else BorderSoft,
                                        CircleShape
                                    )
                            )
                        }
                    }
                }
            }
        }
        displayCoverUrl(item).isNotBlank() -> {
            AsyncImage(
                model = displayCoverUrl(item),
                contentDescription = null,
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(1f),
                contentScale = ContentScale.Crop
            )
        }
    }
}

@Composable
private fun PostDetailActionBar(item: SearchResultItem) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(WarmSurface)
            .padding(horizontal = 16.dp, vertical = 14.dp),
        horizontalArrangement = Arrangement.End
    ) {
        Text(
            stringResource(R.string.post_detail_metrics, item.likeCount, item.collectCount, item.commentCount),
            style = MaterialTheme.typography.bodyMedium,
            color = TextSecondary
        )
    }
}

private fun displayPostTitle(title: String): String {
    return title.takeIf { it.isNotBlank() && it != "无标题" } ?: ""
}

private fun displayCoverUrl(item: SearchResultItem): String {
    return item.coverUrl.ifBlank {
        item.videoCoverUrl.ifBlank {
            item.imageUrls.firstOrNull().orEmpty()
        }
    }
}

@Composable
private fun VideoPlayer(url: String, modifier: Modifier = Modifier) {
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
        modifier = modifier
    )
}

@Composable
fun PublishModule(
    latestTask: AppTask?,
    onFetchTask: () -> Unit,
    onReportResult: () -> Unit,
    onOpenTask: (AppTask) -> Unit,
) {
    Text(stringResource(R.string.publish_page_title), style = MaterialTheme.typography.headlineSmall)
    AppCard {
        Text(stringResource(R.string.section_publish_task), style = MaterialTheme.typography.titleMedium)
        Text(stringResource(R.string.publish_intro), style = MaterialTheme.typography.bodyMedium, color = TextSecondary)
        PrimaryButton(
            text = stringResource(if (latestTask == null) R.string.fetch_task else R.string.task_in_progress),
            onClick = onFetchTask,
            enabled = latestTask == null
        )
        latestTask?.let { task ->
            PublishTaskCard(task = task, onClick = { onOpenTask(task) })
            Text(
                stringResource(R.string.publish_task_hint),
                style = MaterialTheme.typography.bodySmall,
                color = TextSecondary
            )
            PrimaryButton(
                text = stringResource(R.string.start_publish),
                onClick = onReportResult,
            )
        }
    }
}

@Composable
fun PublishTaskDetailScreen(
    task: AppTask,
    status: AppStatus,
    onBack: () -> Unit,
    onReportResult: () -> Unit,
) {
    val detail = remember(task.rawJson) { parsePublishTaskDetail(task) }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(WarmBackground)
    ) {
        SearchDetailTopBar(
            item = SearchResultItem(
                postId = detail.taskId,
                postUrl = detail.publishedPostUrl,
                title = detail.title,
                authorName = "",
                authorAvatar = "",
                likeCount = 0,
                commentCount = 0,
                collectCount = 0,
                contentPreview = detail.content,
                content = detail.content,
                noteType = detail.mediaType,
                topics = detail.topics,
                coverUrl = detail.coverUrl,
                imageUrls = if (detail.mediaType == "image") detail.mediaUrls else emptyList(),
                videoUrl = if (detail.mediaType == "video") detail.mediaUrls.firstOrNull().orEmpty() else "",
                videoCoverUrl = detail.coverUrl,
                publishTime = "",
                location = detail.location,
                workerCookieId = ""
            ),
            onBack = onBack,
            modifier = Modifier.statusBarsPadding()
        )
        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
        ) {
            PublishTaskMediaGallery(detail)
            Column(
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 18.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                Text(detail.title, style = MaterialTheme.typography.titleLarge)
                if (detail.topics.isNotEmpty()) {
                    Text(detail.topics.joinToString(" ") { "#$it" }, style = MaterialTheme.typography.bodyLarge, color = BrandRed)
                }
                if (detail.content.isNotBlank()) {
                    Text(detail.content, style = MaterialTheme.typography.bodyLarge)
                }
                val metaParts = listOf(detail.location, detail.taskStatus).filter { it.isNotBlank() }
                if (metaParts.isNotEmpty()) {
                    Text(metaParts.joinToString(" "), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                }
                if (detail.lastError.isNotBlank()) {
                    Text(detail.lastError, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                }
            }
        }
        PrimaryButton(
            text = stringResource(R.string.start_publish),
            onClick = onReportResult,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp)
        )
        StatusPanel(status = status)
    }
}

@Composable
private fun PublishTaskCard(task: AppTask, onClick: () -> Unit) {
    val detail = remember(task.rawJson) { parsePublishTaskDetail(task) }
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(22.dp))
            .clickable(onClick = onClick),
        color = WarmSurfaceAlt,
        shadowElevation = 1.dp
    ) {
        Column {
            val cover = detail.coverUrl.ifBlank { detail.mediaUrls.firstOrNull().orEmpty() }
            if (cover.isNotBlank()) {
                AsyncImage(
                    model = cover,
                    contentDescription = null,
                    modifier = Modifier
                        .fillMaxWidth()
                        .aspectRatio(1f),
                    contentScale = ContentScale.Crop
                )
            }
            Column(
                modifier = Modifier.padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text(detail.title.ifBlank { task.title }, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                if (detail.content.isNotBlank()) {
                    Text(detail.content, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis, color = TextSecondary)
                }
                Text(stringResource(R.string.task_id, task.taskId), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
            }
        }
    }
}

@Composable
private fun PublishTaskMediaGallery(detail: PublishTaskDetail) {
    val item = SearchResultItem(
        postId = detail.taskId,
        postUrl = detail.publishedPostUrl,
        title = detail.title,
        authorName = "",
        authorAvatar = "",
        likeCount = 0,
        commentCount = 0,
        collectCount = 0,
        contentPreview = detail.content,
        content = detail.content,
        noteType = detail.mediaType,
        topics = detail.topics,
        coverUrl = detail.coverUrl,
        imageUrls = if (detail.mediaType == "image") detail.mediaUrls else emptyList(),
        videoUrl = if (detail.mediaType == "video") detail.mediaUrls.firstOrNull().orEmpty() else "",
        videoCoverUrl = detail.coverUrl,
        publishTime = "",
        location = detail.location,
        workerCookieId = ""
    )
    PostMediaGallery(item)
}

private fun parsePublishTaskDetail(task: AppTask): PublishTaskDetail {
    val json = runCatching { JSONObject(task.rawJson) }.getOrDefault(JSONObject())
    return PublishTaskDetail(
        taskId = json.optString("id", task.taskId),
        title = json.optString("title", task.title),
        content = json.optString("desc"),
        topics = jsonArrayToStringList(json.optJSONArray("topics")),
        location = json.optString("location"),
        mediaType = json.optString("media_type"),
        mediaUrls = jsonArrayToStringList(json.optJSONArray("media_urls")),
        coverUrl = json.optString("cover_url"),
        taskStatus = json.optString("task_status"),
        lastError = json.optString("last_error"),
        publishedPostUrl = json.optString("published_post_url")
    )
}

private fun jsonArrayToStringList(array: JSONArray?): List<String> {
    if (array == null) return emptyList()
    return List(array.length()) { index -> array.optString(index) }.filter { it.isNotBlank() }
}

@Composable
fun ProfileModule(
    config: AppConfig,
    accountSummary: AccountSummary?,
    currentLanguageCode: String,
    requiresRelogin: Boolean,
    isSettingsOpen: Boolean,
    baseUrl: String,
    onBaseUrlChange: (String) -> Unit,
    onSaveBaseUrl: () -> Unit,
    onLoadSummary: () -> Unit,
    onCheckStatus: () -> Unit,
    onLogout: () -> Unit,
    onLanguageChange: (String) -> Unit,
    onOpenPublishedItem: (SearchResultItem) -> Unit,
    onOpenSettings: () -> Unit,
    onCloseSettings: () -> Unit,
) {
    if (isSettingsOpen) {
        ProfileSettingsModule(
            config = config,
            currentLanguageCode = currentLanguageCode,
            requiresRelogin = requiresRelogin,
            baseUrl = baseUrl,
            onBaseUrlChange = onBaseUrlChange,
            onSaveBaseUrl = onSaveBaseUrl,
            onLoadSummary = onLoadSummary,
            onCheckStatus = onCheckStatus,
            onLogout = onLogout,
            onLanguageChange = onLanguageChange,
            onBack = onCloseSettings,
        )
        return
    }

    val summary = accountSummary
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(stringResource(R.string.profile_page_title), style = MaterialTheme.typography.headlineSmall)
        SecondaryButton(stringResource(R.string.open_settings), onOpenSettings)
    }
    Column(verticalArrangement = Arrangement.spacedBy(18.dp), modifier = Modifier.fillMaxWidth()) {
        Row(horizontalArrangement = Arrangement.spacedBy(16.dp), verticalAlignment = Alignment.CenterVertically) {
            AvatarImage(
                avatarUrl = summary?.avatar.orEmpty(),
                authorName = summary?.nickname?.ifBlank { summary?.name.orEmpty() }.orEmpty(),
                modifier = Modifier.size(84.dp)
            )
            Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.weight(1f)) {
                Text(
                    summary?.nickname?.ifBlank { summary.name } ?: stringResource(R.string.profile_page_title),
                    style = MaterialTheme.typography.headlineSmall
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    ProfileInfoChip(text = stringResource(R.string.account_id_chip, config.accountId.takeLast(8)))
                    ProfileInfoChip(text = stringResource(R.string.account_status_chip, summary?.status ?: ""))
                }
                if (requiresRelogin) {
                    Text(
                        stringResource(R.string.relogin_hint),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }
            }
        }
        summary?.let { ProfileStatsStrip(it) }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            SecondaryButton(stringResource(R.string.refresh_and_check), onCheckStatus, modifier = Modifier.weight(1f))
        }
        ProfileNoteTabHeader()
        if (summary == null || summary.publishedNotes.isEmpty()) {
            EmptyProfileNotes()
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                summary.publishedNotes.forEach { item ->
                    SearchPostCard(item = item, onClick = { onOpenPublishedItem(item) })
                }
            }
        }
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
private fun ProfileSettingsModule(
    config: AppConfig,
    currentLanguageCode: String,
    requiresRelogin: Boolean,
    baseUrl: String,
    onBaseUrlChange: (String) -> Unit,
    onSaveBaseUrl: () -> Unit,
    onLoadSummary: () -> Unit,
    onCheckStatus: () -> Unit,
    onLogout: () -> Unit,
    onLanguageChange: (String) -> Unit,
    onBack: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        SecondaryButton(stringResource(R.string.back_action), onBack)
        Text(stringResource(R.string.section_settings), style = MaterialTheme.typography.titleLarge)
        Spacer(modifier = Modifier.width(84.dp))
    }
    AppCard {
        Text(stringResource(R.string.settings_account_title), style = MaterialTheme.typography.titleMedium)
        SecondaryButton(stringResource(R.string.refresh_and_check), onCheckStatus, modifier = Modifier.fillMaxWidth())
        if (requiresRelogin) {
            Text(stringResource(R.string.relogin_hint), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        }
        PrimaryButton(stringResource(R.string.logout_action), onLogout)
    }
    AppCard {
        Text(stringResource(R.string.settings_language_title), style = MaterialTheme.typography.titleMedium)
        LanguageOptionGroup(currentLanguageCode = currentLanguageCode, onLanguageChange = onLanguageChange)
    }
    AppCard {
        Text(stringResource(R.string.settings_connection_title), style = MaterialTheme.typography.titleMedium)
        AppTextField(baseUrl, onBaseUrlChange, R.string.backend_url_label)
        SecondaryButton(stringResource(R.string.save_settings), onSaveBaseUrl)
    }
    AppCard {
        Text(stringResource(R.string.settings_device_title), style = MaterialTheme.typography.titleMedium)
        Text(stringResource(R.string.device_id_value, config.deviceId), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
        Text(stringResource(R.string.app_instance_id_value, config.appInstanceId), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
    }
}

@Composable
private fun LanguageOptionGroup(currentLanguageCode: String, onLanguageChange: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
        LanguageOptionButton(
            text = stringResource(R.string.language_system_option),
            selected = currentLanguageCode.isBlank(),
            onClick = { onLanguageChange("") },
            modifier = Modifier.weight(1f)
        )
        LanguageOptionButton(
            text = stringResource(R.string.language_zh),
            selected = currentLanguageCode == "zh",
            onClick = { onLanguageChange("zh") },
            modifier = Modifier.weight(1f)
        )
        LanguageOptionButton(
            text = stringResource(R.string.language_en),
            selected = currentLanguageCode == "en",
            onClick = { onLanguageChange("en") },
            modifier = Modifier.weight(1f)
        )
    }
}

@Composable
private fun LanguageOptionButton(
    text: String,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Button(
        onClick = onClick,
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = if (selected) BrandRed.copy(alpha = 0.12f) else WarmSurfaceAlt,
            contentColor = if (selected) BrandRed else MaterialTheme.colorScheme.onSurface
        )
    ) {
        Text(text)
    }
}

@Composable
private fun ProfileStatsStrip(summary: AccountSummary) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(24.dp)
    ) {
        ProfileStatItem(value = summary.followingCount, labelRes = R.string.profile_stat_following)
        ProfileStatItem(value = summary.followerCount, labelRes = R.string.profile_stat_followers)
        ProfileStatItem(value = summary.likedCount, labelRes = R.string.profile_stat_likes)
    }
}

@Composable
private fun ProfileStatItem(value: Int, labelRes: Int) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(value.toString(), style = MaterialTheme.typography.titleLarge)
        Text(stringResource(labelRes), style = MaterialTheme.typography.bodySmall, color = TextSecondary)
    }
}

@Composable
private fun ProfileInfoChip(text: String) {
    Surface(
        color = WarmSurface,
        shape = RoundedCornerShape(999.dp),
        tonalElevation = 1.dp,
        shadowElevation = 1.dp
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            style = MaterialTheme.typography.bodySmall,
            color = TextSecondary
        )
    }
}

@Composable
private fun ProfileNoteTabHeader() {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.Center
    ) {
        Surface(
            color = WarmSurface,
            shape = RoundedCornerShape(999.dp),
            tonalElevation = 1.dp
        ) {
            Text(
                text = stringResource(R.string.profile_notes_tab),
                modifier = Modifier.padding(horizontal = 28.dp, vertical = 12.dp),
                style = MaterialTheme.typography.titleMedium
            )
        }
    }
}

@Composable
private fun EmptyProfileNotes() {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 44.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Box(
            modifier = Modifier
                .size(88.dp)
                .border(1.dp, BorderSoft, CircleShape),
            contentAlignment = Alignment.Center
        ) {
            Text("○", style = MaterialTheme.typography.headlineMedium, color = BorderSoft)
        }
        Text(
            stringResource(R.string.profile_notes_empty),
            style = MaterialTheme.typography.bodyMedium,
            color = TextSecondary
        )
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
