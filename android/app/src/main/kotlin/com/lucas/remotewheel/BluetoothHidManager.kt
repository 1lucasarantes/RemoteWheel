package com.lucas.remotewheel

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothHidDevice
import android.bluetooth.BluetoothHidDeviceAppQosSettings
import android.bluetooth.BluetoothHidDeviceAppSdpSettings
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import androidx.core.content.ContextCompat
import org.json.JSONObject

class BluetoothHidManager(private val context: Context, private val listener: StateListener) {

    interface StateListener {
        fun onStatusChanged(status: String, connectedDeviceName: String?)
        fun onLog(message: String)
    }

    private val tag = "BluetoothHidManager"
    private var hidDevice: BluetoothHidDevice? = null
    private var connectedDevice: BluetoothDevice? = null
    private var isAppRegistered = false

    private val bluetoothManager: BluetoothManager? by lazy {
        try {
            context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        } catch (e: Throwable) {
            Log.e(tag, "Erro ao obter BluetoothManager: ${e.message}")
            null
        }
    }

    val bluetoothAdapter: BluetoothAdapter?
        get() = try {
            bluetoothManager?.adapter
        } catch (e: Throwable) {
            Log.e(tag, "Erro ao obter BluetoothAdapter: ${e.message}")
            null
        }

    // Descritor HID de Gamepad Padrão compatível com Samsung Tizen, Android TV, Windows e Linux
    // 16 Botões (A, B, X, Y, LB, RB, LT digital, RT digital, Select, Start, L3, R3, Guide/Home, etc.)
    // 1 Hat Switch (D-Pad com 8 direções e neutro)
    // 4 Eixos Analógicos: X, Y (LS), Z, Rz (RS)
    // 2 Gatilhos Analógicos: Throttle (RT), Brake (LT)
    private val GAMEPAD_REPORT_DESCRIPTOR = byteArrayOf(
        0x05.toByte(), 0x01.toByte(),        // Usage Page (Generic Desktop)
        0x09.toByte(), 0x05.toByte(),        // Usage (Gamepad)
        0xA1.toByte(), 0x01.toByte(),        // Collection (Application)
        0x85.toByte(), 0x01.toByte(),        //   Report ID (1)

        // 16 Botões Digitais
        0x05.toByte(), 0x09.toByte(),        //   Usage Page (Button)
        0x19.toByte(), 0x01.toByte(),        //   Usage Minimum (Button 1)
        0x29.toByte(), 0x10.toByte(),        //   Usage Maximum (Button 16)
        0x15.toByte(), 0x00.toByte(),        //   Logical Minimum (0)
        0x25.toByte(), 0x01.toByte(),        //   Logical Maximum (1)
        0x75.toByte(), 0x01.toByte(),        //   Report Size (1)
        0x95.toByte(), 0x10.toByte(),        //   Report Count (16)
        0x81.toByte(), 0x02.toByte(),        //   Input (Data, Variable, Absolute)

        // D-Pad / Hat Switch (4 bits)
        0x05.toByte(), 0x01.toByte(),        //   Usage Page (Generic Desktop)
        0x09.toByte(), 0x39.toByte(),        //   Usage (Hat Switch)
        0x15.toByte(), 0x01.toByte(),        //   Logical Minimum (1)
        0x25.toByte(), 0x08.toByte(),        //   Logical Maximum (8)
        0x35.toByte(), 0x00.toByte(),        //   Physical Minimum (0)
        0x46.toByte(), 0x3B.toByte(), 0x01.toByte(), // Physical Maximum (315)
        0x65.toByte(), 0x14.toByte(),        //   Unit (Degrees)
        0x75.toByte(), 0x04.toByte(),        //   Report Size (4)
        0x95.toByte(), 0x01.toByte(),        //   Report Count (1)
        0x81.toByte(), 0x42.toByte(),        //   Input (Data, Variable, Absolute, Null State)

        // Padding de 4 bits para alinhar em bytes
        0x75.toByte(), 0x04.toByte(),        //   Report Size (4)
        0x95.toByte(), 0x01.toByte(),        //   Report Count (1)
        0x81.toByte(), 0x03.toByte(),        //   Input (Constant, Variable, Absolute)

        // Analógicos: X, Y, Z, Rz (LS X, LS Y, RS X, RS Y)
        0x05.toByte(), 0x01.toByte(),        //   Usage Page (Generic Desktop)
        0x09.toByte(), 0x30.toByte(),        //   Usage (X)
        0x09.toByte(), 0x31.toByte(),        //   Usage (Y)
        0x09.toByte(), 0x32.toByte(),        //   Usage (Z)
        0x09.toByte(), 0x35.toByte(),        //   Usage (Rz)
        0x15.toByte(), 0x81.toByte(),        //   Logical Minimum (-127)
        0x25.toByte(), 0x7F.toByte(),        //   Logical Maximum (127)
        0x75.toByte(), 0x08.toByte(),        //   Report Size (8)
        0x95.toByte(), 0x04.toByte(),        //   Report Count (4)
        0x81.toByte(), 0x02.toByte(),        //   Input (Data, Variable, Absolute)

        // Gatilhos Analógicos: Throttle (RT) e Brake (LT)
        0x05.toByte(), 0x02.toByte(),        //   Usage Page (Simulation Controls)
        0x09.toByte(), 0xBB.toByte(),        //   Usage (Throttle - RT)
        0x09.toByte(), 0xBA.toByte(),        //   Usage (Brake - LT)
        0x15.toByte(), 0x00.toByte(),        //   Logical Minimum (0)
        0x26.toByte(), 0xFF.toByte(), 0x00.toByte(), // Logical Maximum (255)
        0x75.toByte(), 0x08.toByte(),        //   Report Size (8)
        0x95.toByte(), 0x02.toByte(),        //   Report Count (2)
        0x81.toByte(), 0x02.toByte(),        //   Input (Data, Variable, Absolute)

        0xC0.toByte()                         // End Collection
    )

