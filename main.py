import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hardware import get_hardware, GREEN_LED_PIN, RED_LED_PIN

logger = logging.getLogger("rpi_hardware_project.main")

app = FastAPI(title="Raspberry Pi 5 Hardware API")
app.mount("/dashboard", StaticFiles(directory="static", html=True), name="static")

hardware = get_hardware()

ACCESS_SEQUENCE = [1, 2, 1]
MAX_FAILED_ATTEMPTS = 3
BUTTON_PIN_MAP = {14: 1, 15: 2}

state: Dict[str, Any] = {
    "current_sequence": [],
    "failed_attempts": 0,
    "logs": [],
    # SE AÑADE: Estado virtual de los botones para el Dashboard
    "buttons": {"14": False, "15": False},
}


class AccessAttempt(BaseModel):
    button_id: int


class TelemetryReport(BaseModel):
    temperature_c: float
    luminosity_lux: float
    timestamp: Optional[str] = None


@app.on_event("startup")
async def startup_event() -> None:
    hardware.initialize()
    logger.info("Hardware inicializado en startup")
    # Lanzar monitor de botones en segundo plano para evitar que procesos externos
    # intenten acceder al GPIO directamente y provoquen conflictos.
    try:
        asyncio.create_task(_monitor_buttons_loop())
        logger.info("Monitor de botones iniciado en background")
    except Exception as exc:
        logger.warning("No se pudo iniciar monitor de botones: %s", exc)


async def _pulse_led(pin: int, duration: float) -> None:
    try:
        hardware.set_led_state(pin, True)
        await asyncio.sleep(duration)
    finally:
        hardware.set_led_state(pin, False)


def _log_attempt(request: Optional[Request], result: str, button_id: int) -> None:
    ip = "unknown"
    user_agent = "unknown"
    if request is not None:
        ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
    else:
        ip = "local"
        user_agent = "local"

    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "ip": ip,
        "user_agent": user_agent,
        "button_id": button_id,
        "result": result,
    }
    state["logs"].append(record)


def _handle_button_press(button_id: int, request: Optional[Request] = None) -> Dict[str, Any]:
    """Procesa internamente una pulsación de botón (puede venir del API o del monitor local)."""
    if button_id not in [1, 2]:
        return {"status": "error", "detail": "button_id must be 1 or 2"}

    state["current_sequence"].append(button_id)
    logger.info("Intento de acceso (interno): %s", state["current_sequence"])

    if len(state["current_sequence"]) < len(ACCESS_SEQUENCE):
        return {
            "status": "pending",
            "current_sequence": state["current_sequence"],
            "required_length": len(ACCESS_SEQUENCE),
        }

    if state["current_sequence"] == ACCESS_SEQUENCE:
        _log_attempt(request, "ACCESO CONCEDIDO", button_id)
        state["current_sequence"] = []
        state["failed_attempts"] = 0
        # ACCESO CONCEDIDO: LED VERDE (GPIO 12)
        asyncio.create_task(_pulse_led(GREEN_LED_PIN, 3.0)) 
        return {"status": "granted", "message": "Acceso concedido"}

    state["current_sequence"] = []
    state["failed_attempts"] += 1
    if state["failed_attempts"] >= MAX_FAILED_ATTEMPTS:
        _log_attempt(request, "ACCESO DENEGADO", button_id)
        state["failed_attempts"] = 0
        # FALLO: LED ROJO (GPIO 13)
        asyncio.create_task(_pulse_led(RED_LED_PIN, 3.0)) 
        return {"status": "denied", "message": "Acceso denegado tras 3 intentos fallidos"}

    state["logs"].append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "ip": request.client.host if request and request.client else "local",
        "user_agent": request.headers.get("user-agent", "local") if request else "local",
        "button_id": button_id,
        "result": "INTENTO FALLIDO",
    })
    return {
        "status": "failed",
        "message": "Secuencia incorrecta. Sigue intentando.",
        "failed_attempts": state["failed_attempts"],
    }


@app.post("/access/attempt")
async def access_attempt(attempt: AccessAttempt, request: Request) -> Dict[str, Any]:
    # SE AÑADE: Identificación del pin para el Dashboard
    pin_afectado = "14" if attempt.button_id == 1 else "15"
    
    # SE AÑADE: Forzar cambio visual a True
    state["buttons"][pin_afectado] = True
    
    response = _handle_button_press(attempt.button_id, request=request)
    
    # SE AÑADE: Tarea asíncrona para liberar el botón en la web
    async def liberar_boton():
        await asyncio.sleep(1.5)
        state["buttons"][pin_afectado] = False
        
    asyncio.create_task(liberar_boton())
    
    return response


async def _monitor_buttons_loop() -> None:
    # IMPORTANTE: Inicializamos en True (estado reposo para pull-up)
    previous_states = {pin: True for pin in BUTTON_PIN_MAP}
    try:
        while True:
            current_states = hardware.get_button_states()
            for pin, button_id in BUTTON_PIN_MAP.items():
                # INVERSIÓN: Leemos el estado y aplicamos 'not'
                # Si el hardware devuelve True (reposo), current_pressed es False.
                # Si el hardware devuelve False (pulsado), current_pressed es True.
                current_pressed = not bool(current_states.get(str(pin), True))
                
                # Detectamos el flanco: cuando cambia de False a True
                if current_pressed and not previous_states[pin]:
                    logger.info("Botón físico detectado en pin %s -> id %s", pin, button_id)
                    _handle_button_press(button_id, request=None)
                
                previous_states[pin] = current_pressed
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        logger.info("Monitor de botones detenido")


@app.get("/status")
async def status() -> Dict[str, Any]:
    sensors = hardware.get_sensor_readings()
    peripherals = {
        "leds": hardware.get_led_states(),
        # SE MODIFICA: Ahora lee el estado interno reactivo en lugar de hardware ciego
        "buttons": state["buttons"],
    }
    return {
        "sensors": sensors,
        "peripherals": peripherals,
        "logs": state["logs"],
    }


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/telemetry")
async def telemetry(report: TelemetryReport, request: Request) -> Dict[str, Any]:
    record = {
        "timestamp": report.timestamp or datetime.utcnow().isoformat() + "Z",
        "ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "temperature_c": report.temperature_c,
        "luminosity_lux": report.luminosity_lux,
    }
    logger.info("Telemetry received: %s", record)
    return {"status": "accepted", "received": record}


@app.post("/led/{pin}/on")
async def led_on(pin: int) -> Dict[str, Any]:
    configured = hardware.get_configured_led_pins()
    if pin not in configured:
        raise HTTPException(status_code=404, detail=f"LED pin {pin} no configurado")
    try:
        is_lit = hardware.set_led_state(pin, True)
        return {"status": "ok", "pin": pin, "is_lit": is_lit}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/led/{pin}/off")
async def led_off(pin: int) -> Dict[str, Any]:
    configured = hardware.get_configured_led_pins()
    if pin not in configured:
        raise HTTPException(status_code=404, detail=f"LED pin {pin} no configurado")
    try:
        is_lit = hardware.set_led_state(pin, False)
        return {"status": "ok", "pin": pin, "is_lit": is_lit}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard/")