import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Dict

from gpiozero import Button, LED
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

API_BASE_URL = "https://devops-julenchavarri.onrender.com"

HEADERS = {
    "User-Agent": "RaspberryPi5-Client",
    "Content-Type": "application/json",
}

# --- INICIALIZACIÓN DEL HARDWARE ---
botones_ok = False
leds_ok = False
adc_ok = False

try:
    # Se reactivan los botones localmente con pull_up=True para mantener el pin estable.
    # Se añade bounce_time=0.2 (200 ms) para evitar falsos flancos o ráfagas repetidas.
    boton_1 = Button(14, pull_up=True, bounce_time=0.2)
    boton_2 = Button(15, pull_up=True, bounce_time=0.2)
    botones_ok = True
    print("[client] Botones inicializados localmente (Pines 14 y 15) con filtro de rebotes.")
except Exception as e:
    print(f"[client] Error en botones: {e}")

try:
    led_verde = LED(12)
    led_rojo = LED(13)
    leds_ok = True
    print("[client] LEDs inicializados correctamente (Pines 12 y 13).")
except Exception as e:
    print(f"[client] Error en LEDs: {e}")

try:
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    canal_ntc = AnalogIn(ads, 0)
    canal_ldr = AnalogIn(ads, 1)
    adc_ok = True
    print("[client] ADC ADS1115 operativo.")
except Exception as e:
    print(f"[client] Error en ADC: {e}")

# ------------------------------------------------------------

def post_json(endpoint: str, payload: Dict) -> Dict:
    url = f"{API_BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except Exception as exc:
        print(f"[client] Error en comunicación con {endpoint}: {exc}")
    return {}

def fetch_and_sync_status() -> None:
    """Consulta el endpoint /status para replicar el estado de los LEDs dictado por el backend."""
    if not leds_ok:
        return
    url = f"{API_BASE_URL}/status"
    request = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            res_json = json.loads(response.read().decode("utf-8"))
            
            perif = res_json.get("peripherals", {})
            leds_state = perif.get("leds", {}) 
            
            # Sincronización de los LEDs basándose en la respuesta del backend
            estado_v = leds_state.get("12", leds_state.get(12, False))
            estado_r = leds_state.get("13", leds_state.get(13, False))
            
            if estado_v:
                led_verde.on()
            else:
                led_verde.off()
                
            if estado_r:
                led_rojo.on()
            else:
                led_rojo.off()
    except Exception as exc:
        print(f"[client] Error sincronizando LEDs desde /status: {exc}")

def send_access_attempt(button_id: int) -> None:
    """Envía la pulsación detectada localmente hacia el endpoint de la API."""
    print(f"[client] Botón {button_id} presionado físicamente. Enviando intento a la API...")
    
    post_json("/access/attempt", {"button_id": button_id}) 
    
    # Se espera un instante a que el backend procese el cambio y se actualizan los LEDs locales
    time.sleep(0.1)
    fetch_and_sync_status()

def send_telemetry() -> None:
    """Envía los reportes de los sensores usando el modelo estricto TelemetryReport."""
    temp_c = round(canal_ntc.voltage * 10, 2) if adc_ok else 0.0
    lux = round(canal_ldr.voltage * 100, 2) if adc_ok else 0.0

    payload = {
        "temperature_c": temp_c,
        "luminosity_lux": lux,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    
    print(f"[client] Enviando telemetría válida: {payload}")
    post_json("/telemetry", payload) 
    
    # Se aprovecha el ciclo automático de telemetría para refrescar el estado de los LEDs
    fetch_and_sync_status()

# Se asignan los eventos de interrupción locales de forma directa
if botones_ok:
    boton_1.when_pressed = lambda: send_access_attempt(1)
    boton_2.when_pressed = lambda: send_access_attempt(2)

def interactive_loop(auto: bool = False, telemetry_interval: float = 2.0) -> None:
    print("Cliente HTTP unificado corriendo...")
    last_telemetry = 0.0
    try:
        while True:
            if auto:
                now = time.time()
                if now - last_telemetry >= telemetry_interval:
                    send_telemetry()
                    last_telemetry = now
                time.sleep(0.1)
                continue
            
            cmd = input("cmd> ").strip().lower()
            if cmd == "q": break
            if cmd == "t": send_telemetry()
    except KeyboardInterrupt:
        print("Detenido por el usuario.")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", action="store_true")
    args = parser.parse_args()
    interactive_loop(auto=args.auto)

if __name__ == "__main__":
    main()