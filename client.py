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

# 1. Botones 
try:
    boton_1 = Button(14, pull_up=False)
    boton_2 = Button(15, pull_up=False)
    botones_ok = True
    print("[client] Botones inicializados (Pines 14 y 15).")
except Exception as e:
    print(f"[client] Error en botones: {e}")

# 2. LEDs Físicos
try:
    led_verde = LED(12)
    led_rojo = LED(13)
    leds_ok = True
    print("[client] LEDs inicializados (Pines 12 y 13).")
except Exception as e:
    print(f"[client] Error en LEDs: {e}")

# 3. ADC (Corrección por índices numéricos)
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c)
    canal_ntc = AnalogIn(ads, 0)  # Pin 0 del ADC
    canal_ldr = AnalogIn(ads, 1)  # Pin 1 del ADC
    adc_ok = True
    print("[client] ADC ADS1115 inicializado.")
except Exception as e:
    print(f"[client] Error en ADC: {e}")

# ------------------------------------

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

def actualizar_leds_locales(respuesta_servidor: Dict) -> None:
    """Modifica los pines de los LEDs basándose en la respuesta de la API."""
    if not leds_ok or not respuesta_servidor:
        return
    
    # Se extrae el estado de los componentes devuelto por el backend
    # Ajustar las claves ('led_verde', 'led_rojo') según la respuesta exacta de tu API
    estado_perifericos = respuesta_servidor.get("peripherals", {})
    
    if "led_verde" in estado_perifericos:
        if estado_perifericos["led_verde"] == "Encendido" or estado_perifericos["led_verde"] is True:
            led_verde.on()
        else:
            led_verde.off()

    if "led_rojo" in estado_perifericos:
        if estado_perifericos["led_rojo"] == "Encendido" or estado_perifericos["led_rojo"] is True:
            led_rojo.on()
        else:
            led_rojo.off()

def send_access_attempt(button_id: int) -> None:
    print(f"[client] Botón {button_id} pulsado. Enviando intento...")
    result = post_json("/access/attempt", {"button_id": button_id})
    # Al recibir la respuesta del intento de acceso, se actualizan los LEDs inmediatamente
    actualizar_leds_locales(result)

def send_telemetry() -> None:
    temp_c = round(canal_ntc.voltage * 10, 2) if adc_ok else 0.0
    lux = round(canal_ldr.voltage * 100, 2) if adc_ok else 0.0

    # Se lee el estado lógico invertido si se usa pull-up interno, 
    # para enviar al servidor si realmente están presionados (True) o no (False)
    payload = {
        "temperature_c": temp_c,
        "luminosity_lux": lux,
        "button_1_pressed": boton_1.is_pressed if botones_ok else False,
        "button_2_pressed": boton_2.is_pressed if botones_ok else False,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    
    print(f"[client] Enviando telemetría y estados: {payload}")
    result = post_json("/telemetry", payload)
    # La telemetría cíclica también aprovecha para actualizar los LEDs si cambiaron desde la web
    actualizar_leds_locales(result)

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
        print("Detenido.")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", action="store_true")
    args = parser.parse_args()
    interactive_loop(auto=args.auto)

if __name__ == "__main__":
    main()