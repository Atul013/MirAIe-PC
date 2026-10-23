"""
test_ac_controller.py
=====================
Test suite for ACController.

Unit tests: run without credentials – everything is mocked.
Integration test: requires a real .env file with valid credentials.

Run all unit tests:
    python -m pytest test_ac_controller.py -v -m "not integration"

Run integration (real device):
    python -m pytest test_ac_controller.py -v -m integration
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
import unittest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

# ── Make sure the local module is importable ─────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))


# ════════════════════════════════════════════════════════════════════════════
#  Helpers – lightweight stubs for miraie_ac internals
# ════════════════════════════════════════════════════════════════════════════

def _make_status(
    is_online=True,
    temperature=24.0,
    room_temperature=27.5,
):
    """Return a minimal fake DeviceStatus object."""

    class _Enum:
        def __init__(self, v):
            self.value = v

    status = MagicMock()
    status.is_online = is_online
    status.temperature = temperature
    status.room_temperature = room_temperature
    status.power_mode = _Enum("on")
    status.fan_mode = _Enum("auto")
    status.v_swing_mode = _Enum("0")
    status.h_swing_mode = _Enum("0")
    status.display_mode = _Enum("on")
    status.hvac_mode = _Enum("cool")
    status.preset_mode = _Enum("none")
    status.converti_mode = _Enum("0")
    return status


def _make_device(status=None):
    """Return a fully-mocked Device object."""
    device = MagicMock()
    device.name = "Bedroom AC"
    device.friendly_name = "Bedroom AC"
    device.status = status or _make_status()
    device.turn_on = AsyncMock()
    device.turn_off = AsyncMock()
    device.set_temperature = AsyncMock()
    return device


def _make_hub(devices=None):
    hub = MagicMock()
    if devices is None:
        devices = [_make_device()]
    hub.home.devices = devices
    hub.init = AsyncMock()
    return hub


def _make_broker(ready=True):
    broker = MagicMock()
    if ready:
        broker.client = MagicMock()   # truthy → broker is "ready" immediately
    else:
        broker.client = None
    return broker


# ════════════════════════════════════════════════════════════════════════════
#  Unit tests (no .env / no network needed)
# ════════════════════════════════════════════════════════════════════════════

class TestACControllerUnit(unittest.TestCase):
    """Pure-unit tests: every external call is mocked."""

    # ── fixture ──────────────────────────────────────────────────────────

    def _make_controller(self, devices=None, broker_ready=True):
        """
        Build an ACController with mocked hub/broker already injected,
        so _connect() short-circuits after the first call.
        """
        from ac_controller import ACController

        ctrl = ACController(
            phone="+910000000000",
            password="fake_password",
            device_index=0,
        )
        # Pre-wire internals so _connect() won't touch the network
        ctrl._broker = _make_broker(ready=broker_ready)
        ctrl._hub = _make_hub(devices=devices if devices is not None else [_make_device()])
        ctrl._device = ctrl._hub.home.devices[0]
        ctrl._connected = True        # skip the real connection path
        return ctrl

    # ── ACResult dataclass ────────────────────────────────────────────────

    def test_result_str_success(self):
        from ac_controller import ACResult
        r = ACResult(success=True, message="ok")
        self.assertIn("success=True", str(r))

    def test_result_str_with_data(self):
        from ac_controller import ACResult
        r = ACResult(success=True, message="ok", data={"foo": 1})
        self.assertIn("foo", str(r))

    # ── turn_on ───────────────────────────────────────────────────────────

    def test_turn_on_calls_device(self):
        ctrl = self._make_controller()
        result = asyncio.run(ctrl.turn_on())
        ctrl._device.turn_on.assert_awaited_once()
        self.assertTrue(result.success)

    # ── turn_off ──────────────────────────────────────────────────────────

    def test_turn_off_calls_device(self):
        ctrl = self._make_controller()
        result = asyncio.run(ctrl.turn_off())
        ctrl._device.turn_off.assert_awaited_once()
        self.assertTrue(result.success)

    # ── set_temp ──────────────────────────────────────────────────────────

    def test_set_temp_valid(self):
        ctrl = self._make_controller()
        result = asyncio.run(ctrl.set_temp(22))
        ctrl._device.set_temperature.assert_awaited_once_with(22.0)
        self.assertTrue(result.success)

    def test_set_temp_boundary_low(self):
        ctrl = self._make_controller()
        result = asyncio.run(ctrl.set_temp(16))
        self.assertTrue(result.success)

    def test_set_temp_boundary_high(self):
        ctrl = self._make_controller()
        result = asyncio.run(ctrl.set_temp(30))
        self.assertTrue(result.success)

    def test_set_temp_too_low_rejected(self):
        ctrl = self._make_controller()
        result = asyncio.run(ctrl.set_temp(15))
        self.assertFalse(result.success)
        self.assertIn("out of range", result.message)

    def test_set_temp_too_high_rejected(self):
        ctrl = self._make_controller()
        result = asyncio.run(ctrl.set_temp(31))
        self.assertFalse(result.success)
        self.assertIn("out of range", result.message)

    def test_set_temp_float_precision(self):
        ctrl = self._make_controller()
        result = asyncio.run(ctrl.set_temp(24.5))
        ctrl._device.set_temperature.assert_awaited_once_with(24.5)
        self.assertTrue(result.success)

    def test_set_temp_non_numeric_rejected_without_connecting(self):
        ctrl = self._make_controller()
        ctrl._connect = AsyncMock(side_effect=AssertionError("must not connect"))

        result = asyncio.run(ctrl.set_temp("warm"))

        self.assertFalse(result.success)
        self.assertIn("Invalid temperature", result.message)
        ctrl._connect.assert_not_awaited()
        ctrl._device.set_temperature.assert_not_awaited()

    def test_malformed_modes_rejected_without_connecting(self):
        ctrl = self._make_controller()
        ctrl._connect = AsyncMock(side_effect=AssertionError("must not connect"))
        cases = (
            (ctrl.set_hvac_mode, None, "Invalid HVAC mode"),
            (ctrl.set_fan_mode, 1, "Invalid Fan mode"),
            (ctrl.set_v_swing, None, "Invalid v_swing mode"),
            (ctrl.set_h_swing, float("inf"), "Invalid h_swing mode"),
            (ctrl.set_display_mode, None, "Invalid display mode"),
            (ctrl.set_preset_mode, [], "Invalid preset mode"),
        )

        for setter, value, expected_message in cases:
            with self.subTest(setter=setter.__name__, value=value):
                result = asyncio.run(setter(value))
                self.assertFalse(result.success)
                self.assertIn(expected_message, result.message)

        ctrl._connect.assert_not_awaited()

    # ── get_status ────────────────────────────────────────────────────────

    def test_get_status_returns_data(self):
        ctrl = self._make_controller()
        result = asyncio.run(ctrl.get_status())
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)
        self.assertIn("room_temperature", result.data)
        self.assertIn("set_temperature", result.data)
        self.assertIn("power", result.data)

    def test_get_status_values(self):
        status = _make_status(temperature=22.0, room_temperature=28.0)
        ctrl = self._make_controller(devices=[_make_device(status=status)])
        result = asyncio.run(ctrl.get_status())
        self.assertEqual(result.data["set_temperature"], 22.0)
        self.assertEqual(result.data["room_temperature"], 28.0)

    def test_get_status_offline_device(self):
        status = _make_status(is_online=False)
        ctrl = self._make_controller(devices=[_make_device(status=status)])
        result = asyncio.run(ctrl.get_status())
        self.assertTrue(result.success)          # still returns; is_online is just a field
        self.assertFalse(result.data["is_online"])

    # ── list_devices ──────────────────────────────────────────────────────

    def test_list_devices(self):
        devices = [_make_device(), _make_device()]
        devices[0].name = "Living Room"
        devices[1].name = "Bedroom"
        ctrl = self._make_controller(devices=devices)
        ctrl._hub.home.devices = devices
        result = asyncio.run(ctrl.list_devices())
        self.assertTrue(result.success)
        self.assertEqual(len(result.data["devices"]), 2)

    # ── credential guard ──────────────────────────────────────────────────

    def test_missing_credentials_raise(self):
        from ac_controller import ACController
        with self.assertRaises(EnvironmentError):
            ACController(phone="", password="", device_index=0)

    # ── device-index guard ────────────────────────────────────────────────

    def test_device_index_out_of_range(self):
        from ac_controller import ACController

        mock_broker = _make_broker(ready=True)
        mock_hub = _make_hub(devices=[_make_device()])

        with patch("ac_controller.MirAIeBroker", return_value=mock_broker), \
             patch("ac_controller.MirAIeHub", return_value=mock_hub):
            ctrl = ACController(phone="+910000000000", password="fake", device_index=99)
            # _connect() will run, use our mock hub (1 device), but index=99 → IndexError
            result = asyncio.run(ctrl.turn_on())

        self.assertFalse(result.success)
        self.assertIn("out of range", result.message)

    # ── error propagation ─────────────────────────────────────────────────

    def test_device_exception_captured(self):
        ctrl = self._make_controller()
        ctrl._device.turn_on = AsyncMock(side_effect=RuntimeError("MQTT disconnected"))
        result = asyncio.run(ctrl.turn_on())
        self.assertFalse(result.success)
        self.assertIn("MQTT disconnected", result.message)


# ════════════════════════════════════════════════════════════════════════════
#  Integration smoke-test (needs a real .env + live AC)
# ════════════════════════════════════════════════════════════════════════════

import pytest  # noqa: E402  – imported here so unit tests don't need pytest

@pytest.mark.integration
class TestACControllerIntegration(unittest.TestCase):
    """
    Live smoke-tests. Skipped automatically when credentials are missing.
    Uses a single shared ACController (and therefore a single event loop /
    aiohttp session) across all tests to avoid 'Event loop is closed' issues.
    """

    ctrl: "ACController" = None   # type: ignore[assignment]
    loop: asyncio.AbstractEventLoop = None  # type: ignore[assignment]

    @classmethod
    def setUpClass(cls):
        from dotenv import load_dotenv
        load_dotenv()
        phone = os.getenv("MIRAIE_PHONE", "")
        password = os.getenv("MIRAIE_PASSWORD", "")
        if not phone or not password or phone.startswith("+91X"):
            raise unittest.SkipTest("No real credentials in .env – skipping integration tests.")

        from ac_controller import ACController
        # Create one persistent event loop for ALL integration tests
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.ctrl = ACController(phone=phone, password=password)
        # Pre-connect once (HTTP auth + device list)
        cls.loop.run_until_complete(cls.ctrl._connect())

    @classmethod
    def tearDownClass(cls):
        if cls.loop and not cls.loop.is_closed():
            cls.loop.close()

    def _run(self, coro):
        """Run a coroutine on the shared event loop."""
        return self.__class__.loop.run_until_complete(coro)

    def test_live_get_status(self):
        result = self._run(self.ctrl.get_status())
        print(f"\n[integration] get_status -> {result}")
        self.assertTrue(result.success, msg=result.message)
        self.assertIn("room_temperature", result.data)

    def test_live_list_devices(self):
        result = self._run(self.ctrl.list_devices())
        print(f"\n[integration] list_devices -> {result}")
        self.assertTrue(result.success, msg=result.message)
        self.assertGreater(len(result.data["devices"]), 0)


# ── entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    unittest.main(verbosity=2)
