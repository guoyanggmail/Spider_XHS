package com.yangguo.xhs_android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.yangguo.xhs_android.data.AppConfigStore
import com.yangguo.xhs_android.ui.AppScreen
import com.yangguo.xhs_android.ui.theme.XhsandroidTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val configStore = AppConfigStore(this)
        configStore.applySavedLanguage()
        enableEdgeToEdge()
        setContent {
            XhsandroidTheme {
                AppScreen(configStore = configStore)
            }
        }
    }
}
