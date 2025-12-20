import subprocess
import time
import json
import re
import sys

TABLES = {'kpi': 'system_metrics', 'aor': 'user_profiles'}
UPDATE_TIME = 5  # seconds


def fetch_table(table_name):
    """Run kamcmd to dump a specific hash table."""
    try:
        result = subprocess.run(
            ['kamcmd', 'htable.dump', table_name],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return {}

        return parse_kamcmd_output(result.stdout)
    except Exception as e:
        print(f'Error fetching {table_name}: {e}', file=sys.stderr)
        return {}


def parse_kamcmd_output(raw_text):
    """
    Parses Kamailio RPC structure:
    {
        name: key_name
        value: some_value
        type: str
    }
    """
    data = {}

    pattern = re.compile(r'name:\s+(?P<key>\S+)\s+value:\s+(?P<val>.*?)\s+type:', re.DOTALL)

    matches = pattern.finditer(raw_text)

    for m in matches:
        key = m.group('key').strip()
        val_str = m.group('val').strip()

        try:
            clean_val = json.loads(val_str)
        except (json.JSONDecodeError, TypeError):
            if val_str.isdigit():
                clean_val = int(val_str)
            else:
                clean_val = val_str

        data[key] = clean_val

    return data


def main():
    print('Initialising KPI AGENT (Strict Mode)...')
    time.sleep(UPDATE_TIME)

    while True:
        telemetry_data = {'timestamp': time.time(), 'source': 'acme.operador', 'system': 'redial_2.0', 'metrics': {}}

        for table_kamailio, label_json in TABLES.items():
            telemetry_data['metrics'][label_json] = fetch_table(table_kamailio)

        print(f'\n--- [gNMI TELEMETRY] ---', flush=True)
        print(json.dumps(telemetry_data, indent=4), flush=True)

        time.sleep(5)


if __name__ == '__main__':
    main()
