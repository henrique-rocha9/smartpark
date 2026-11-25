"""
SmartPark Sim - Monitoramento de vagas (ESP32 + HC-SR04 + API REST)
Fluxo: HC-SR04 -> ESP32 (filtro/estado) -> LEDs/OLED -> Wi-Fi -> HTTPS -> Supabase
"""
import sys
import time
import select
import network
import urequests
import json
from machine import Pin, I2C, time_pulse_us
import secrets  # API_URL e DEVICE_KEY (arquivo secrets.py, fora do GitHub)

try:
    from ssd1306 import SSD1306_I2C
except ImportError:
    SSD1306_I2C = None

# ======================= CONFIGURACOES =======================
WIFI_SSID = "Wokwi-GUEST"
WIFI_SENHA = ""
DISPOSITIVO = "esp32-smartpark-01"

LIMIAR_OCUPADA_CM = 20.0
DIST_MIN_CM = 2.0
DIST_MAX_CM = 400.0
TIMEOUT_ECHO_US = 30000
INTERVALO_LEITURA_MS = 2000
INTERVALO_WIFI_MS = 10000
CONFIRMACOES = 2

ESTADO_DESCONHECIDO = 0
ESTADO_LIVRE = 1
ESTADO_OCUPADA = 2
TEXTO_ESTADO = {0: "desconhecido", 1: "livre", 2: "ocupada"}

PIN_SDA = 21
PIN_SCL = 22
OLED_ENDERECO = 0x3C


# ======================= DADOS DAS VAGAS =======================
class Vaga:
    def __init__(self, numero, pin_trig, pin_echo, pin_led_verde, pin_led_vermelho):
        self.numero = numero
        self.trig = Pin(pin_trig, Pin.OUT, value=0)
        self.echo = Pin(pin_echo, Pin.IN)
        self.led_verde = Pin(pin_led_verde, Pin.OUT, value=0)
        self.led_vermelho = Pin(pin_led_vermelho, Pin.OUT, value=0)
        self.estado = ESTADO_DESCONHECIDO
        self.candidato = ESTADO_DESCONHECIDO
        self.contagem = 0
        self.distancia = None
        self.leitura_valida = False
        self.falhas_seguidas = 0


# TRIG, ECHO, LED verde, LED vermelho
vagas = [
    Vaga(1, 13, 34, 16, 17),
    Vaga(2, 14, 35, 18, 19),
    Vaga(3, 27, 32, 23, 25),
]

# ======================= ESTADO GLOBAL =======================
sta = network.WLAN(network.STA_IF)
oled = None
wifi_estava_conectado = False
ultima_wifi = None
api_ok = False
poll_serial = select.poll()
poll_serial.register(sys.stdin, select.POLLIN)


# ======================= AUXILIARES =======================
def contar_vagas():
    livres = 0
    ocupadas = 0
    for v in vagas:
        if v.estado == ESTADO_LIVRE:
            livres += 1
        elif v.estado == ESTADO_OCUPADA:
            ocupadas += 1
    return livres, ocupadas


def passou(inicio, intervalo_ms):
    return inicio is None or time.ticks_diff(time.ticks_ms(), inicio) >= intervalo_ms


# ======================= WI-FI (NAO BLOQUEANTE) =======================
def conectar_wifi():
    global wifi_estava_conectado, ultima_wifi
    conectado = sta.isconnected()
    if conectado and not wifi_estava_conectado:
        print("[WIFI] Conectado. IP:", sta.ifconfig()[0])
    if not conectado and wifi_estava_conectado:
        print("[WIFI] Conexao perdida.")
    wifi_estava_conectado = conectado
    if conectado:
        return
    if not passou(ultima_wifi, INTERVALO_WIFI_MS):
        return
    ultima_wifi = time.ticks_ms()
    print("[WIFI] Tentando conectar a Wokwi-GUEST...")
    sta.connect(WIFI_SSID, WIFI_SENHA)


# ======================= SENSOR HC-SR04 =======================
def ler_distancia(v):
    """Distancia em cm, ou None se invalida/timeout."""
    v.trig.value(0)
    time.sleep_us(2)
    v.trig.value(1)
    time.sleep_us(10)
    v.trig.value(0)
    duracao_us = time_pulse_us(v.echo, 1, TIMEOUT_ECHO_US)
    if duracao_us < 0:
        return None
    distancia_cm = duracao_us / 58.0
    if distancia_cm < DIST_MIN_CM or distancia_cm > DIST_MAX_CM:
        return None
    return distancia_cm


