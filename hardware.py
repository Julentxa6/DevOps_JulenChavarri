import logging
import os
import fcntl
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("rpi_hardware_project.hardware")

try:
    from gpiozero import Device, LED, Button
except Exception as exc:
    LED = None
    Button = None
    logger.warning("No se pudo importar gpiozero: %s", exc)

try:
    import board
    import busio
except Exception as exc:
    board = None
    busio = None
    logger.warning("No se pudo importar board/busio: %s", exc)

try:
    from adafruit_ads1x15.ads1115 import ADS1115
except Exception as exc:
    ADS1115 = None
    logger.warning("No se pudo importar adafruit_ads1x15: %s", exc)

if "GPIOZERO_PIN_FACTORY" not in os.environ:
    try:
        if LED is not None and Device.pin_factory is None:
            from gpiozero.pins.rpigpio import RPiGPIOFactory

            Device.pin_factory = RPiGPIOFactory()
            logger.info("GPIOZERO pin factory configurado a RPiGPIOFactory")
    except Exception as exc:
        logger.warning("No se pudo configurar RPiGPIOFactory para gpiozero: %s", exc)

BUTTON_PINS = [14, 15]        # Pin 14 = Botón 1 (Verde), Pin 15 = Botón 2 (Rojo)
GREEN_LED_PIN = 12            # LED de acceso concedido
RED_LED_PIN = 13              # LED de acceso denegado
NTC_ADC_CHANNEL = 0           # Canal ADC del sensor de temperatura
LDR_ADC_CHANNEL = 1           # Canal ADC del sensor de luminosidad
DEFAULT_ADC_ADDRESS = 0x48    # Dirección I2C estándar del ADS1115
DEFAULT_ADC_GAIN = 1
LOCK_FILE_PATH = "/tmp/rpi_hardware.lock"


def _convert_adc_to_temperature(raw_value: int) -> float:
    voltage = max(0.0, min(raw_value, 32767)) * 4.096 / 32767.0
    temperature = 20.0 + 5.0 * (voltage / 4.096)
    return round(temperature, 2)


def _convert_adc_to_luminosity(raw_value: int) -> float:
    lux = 200.0 + (max(0, raw_value) / 32767.0) * 800.0
    return round(lux, 2)


class MockLED:
    def __init__(self, pin: int) -> None:
        self.pin = pin
        self._is_lit = False

    @property
    def is_lit(self) -> bool:
        return self._is_lit

    def on(self) -> None:
        self._is_lit = True

    def off(self) -> None:
        self._is_lit = False

    def toggle(self) -> None:
        self._is_lit = not self._is_lit


class MockButton:
    def __init__(self, pin: int, pull_up: bool = True) -> None:
        self.pin = pin
        self.pull_up = pull_up
        self._is_pressed = False

    @property
    def is_pressed(self) -> bool:
        return self._is_pressed

    def press(self) -> None:
        self._is_pressed = True

    def release(self) -> None:
        self._is_pressed = False


class MockADS1115:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._ntc_raw = 18500
        self._ldr_raw = 15000

    def read_adc(self, channel: int, gain: int = 1) -> int:
        if channel == NTC_ADC_CHANNEL:
            return self._ntc_raw
        if channel == LDR_ADC_CHANNEL:
            return self._ldr_raw
        return 0

    def read(self, channel: int) -> int:
        """CircuitPython API compatibility"""
        return self.read_adc(channel, gain=1)


