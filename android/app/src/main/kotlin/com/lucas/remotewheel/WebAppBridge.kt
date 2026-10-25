package com.lucas.remotewheel

import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.webkit.JavascriptInterface

class WebAppBridge(
    private val activity: MainActivity,
    private val btManager: BluetoothHidManager
) {
    private var connectionMode = "wifi" // "wifi" ou "bluetooth"

    @JavascriptInterface
    fun sendGamepadInput(jsonString: String) {
        if (connectionMode == "bluetooth") {
            btManager.sendGamepadState(jsonString)
        }
    }

    @JavascriptInterface
    fun getConnectionMode(): String = connectionMode

    @JavascriptInterface
    fun setConnectionMode(mode: String) {
        connectionMode = if (mode.equals("bluetooth", ignoreCase = true)) "bluetooth" else "wifi"
        activity.runOnUiThread {
            if (connectionMode == "bluetooth") {
                activity.ensureBluetoothPermissionsAndStart()
            }
        }
    }

    @JavascriptInterface
    fun makeBluetoothDiscoverable() {
        activity.runOnUiThread {
            activity.requestBluetoothDiscoverable()
        }
    }

    @JavascriptInterface
    fun isBluetoothConnected(): Boolean = btManager.isConnected()

    @JavascriptInterface
    fun vibrate(durationMs: Long) {
        try {
            val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val vm = activity.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
                vm?.defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                activity.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
            }

            vibrator?.let {
                if (it.hasVibrator()) {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        it.vibrate(VibrationEffect.createOneShot(durationMs.coerceAtLeast(10), VibrationEffect.DEFAULT_AMPLITUDE))
                    } else {
                        @Suppress("DEPRECATION")
                        it.vibrate(durationMs.coerceAtLeast(10))
                    }
                }
            }
        } catch (_: Throwable) {}
    }
}
