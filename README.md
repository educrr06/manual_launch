# CANDUMP2MCAP

Converts CAN bus logs from `candump` format (`.txt` / `.log`) into `.mcap` files ready for visualization in [Foxglove Studio](https://foxglove.dev).

Each CAN ID is mapped to a dedicated topic with a typed JSON schema, allowing Foxglove's plot panel to discover and graph signals directly. If a `calibraciones.csv` database is provided, raw bytes are decoded into named physical variables (RPM, temperature, torque, etc.) applying the configured factor and offset. Unknown IDs are logged as raw hex.

## Project Structure
- `raw_logs/` — Place your `.txt` or `.log` candump files here.
- `mcap_logs/` — Generated `.mcap` files will appear here.
- `candump2mcap.py` — Main processing script.
- `calibraciones.csv` — CAN signal database (ID, byte layout, type, factor, offset).

## Installation
1. Make sure you have Python 3.8 or higher installed.
2. Install the required dependencies:
```bash
pip install mcap
```

## Usage
1. Place your candump log files in `raw_logs/`.
2. Run the script:
```bash
python3 candump2mcap.py
```
3. Open the generated `.mcap` files from `mcap_logs/` in Foxglove Studio.