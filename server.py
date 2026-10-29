import asyncio
import datetime
import http.server
import ipaddress
import json
import os
import socket
import ssl
import sys
import threading
import time

# Garante suporte a UTF-8 no console do Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import qrcode
except ImportError:
    qrcode = None

try:
    import vgamepad as vg
    HAVE_VGAMEPAD = True
except Exception as e:
    HAVE_VGAMEPAD = False
    print("=" * 66)
    print("⚠️  AVISO IMPORTANTE: Driver ViGEmBus não encontrado neste computador!")
    print(f"    Detalhe: {e}")
    print("\n👉 Para que o Windows reconheça o controle virtual Xbox 360:")
    print("   Execute o instalador oficial que acompanha este pacote:")
    print("   👉 Instalar_ViGEmBus_x64.msi")
    print("=" * 66 + "\n")

try:
    from pynput.keyboard import Controller as KeyboardController, Key
    kb = KeyboardController()
    HAVE_PYNPUT = True
except Exception:
    HAVE_PYNPUT = False
    kb = None

import ctypes


class MouseKeyboardHandler:
    """Gerencia eventos de Mouse e Teclado com latência ultra-baixa via APIs nativas do Windows."""

    @staticmethod
    def move(dx, dy):
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)
            except Exception:
                pass

    @staticmethod
    def click(button="left", action="click"):
        if sys.platform != "win32":
            return
        try:
            if button == "left":
                if action == "down":
                    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                elif action == "up":
                    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                else:
                    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            elif button == "right":
                if action == "down":
                    ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
                elif action == "up":
                    ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)
                else:
                    ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
                    ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)
        except Exception:
            pass

    @staticmethod
    def scroll(dy):
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(dy * 120), 0)
            except Exception:
                pass

    @staticmethod
    def type_key(key):
        if HAVE_PYNPUT and kb:
            try:
                special_keys = {
                    "Enter": Key.enter,
                    "Backspace": Key.backspace,
                    "Space": Key.space,
                    "Tab": Key.tab,
                    "Escape": Key.esc,
                    "ArrowUp": Key.up,
                    "ArrowDown": Key.down,
                    "ArrowLeft": Key.left,
                    "ArrowRight": Key.right,
                    "Delete": Key.delete,
                }
                if key in special_keys:
                    kb.press(special_keys[key])
                    kb.release(special_keys[key])
                elif len(key) == 1:
                    kb.type(key)
            except Exception:
                pass

HTTP_PORT = 8080
HTTPS_PORT = 8443
WS_PORT = 8765
WSS_PORT = 8766

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
CERT_PATH = os.path.join(BASE_DIR, "cert.pem")
KEY_PATH = os.path.join(BASE_DIR, "key.pem")