    // Buffer de 9 bytes para zero alocação de memória em 60 FPS
    private val reportBuffer = ByteArray(9)

    private val hidCallback = object : BluetoothHidDevice.Callback() {
        override fun onAppStatusChanged(pluggedDevice: BluetoothDevice?, registered: Boolean) {
            super.onAppStatusChanged(pluggedDevice, registered)
            isAppRegistered = registered
            Log.d(tag, "onAppStatusChanged: registered=$registered")
            if (registered) {
                listener.onStatusChanged("ready", null)
                listener.onLog("Pronto para parear com TV Samsung / TVBox!")
            } else {
                listener.onStatusChanged("unregistered", null)
            }
        }

        @SuppressLint("MissingPermission")
        override fun onConnectionStateChanged(device: BluetoothDevice?, state: Int) {
            super.onConnectionStateChanged(device, state)
            try {
                when (state) {
                    BluetoothProfile.STATE_CONNECTED -> {
                        connectedDevice = device
                        val devName = try { device?.name ?: "Dispositivo Bluetooth" } catch (_: Throwable) { "Dispositivo Bluetooth" }
                        Log.d(tag, "Conectado a: $devName")
                        listener.onStatusChanged("connected", devName)
                        listener.onLog("Conectado na TV: $devName")
                    }
                    BluetoothProfile.STATE_DISCONNECTED -> {
                        if (connectedDevice == device) connectedDevice = null
                        Log.d(tag, "Desconectado")
                        listener.onStatusChanged("disconnected", null)
                        listener.onLog("Desconectado da TV")
                    }
                    BluetoothProfile.STATE_CONNECTING -> {
                        val devName = try { device?.name } catch (_: Throwable) { null }
                        listener.onStatusChanged("connecting", devName)
                        listener.onLog("Conectando à TV...")
                    }
                }
            } catch (e: Throwable) {
                Log.e(tag, "Erro no onConnectionStateChanged: ${e.message}")
            }
        }
    }