class HardwareManager:
    def __init__(
        self,
        led_pins: Optional[List[int]] = None,
        button_pins: Optional[List[int]] = None,
        adc_address: int = DEFAULT_ADC_ADDRESS,
        adc_gain: int = DEFAULT_ADC_GAIN,
    ) -> None:
        self.led_pins = led_pins or [GREEN_LED_PIN, RED_LED_PIN]
        self.button_pins = button_pins or BUTTON_PINS
        self.adc_address = adc_address
        self.adc_gain = adc_gain

        self.leds: Dict[int, Any] = {}
        self.buttons: Dict[int, Any] = {}
        self.adc: Optional[Any] = None
        self.failed_led_pins: List[int] = []
        self.failed_button_pins: List[int] = []
        self.failed_led_errors: Dict[int, str] = {}
        self.failed_button_errors: Dict[int, str] = {}
        self.adc_error: Optional[str] = None
        self.hardware_ready = False
        self._lock_fd = None
        self._acquired_lock = False
        self.force_mock = False

    def initialize(self) -> None:
        # Try to acquire an OS-level lock so only one process uses the GPIO
        self._acquire_hardware_lock()

        self._initialize_leds()
        self._initialize_buttons()
        self._initialize_adc()
        self.hardware_ready = (
            len(self.failed_led_pins) == 0
            and len(self.failed_button_pins) == 0
            and self.adc is not None
        )

    def _acquire_hardware_lock(self) -> None:
        try:
            fd = os.open(LOCK_FILE_PATH, os.O_CREAT | os.O_RDWR)
            # Try to take an exclusive non-blocking lock
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_fd = fd
            self._acquired_lock = True
            logger.info("Adquirido bloqueo de hardware: %s", LOCK_FILE_PATH)
        except BlockingIOError:
            # Another process holds the lock — fall back to mocks to avoid GPIO busy
            self.force_mock = True
            logger.warning(
                "No se pudo adquirir el bloqueo de hardware (%s). Usando emulación para evitar conflicto GPIO.",
                LOCK_FILE_PATH,
            )
        except Exception as exc:
            self.force_mock = True
            logger.warning("Error al intentar adquirir bloqueo hardware: %s. Usando emulación.", exc)

    def _initialize_leds(self) -> None:
        self.leds = {}
        self.failed_led_pins = []
        self.failed_led_errors = {}

        if LED is None or self.force_mock:
            logger.warning("gpiozero no disponible o bloqueo no adquirido: usando emulación de LEDs")

        for pin in self.led_pins:
            if LED is None or self.force_mock:
                self.leds[pin] = MockLED(pin)
                logger.info("LED inicializado en pin %s (mock)", pin)
            else:
                try:
                    self.leds[pin] = LED(pin)
                    logger.info("LED inicializado en pin %s", pin)
                except Exception as exc:
                    self.leds[pin] = MockLED(pin)
                    self.failed_led_errors[pin] = f"{type(exc).__name__}: {exc}"
                    logger.warning("LED en pin %s falló, usando mock: %s", pin, exc)

    def _initialize_buttons(self) -> None:
        self.buttons = {}
        self.failed_button_pins = []
        self.failed_button_errors = {}

        if Button is None or self.force_mock:
            logger.warning("gpiozero no disponible o bloqueo no adquirido: usando emulación de botones")

        for pin in self.button_pins:
            if Button is None or self.force_mock:
                self.buttons[pin] = MockButton(pin, pull_up=True)
                logger.info("Botón inicializado en pin %s (mock)", pin)
            else:
                try:
                    self.buttons[pin] = Button(pin, pull_up=True)
                    logger.info("Botón inicializado en pin %s", pin)
                except Exception as exc:
                    self.buttons[pin] = MockButton(pin, pull_up=True)
                    self.failed_button_errors[pin] = f"{type(exc).__name__}: {exc}"
                    logger.warning("Botón en pin %s falló, usando mock: %s", pin, exc)

    def _initialize_adc(self) -> None:
        self.adc = None
        self.adc_error = None
        if ADS1115 is None or board is None or busio is None:
            logger.warning("Librerías ADS1115/board/busio no disponibles: usando emulación de ADC")
            self.adc = MockADS1115()
            return

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.adc = ADS1115(i2c)
            logger.info("ADC ADS1115 inicializado en dirección 0x%02x", self.adc_address)
        except Exception as exc:
            self.adc_error = f"{type(exc).__name__}: {exc}"
            logger.exception("No se pudo inicializar el ADC ADS1115")
            self.adc = None

    def is_ready(self) -> bool:
        return self.hardware_ready

    def get_led_states(self) -> Dict[str, bool]:
        return {str(pin): bool(led.is_lit) for pin, led in self.leds.items()}

    def get_button_states(self) -> Dict[str, bool]:
        return {str(pin): bool(btn.is_pressed) for pin, btn in self.buttons.items()}

    def get_raw_adc_values(self) -> Dict[str, Optional[int]]:
        if self.adc is None:
            return {"ntc": None, "ldr": None}

        ntc_value = None
        ldr_value = None

        try:
            ntc_value = self.adc.read_adc(NTC_ADC_CHANNEL, gain=self.adc_gain)
        except AttributeError:
            try:
                ntc_value = self.adc.read(NTC_ADC_CHANNEL)
            except Exception as exc:
                logger.warning("No se pudo leer canal NTC del ADC: %s", exc)
        except Exception as exc:
            logger.warning("No se pudo leer canal NTC del ADC: %s", exc)

        try:
            ldr_value = self.adc.read_adc(LDR_ADC_CHANNEL, gain=self.adc_gain)
        except AttributeError:
            try:
                ldr_value = self.adc.read(LDR_ADC_CHANNEL)
            except Exception as exc:
                logger.warning("No se pudo leer canal LDR del ADC: %s", exc)
        except Exception as exc:
            logger.warning("No se pudo leer canal LDR del ADC: %s", exc)

        return {"ntc": ntc_value, "ldr": ldr_value}

    def get_sensor_readings(self) -> Dict[str, float]:
        raw = self.get_raw_adc_values()
        
        ntc_value = raw["ntc"]
        ldr_value = raw["ldr"]
        
        if ntc_value is None:
            logger.warning("NTC devolvió None, usando valor simulado por defecto")
            ntc_value = 18500
        
        if ldr_value is None:
            logger.warning("LDR devolvió None, usando valor simulado por defecto")
            ldr_value = 15000

        return {
            "temperature_c": _convert_adc_to_temperature(ntc_value),
            "luminosity_lux": _convert_adc_to_luminosity(ldr_value),
        }

    def set_led_state(self, pin: int, state: bool) -> bool:
        if pin not in self.leds:
            raise ValueError(f"LED no configurado para el pin {pin}")
        if state:
            self.leds[pin].on()
        else:
            self.leds[pin].off()
        logger.info("LED en pin %s fijado a %s", pin, state)
        return bool(self.leds[pin].is_lit)

    def toggle_led(self, pin: int) -> bool:
        if pin not in self.leds:
            raise ValueError(f"LED no configurado para el pin {pin}")
        self.leds[pin].toggle()
        logger.info("LED en pin %s alternado a %s", pin, self.leds[pin].is_lit)
        return bool(self.leds[pin].is_lit)

    def get_configured_led_pins(self) -> List[int]:
        return list(self.led_pins)

    def get_configured_button_pins(self) -> List[int]:
        return list(self.button_pins)

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "hardware_ready": self.hardware_ready,
            "led_pins": self.get_configured_led_pins(),
            "button_pins": self.get_configured_button_pins(),
            "failed_led_pins": self.failed_led_pins,
            "failed_button_pins": self.failed_button_pins,
            "failed_led_errors": self.failed_led_errors,
            "failed_button_errors": self.failed_button_errors,
            "adc_error": self.adc_error,
            "gpiozero_available": LED is not None and Button is not None,
            "ads1115_available": ADS1115 is not None,
            "board_available": board is not None,
            "busio_available": busio is not None,
        }


_hardware_manager = HardwareManager()


def get_hardware() -> HardwareManager:
    return _hardware_manager


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    hw = get_hardware()
    hw.initialize()
    print("Hardware ready:", hw.is_ready())
    print("LED states:", hw.get_led_states())
    print("Button states:", hw.get_button_states())
    print("Sensor readings:", hw.get_sensor_readings())
    print("Diagnostics:", hw.get_diagnostics())
