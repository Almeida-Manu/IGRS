import subprocess
import time
import json
import re
import sys

TABLES = {
    'kpi': 'system_metrics',
    'calls': 'live_calls',
    'aor': 'user_profiles'
}

def fetch_table(table_name):
    """Run kamcmd to dump a specific hash table."""
    try:
        # Note: kamcmd output format is text-based RPC
        result = subprocess.run(
            ['kamcmd', 'htable.dump', table_name],
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            # Table might be empty or not exist yet
            return {}
            
        return parse_kamcmd_output(result.stdout)
    except Exception as e:
        print(f"Error fetching {table_name}: {e}", file=sys.stderr)
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
    
    # Regex to find name/value pairs. 
    # value match stops before 'type:' or closing brace
    pattern = re.compile(r'name:\s+(?P<key>\S+)\s+value:\s+(?P<val>.*?)\s+type:', re.DOTALL)
    
    matches = pattern.finditer(raw_text)
    
    for m in matches:
        key = m.group('key').strip()
        val_str = m.group('val').strip()
        
        # Try to decode internal JSON (stored by redial_service.py)
        # e.g. '{"start": 123456, "callee": "bob"}'
        try:
            clean_val = json.loads(val_str)
        except (json.JSONDecodeError, TypeError):
            # If not JSON, try integer, else keep string
            if val_str.isdigit():
                clean_val = int(val_str)
            else:
                clean_val = val_str
                
        data[key] = clean_val

    return data

def main():
    print('Initialising KPI AGENT (gNMI simulation)...')
    # Wait for Kamailio to fully start
    time.sleep(5) 

    while True:
        telemetry_data = {
            'timestamp': time.time(),
            'source': 'acme.operador',
            'system': 'redial_2.0',
            'metrics': {}
        }

        # Fetch data from all relevant tables
        for table_kamailio, label_json in TABLES.items():
            table_data = fetch_table(table_kamailio)
            telemetry_data['metrics'][label_json] = table_data

        # Post-Processing: Calculate total billing from user profiles
        total_billed = 0
        users = telemetry_data['metrics'].get('user_profiles', {})
        for user, profile in users.items():
            if isinstance(profile, dict):
                total_billed += profile.get('billed_seconds', 0)
        
        # Add a derived metric
        telemetry_data['metrics']['system_metrics']['global_billed_seconds'] = total_billed

        # Output the telemetry
        print(f'\n--- [gNMI TELEMETRY] ---',flush=True)
        print(json.dumps(telemetry_data, indent=4),flush=True)

        time.sleep(5)

if __name__ == '__main__':
    main()