def get_local_ip():
    """Detecta o IP da máquina na rede local Wi-Fi/Ethernet."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def ensure_ssl_certs(local_ip):
    """Gera certificados SSL autoassinados se não existirem."""
    if os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH):
        return True

    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        print("[*] Gerando certificado SSL autoassinado para HTTPS...")
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, local_ip),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "RemoteWheel")
        ])

        alt_names = [x509.DNSName("localhost")]
        try:
            alt_names.append(x509.IPAddress(ipaddress.IPv4Address(local_ip)))
        except Exception:
            pass

        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
            .sign(key, hashes.SHA256())
        )

        with open(KEY_PATH, "wb") as f:
            f.write(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption()
            ))

        with open(CERT_PATH, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        print("[OK] Certificado SSL gerado com sucesso!")
        return True
    except Exception as e:
        print(f"[!] Não foi possível gerar certificado SSL: {e}")
        return False


# --- SERVIDOR HTTP / HTTPS (ESTÁTICO) ---
class QuietHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def log_message(self, format, *args):
        pass


def start_http_servers(host, http_port, https_port, ssl_ctx):
    # Servidor HTTP padrão
    def run_http():
        try:
            server = http.server.ThreadingHTTPServer((host, http_port), QuietHTTPHandler)
            server.serve_forever()
        except Exception as e:
            print(f"[!] Erro ao iniciar HTTP: {e}")

    threading.Thread(target=run_http, daemon=True).start()

    # Servidor HTTPS (essencial para Chrome/Safari liberarem o giroscópio e acelerômetro)
    if ssl_ctx:
        def run_https():
            try:
                server = http.server.ThreadingHTTPServer((host, https_port), QuietHTTPHandler)
                server.socket = ssl_ctx.wrap_socket(server.socket, server_side=True)
                server.serve_forever()
            except Exception as e:
                print(f"[!] Erro ao iniciar HTTPS: {e}")

        threading.Thread(target=run_https, daemon=True).start()


# --- GERENCIADOR DE CLIENTES E FORCE FEEDBACK (RUMBLE) ---
connected_clients = set()
asyncio_loop = None


async def broadcast_to_all(message_str):
    """Envia uma mensagem JSON para todos os celulares conectados."""
    if not connected_clients:
        return
    for ws in list(connected_clients):
        try:
            await ws.send(message_str)
        except Exception:
            pass


# --- MÓDULO DE TELEMETRIA UDP DE CORRIDA (FORZA HORIZON, MOTORSPORT, F1) ---
import struct

TELEMETRY_PORT = 5300


def parse_forza_telemetry(data):
    """Decodifica pacotes UDP do protocolo padrão Forza DataOut (311 ou 324 bytes)."""
    if len(data) < 311:
        return None
    try:
        is_race_on = struct.unpack_from('<i', data, 0)[0]
        max_rpm = struct.unpack_from('<f', data, 8)[0]
        idle_rpm = struct.unpack_from('<f', data, 12)[0]
        rpm = struct.unpack_from('<f', data, 16)[0]

        # Velocidade em metros por segundo -> converter para km/h
        speed_ms = struct.unpack_from('<f', data, 244)[0]
        speed_kmh = max(0, speed_ms * 3.6)

        # Marcha: 0 = Ré, 1 a 10 = Marchas à frente, 11+ = Neutro
        gear = 0
        if len(data) >= 324:
            gear = struct.unpack_from('<B', data, 318)[0]
        elif len(data) >= 311:
            gear = struct.unpack_from('<B', data, 305)[0]

        return {
            "type": "telemetry",
            "is_race_on": bool(is_race_on),
            "rpm": int(rpm),
            "max_rpm": int(max_rpm if max_rpm > 1000 else 8000),
            "speed": int(speed_kmh),
            "gear": int(gear)
        }
    except Exception:
        return None


def telemetry_udp_listener():
    """Escuta dados de telemetria UDP enviados por jogos de corrida e repassa aos celulares."""
    global asyncio_loop, connected_clients
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", TELEMETRY_PORT))
        print(f"[OK] Módulo de Telemetria UDP ativo na porta {TELEMETRY_PORT} (Forza / F1 / Simulação)!")
    except Exception as e:
        print(f"[!] Não foi possível iniciar Telemetria UDP na porta {TELEMETRY_PORT}: {e}")
        return

    last_send = 0.0

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            now = time.time()
            # Limita transmissão a ~30 vezes por segundo para fluidez sem sobrecarga
            if now - last_send < 0.033:
                continue

            telemetry = parse_forza_telemetry(data)
            if telemetry and connected_clients and asyncio_loop:
                last_send = now
                msg = json.dumps(telemetry)
                asyncio_loop.call_soon_threadsafe(
                    lambda m=msg: asyncio.create_task(broadcast_to_all(m))
                )
        except Exception:
            time.sleep(0.01)


# --- MÓDULO DE OCR VISUAL EM TEMPO REAL PARA THE CREW 2 ---
class ScreenOcrTelemetry:
    """Captura e reconhece em tempo real o velocímetro e marcha do The Crew 2 via GDI nativo."""

    def __init__(self):
        self.running = False
        self.last_speed = 0
        self.last_gear = 1
        self.simulated_rpm = 1000
        self.max_rpm = 8500
        self.idle_rpm = 900
        self.gear_ratios = [0.0, 35.0, 65.0, 110.0, 165.0, 230.0, 310.0, 390.0]

    @staticmethod
    def capture_gdi_crop(x, y, w, h):
        """Captura região retangular da tela em ultrarrápida velocidade (<0.1ms)."""
        if sys.platform != "win32":
            return None
        import ctypes.wintypes
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', ctypes.wintypes.DWORD),
                ('biWidth', ctypes.wintypes.LONG),
                ('biHeight', ctypes.wintypes.LONG),
                ('biPlanes', ctypes.wintypes.WORD),
                ('biBitCount', ctypes.wintypes.WORD),
                ('biCompression', ctypes.wintypes.DWORD),
                ('biSizeImage', ctypes.wintypes.DWORD),
                ('biXPelsPerMeter', ctypes.wintypes.LONG),
                ('biYPelsPerMeter', ctypes.wintypes.LONG),
                ('biClrUsed', ctypes.wintypes.DWORD),
                ('biClrImportant', ctypes.wintypes.DWORD)
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', ctypes.wintypes.DWORD * 3)]

        hDesktop = user32.GetDesktopWindow()
        hDC = user32.GetDC(hDesktop)
        hMemDC = gdi32.CreateCompatibleDC(hDC)
        hBitmap = gdi32.CreateCompatibleBitmap(hDC, w, h)
        gdi32.SelectObject(hMemDC, hBitmap)
        gdi32.BitBlt(hMemDC, 0, 0, w, h, hDC, x, y, 0x00CC0020)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0

        buf = (ctypes.c_ubyte * (w * h * 4))()
        gdi32.GetDIBits(hMemDC, hBitmap, 0, h, ctypes.byref(buf), ctypes.byref(bmi), 0)

        gdi32.DeleteObject(hBitmap)
        gdi32.DeleteDC(hMemDC)
        user32.ReleaseDC(hDesktop, hDC)

        from PIL import Image
        return Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1).convert('L')

    @staticmethod
    def read_digit(img, x1, x2, y1, y2):
        w = x2 - x1
        h = y2 - y1
        def p(rx, ry):
            val = img.getpixel((int(x1 + w * rx), int(y1 + h * ry)))
            return 1 if val > 150 else 0

        top = p(0.5, 0.1)
        mid = p(0.5, 0.5)
        bot = p(0.5, 0.9)
        tl = p(0.2, 0.25)
        tr = p(0.8, 0.25)
        bl = p(0.2, 0.75)
        br = p(0.8, 0.75)

        if not (top or mid or bot or tl or tr or bl or br):
            return None
        if top and bot and tl and tr and bl and br and not mid:
            return 0
        if tr and br and not (top or mid or bot or tl or bl):
            return 1
        if top and tr and mid and bl and bot:
            return 2
        if top and tr and mid and br and bot:
            return 3
        if tl and mid and tr and br and not (top or bot or bl):
            return 4
        if top and tl and mid and br and bot:
            return 5
        if top and tl and mid and bl and br and bot and not tr:
            return 6
        if top and tr and br and not (mid or bot or tl or bl):
            return 7
        if top and mid and bot and tl and tr and bl and br:
            return 8
        if top and mid and bot and tl and tr and br and not bl:
            return 9
        return 0

    @staticmethod
    def read_gear(img, gx, gy, gw, gh):
        # Reconhece 1..7, R ou N no The Crew 2
        def gp(rx, ry):
            return 1 if img.getpixel((int(gx + gw * rx), int(gy + gh * ry))) > 150 else 0

        top = gp(0.5, 0.08)
        bot = gp(0.5, 0.90)
        mid = gp(0.5, 0.45)
        ul = gp(0.25, 0.28)
        ur = gp(0.75, 0.28)
        ll = gp(0.25, 0.72)
        lr = gp(0.75, 0.72)

        # Identificação de caracteres
        if gp(0.2, 0.5) and gp(0.8, 0.5) and not mid:
            return 11 # 'N' (Neutral)
        if ul and not ur and not ll and lr and top and bot and mid:
            return 5
        if top and ur and mid and not ul and (ll and bot):
            return 2
        if top and ur and mid and lr and bot and not ul and not ll:
            return 3
        if ul and mid and ur and lr and not top and not bot:
            return 4
        if top and ul and mid and ll and lr and bot and not ur:
            return 6
        if top and ur and lr and not (mid or bot or ul or ll):
            return 7
        if not top and not bot and ur and lr:
            return 1
        if top and ul and ur and mid and ll and lr:
            return 0 # 'R' (Reverse)
        return 1

    def run_loop(self):
        """Thread executada continuamente que ativa o OCR apenas quando The Crew 2 estiver aberto."""
        global connected_clients, asyncio_loop

        while True:
            time.sleep(0.045)  # ~22 FPS de taxa de atualização
            if not connected_clients:
                continue

            try:
                active_exe = get_active_process_name()
                if not (active_exe and ("thecrew" in active_exe)):
                    continue

                user32 = ctypes.windll.user32
                screen_w = user32.GetSystemMetrics(0)
                screen_h = user32.GetSystemMetrics(1)

                # Coordenadas proporcionais ancoradas no cluster inferior esquerdo
                # Calibrado perfeitamente na proporção da resolução (ex: 1366x768 ou 1920x1080)
                scale_x = screen_w / 1366.0
                scale_y = screen_h / 768.0

                crop_x = int(0 * scale_x)
                crop_y = int(580 * scale_y)
                crop_w = int(240 * scale_x)
                crop_h = int(180 * scale_y)

                cluster_img = self.capture_gdi_crop(crop_x, crop_y, crop_w, crop_h)
                if not cluster_img:
                    continue

                # Redimensiona para o espaço normalizado de 1366x768 se a tela for diferente
                if cluster_img.size != (240, 180):
                    cluster_img = cluster_img.resize((240, 180))

                # Leitura da velocidade (3 dígitos no velocímetro)
                d1 = self.read_digit(cluster_img, 87, 98, 134, 149)
                d2 = self.read_digit(cluster_img, 99, 110, 134, 149)
                d3 = self.read_digit(cluster_img, 111, 122, 134, 149)

                speed_str = ""
                for d in [d1, d2, d3]:
                    if d is not None:
                        speed_str += str(d)

                if speed_str:
                    try:
                        self.last_speed = int(speed_str)
                    except ValueError:
                        pass

                # Leitura da marcha
                gear = self.read_gear(cluster_img, 92, 71, 28, 43)
                if gear is not None:
                    self.last_gear = gear

                # Estimativa de RPM fluida sincronizada com marcha e velocidade
                current_gear_idx = max(1, min(7, self.last_gear if self.last_gear not in [0, 11] else 1))
                top_speed_gear = self.gear_ratios[current_gear_idx]
                prev_speed_gear = self.gear_ratios[current_gear_idx - 1] if current_gear_idx > 1 else 0.0

                if self.last_speed <= 0:
                    target_rpm = self.idle_rpm
                else:
                    gear_prog = max(0.0, min(1.0, (self.last_speed - prev_speed_gear) / max(1.0, top_speed_gear - prev_speed_gear)))
                    target_rpm = self.idle_rpm + gear_prog * (self.max_rpm - self.idle_rpm)

                self.simulated_rpm = self.simulated_rpm * 0.75 + target_rpm * 0.25

                telemetry = {
                    "type": "telemetry",
                    "speed_kmh": float(self.last_speed),
                    "gear": int(self.last_gear),
                    "rpm": float(round(self.simulated_rpm)),
                    "max_rpm": float(self.max_rpm),
                    "idle_rpm": float(self.idle_rpm)
                }

                if asyncio_loop:
                    msg = json.dumps(telemetry)
                    asyncio_loop.call_soon_threadsafe(
                        lambda m=msg: asyncio.create_task(broadcast_to_all(m))
                    )
            except Exception:
                pass


the_crew_ocr = ScreenOcrTelemetry()


# --- MÓDULO DE DETECÇÃO AUTOMÁTICA DE JOGOS (AUTO-PROFILE SWITCH) ---
GAME_PROFILES_MAP = {
    # Jogos de Corrida -> Perfil "racing" (Volante)
    "forzahorizon5.exe": "racing",
    "forzahorizon4.exe": "racing",
    "forzamotorsport.exe": "racing",
    "thecrew2.exe": "racing",
    "thecrewmotorfest.exe": "racing",
    "f1_23.exe": "racing",
    "f1_24.exe": "racing",
    "f1_22.exe": "racing",
    "assettocorsa.exe": "racing",
    "acs.exe": "racing",
    "needforspeed.exe": "racing",
    "dirt4.exe": "racing",
    "dirtrally2.exe": "racing",
    "beamng.drive.x64.exe": "racing",
    "eurotrucks2.exe": "racing",

    # Jogos de Ação e Tiro -> Perfil "shooter" (Gamepad + Gyro Aim)
    "gta5.exe": "shooter",
    "cyberpunk2077.exe": "shooter",
    "cs2.exe": "shooter",
    "cod.exe": "shooter",
    "fortniteclient-win64-shipping.exe": "shooter",
    "rdr2.exe": "shooter",

    # Jogos de Esporte e Casuais -> Perfil "casual" (Gamepad Clássico)
    "fifa23.exe": "casual",
    "fc24.exe": "casual",
    "fc25.exe": "casual",
    "rocketleague.exe": "casual",
    "fallguys_client.exe": "casual"
}


def get_active_process_name():
    """Identifica o executável em primeiro plano no Windows via API nativa ctypes."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes.wintypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None
        h_proc = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
        if not h_proc:
            return None
        buf = ctypes.create_unicode_buffer(512)
        size = ctypes.wintypes.DWORD(512)
        res = ctypes.windll.kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size))
        ctypes.windll.kernel32.CloseHandle(h_proc)
        if res:
            return os.path.basename(buf.value).lower()
    except Exception:
        pass
    return None


