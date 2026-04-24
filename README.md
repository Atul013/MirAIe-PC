# 🌡️ MirAIe PC — Panasonic AC Controller Engine

An asynchronous Python controller layer for integrating local automation with Panasonic MirAIe HVAC operations. Leveraging reverse-engineered MQTT broker protocols alongside RESTful authentication, this module encapsulates the raw cloud API into a strictly-typed, deterministic toolchain. It is uniquely architected for headless smart home systems, interactive programmatic execution, and seamless orchestration by LLM-driven autonomous agents (e.g. LangChain, OpenAI Function Calling).

---

## 📁 System Architecture & Project Structure

```
MirAIe PC/
├── ac_controller.py       # Main module — ACController class
├── interactive_cli.py     # Interactive terminal program to edit settings
├── test_ac_controller.py  # Unit + integration tests
├── .env                   # Your credentials
├── pytest.ini             # Pytest config
└── .gitignore
```

---

## ⚙️ Setup

### 1. Install dependencies
```bash
pip install miraie-ac python-dotenv
```

### 2. Configure credentials
Copy `.env.example` to `.env` and fill in your MirAIe account details:
```env
MIRAIE_PHONE=+91XXXXXXXXXX
MIRAIE_PASSWORD=your_password_here
MIRAIE_DEVICE=0   # 0-based index if you have multiple ACs
```

---

## 🚀 Usage

### Interactive Command-Line Interface (CLI)
Included is a synchronous abstraction via an interactive terminal script that fetches current payload states and enables rapid mutation of the application interface (temperature, modes, horizontal/vertical swing positioning, display indicators). Input streams default to the live device state.

```bash
python interactive_cli.py
```

### Programmatic Execution (Structured Results)
```python
from ac_controller import ACController
import asyncio

ctrl = ACController()

asyncio.run(ctrl.turn_on())
asyncio.run(ctrl.set_temp(24))
asyncio.run(ctrl.turn_off())

result = asyncio.run(ctrl.get_status())
print(result.data)
```

### Built-in Execution Context
```bash
python ac_controller.py
```

---

## 🧰 API Reference

All methods are `async` and return an `ACResult` object.

```python
@dataclass
class ACResult:
    success: bool
    message: str
    data: dict | None     # populated by get_status() and list_devices()
```

| Method | Description |
|---|---|
| `await turn_on()` | Power the AC on |
| `await turn_off()` | Power the AC off |
| `await set_temp(val)` | Set target temperature in °C (valid range: 16–30) |
| `await set_hvac_mode(mode)` | Set HVAC mode ("cool", "dry", "fan", "heat", "auto") |
| `await set_fan_mode(mode)` | Set Fan mode ("auto", "low", "medium", "high", "quiet") |
| `await set_v_swing(val)` | Set Vertical Swing (0="auto", 1-5=positions) |
| `await set_h_swing(val)` | Set Horizontal Swing (0="auto", 1-5=positions) |
| `await set_preset_mode(mode)` | Set Preset mode ("none", "eco", "boost", "clean") |
| `await set_display_mode(mode)` | Set Display mode ("on", "off") - controls AC lights |
| `await get_status()` | Get full device status (power, temp, fan, mode, etc.) |
| `await list_devices()` | List all registered devices on the account |

### `get_status()` response fields
```python
{
  "is_online":        bool,
  "power":            str,   # "on" / "off"
  "set_temperature":  float,
  "room_temperature": float,
  "hvac_mode":        str,   # "cool", "heat", "auto", etc.
  "fan_mode":         str,
  "v_swing":          str,
  "h_swing":          str,
  "preset_mode":      str,
  "display_mode":     str,
  "converti_mode":    str,
}
```

---

## 🤖 Integration with LLM Autonomous Agents

The module is specifically engineered to be injected as a bound toolset within cognitive architectures (LangChain, OpenAI Function Calling, semantic routers, or proprietary agent frameworks).

```python
# LangChain Integration Example
from langchain.tools import tool
from ac_controller import ACController
import asyncio

ctrl = ACController()

@tool
def set_ac_temperature(temperature: float) -> str:
    """Set the Panasonic AC temperature. Valid range: 16–30°C."""
    result = asyncio.run(ctrl.set_temp(temperature))
    return result.message

@tool
def get_ac_status() -> str:
    """Get current AC status including temperature and mode."""
    result = asyncio.run(ctrl.get_status())
    return str(result.data) if result.success else result.message
```

**Architectural Advantages for Agents:**
- ✅ **Deterministic Payloads:** Returns strict `ACResult(success, message, data)` schemas, entirely eliminating the need for heuristic screen-scraping or regex extraction.
- ✅ **Boundary Enforcement:** Intrinsic argument validation (e.g., temperature constraints, typed enums) immediately halts hallucinated parameters.
- ✅ **Credential Isolation:** Environmental variables manage secrets off-thread, safely abstracting authentication from the agent's context window.
- ✅ **Concurrency Model:** A fully `async` implementation ensures non-blocking execution, fitting natively into high-throughput asynchronous agent lifecycles.

---

## 🧪 Validation & Test Suite

### Execute Unit Tests (Mocked Infrastructure)
```bash
python -m pytest test_ac_controller.py -v -m "not integration"
```

### Execute End-to-End Integration Tests (Requires Production Credentials)
```bash
python -m pytest test_ac_controller.py -v -m integration
```

**Test Coverage & Constraints:**
- **Unit layer (17 tests):** Operates against a fully mocked MQTT broker and REST client (zero network egress required).
- **Integration layer (2 tests):** Performs live authentication and executes state retrieval against the production endpoints.

---

## ⚠️ Notes

- **Windows users:** The library uses `asyncio.WindowsSelectorEventLoopPolicy` automatically — no manual setup needed.
- This tool uses the **unofficial** MirAIe MQTT API (reverse-engineered). It may break if Panasonic changes their backend.
- Supported devices: Panasonic split ACs with MirAIe Wi-Fi connectivity.

---

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `miraie-ac` | MirAIe cloud API + MQTT client |
| `python-dotenv` | Load credentials from `.env` |
| `pytest` | Test runner |
