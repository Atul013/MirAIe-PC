"""
ac_controller.py
================
A modular, async-ready controller for Panasonic MirAIe AC units.
Designed to be called by a personal assistant agent or imported as a module.

Dependencies:
    pip install miraie-ac python-dotenv

Environment variables (place in a .env file next to this script):
    MIRAIE_PHONE    – Registered phone number, e.g. +919xxxxxxxxx
    MIRAIE_PASSWORD – MirAIe account password
    MIRAIE_DEVICE   – (Optional) 0-based index of the device to control (default: 0)
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Any, Optional

from dotenv import load_dotenv
from miraie_ac import MirAIeBroker, MirAIeHub
from miraie_ac.device import Device, DeviceStatus
from miraie_ac.enums import FanMode, HVACMode, PresetMode, SwingMode, DisplayMode, ConvertiMode, PowerMode

# ── Windows fix: aiomqtt uses add_reader/add_writer which require SelectorEventLoop
# ProactorEventLoop (Windows default on Python 3.8+) does NOT support them.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── Load credentials ────────────────────────────────────────────────────────
load_dotenv()

_PHONE:    str = os.getenv("MIRAIE_PHONE", "")
_PASSWORD: str = os.getenv("MIRAIE_PASSWORD", "")
_DEVICE_INDEX: int = int(os.getenv("MIRAIE_DEVICE", "0"))

# Temperature bounds enforced by Panasonic firmware
_TEMP_MIN: float = 16.0
_TEMP_MAX: float = 30.0

# How long (seconds) to wait for the MQTT broker before sending control commands
_MQTT_CONNECT_TIMEOUT: int = 15


# ── Result type ─────────────────────────────────────────────────────────────
@dataclass
class ACResult:
    """Returned by every ACController method."""
    success: bool
    message: str
    data: Optional[dict[str, Any]] = None

    def __str__(self) -> str:
        parts = [f"success={self.success}", f"message='{self.message}'"]
        if self.data:
            parts.append(f"data={self.data}")
        return f"ACResult({', '.join(parts)})"


# ── Controller ───────────────────────────────────────────────────────────────
class ACController:
    """
    High-level async interface to a single MirAIe-connected AC unit.

    Usage (standalone):
        controller = ACController()
        result = asyncio.run(controller.turn_on())
        print(result)

    Usage (within an existing event loop):
        controller = ACController()
        await controller._connect()       # optional – auto-called by every method
        result = await controller.turn_on()
    """

    def __init__(
        self,
        phone: str = _PHONE,
        password: str = _PASSWORD,
        device_index: int = _DEVICE_INDEX,
    ) -> None:
        if not phone or not password:
            raise EnvironmentError(
                "MIRAIE_PHONE and MIRAIE_PASSWORD must be set in the .env file "
                "or passed explicitly to ACController()."
            )
        self._phone = phone
        self._password = password
        self._device_index = device_index

        self._hub: Optional[MirAIeHub] = None
        self._broker: Optional[MirAIeBroker] = None
        self._device: Optional[Device] = None
        self._connected: bool = False

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _connect(self) -> None:
        """
        Authenticate via HTTP, pre-load device status, and schedule the MQTT
        broker as a background task.

        NOTE: hub.init() calls get_all_device_status() internally, so
        device.status is populated via HTTP immediately — no need to wait for
        MQTT just to read status. MQTT is only required for control commands.
        """
        if self._connected:
            return

        self._broker = MirAIeBroker()
        self._hub = MirAIeHub()

        # Authenticates, fetches home + device list, fetches initial status
        # via HTTP, then schedules broker.connect() as a background asyncio task.
        await self._hub.init(self._phone, self._password, self._broker)

        devices = self._hub.home.devices
        if not devices:
            raise RuntimeError("No MirAIe devices found on this account.")
        if self._device_index >= len(devices):
            raise IndexError(
                f"Device index {self._device_index} is out of range "
                f"({len(devices)} device(s) found)."
            )

        self._device = devices[self._device_index]
        self._connected = True

    async def _wait_for_mqtt(self) -> None:
        """
        Yield to the event loop until the MQTT broker background task has
        established its connection. Required before publishing control commands.
        """
        elapsed = 0
        while not (hasattr(self._broker, "client") and self._broker.client is not None):
            if elapsed >= _MQTT_CONNECT_TIMEOUT:
                raise TimeoutError(
                    f"MQTT broker did not connect within {_MQTT_CONNECT_TIMEOUT}s. "
                    "Check your network and credentials."
                )
            await asyncio.sleep(1)
            elapsed += 1

    async def _run(self, coro_factory) -> ACResult:
        """
        Connect (HTTP auth + device list) if needed, wait for the MQTT broker,
        then execute the coroutine produced by coro_factory.
        """
        try:
            await self._connect()
            await self._wait_for_mqtt()   # MQTT required for control commands
            await coro_factory()
            return ACResult(success=True, message="Command executed successfully.")
        except Exception as exc:  # noqa: BLE001
            return ACResult(success=False, message=str(exc))

    # ── Public API ────────────────────────────────────────────────────────

    async def turn_on(self) -> ACResult:
        """Power on the AC unit."""
        return await self._run(lambda: self._device.turn_on())

    async def turn_off(self) -> ACResult:
        """Power off the AC unit."""
        return await self._run(lambda: self._device.turn_off())

    async def set_temp(self, val: float) -> ACResult:
        """
        Set the target temperature.

        Args:
            val: Desired temperature in °C. Must be between 16 and 30.

        Returns:
            ACResult with success/failure details.
        """
        try:
            val = float(val)
        except (TypeError, ValueError, OverflowError):
            return ACResult(
                success=False,
                message=f"Invalid temperature: {val!r}. Expected a number between {_TEMP_MIN} and {_TEMP_MAX}°C.",
            )
        if not (_TEMP_MIN <= val <= _TEMP_MAX):
            return ACResult(
                success=False,
                message=f"Temperature {val}°C is out of range ({_TEMP_MIN}–{_TEMP_MAX}°C).",
            )
        return await self._run(lambda: self._device.set_temperature(val))

    async def set_hvac_mode(self, mode: str) -> ACResult:
        """Set HVAC mode (cool, dry, fan, heat, auto)."""
        try:
            m = HVACMode(mode.lower())
        except (AttributeError, TypeError, ValueError):
            valid = [e.value for e in HVACMode]
            return ACResult(success=False, message=f"Invalid HVAC mode: {mode}. Valid: {valid}")
        return await self._run(lambda: self._device.set_hvac_mode(m))

    async def set_fan_mode(self, mode: str) -> ACResult:
        """Set Fan mode (auto, low, medium, high, quiet)."""
        try:
            m = FanMode(mode.lower())
        except (AttributeError, TypeError, ValueError):
            valid = [e.value for e in FanMode]
            return ACResult(success=False, message=f"Invalid Fan mode: {mode}. Valid: {valid}")
        return await self._run(lambda: self._device.set_fan_mode(m))

    async def set_v_swing(self, mode: int | str) -> ACResult:
        """Set Vertical Swing mode (0=auto, 1-5=positions)."""
        try:
            m = SwingMode(int(mode))
        except (TypeError, ValueError, OverflowError):
            valid = [e.value for e in SwingMode]
            return ACResult(success=False, message=f"Invalid v_swing mode: {mode}. Valid: {valid}")
        return await self._run(lambda: self._device.set_v_swing_mode(m))

    async def set_h_swing(self, mode: int | str) -> ACResult:
        """Set Horizontal Swing mode (0=auto, 1-5=positions)."""
        try:
            m = SwingMode(int(mode))
        except (TypeError, ValueError, OverflowError):
            valid = [e.value for e in SwingMode]
            return ACResult(success=False, message=f"Invalid h_swing mode: {mode}. Valid: {valid}")
        return await self._run(lambda: self._device.set_h_swing_mode(m))

    async def set_display_mode(self, mode: str) -> ACResult:
        """Set Display mode (on, off)."""
        try:
            m = DisplayMode(mode.lower())
        except (AttributeError, TypeError, ValueError):
            valid = [e.value for e in DisplayMode]
            return ACResult(success=False, message=f"Invalid display mode: {mode}. Valid: {valid}")
        return await self._run(lambda: self._device.set_display_mode(m))

    async def set_preset_mode(self, mode: str) -> ACResult:
        """Set Preset mode (none, eco, boost, clean)."""
        try:
            m = PresetMode(mode.lower())
        except (AttributeError, TypeError, ValueError):
            valid = [e.value for e in PresetMode]
            return ACResult(success=False, message=f"Invalid preset mode: {mode}. Valid: {valid}")
        return await self._run(lambda: self._device.set_preset_mode(m))

    async def get_status(self) -> ACResult:
        """
        Fetch the latest cached status of the AC unit.

        Returns:
            ACResult with a 'data' dict containing all status fields.
        """
        def _val(field) -> Any:
            """Safely extract .value from an enum; fall back to str() for unknown values."""
            try:
                return field.value
            except (AttributeError, KeyError, ValueError):
                return str(field)

        try:
            await self._connect()
            status: DeviceStatus = self._device.status  # type: ignore[union-attr]
            data = {
                "is_online":        status.is_online,
                "power":            _val(status.power_mode),
                "set_temperature":  status.temperature,
                "room_temperature": status.room_temperature,
                "hvac_mode":        _val(status.hvac_mode),
                "fan_mode":         _val(status.fan_mode),
                "v_swing":          _val(status.v_swing_mode),
                "h_swing":          _val(status.h_swing_mode),
                "preset_mode":      _val(status.preset_mode),
                "display_mode":     _val(status.display_mode),
                "converti_mode":    _val(status.converti_mode),
            }
            return ACResult(success=True, message="Status retrieved.", data=data)
        except Exception as exc:  # noqa: BLE001
            return ACResult(success=False, message=str(exc))



    # ── List devices (utility) ────────────────────────────────────────────

    async def list_devices(self) -> ACResult:
        """Return names of all devices registered on this account."""
        try:
            await self._connect()
            devices = self._hub.home.devices  # type: ignore[union-attr]
            names = [
                {"index": i, "name": d.name, "friendly_name": d.friendly_name}
                for i, d in enumerate(devices)
            ]
            return ACResult(success=True, message="Devices retrieved.", data={"devices": names})
        except Exception as exc:  # noqa: BLE001
            return ACResult(success=False, message=str(exc))


# ── CLI / quick-test entry-point ─────────────────────────────────────────────
async def _demo() -> None:
    ctrl = ACController()

    print("=== Listing devices ===")
    print(await ctrl.list_devices())

    print("\n=== Current status ===")
    print(await ctrl.get_status())

    print("\n=== Turning ON ===")
    print(await ctrl.turn_on())

    print("\n=== Setting temperature to 24°C ===")
    print(await ctrl.set_temp(24))

    await asyncio.sleep(3)   # let commands propagate before exit

    print("\n=== Turning OFF ===")
    print(await ctrl.turn_off())


if __name__ == "__main__":
    asyncio.run(_demo())
