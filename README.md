# Proyecto Informática Industrial 

Este proyecto implementa un sistema de gestión de periféricos y control de acceso seguro para Raspberry Pi 5.

## Características
- **Control de Acceso:** Sistema basado en una secuencia física de botones.
- **Periféricos:** - Dos botones físicos (configurables vía GPIO).
  - Dos LEDs (verde para éxito, rojo para fallo).
  - Sensor analógico (NTC/LDR) mediante ADC ADS1115 (I2C).
- **Compatibilidad:** Modo emulado para despliegue en la nube (Render) sin necesidad de hardware físico.

## Lógica de Acceso (Contraseña)
El sistema valida la identidad del usuario mediante una secuencia de pulsaciones en los botones físicos:

1. **Secuencia Requerida:** `Botón 1` -> `Botón 2` -> `Botón 1`.
2. **Retroalimentación:**
   - **Éxito:** Si la secuencia es correcta, el LED verde (GPIO 12) se activará durante 3 segundos.
   - **Fallo:** Tras 3 intentos incorrectos, el LED rojo (GPIO 13) se activará durante 3 segundos y el intento quedará registrado en la auditoría del Dashboard.

## Despliegue y Uso

### Ejecución Local
Para ejecutar en una Raspberry Pi con el hardware conectado:
```bash
pip install -r requirements.txt
python client.py -> ejecutar con: "GPIOZERO_PIN_FACTORY=lgpio .venv/bin/python client.py --auto"
