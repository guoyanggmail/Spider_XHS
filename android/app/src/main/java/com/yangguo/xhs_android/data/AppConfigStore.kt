package com.yangguo.xhs_android.data

import android.content.Context
import android.os.Build
import android.provider.Settings
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.os.LocaleListCompat
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
            primaryCookie = preferences.getString(KEY_PRIMARY_COOKIE, "") ?: "",
            languageCode = preferences.getString(KEY_LANGUAGE_CODE, "") ?: "",
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

    fun saveLoginState(accountId: String, primaryCookie: String): AppConfig {
        preferences.edit()
            .putString(KEY_ACCOUNT_ID, accountId.trim())
            .putString(KEY_PRIMARY_COOKIE, primaryCookie)
            .apply()
        return load()
    }

    fun saveLanguage(languageCode: String): AppConfig {
        preferences.edit()
            .putString(KEY_LANGUAGE_CODE, languageCode.trim())
            .apply()
        applyLanguage(languageCode)
        return load()
    }

    fun applySavedLanguage() {
        applyLanguage(preferences.getString(KEY_LANGUAGE_CODE, "") ?: "")
    }

    private fun applyLanguage(languageCode: String) {
        val locales = if (languageCode.isBlank()) {
            LocaleListCompat.getEmptyLocaleList()
        } else {
            LocaleListCompat.forLanguageTags(languageCode)
        }
        AppCompatDelegate.setApplicationLocales(locales)
    }

    fun clearLoginState(): AppConfig {
        preferences.edit()
            .putString(KEY_ACCOUNT_ID, "")
            .putString(KEY_PRIMARY_COOKIE, "")
            .apply()
        return load()
    }

    private companion object {
        const val KEY_BASE_URL = "base_url"
        const val KEY_ACCOUNT_ID = "account_id"
        const val KEY_PRIMARY_COOKIE = "primary_cookie"
        const val KEY_LANGUAGE_CODE = "language_code"
        const val KEY_APP_INSTANCE_ID = "app_instance_id"
    }
}