def auto_game_detector_loop():
    """Monitora qual jogo está ativo e solicita a troca de perfil automática no celular."""
    global asyncio_loop, connected_clients
    last_detected_game = None

    while True:
        time.sleep(2.0)
        if not connected_clients:
            continue

        try:
            exe_name = get_active_process_name()
            if exe_name and exe_name != last_detected_game:
                if exe_name in GAME_PROFILES_MAP:
                    profile_id = GAME_PROFILES_MAP[exe_name]
                    last_detected_game = exe_name
                    print(f"\n[AUTO-PROFILE] Jogo detectado: {exe_name} ➔ Alternando para perfil: {profile_id}")
                    if asyncio_loop:
                        msg = json.dumps({
                            "type": "auto_profile_switch",
                            "profile_id": profile_id,
                            "game_name": exe_name
                        })
                        asyncio_loop.call_soon_threadsafe(
                            lambda m=msg: asyncio.create_task(broadcast_to_all(m))
                        )
        except Exception:
            pass


# --- GERENCIADOR DE JOGADORES MULTIPLAYER (ATÉ 4 CONTROLES XBOX VIRTUAIS) ---
class PlayerController:
    """Gerencia um controle virtual individual de Xbox 360 para um Player (P1 a P4)."""

    def __init__(self, player_id):
        self.player_id = player_id
        self.gamepad = None
        self.mode = "gamepad"
        self.kb_pressed = set()
        self.websocket = None
        self.last_rumble_sent_time = 0.0
        self.last_rumble_values = (0, 0)

        if HAVE_VGAMEPAD:
            try:
                self.gamepad = vg.VX360Gamepad()

                # Registra callback de Rumble específico para este player
                def rumble_callback(client, target, large_motor, small_motor, led_number, user_data):
                    self.send_rumble_sync(large_motor, small_motor)

                self.gamepad.register_notification(rumble_callback)
                print(f"[OK] Player {player_id}: Controle Virtual Xbox 360 alocado via ViGEmBus!")
            except Exception as e:
                print(f"[!] Player {player_id}: Erro ao criar VX360Gamepad: {e}")
                self.mode = "keyboard"
        else:
            self.mode = "keyboard"

    def send_rumble_sync(self, large_motor, small_motor):
        global asyncio_loop
        if not (asyncio_loop and asyncio_loop.is_running() and self.websocket):
            return

        now = time.time()
        l, s = int(large_motor), int(small_motor)

        if l == 0 and s == 0:
            if self.last_rumble_values != (0, 0):
                self.last_rumble_values = (0, 0)
                self.last_rumble_sent_time = now
                asyncio_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self.send_rumble_async(0, 0))
                )
            return

        diff = max(abs(l - self.last_rumble_values[0]), abs(s - self.last_rumble_values[1]))
        if (now - self.last_rumble_sent_time >= 0.05) or (diff >= 35):
            self.last_rumble_values = (l, s)
            self.last_rumble_sent_time = now
            asyncio_loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.send_rumble_async(l, s))
            )

    async def send_rumble_async(self, large_motor, small_motor):
        if not self.websocket:
            return
        msg = json.dumps({
            "type": "rumble",
            "player_id": self.player_id,
            "large": int(large_motor),
            "small": int(small_motor)
        })
        try:
            await self.websocket.send(msg)
        except Exception:
            pass

    def _set_btn(self, button_enum, is_pressed):
        if not self.gamepad:
            return
        if is_pressed:
            self.gamepad.press_button(button=button_enum)
        else:
            self.gamepad.release_button(button=button_enum)

    def handle_wheel_input(self, data):
        """Processa dados do Modo Volante de Corrida."""
        steer = max(-1.0, min(1.0, float(data.get("steer", 0.0))))
        gas = max(0.0, min(1.0, float(data.get("gas", 0.0))))
        brake = max(0.0, min(1.0, float(data.get("brake", 0.0))))
        handbrake = bool(data.get("handbrake", False))
        nitro = bool(data.get("nitro", False))
        gear_up = bool(data.get("gear_up", False))
        gear_down = bool(data.get("gear_down", False))
        camera = bool(data.get("camera", False))
        home = bool(data.get("home", False))
        pause = bool(data.get("pause", False))

        if self.gamepad:
            self.gamepad.left_joystick_float(x_value_float=steer, y_value_float=0.0)
            self.gamepad.right_trigger_float(value_float=gas)
            self.gamepad.left_trigger_float(value_float=brake)

            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_A, handbrake)
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_X, nitro)
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_Y, camera)
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_GUIDE, home)
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, gear_up)
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER, gear_down)
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_START, pause)
            self.gamepad.update()
        elif HAVE_PYNPUT and kb and self.player_id == 1:
            self._set_key('w', gas > 0.2)
            self._set_key('s', brake > 0.2)
            self._set_key('a', steer < -0.2)
            self._set_key('d', steer > 0.2)
            self._set_key(Key.space, handbrake)
            self._set_key(Key.shift, nitro)
            self._set_key('c', camera)

    def handle_gamepad_input(self, data):
        """Processa dados do Modo Gamepad Completo (Estilo Xbox 360)."""
        ls_x = max(-1.0, min(1.0, float(data.get("ls_x", 0.0))))
        ls_y = max(-1.0, min(1.0, float(data.get("ls_y", 0.0))))
        rs_x = max(-1.0, min(1.0, float(data.get("rs_x", 0.0))))
        rs_y = max(-1.0, min(1.0, float(data.get("rs_y", 0.0))))
        lt = max(0.0, min(1.0, float(data.get("lt", 0.0))))
        rt = max(0.0, min(1.0, float(data.get("rt", 0.0))))

        if self.gamepad:
            # Analógicos (Y invertido para padrão XInput: positivo é cima)
            self.gamepad.left_joystick_float(x_value_float=ls_x, y_value_float=ls_y)
            self.gamepad.right_joystick_float(x_value_float=rs_x, y_value_float=rs_y)

            # Gatilhos
            self.gamepad.left_trigger_float(value_float=lt)
            self.gamepad.right_trigger_float(value_float=rt)

            # D-Pad
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, bool(data.get("dpad_up")))
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, bool(data.get("dpad_down")))
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT, bool(data.get("dpad_left")))
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, bool(data.get("dpad_right")))

            # ABXY
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_A, bool(data.get("btn_a")))
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_B, bool(data.get("btn_b")))
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_X, bool(data.get("btn_x")))
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_Y, bool(data.get("btn_y")))

            # Bumpers
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER, bool(data.get("btn_lb")))
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, bool(data.get("btn_rb")))

            # L3 / R3 (Cliques dos analógicos)
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB, bool(data.get("btn_l3")))
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB, bool(data.get("btn_r3")))

            # Start / Select / Home (Xbox Guide / PS / Steam)
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_START, bool(data.get("btn_start")))
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK, bool(data.get("btn_select")))
            self._set_btn(vg.XUSB_BUTTON.XUSB_GAMEPAD_GUIDE, bool(data.get("btn_guide")))

            self.gamepad.update()
        elif HAVE_PYNPUT and kb and self.player_id == 1:
            self._set_key('w', ls_y > 0.3)
            self._set_key('s', ls_y < -0.3)
            self._set_key('a', ls_x < -0.3)
            self._set_key('d', ls_x > 0.3)
            self._set_key(Key.space, bool(data.get("btn_a")))

    def _set_key(self, key, should_press):
        if should_press and key not in self.kb_pressed:
            kb.press(key)
            self.kb_pressed.add(key)
        elif not should_press and key in self.kb_pressed:
            kb.release(key)
            self.kb_pressed.remove(key)

    def reset_all(self):
        if self.gamepad:
            self.gamepad.reset()
            self.gamepad.update()
        if HAVE_PYNPUT and kb:
            for k in list(self.kb_pressed):
                try:
                    kb.release(k)
                except Exception:
                    pass
            self.kb_pressed.clear()