def classificar_vaga(v, distancia_cm):
    """Filtro de confirmacao. Retorna True se o estado mudou."""
    lido = ESTADO_OCUPADA if distancia_cm < LIMIAR_OCUPADA_CM else ESTADO_LIVRE

    if v.estado == ESTADO_DESCONHECIDO:
        v.estado = lido
        v.candidato = lido
        v.contagem = 0
        return True

    if lido == v.estado:
        v.candidato = v.estado
        v.contagem = 0
        return False

    if lido == v.candidato:
        v.contagem += 1
    else:
        v.candidato = lido
        v.contagem = 1

    if v.contagem >= CONFIRMACOES:
        v.estado = lido
        v.contagem = 0
        return True
    return False


# ======================= SAIDAS LOCAIS =======================
def atualizar_leds(v):
    v.led_verde.value(1 if v.estado == ESTADO_LIVRE else 0)
    v.led_vermelho.value(1 if v.estado == ESTADO_OCUPADA else 0)


def atualizar_oled():
    if oled is None:
        return
    livres, ocupadas = contar_vagas()
    oled.fill(0)
    oled.text("SmartPark Sim", 0, 0)
    oled.hline(0, 11, 128, 1)
    oled.text("Livres: %d" % livres, 0, 22)
    oled.text("Ocupadas: %d" % ocupadas, 0, 36)
    oled.text("WiFi:%s API:%s" % ("OK" if sta.isconnected() else "--",
                                  "OK" if api_ok else "--"), 0, 54)
    oled.show()


# ======================= ENVIO PARA A API =======================
def enviar_api():
    global api_ok
    if not sta.isconnected():
        api_ok = False
        print("[API] sem Wi-Fi, envio adiado")
        return
    vs = [{"vaga": v.numero,
           "status": TEXTO_ESTADO[v.estado],
           "distancia_cm": round(v.distancia, 1) if v.leitura_valida else None}
          for v in vagas if v.estado != ESTADO_DESCONHECIDO]
    if not vs:
        return
    try:
        r = urequests.post(
            secrets.API_URL,
            data=json.dumps({"dispositivo": DISPOSITIVO, "vagas": vs}),
            headers={"Content-Type": "application/json",
                     "x-device-key": secrets.DEVICE_KEY})
        print("[API] HTTP", r.status_code)
        api_ok = (r.status_code == 200)
        r.close()
    except Exception as e:
        api_ok = False
        print("[API] ERRO", e)


# ======================= CICLO DE LEITURA =======================
def ciclo_leitura():
    for v in vagas:
        d = ler_distancia(v)
        if d is None:
            v.leitura_valida = False
            v.falhas_seguidas += 1
            print("[SENSOR] Vaga %d: leitura invalida/timeout (falhas: %d)" %
                  (v.numero, v.falhas_seguidas))
        else:
            v.leitura_valida = True
            v.distancia = d
            v.falhas_seguidas = 0
            mudou = classificar_vaga(v, d)
            print("[SENSOR] Vaga %d: %.1f cm -> %s" % (v.numero, d, TEXTO_ESTADO[v.estado]))
            if mudou:
                print("[EVENTO] Vaga %d mudou para %s" % (v.numero, TEXTO_ESTADO[v.estado]))
        atualizar_leds(v)

    enviar_api()
    atualizar_oled()


# ======================= COMANDO DE TESTE (terminal) =======================
# tecla w = derruba o Wi-Fi
def tratar_comandos_serial():
    while poll_serial.poll(0):
        c = sys.stdin.read(1)
        if c == "w":
            print("[TESTE] Forcando queda do Wi-Fi.")
            sta.disconnect()


# ======================= PROGRAMA PRINCIPAL =======================
def main():
    global oled
    print("\n=== SmartPark Sim iniciando (MicroPython) ===")

    if SSD1306_I2C is None:
        print("[OLED] ssd1306.py nao encontrado (sem display).")
    else:
        try:
            i2c = I2C(0, scl=Pin(PIN_SCL), sda=Pin(PIN_SDA), freq=400000)
            oled = SSD1306_I2C(128, 64, i2c, OLED_ENDERECO)
        except Exception as e:
            print("[OLED] Falha ao iniciar (%s)." % e)
    atualizar_oled()

    sta.active(True)
    for tentativa in range(3):
        print("[WIFI] Tentativa", tentativa + 1, end=" ")
        sta.disconnect()
        time.sleep_ms(500)
        sta.connect(WIFI_SSID, WIFI_SENHA)
        t0 = time.ticks_ms()
        while not sta.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < 10000:
            print(".", end="")
            time.sleep_ms(300)
        print()
        if sta.isconnected():
            break
    ultima_leitura = time.ticks_add(time.ticks_ms(), -INTERVALO_LEITURA_MS)

    while True:
        conectar_wifi()
        tratar_comandos_serial()
        if time.ticks_diff(time.ticks_ms(), ultima_leitura) >= INTERVALO_LEITURA_MS:
            ultima_leitura = time.ticks_ms()
            ciclo_leitura()
        time.sleep_ms(20)


if __name__ == "__main__":
    main()
