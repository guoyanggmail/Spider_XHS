package com.yangguo.xhs_android.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val DarkColorScheme = darkColorScheme(
    primary = BrandRedSoft,
    onPrimary = WarmSurface,
    secondary = WarmSurfaceAlt,
    onSecondary = TextPrimary,
    tertiary = SuccessGreen,
    background = DarkBackground,
    onBackground = WarmSurface,
    surface = DarkSurface,
    onSurface = WarmSurface,
    surfaceVariant = DarkBorder,
    onSurfaceVariant = TextTertiary,
    outline = DarkBorder,
    error = ErrorRed
)

private val LightColorScheme = lightColorScheme(
    primary = BrandRed,
    onPrimary = WarmSurface,
    secondary = WarmSurfaceAlt,
    onSecondary = TextPrimary,
    tertiary = SuccessGreen,
    background = WarmBackground,
    onBackground = TextPrimary,
    surface = WarmSurface,
    onSurface = TextPrimary,
    surfaceVariant = WarmSurfaceAlt,
    onSurfaceVariant = TextSecondary,
    outline = BorderSoft,
    error = ErrorRed
)

@Composable
fun XhsandroidTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme,
        typography = Typography,
        content = content
    )
}