class MultiplayerManager:
    """Aloca e gerencia até 4 jogadores simultâneos conectados por smartphone."""

    def __init__(self, max_players=4):
        self.max_players = max_players
        self.slots = [None] * max_players
        self.ws_to_player = {}

    def allocate(self, websocket):
        for idx in range(self.max_players):
            if self.slots[idx] is None:
                p_id = idx + 1
                ctrl = PlayerController(p_id)
                ctrl.websocket = websocket
                self.slots[idx] = ctrl
                self.ws_to_player[websocket] = ctrl
                return ctrl
        return None

    def release(self, websocket):
        if websocket in self.ws_to_player:
            ctrl = self.ws_to_player[websocket]
            idx = ctrl.player_id - 1
            ctrl.reset_all()
            if ctrl.gamepad:
                try:
                    del ctrl.gamepad
                except Exception:
                    pass
            self.slots[idx] = None
            del self.ws_to_player[websocket]
            print(f"[-] Player {ctrl.player_id} desconectado (Slot liberado).")

    def get_player(self, websocket):
        return self.ws_to_player.get(websocket)


multiplayer_mgr = MultiplayerManager(max_players=4)


# --- HANDLER WEBSOCKET (COMUM PARA WS E WSS) ---
async def ws_handler(websocket):
    client_ip = websocket.remote_address[0]
    ctrl = multiplayer_mgr.allocate(websocket)

    if not ctrl:
        print(f"\n[!] Conexão recusada para {client_ip}: Todos os 4 slots de jogadores estão ocupados.")
        await websocket.send(json.dumps({
            "type": "error",
            "message": "Servidor cheio! Máximo de 4 jogadores simultâneos atingido."
        }))
        return

    print(f"\n[+] Celular conectado! IP: {client_ip} ➔ ATRIBUÍDO: PLAYER {ctrl.player_id}")
    connected_clients.add(websocket)

    await websocket.send(json.dumps({
        "type": "welcome",
        "player_id": ctrl.player_id,
        "has_gamepad": HAVE_VGAMEPAD,
        "default_mode": ctrl.mode
    }))

    last_stats = time.time()
    packet_count = 0
    current_type = "input"

    try:
        async for message in websocket:
            packet_count += 1
            data = json.loads(message)
            msg_type = data.get("type", "input")
            current_type = msg_type

            if msg_type == "input":
                ctrl.handle_wheel_input(data)
            elif msg_type == "gamepad_input":
                ctrl.handle_gamepad_input(data)
            elif msg_type == "mouse_move":
                MouseKeyboardHandler.move(data.get("dx", 0), data.get("dy", 0))
            elif msg_type == "mouse_click":
                MouseKeyboardHandler.click(data.get("button", "left"), data.get("action", "click"))
            elif msg_type == "mouse_scroll":
                MouseKeyboardHandler.scroll(data.get("dy", 0))
            elif msg_type == "keyboard_input":
                MouseKeyboardHandler.type_key(data.get("key", ""))
            elif msg_type == "ping":
                await websocket.send(json.dumps({"type": "pong", "time": data.get("time")}))

            now = time.time()
            if now - last_stats >= 1.0:
                p_tag = f"[P{ctrl.player_id}]"
                if current_type == "input":
                    steer = float(data.get("steer", 0.0)) * 100
                    gas = float(data.get("gas", 0.0)) * 100
                    brake = float(data.get("brake", 0.0)) * 100
                    steer_str = f"◀ {abs(steer):4.1f}%" if steer < -1 else (f"{steer:4.1f}% ▶" if steer > 1 else "  CENTRO ")
                    print(f"\r{p_tag} [VOLANTE] {steer_str} | Gás: {gas:3.0f}% | Freio: {brake:3.0f}% | {packet_count} pps ", end="", flush=True)
                else:
                    ls_x = float(data.get("ls_x", 0.0))
                    ls_y = float(data.get("ls_y", 0.0))
                    print(f"\r{p_tag} [GAMEPAD] LS: ({ls_x:+.2f}, {ls_y:+.2f}) | LT: {float(data.get('lt', 0)):.1f} | RT: {float(data.get('rt', 0)):.1f} | {packet_count} pps ", end="", flush=True)

                packet_count = 0
                last_stats = now

    except Exception:
        pass
    finally:
        connected_clients.discard(websocket)
        multiplayer_mgr.release(websocket)


