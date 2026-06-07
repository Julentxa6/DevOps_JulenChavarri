import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Dict

# Importaciones para el hardware físico de la Raspberry Pi
from gpiozero import Button
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

API_BASE_URL = "https://devops-julenchavarri.onrender.com"

HEADERS = {
    "User-Agent": "RaspberryPi5-Client",
    "Content-Type": "application/json",
}

# --- INICIALIZACIÓN DEL HARDWARE EN BLOQUES SEPARADOS ---
botones_ok = False
adc_ok = False

# 1. Inicialización de los Botones
try:
    boton_1 = Button(14)
    boton_2 = Button(15)
    botones_ok = True
    print("[client] Botones físicos (pines 14 y 15) inicializados correctamente.")
except Exception as e:
    print(f"[client] Error inicializando botones físicos: {e}")

# 2. Inicialización del ADC (Con corrección de constantes)
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    
    # CORRECCIÓN SINTAXIS: Se utiliza AnalogIn.P0 y AnalogIn.P1
    canal_ntc = AnalogIn(ads, 1)
    canal_ldr = AnalogIn(ads, 0)
    adc_ok = True
    print("[client] ADC ADS1115 e hilos analógicos inicializados correctamente.")
except Exception as e:
    print(f"[client] Error inicializando ADC: {e}")

hardware_ok = botones_ok or adc_ok
# -------------------------------------------------------

def post_json(endpoint: str, payload: Dict) -> Dict:
    url = f"{API_BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        payload_text = payload if isinstance(payload, str) else json.dumps(payload)
        print(f"HTTP error al enviar {endpoint}: {exc.code} {exc.reason} - {payload_text}")
    except urllib.error.URLError as exc:
        print(f"Error de conexión al enviar {endpoint}: {exc.reason}")
    except ValueError as exc:
        print(f"Error al parsear respuesta JSON de {endpoint}: {exc}")
    except Exception as exc:
        print(f"Error inesperado al enviar {endpoint}: {exc}")
    return {}

def send_access_attempt(button_id: int) -> None:
    print(f"[client] Botón {button_id} pulsado físicamente. Enviando intento de acceso...")
    result = post_json("/access/attempt", {"button_id": button_id})
    print(f"[client] Respuesta de acceso del servidor: {result}")

def send_telemetry() -> None:
    if adc_ok:
        # Reemplazar con las ecuaciones reales de calibración si fuera necesario
        temp_c = round(canal_ntc.voltage * 10, 2)
        lux = round(canal_ldr.voltage * 100, 2)
    else:
        temp_c = 0.0
        lux = 0.0

    payload = {
        "temperature_c": temp_c,
        "luminosity_lux": lux,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    print(f"[client] Enviando telemetría real: {payload}")
    result = post_json("/telemetry", payload)
    print(f"[client] Respuesta de telemetría del servidor: {result}")

# --- VINCULACIÓN ASÍNCRONA DE EVENTOS ---
if botones_ok:
    boton_1.when_pressed = lambda: send_access_attempt(1)
    boton_2.when_pressed = lambda: send_access_attempt(2)
    print("[client] Eventos físicos asignados a los botones.")
# -----------------------------------------

def interactive_loop(auto: bool = False, telemetry_interval: float = 5.0) -> None:
    print("Cliente HTTP activo.")
    print("Controles manuales por teclado: '1' o '2' para forzar accesos, 't' para telemetría, 'q' para salir.")
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
            if cmd == "q":
                print("Saliendo.")
                break
            if cmd == "t":
                send_telemetry()
                continue
            if cmd in ("1", "2"):
                send_access_attempt(int(cmd))
                continue
            print("Comando no reconocido. Usa '1', '2', 't' o 'q'.")
    except KeyboardInterrupt:
        print("Interrumpido por usuario.")

def main() -> None:
    parser = argparse.ArgumentParser(description="Cliente HTTP del sistema de acceso con GPIO")
    parser.add_argument("--auto", action="store_true", help="Enviar telemetría de forma automática")
    args = parser.parse_args()

    print(f"API base configurada: {API_BASE_URL}")
    interactive_loop(auto=args.auto)

if __name__ == "__main__":
    main()