package com.yangguo.xhs_android.data

import android.content.Context
import android.os.Build
import android.provider.Settings
import java.util.UUID

class AppConfigStore(context: Context) {
    private val appContext = context.applicationContext
    private val preferences = appContext.getSharedPreferences("xhs_android_config", Context.MODE_PRIVATE)

    fun load(): AppConfig {
        val instanceId = preferences.getString(KEY_APP_INSTANCE_ID, null) ?: UUID.randomUUID().toString().also {
            preferences.edit().putString(KEY_APP_INSTANCE_ID, it).apply()
        }
        val androidId = Settings.Secure.getString(appContext.contentResolver, Settings.Secure.ANDROID_ID).orEmpty()
        return AppConfig(
            baseUrl = preferences.getString(KEY_BASE_URL, "http://10.0.2.2:8000") ?: "http://10.0.2.2:8000",
            accountId = preferences.getString(KEY_ACCOUNT_ID, "") ?: "",
            deviceId = androidId.ifBlank { "android-${Build.MODEL}" },
            appInstanceId = instanceId,
            deviceName = "${Build.MANUFACTURER} ${Build.MODEL}".trim(),
            appVersion = "1.0"
        )
    }

    fun save(baseUrl: String, accountId: String): AppConfig {
        preferences.edit()
            .putString(KEY_BASE_URL, baseUrl.trim().trimEnd('/'))
            .putString(KEY_ACCOUNT_ID, accountId.trim())
            .apply()
        return load()
    }

    private companion object {
        const val KEY_BASE_URL = "base_url"
        const val KEY_ACCOUNT_ID = "account_id"
        const val KEY_APP_INSTANCE_ID = "app_instance_id"
    }
}