async def main():
    import websockets
    global asyncio_loop
    asyncio_loop = asyncio.get_running_loop()

    local_ip = get_local_ip()
    ensure_ssl_certs(local_ip)

    # Cria contexto SSL para HTTPS e WSS
    ssl_ctx = None
    if os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH):
        try:
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_ctx.load_cert_chain(CERT_PATH, KEY_PATH)
        except Exception as e:
            print(f"[!] Erro ao criar SSLContext: {e}")

    # Inicia servidores HTTP e HTTPS
    start_http_servers("0.0.0.0", HTTP_PORT, HTTPS_PORT, ssl_ctx)

    https_url = f"https://{local_ip}:{HTTPS_PORT}"
    http_url = f"http://{local_ip}:{HTTP_PORT}"

    print("=" * 66)
    print("      🏎️  REMOTE WHEEL & GAMEPAD - Mobile -> PC Virtual Pad  🎮")
    print("=" * 66)
    print(f"\n1. Conecte o seu celular na MESMA rede Wi-Fi deste PC.")
    print(f"\n👉 LINK RECOMENDADO (HTTPS - Libera o Giroscópio/Acelerômetro):")
    print(f"   {https_url}")
    print(f"   (No Chrome do celular, toque em 'Avançado' -> 'Prosseguir')")
    print(f"\n👉 Link alternativo (HTTP simples):")
    print(f"   {http_url}")

    if qrcode:
        print("\nQR Code para escanear com a câmera do celular (HTTPS):")
        qr = qrcode.QRCode(box_size=1, border=2)
        qr.add_data(https_url)
        qr.make(fit=True)
        try:
            qr.print_ascii(invert=True)
        except Exception:
            pass

    print(f"\nServidores WebSocket ativos nas portas {WS_PORT} (WS) e {WSS_PORT} (WSS)...")
    print("=" * 66 + "\n")

    # Inicia threads em segundo plano para Telemetria UDP, OCR do The Crew 2 e Detecção de Jogos
    threading.Thread(target=telemetry_udp_listener, daemon=True).start()
    threading.Thread(target=the_crew_ocr.run_loop, daemon=True).start()
    threading.Thread(target=auto_game_detector_loop, daemon=True).start()

    # Inicia servidores WebSocket
    await websockets.serve(ws_handler, "0.0.0.0", WS_PORT)
    if ssl_ctx:
        await websockets.serve(ws_handler, "0.0.0.0", WSS_PORT, ssl=ssl_ctx)

    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Encerrando Remote Wheel...")
        sys.exit(0)
