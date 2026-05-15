import json
import re
import os
from mcap.writer import Writer

# --- CONFIGURACIÓN ---
CARPETA_ENTRADA = "./logs_crudos"
CARPETA_SALIDA = "./logs_mcap"
# ---------------------

def candump_to_mcap(input_path, output_path):
    with open(output_path, "wb", buffering=1024*1024) as f:
        writer = Writer(f)
        writer.start()

        schema_id = writer.register_schema(
            name="can_msg",
            encoding="jsonschema",
            data=json.dumps({
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "data": {"type": "array", "items": {"type": "integer"}},
                    "interface": {"type": "string"}
                }
            }).encode()
        )

        channel_id = writer.register_channel(
            topic="/can/raw",
            message_encoding="json",
            schema_id=schema_id,
        )

        # Regex robusta
        line_regex = re.compile(
            r"\((?P<time>\d+\.\d+)\)\s+(?P<iface>\S+)\s+(?P<id>[0-9A-F]+)\s+\[\d+\]\s+(?P<data>.+)",
            re.IGNORECASE
        )

        with open(input_path, "r") as log:
            for line in log:
                match = line_regex.search(line)
                if not match:
                    continue

                groups = match.groupdict()
                
                # Extraemos los bytes limpiando cualquier residuo
                # .split() separa por cualquier espacio, luego filtramos solo lo que parezca Hex
                raw_parts = groups["data"].split()
                byte_data = []
                for part in raw_parts:
                    if len(part) <= 2 and all(c in "0123456789abcdefABCDEF" for c in part):
                        byte_data.append(int(part, 16))

                timestamp_ns = int(float(groups["time"]) * 1e9)
                
                writer.add_message(
                    channel_id=channel_id,
                    log_time=timestamp_ns,
                    publish_time=timestamp_ns,
                    data=json.dumps({
                        "id": int(groups["id"], 16),
                        "data": byte_data,
                        "interface": groups["iface"]
                    }).encode("utf-8")
                )

        writer.finish()

if __name__ == "__main__":

    # Comprobar y crear carpeta de salida si no existe
    if not os.path.exists(CARPETA_SALIDA):
        os.makedirs(CARPETA_SALIDA)
        print(f"Carpeta creada: {CARPETA_SALIDA}")

    # Comprobar y crear carpeta de entrada si no existe (para que no de error al listar)
    if not os.path.exists(CARPETA_ENTRADA):
        os.makedirs(CARPETA_ENTRADA)
        print(f"Carpeta de entrada creada: {CARPETA_ENTRADA}. Mete .txt aquí para procesar.")
    
    archivos = [f for f in os.listdir(CARPETA_ENTRADA) if f.endswith((".txt", ".log"))]
    for nombre_archivo in archivos:
        print(f"Procesando {nombre_archivo}...", end="\r")
        ruta_in = os.path.join(CARPETA_ENTRADA, nombre_archivo)
        ruta_out = os.path.join(CARPETA_SALIDA, os.path.splitext(nombre_archivo)[0] + ".mcap")
        
        try:
            candump_to_mcap(ruta_in, ruta_out)
        except Exception as e:
            print(f"\n [ERROR]{nombre_archivo}: {e}")
    
    print("\n Proceso completado.")