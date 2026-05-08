package com.yangguo.xhs_android.xhs

import android.content.Context
import android.content.Intent

class XhsAutomation(private val context: Context) {
    fun openXhsApp(): Boolean {
        val intent = context.packageManager.getLaunchIntentForPackage(XHS_PACKAGE) ?: return false
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return true
    }

    companion object {
        const val XHS_PACKAGE = "com.xingin.xhs"
    }
}
