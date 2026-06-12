#!/usr/bin/env python3
import json
import re
import os
import csv
import struct
from mcap.writer import Writer

# --- CONFIGURATION ---
input_folder = "./raw_logs"
output_folder = "./mcap_logs"
csv_database_path = "./calibraciones.csv"
# ---------------------

def load_can_database(csv_path):
    can_db = {}
    if not os.path.exists(csv_path):
        print(f"Warning: Database CSV not found at {csv_path}. Standard raw logging will be used.")
        return can_db

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        
        for row in reader:
            id_raw = row.get("ID_Hex")
            var_name = row.get("Variable")
            
            if not id_raw or not var_name or not var_name.strip():
                continue
                
            try:
                id_clean = id_raw.strip().upper().replace("0X", "")
                id_int = int(id_clean, 16)
                
                byte_start = int(row.get("Byte_Start").strip()) if row.get("Byte_Start") else 1
                bit_start = int(row.get("Bit_Start").strip()) if row.get("Bit_Start") else 0
                tipo_msg = row.get("Tipo").strip().lower() if row.get("Tipo") else "uint8"
                
                factor_str = row.get("Factor", "1.0").replace(",", ".").strip()
                offset_str = row.get("Offset", "0.0").replace(",", ".").strip()
                
                factor = float(factor_str) if factor_str else 1.0
                offset = float(offset_str) if offset_str else 0.0
                
            except Exception as e:
                print(f"Row skipped in CSV due to formatting error on ID {id_raw}: {e}")
                continue

            variable_info = {
                "name": var_name.strip(),
                "type": tipo_msg,
                "start": byte_start,
                "bit_start": bit_start,
                "factor": factor,
                "offset": offset
            }
            
            if id_int not in can_db:
                can_db[id_int] = []
            can_db[id_int].append(variable_info)
            
    print(f"Loaded {sum(len(v) for v in can_db.values())} variables across {len(can_db)} CAN IDs.")
    return can_db


def decode_variable(bytes_data, tipo, start_byte, bit_start, factor, offset):
    """Desempaqueta bytes asegurando que no se salga del tamaño del payload actual."""
    try:
        idx = start_byte - 1  # Base 1 a Base 0
        
        if idx < 0 or idx >= len(bytes_data):
            return None

        slice_data = bytes_data[idx:]

        if tipo == "uint8":
            raw_val = slice_data[0]
        elif tipo == "int8":
            raw_val = struct.unpack("b", bytes(slice_data[:1]))[0]
        elif tipo == "uint16":
            if len(slice_data) < 2: return None
            raw_val = struct.unpack("<H", bytes(slice_data[:2]))[0]
        elif tipo == "int16":
            if len(slice_data) < 2: return None
            raw_val = struct.unpack("<h", bytes(slice_data[:2]))[0]
        elif tipo == "uint16_be":
            if len(slice_data) < 2: return None
            raw_val = struct.unpack(">H", bytes(slice_data[:2]))[0]
        elif tipo == "int16_be":
            if len(slice_data) < 2: return None
            raw_val = struct.unpack(">h", bytes(slice_data[:2]))[0]
        elif tipo == "uint32":
            if len(slice_data) < 4: return None
            raw_val = struct.unpack("<I", bytes(slice_data[:4]))[0]
        elif tipo == "int32":
            if len(slice_data) < 4: return None
            raw_val = struct.unpack("<i", bytes(slice_data[:4]))[0]
        elif tipo == "uint32_be":
            if len(slice_data) < 4: return None
            raw_val = struct.unpack(">I", bytes(slice_data[:4]))[0]
        elif tipo == "int32_be":
            if len(slice_data) < 4: return None
            raw_val = struct.unpack(">i", bytes(slice_data[:4]))[0]
        elif tipo in ("bit", "bool"):
            raw_val = (slice_data[0] >> bit_start) & 0x01
        else:
            return None
            
        return (raw_val * factor) + offset
    except Exception:
        return None


