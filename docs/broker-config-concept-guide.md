# Broker Connection Config — Concept Guide
*Source: `framework/broker/config.py`*
*Depth: Balanced*
*Generated: 2026-03-07*

---

## Port Architecture: TWS vs IB Gateway

### What It Is
`config.py` defines the four TCP port constants used to connect to Interactive Brokers' trading infrastructure, and a `ConnectionConfig` dataclass that manages which port to use based on two binary choices: paper vs live, and TWS vs IB Gateway.

### How It Works
IBKR exposes its API through two different applications, each with two port variants:

| Application | Account Type | Port |
|---|---|---|
| TWS (full GUI) | Paper | 7497 |
| TWS (full GUI) | Live | 7496 |
| IB Gateway (headless) | Paper | 4002 |
| IB Gateway (headless) | Live | 4001 |

**TWS (Trader Workstation)** is the full desktop application with charts, order management, and a live blotter. You run this during active development — you can see every order, position, and API call in real time.

**IB Gateway** is the lightweight headless variant. No GUI, lower memory footprint, and designed to run in the background. This is the right choice for automated overnight strategies or scheduled jobs where no one is watching a screen.

### The Intuition
The port number is the handshake between your Python code and IBKR's software. If you're connected to the wrong port, the connection will either fail outright or — more dangerously — you'll think you're on paper when you're on live. The port constants make the intent explicit and reduce the chance of this mistake.

### Watch Out For
- The most common mistake is having TWS open on the paper port (7497) but connecting with `paper=False` — the code resolves to port 7496, the connection fails, and the error message points you to the right diagnosis.
- If you configure TWS to use a non-standard port (via Edit → Global Configuration → API → Socket port), pass `port=your_port` explicitly to override auto-selection.
- IB Gateway requires a separate login from TWS — they cannot both be running and accepting connections on the same port simultaneously.

---

## ConnectionConfig

### What It Is
`ConnectionConfig` is a dataclass that bundles all connection parameters into a single, validated object. It's passed to `IBKRBroker` internally and drives auto-port selection, timeout handling, and account type awareness.

### How It Works
Six fields cover all connection scenarios:

- **`host`** — IP address of the machine running TWS/Gateway. `"127.0.0.1"` for local (standard). Change only if running TWS on a separate machine on your network.
- **`port`** — Override port. If `None`, auto-selected by `resolved_port()`.
- **`client_id`** — An integer sent to TWS to identify this connection. TWS allows multiple simultaneous API connections, each with a unique `client_id`. Use `1` for a single script; increment (2, 3...) if running multiple scripts against the same TWS instance at once.
- **`paper`** — `True` for paper trading (default), `False` for live.
- **`gateway`** — `True` to target IB Gateway, `False` for TWS.
- **`timeout`** — Seconds to wait for the TWS handshake. Default 10. Increase on slow networks.

### The Intuition
`ConnectionConfig` exists so that connection parameters are declared once and used consistently. Rather than passing `host`, `port`, `client_id`, `paper`, and `gateway` as five separate arguments to every broker method, they're bundled into one object with a well-defined resolution logic.

### In the Code
```python
def resolved_port(self) -> int:
    if self.port is not None:
        return self.port           # explicit override wins

    if self.gateway:
        return GATEWAY_PAPER_PORT if self.paper else GATEWAY_LIVE_PORT
    else:
        return TWS_PAPER_PORT if self.paper else TWS_LIVE_PORT
```

### Watch Out For
- `client_id` conflicts are a common source of confusing errors. If two scripts connect with `client_id=1` simultaneously, TWS rejects the second connection. The error is not always obvious — keep a note of which `client_id` each script uses.
- `paper=True` is the default. This is deliberate — the safe default means you must consciously set `paper=False` to connect to a live account, reducing the chance of accidental real-money orders.
- `timeout=10` is usually sufficient for a local TWS instance. On a remote machine or a slow VM, increase to 30.

---

## Concept Relationships

```
ConnectionConfig
    │
    ├── paper=True/False  ─┐
    ├── gateway=True/False ─┤──► resolved_port()  →  7497 / 7496 / 4002 / 4001
    └── port (override)   ─┘
                │
                ▼
        IBKRBroker.__init__()
                │
                ▼
        IBKRBroker.connect()
            IB.connect(host, resolved_port(), client_id)
```

`config.py` is the only file in the broker layer that needs to change when switching between development (paper, TWS) and production (live, Gateway) environments.

---

## Glossary

| Term | Definition |
|---|---|
| TWS | Trader Workstation — IBKR's full GUI desktop application |
| IB Gateway | IBKR's lightweight headless API server — no GUI, lower resource usage |
| Port | TCP port number on which TWS/Gateway listens for API connections |
| Paper trading | Simulated trading with virtual money on IBKR's paper account |
| client_id | Integer identifier sent to TWS to distinguish simultaneous API connections |
| auto_adjust | (Not in this file — see data.py) |
| Headless | Running without a graphical interface — appropriate for automated scheduled jobs |
| Host | IP address of the machine running TWS or IB Gateway |
| Timeout | Seconds to wait for TWS to acknowledge the connection request |

---

## Further Reading

- **IBKR TWS API Documentation** — [interactivebrokers.github.io/tws-api](https://interactivebrokers.github.io/tws-api/). The official reference for port numbers, connection setup, and TWS configuration.
- **ib_insync documentation** — [ib-insync.readthedocs.io](https://ib-insync.readthedocs.io). The library wrapping the raw TWS API used throughout `ibkr.py`.