    private val profileListener = object : BluetoothProfile.ServiceListener {
        @SuppressLint("MissingPermission")
        override fun onServiceConnected(profile: Int, proxy: BluetoothProfile) {
            try {
                if (profile == BluetoothProfile.HID_DEVICE) {
                    hidDevice = proxy as? BluetoothHidDevice
                    registerApp()
                }
            } catch (e: Throwable) {
                Log.e(tag, "Erro ao conectar serviço HID_DEVICE: ${e.message}")
                listener.onLog("Erro ao ativar HID: ${e.message}")
            }
        }

        override fun onServiceDisconnected(profile: Int) {
            if (profile == BluetoothProfile.HID_DEVICE) {
                hidDevice = null
                isAppRegistered = false
                connectedDevice = null
                listener.onStatusChanged("disconnected", null)
            }
        }
    }

    fun hasPermissions(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            ContextCompat.checkSelfPermission(context, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.BLUETOOTH_ADVERTISE) == PackageManager.PERMISSION_GRANTED
        } else {
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        }
    }

    @SuppressLint("MissingPermission")
    fun initialize() {
        try {
            if (!hasPermissions()) {
                listener.onLog("Permissões de Bluetooth pendentes")
                listener.onStatusChanged("need_permissions", null)
                return
            }

            val adapter = bluetoothAdapter
            if (adapter == null) {
                listener.onLog("Bluetooth não encontrado no aparelho")
                listener.onStatusChanged("unsupported", null)
                return
            }

            if (!adapter.isEnabled) {
                listener.onLog("Bluetooth desativado no aparelho")
                listener.onStatusChanged("disabled", null)
                return
            }

            // Verifica se o perfil HID_DEVICE é suportado
            val success = adapter.getProfileProxy(context, profileListener, BluetoothProfile.HID_DEVICE)
            if (!success) {
                listener.onLog("Este aparelho não suporta perfil Bluetooth HID Gamepad")
                listener.onStatusChanged("unsupported", null)
            }
        } catch (e: SecurityException) {
            Log.e(tag, "Permissão negada ao inicializar Bluetooth: ${e.message}")
            listener.onLog("Permissão de Bluetooth necessária")
            listener.onStatusChanged("need_permissions", null)
        } catch (e: Throwable) {
            Log.e(tag, "Erro geral ao inicializar Bluetooth: ${e.message}")
            listener.onLog("Erro no Bluetooth: ${e.message}")
            listener.onStatusChanged("error", null)
        }
    }

    @SuppressLint("MissingPermission")
    private fun registerApp() {
        val hid = hidDevice ?: return
        if (isAppRegistered) return

        try {
            val sdp = BluetoothHidDeviceAppSdpSettings(
                "Remote Gamepad",
                "Controle Virtual Bluetooth para Smart TV e PC",
                "Lucas",
                BluetoothHidDevice.SUBCLASS1_COMBO,
                GAMEPAD_REPORT_DESCRIPTOR
            )

            val qos = BluetoothHidDeviceAppQosSettings(
                BluetoothHidDeviceAppQosSettings.SERVICE_BEST_EFFORT,
                800, 9, 0, 11250,
                BluetoothHidDeviceAppQosSettings.MAX
            )

            hid.registerApp(sdp, null, qos, ContextCompat.getMainExecutor(context), hidCallback)
        } catch (e: Throwable) {
            Log.e(tag, "Erro ao registrar app HID: ${e.message}")
            listener.onLog("Falha ao registrar serviço HID: ${e.message}")
        }
    }

    @SuppressLint("MissingPermission")
    fun close() {
        try {
            hidDevice?.let {
                if (isAppRegistered) it.unregisterApp()
                bluetoothAdapter?.closeProfileProxy(BluetoothProfile.HID_DEVICE, it)
            }
        } catch (e: Throwable) {
            Log.e(tag, "Erro ao fechar Bluetooth HID: ${e.message}")
        }
        hidDevice = null
        isAppRegistered = false
        connectedDevice = null
    }

    fun isConnected(): Boolean = connectedDevice != null

    @SuppressLint("MissingPermission")
    fun sendGamepadState(jsonString: String) {
        val hid = hidDevice ?: return
        val target = connectedDevice ?: return

        try {
            val json = JSONObject(jsonString)

            // Byte 0: Botões 1 a 8
            var b0 = 0
            if (json.optBoolean("btn_a")) b0 = b0 or 0x01
            if (json.optBoolean("btn_b")) b0 = b0 or 0x02
            if (json.optBoolean("btn_x")) b0 = b0 or 0x04
            if (json.optBoolean("btn_y")) b0 = b0 or 0x08
            if (json.optBoolean("btn_lb")) b0 = b0 or 0x10
            if (json.optBoolean("btn_rb")) b0 = b0 or 0x20
            if (json.optDouble("lt", 0.0) > 0.5) b0 = b0 or 0x40
            if (json.optDouble("rt", 0.0) > 0.5) b0 = b0 or 0x80
            reportBuffer[0] = b0.toByte()

            // Byte 1: Botões 9 a 16
            var b1 = 0
            if (json.optBoolean("btn_select")) b1 = b1 or 0x01
            if (json.optBoolean("btn_start")) b1 = b1 or 0x02
            if (json.optBoolean("btn_l3")) b1 = b1 or 0x04
            if (json.optBoolean("btn_r3")) b1 = b1 or 0x08
            if (json.optBoolean("btn_guide") || json.optBoolean("home")) b1 = b1 or 0x10
            reportBuffer[1] = b1.toByte()

            // Byte 2: D-Pad / Hat Switch (1=Up, 2=Up-Right, 3=Right, 4=Down-Right, 5=Down, 6=Down-Left, 7=Left, 8=Up-Left, 0=Neutro)
            val up = json.optBoolean("dpad_up")
            val down = json.optBoolean("dpad_down")
            val left = json.optBoolean("dpad_left")
            val right = json.optBoolean("dpad_right")

            val hat = when {
                up && right -> 2
                down && right -> 4
                down && left -> 6
                up && left -> 8
                up -> 1
                right -> 3
                down -> 5
                left -> 7
                else -> 0
            }
            reportBuffer[2] = (hat and 0x0F).toByte()

            // Bytes 3 e 4: Analógico Esquerdo X e Y (-127 a 127)
            val lsX = (json.optDouble("ls_x", 0.0) * 127).toInt().coerceIn(-127, 127)
            val lsY = (-json.optDouble("ls_y", 0.0) * 127).toInt().coerceIn(-127, 127)
            reportBuffer[3] = lsX.toByte()
            reportBuffer[4] = lsY.toByte()

            // Bytes 5 e 6: Analógico Direito X e Y (-127 a 127)
            val rsX = (json.optDouble("rs_x", 0.0) * 127).toInt().coerceIn(-127, 127)
            val rsY = (-json.optDouble("rs_y", 0.0) * 127).toInt().coerceIn(-127, 127)
            reportBuffer[5] = rsX.toByte()
            reportBuffer[6] = rsY.toByte()

            // Bytes 7 e 8: Gatilhos Analógicos RT (Gás) e LT (Freio) (0 a 255)
            val rt = (json.optDouble("rt", json.optDouble("gas", 0.0)) * 255).toInt().coerceIn(0, 255)
            val lt = (json.optDouble("lt", json.optDouble("brake", 0.0)) * 255).toInt().coerceIn(0, 255)
            reportBuffer[7] = rt.toByte()
            reportBuffer[8] = lt.toByte()

            // Se for volante com acelerômetro/giroscópio: steer vira ls_x
            if (json.has("steer")) {
                val steer = (json.optDouble("steer", 0.0) * 127).toInt().coerceIn(-127, 127)
                reportBuffer[3] = steer.toByte()
            }

            hid.sendReport(target, 1, reportBuffer)
        } catch (e: Throwable) {
            Log.e(tag, "sendGamepadState erro: ${e.message}")
        }
    }
}
