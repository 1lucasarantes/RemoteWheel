package com.lucas.remotewheel

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.bluetooth.BluetoothAdapter
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.Toast
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter

class MainActivity : Activity(), BluetoothHidManager.StateListener {

    private val tag = "RemoteWheelMain"
    private lateinit var webView: WebView
    lateinit var btManager: BluetoothHidManager
    private lateinit var webAppBridge: WebAppBridge

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Instala Handler Global de Exceções Não Tratadas (Evita Crash Silencioso)
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            val stackTrace = StringWriter().also { throwable.printStackTrace(PrintWriter(it)) }.toString()
            Log.e(tag, "FATAL CRASH na thread ${thread.name}:\n$stackTrace")
            try {
                val crashFile = File(filesDir, "crash_log.txt")
                crashFile.writeText(stackTrace)
            } catch (_: Throwable) {}
        }

        try {
            // Configuração de Tela Cheia Imersiva
            hideSystemUI()
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

            // Inicializa Bluetooth HID Manager (Modo Passivo - não toca no rádio até ser solicitado)
            btManager = BluetoothHidManager(this, this)
            webAppBridge = WebAppBridge(this, btManager)

            // Inicializa WebView de alta performance
            setupWebView()
        } catch (e: Throwable) {
            Log.e(tag, "Erro no onCreate: ${e.message}", e)
            showFatalError("Falha na inicialização", e.localizedMessage ?: e.toString())
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        webView = WebView(this).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )

            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                allowFileAccess = true
                allowContentAccess = true
                useWideViewPort = true
                loadWithOverviewMode = true
                mediaPlaybackRequiresUserGesture = false
                cacheMode = WebSettings.LOAD_NO_CACHE
                mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            }

            webChromeClient = object : WebChromeClient() {
                override fun onConsoleMessage(consoleMessage: ConsoleMessage?): Boolean {
                    Log.d("RemoteWheelWeb", "${consoleMessage?.message()} -- From line ${consoleMessage?.lineNumber()}")
                    return true
                }
            }

            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    evaluateJavascript("if (window.setAndroidBridgeActive) window.setAndroidBridgeActive(true);", null)
                }

                override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                    super.onReceivedError(view, request, error)
                    Log.e("RemoteWheelWeb", "Erro WebView: ${error?.description}")
                }
            }

            // Adiciona ponte JavaScript -> Kotlin Nativo
            addJavascriptInterface(webAppBridge, "AndroidController")
        }

        setContentView(webView)

        // Carrega a interface web local empacotada no APK
        webView.loadUrl("file:///android_asset/web/index.html")
    }

    private fun hideSystemUI() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                window.setDecorFitsSystemWindows(false)
                window.insetsController?.let { controller ->
                    controller.hide(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
                    controller.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                }
            } else {
                @Suppress("DEPRECATION")
                window.decorView.systemUiVisibility = (
                    View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    or View.SYSTEM_UI_FLAG_FULLSCREEN
                )
            }
        } catch (e: Throwable) {
            Log.w(tag, "Não foi possível aplicar hideSystemUI: ${e.message}")
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) {
            hideSystemUI()
        }
    }

    fun ensureBluetoothPermissionsAndStart() {
        val permissions = mutableListOf<String>()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
                permissions.add(Manifest.permission.BLUETOOTH_CONNECT)
            }
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_ADVERTISE) != PackageManager.PERMISSION_GRANTED) {
                permissions.add(Manifest.permission.BLUETOOTH_ADVERTISE)
            }
        } else {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                permissions.add(Manifest.permission.ACCESS_FINE_LOCATION)
            }
        }

        if (permissions.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, permissions.toTypedArray(), 1001)
        } else {
            btManager.initialize()
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 1001) {
            if (grantResults.isNotEmpty() && grantResults.all { it == PackageManager.PERMISSION_GRANTED }) {
                btManager.initialize()
            } else {
                Toast.makeText(this, "Permissão de Bluetooth necessária para modo TV!", Toast.LENGTH_LONG).show()
                onStatusChanged("need_permissions", null)
            }
        }
    }

    @SuppressLint("MissingPermission")
    fun requestBluetoothDiscoverable() {
        try {
            if (!btManager.hasPermissions()) {
                ensureBluetoothPermissionsAndStart()
                return
            }

            val adapter = btManager.bluetoothAdapter
            if (adapter == null) {
                Toast.makeText(this, "Bluetooth indisponível neste aparelho", Toast.LENGTH_SHORT).show()
                return
            }

            if (!adapter.isEnabled) {
                val enableBtIntent = Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE)
                startActivity(enableBtIntent)
                return
            }

            // Torna o celular detectável na TV por 300 segundos (5 minutos)
            val discoverableIntent = Intent(BluetoothAdapter.ACTION_REQUEST_DISCOVERABLE).apply {
                putExtra(BluetoothAdapter.EXTRA_DISCOVERABLE_DURATION, 300)
            }
            startActivity(discoverableIntent)
            Toast.makeText(this, "Visível na TV! Conecte em Controle Bluetooth na sua TV Samsung/TVBox", Toast.LENGTH_LONG).show()
        } catch (e: Throwable) {
            Log.e(tag, "Erro ao solicitar discoverable: ${e.message}")
            Toast.makeText(this, "Erro ao abrir Bluetooth: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onStatusChanged(status: String, connectedDeviceName: String?) {
        runOnUiThread {
            try {
                val dev = connectedDeviceName ?: ""
                webView.evaluateJavascript("if (window.onBluetoothStatusChanged) window.onBluetoothStatusChanged('$status', '$dev');", null)
            } catch (e: Throwable) {
                Log.e(tag, "Erro ao atualizar status na WebView: ${e.message}")
            }
        }
    }

    override fun onLog(message: String) {
        runOnUiThread {
            try {
                val escaped = message.replace("'", "\\'")
                webView.evaluateJavascript("console.log('[Android BT]: $escaped');", null)
            } catch (_: Throwable) {}
        }
    }

    private fun showFatalError(title: String, message: String) {
        AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage(message)
            .setPositiveButton("OK") { d, _ -> d.dismiss() }
            .show()
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            btManager.close()
        } catch (_: Throwable) {}
    }
}
