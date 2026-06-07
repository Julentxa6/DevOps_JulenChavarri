import argparse
import json
import random
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Dict

# Cambia entre la URL local y la URL de producción en Render
API_BASE_URL = "http://localhost:8000"
# API_BASE_URL = "https://tu-app-en-render.onrender.com"

HEADERS = {
    "User-Agent": "RaspberryPi5-Client",
    "Content-Type": "application/json",
}

BUTTON_IDS = [1, 2]


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
    print(f"[client] Botón {button_id} pulsado. Enviando intento de acceso...")
    result = post_json("/access/attempt", {"button_id": button_id})
    print(f"[client] Respuesta de acceso: {result}")


def send_telemetry() -> None:
    # Cliente ya no accede al hardware; usamos datos simulados
    payload = {
        "temperature_c": round(random.uniform(20.0, 26.0), 2),
        "luminosity_lux": round(random.uniform(100.0, 800.0), 2),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    print(f"[client] Enviando telemetría: {payload}")
    result = post_json("/telemetry", payload)
    print(f"[client] Respuesta de telemetría: {result}")


def interactive_loop(auto: bool = False, telemetry_interval: float = 5.0) -> None:
    print("Cliente HTTP interactivo. Presiona '1' o '2' para enviar intentos de acceso, 't' para telemetría, 'q' para salir.")
    last_telemetry = 0.0
    try:
        while True:
            if auto:
                now = time.time()
                if now - last_telemetry >= telemetry_interval:
                    send_telemetry()
                    last_telemetry = now
                # Simular pulsación aleatoria ocasional
                if random.random() < 0.05:
                    send_access_attempt(random.choice(BUTTON_IDS))
                time.sleep(0.1)
                continue

            # modo interactivo por teclado
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
    parser = argparse.ArgumentParser(description="Cliente HTTP del sistema de acceso (sin GPIO)")
    parser.add_argument("--auto", action="store_true", help="Enviar telemetría y eventos de forma automática (simulada)")
    args = parser.parse_args()

    print("Cliente HTTP iniciado (sin acceso a hardware).")
    print(f"API base: {API_BASE_URL}")
    interactive_loop(auto=args.auto)


if __name__ == "__main__":
    main()
