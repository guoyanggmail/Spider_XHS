package com.yangguo.xhs_android.data

import org.junit.Assert.assertEquals
import org.junit.Test

class BackendClientPublishTaskPayloadTest {
    @Test
    fun `build publish task request uses post detail fields`() {
        val client = BackendClient(
            AppConfig(
                baseUrl = "http://127.0.0.1:8000",
                accountId = "account-1"
            )
        )
        val item = SearchResultItem(
            postId = "post-1",
            postUrl = "https://www.xiaohongshu.com/explore/post-1",
            title = "新加坡酒店攻略",
            authorName = "作者",
            authorAvatar = "https://img/avatar.jpg",
            likeCount = 12,
            commentCount = 3,
            collectCount = 4,
            contentPreview = "正文摘要",
            content = "正文全文",
            noteType = "normal",
            topics = listOf("新加坡", "酒店"),
            coverUrl = "https://img/cover.jpg",
            imageUrls = listOf("https://img/1.jpg", "https://img/2.jpg"),
            videoUrl = "",
            videoCoverUrl = "",
            publishTime = "2026-05-10",
            location = "新加坡",
            workerCookieId = "worker-1"
        )

        val draft = client.buildPublishTaskDraft(item)

        assertEquals("account-1", draft.accountId)
        assertEquals("新加坡酒店攻略", draft.title)
        assertEquals("正文全文", draft.desc)
        assertEquals("image", draft.mediaType)
        assertEquals("https://img/cover.jpg", draft.coverUrl)
        assertEquals("https://img/1.jpg", draft.mediaUrls.first())
        assertEquals("新加坡", draft.topics.first())
        assertEquals("pending", draft.reviewStatus)
    }

    @Test
    fun `build publish task request falls back to video and preview title`() {
        val client = BackendClient(
            AppConfig(
                baseUrl = "http://127.0.0.1:8000",
                accountId = "account-2"
            )
        )
        val item = SearchResultItem(
            postId = "post-2",
            postUrl = "https://www.xiaohongshu.com/explore/post-2",
            title = "",
            authorName = "",
            authorAvatar = "",
            likeCount = 0,
            commentCount = 0,
            collectCount = 0,
            contentPreview = "视频正文摘要",
            content = "",
            noteType = "video",
            topics = emptyList(),
            coverUrl = "",
            imageUrls = emptyList(),
            videoUrl = "https://video/video.mp4",
            videoCoverUrl = "https://img/video-cover.jpg",
            publishTime = "",
            location = "",
            workerCookieId = ""
        )

        val draft = client.buildPublishTaskDraft(item)

        assertEquals("视频正文摘要", draft.title)
        assertEquals("视频正文摘要", draft.desc)
        assertEquals("video", draft.mediaType)
        assertEquals("https://video/video.mp4", draft.mediaUrls.first())
        assertEquals("https://img/video-cover.jpg", draft.coverUrl)
    }
}
