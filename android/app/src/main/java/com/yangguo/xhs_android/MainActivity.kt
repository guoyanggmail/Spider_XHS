package com.yangguo.xhs_android

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import com.yangguo.xhs_android.data.AppConfigStore
import com.yangguo.xhs_android.ui.AppScreen
import com.yangguo.xhs_android.ui.theme.XhsandroidTheme

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        val configStore = AppConfigStore(this)
        configStore.applySavedLanguage()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            XhsandroidTheme {
                AppScreen(configStore = configStore)
            }
        }
    }
}