def build_schema_for_topic(id_int, can_db):
    """
    Genera un JSON Schema con propiedades explícitas para cada variable del topic.
    Foxglove necesita los campos declarados en el schema para poder plotearlos.
    Los topics desconocidos usan un schema genérico ya que sus campos no son predecibles.
    """
    base_properties = {
        "_raw_id": {"type": "integer"},
        "_interface": {"type": "string"},
    }

    if id_int in can_db:
        for var in can_db[id_int]:
            tipo = var["type"]
            # Bits/bools son enteros (0 o 1), el resto son números con decimales posibles
            json_type = "integer" if tipo in ("bit", "bool") else "number"
            base_properties[var["name"]] = {"type": json_type}
        schema = {
            "type": "object",
            "properties": base_properties,
        }
    else:
        # Topic desconocido: schema genérico, no se podrá plotear pero se preserva el dato
        schema = {
            "type": "object",
            "properties": {
                **base_properties,
                "data_raw_hex": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        }

    return schema


def candump_to_mcap(input_path, output_path, can_db):
    with open(output_path, "wb", buffering=1024*1024) as f:
        writer = Writer(f)
        writer.start()

        # Registramos un schema por topic (ID CAN)
        active_channels = {}   # topic_name -> channel_id
        active_schemas = {}    # topic_name -> schema_id

        line_regex = re.compile(
            r"\((?P<time>\d+\.\d+)\)\s+(?P<iface>\S+)\s+(?P<id>[0-9a-fA-F]+)\s+\[\d+\]\s+(?P<data>.+)"
        )

        with open(input_path, "r") as log:
            for line in log:
                match = line_regex.search(line)
                if not match: 
                    continue

                groups = match.groupdict()
                
                try:
                    id_int = int(groups["id"], 16)
                except ValueError:
                    continue 

                id_hex_clean = f"{id_int:X}" 

                raw_parts = groups["data"].split()
                byte_data = []
                for p in raw_parts:
                    if len(p) == 2 and all(c in "0123456789abcdefABCDEF" for c in p):
                        byte_data.append(int(p, 16))
                    else:
                        break

                payload = {"_raw_id": id_int, "_interface": groups["iface"]}
                
                if id_int in can_db:
                    primary_group = can_db[id_int][0]["name"]
                    topic_name = f"/can/id_0x{id_hex_clean}_{primary_group.split('_')[0]}"
                    
                    for var in can_db[id_int]:
                        val = decode_variable(
                            byte_data, var["type"], var["start"], var["bit_start"],
                            var.get("factor", 1.0), var.get("offset", 0.0)
                        )
                        if val is not None:
                            payload[var["name"]] = val
                else:
                    topic_name = f"/can/unknown_0x{id_hex_clean}"
                    payload["data_raw_hex"] = [f"{b:02X}" for b in byte_data]

                # Registrar schema y channel la primera vez que vemos este topic
                if topic_name not in active_channels:
                    schema = build_schema_for_topic(id_int, can_db)
                    schema_id = writer.register_schema(
                        name=topic_name,          # nombre único por topic
                        encoding="jsonschema",
                        data=json.dumps(schema).encode()
                    )
                    active_schemas[topic_name] = schema_id
                    active_channels[topic_name] = writer.register_channel(
                        topic=topic_name,
                        message_encoding="json",
                        schema_id=schema_id,
                    )

                timestamp_ns = int(float(groups["time"]) * 1e9)
                writer.add_message(
                    channel_id=active_channels[topic_name],
                    log_time=timestamp_ns,
                    publish_time=timestamp_ns,
                    data=json.dumps(payload).encode("utf-8")
                )

        writer.finish()


if __name__ == "__main__":
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    if not os.path.exists(input_folder):
        os.makedirs(input_folder)

    for folder in (input_folder, output_folder):
        gitkeep_path = os.path.join(folder, ".gitkeep")
        if not os.path.exists(gitkeep_path):
            open(gitkeep_path, "w").close()

    can_db_loaded = load_can_database(csv_database_path)
    log_files = [f for f in os.listdir(input_folder) if f.endswith((".txt", ".log"))]
    
    if not log_files:
        print("No log files found to process.")
    else:
        for filename in log_files:
            print(f"Processing {filename}...")
            in_path = os.path.join(input_folder, filename)
            out_path = os.path.join(output_folder, os.path.splitext(filename)[0] + ".mcap")
            candump_to_mcap(in_path, out_path, can_db_loaded)
            print(f"  -> {out_path}")