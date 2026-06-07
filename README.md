# Proyecto Informática Industrial

Este proyecto independiente contiene la gestión de periféricos para una Raspberry Pi 5:

- Dos botones físicos en GPIO 17 y 27
- Dos LEDs en GPIO 22 (verde) y GPIO 24 (rojo)
- Un ADC ADS1115 conectado por I2C para un sensor NTC (temperatura) y un LDR (luminosidad)

El código está preparado para desplegarse en entornos que no disponen de las librerías de hardware. Si `gpiozero`, `adafruit_ads1x15`, `busio` o `board` no están disponibles, el proyecto usa clases de emulación que mantienen estados lógicos coherentes y valores de sensor estables.

## Uso

```bash
python hardware.py
```

## Requisitos

Instalar desde `requirements.txt` si se desea ejecutar con hardware real:

```bash
pip install -r requirements.txt
```
