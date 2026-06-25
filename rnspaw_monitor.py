#!/usr/bin/env python3
"""
Reticulum Network Monitor
=============================================
Monitors Reticulum network for new nodes and traffic spikes.
Sends alerts to PythonAnywhere dashboard.
"""

import subprocess
import json
import time
import requests
import re
from datetime import datetime
import os
import logging

# ============ CONFIGURATION ============
PYTHONANYWHERE_URL = "https://YOURNAME.pythonanywhere.com/api/alert"

# Authentication (leave empty if no password protection)
AUTH_USERNAME = ""  # Your PythonAnywhere username
AUTH_PASSWORD = ""  # Your PythonAnywhere password

# Report format
SHOW_FULL_HASH = True  # True - full hash, False - first 8 chars

# LoRa details
SHOW_LORA_DETAILS = True

# File to store last known state
STATE_FILE = "/tmp/rn_monitor_state.json"
LOG_FILE = "/tmp/rn_monitor.log"

# Alert if traffic increases by this percentage
TRAFFIC_THRESHOLD_PERCENT = 10.0

# Heartbeat interval in seconds
HEARTBEAT_INTERVAL = 3600  # 1 hour

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)


class ReticulumMonitor:
    """Main monitor class"""
    
    def __init__(self):
        self.state = self._load_state()
        self.current = {}
        self.alerts = []
        self.full_status = ""
        
    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {'paths': [], 'traffic': {}, 'last_seen': {}, 'last_heartbeat': 0}
        return {'paths': [], 'traffic': {}, 'last_seen': {}, 'last_heartbeat': 0}
    
    def _save_state(self):
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.current, f)
        except Exception as e:
            logging.error(f"Failed to save state: {e}")
    
    def _format_hash(self, hash_value):
        if SHOW_FULL_HASH:
            return hash_value
        else:
            return f"{hash_value[:8]}..."
    
    def get_rnpath(self):
        try:
            result = subprocess.run(
                ['/home/octopi/venv/reticulum/bin/rnpath', '-t', '-r'],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            nodes = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                match = re.search(
                    r'<([a-f0-9]+)> is (\d+) hops away via <([a-f0-9]+)> on (.+?) expires (.+)',
                    line
                )
                if match:
                    nodes.append({
                        'destination': match.group(1),
                        'hops': int(match.group(2)),
                        'next_hop': match.group(3),
                        'interface': match.group(4).strip(),
                        'expires': match.group(5)
                    })
            return nodes
        except Exception as e:
            logging.error(f"Error in get_rnpath: {e}")
            return []
    
    def get_rnstatus_traffic(self):
        """Parse rnstatus to get traffic data per interface"""
        try:
            result = subprocess.run(
                ['/home/octopi/venv/reticulum/bin/rnstatus'],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            traffic = {}
            current_interface = None
            current_details = {}
            
            lines = result.stdout.strip().split('\n')
            i = 0
            while i < len(lines):
                line = lines[i]
                
                # Find interface headers
                if 'Interface[' in line:
                    match = re.search(r'Interface\[(.*?)\]', line)
                    if match:
                        current_interface = match.group(1)
                        traffic[current_interface] = {}
                        current_details = {}
                
                # Parse traffic - look for "Traffic" in current line OR next line
                if current_interface and 'Traffic' in line:
                    # Try to parse traffic from current line (single line format)
                    match = re.search(
                        r'Traffic\s+:\s+↑([\d.]+)\s+(\w+)\s+([\d.]+)\s+(\w+)\s+↓([\d.]+)\s+(\w+)\s+([\d.]+)\s+(\w+)',
                        line
                    )
                    if match:
                        traffic[current_interface] = {
                            'up_bytes': self._parse_size(match.group(1), match.group(2)),
                            'up_rate': self._parse_size(match.group(3), match.group(4)),
                            'down_bytes': self._parse_size(match.group(5), match.group(6)),
                            'down_rate': self._parse_size(match.group(7), match.group(8)),
                            'up_bytes_human': f"{match.group(1)} {match.group(2)}",
                            'down_bytes_human': f"{match.group(5)} {match.group(6)}",
                            'up_rate_human': f"{match.group(3)} {match.group(4)}",
                            'down_rate_human': f"{match.group(7)} {match.group(8)}"
                        }
                        traffic[current_interface].update(current_details)
                    else:
                        # Try to parse multi-line traffic (up on one line, down on next)
                        if i + 1 < len(lines):
                            next_line = lines[i + 1]
                            if '↓' in next_line:
                                up_match = re.search(r'↑([\d.]+)\s+(\w+)\s+([\d.]+)\s+(\w+)', line)
                                down_match = re.search(r'↓([\d.]+)\s+(\w+)\s+([\d.]+)\s+(\w+)', next_line)
                                if up_match and down_match:
                                    traffic[current_interface] = {
                                        'up_bytes': self._parse_size(up_match.group(1), up_match.group(2)),
                                        'up_rate': self._parse_size(up_match.group(3), up_match.group(4)),
                                        'down_bytes': self._parse_size(down_match.group(1), down_match.group(2)),
                                        'down_rate': self._parse_size(down_match.group(3), down_match.group(4)),
                                        'up_bytes_human': f"{up_match.group(1)} {up_match.group(2)}",
                                        'down_bytes_human': f"{down_match.group(1)} {down_match.group(2)}",
                                        'up_rate_human': f"{up_match.group(3)} {up_match.group(4)}",
                                        'down_rate_human': f"{down_match.group(3)} {down_match.group(4)}"
                                    }
                                    traffic[current_interface].update(current_details)
                                    i += 1  # Skip next line since we processed it
                
                # Parse other details (Noise, Airtime, etc.)
                if current_interface:
                    if 'Noise Fl.' in line:
                        match = re.search(r'Noise Fl\.\s+:\s+([-\d]+)\s+dBm', line)
                        if match:
                            current_details['noise_floor'] = match.group(1)
                    
                    if 'Intrfrnc.' in line:
                        match = re.search(r'Intrfrnc\.\s+:\s+([-\d]+)\s+dBm\s+([\ds]+ago)', line)
                        if match:
                            current_details['interference'] = match.group(1)
                            current_details['interference_age'] = match.group(2)
                    
                    if 'Airtime' in line:
                        match = re.search(
                            r'Airtime\s+:\s+([\d.]+)%\s+\(([\ds]+)\),\s+([\d.]+)%\s+\(([\dh]+)\)',
                            line
                        )
                        if match:
                            current_details['airtime_short'] = match.group(1)
                            current_details['airtime_short_period'] = match.group(2)
                            current_details['airtime_long'] = match.group(3)
                            current_details['airtime_long_period'] = match.group(4)
                    
                    if 'Ch. Load' in line:
                        match = re.search(
                            r'Ch\. Load\s+:\s+([\d.]+)%\s+\(([\ds]+)\),\s+([\d.]+)%\s+\(([\dh]+)\)',
                            line
                        )
                        if match:
                            current_details['channel_load_short'] = match.group(1)
                            current_details['channel_load_short_period'] = match.group(2)
                            current_details['channel_load_long'] = match.group(3)
                            current_details['channel_load_long_period'] = match.group(4)
                
                i += 1
            
            self.full_status = result.stdout
            return traffic
        except Exception as e:
            logging.error(f"Error in get_rnstatus: {e}")
            return {}
    
    def _parse_size(self, value, unit):
        multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3}
        try:
            return float(value) * multipliers.get(unit, 1)
        except:
            return 0
    
    def _get_lora_traffic_details(self):
        """Get detailed LoRa traffic information from current data"""
        lora_interfaces = {}
        
        for iface, data in self.current.get('traffic', {}).items():
            if 'lora' in iface.lower():
                # Extract clean name
                clean_name = iface
                if 'RNodeInterface' in iface:
                    clean_name = iface.replace('RNodeInterface[', '').replace(']', '').strip()
                
                lora_interfaces[iface] = {
                    'clean_name': clean_name,
                    'down': data.get('down_bytes_human', '0'),
                    'up': data.get('up_bytes_human', '0'),
                    'down_rate': data.get('down_rate_human', '0'),
                    'up_rate': data.get('up_rate_human', '0'),
                    'noise_floor': data.get('noise_floor', 'N/A'),
                    'interference': data.get('interference', 'N/A'),
                    'airtime': data.get('airtime_short', 'N/A'),
                    'channel_load': data.get('channel_load_short', 'N/A')
                }
        
        return lora_interfaces
    
    def check_new_nodes(self, current_nodes):
        previous_nodes = {n['destination']: n for n in self.state.get('paths', [])}
        
        for node in current_nodes:
            dest = node['destination']
            dest_display = self._format_hash(dest)
            
            if dest not in previous_nodes:
                if 'LoRa' in node['interface']:
                    interface_type = "LoRa"
                    icon = "[LoRa]"
                elif 'TCP' in node['interface']:
                    interface_type = "TCP"
                    icon = "[TCP]"
                elif 'I2P' in node['interface']:
                    interface_type = "I2P"
                    icon = "[I2P]"
                elif 'Local' in node['interface']:
                    interface_type = "Local"
                    icon = "[Local]"
                else:
                    interface_type = node['interface']
                    icon = "[Link]"
                
                traffic_info = ""
                if node['interface'] in self.current.get('traffic', {}):
                    t = self.current['traffic'][node['interface']]
                    if t.get('down_bytes', 0) > 0:
                        traffic_info = f", Incoming: {t.get('down_bytes_human', '0')}"
                
                lora_details = ""
                if SHOW_LORA_DETAILS and 'LoRa' in node['interface']:
                    lora_data = self._get_lora_traffic_details()
                    if node['interface'] in lora_data:
                        l = lora_data[node['interface']]
                        lora_details = f"""
   LoRa Details:
      * Noise Floor: {l.get('noise_floor', 'N/A')} dBm
      * Interference: {l.get('interference', 'N/A')} dBm
      * Airtime: {l.get('airtime', 'N/A')}%
      * Channel Load: {l.get('channel_load', 'N/A')}%
      * Up: {l.get('up', '0')} | Down: {l.get('down', '0')}
      * Rate: up {l.get('up_rate', '0')} down {l.get('down_rate', '0')}"""
                
                self.alerts.append({
                    'type': 'new_node',
                    'destination': dest,
                    'full_hash': dest,
                    'display_hash': dest_display,
                    'hops': node['hops'],
                    'interface': node['interface'],
                    'interface_type': interface_type,
                    'icon': icon,
                    'expires': node['expires'],
                    'traffic_info': traffic_info,
                    'lora_details': lora_details,
                    'message': (
                        f"{icon} NEW NODE: {dest_display}\n"
                        f"   Interface: {node['interface']} ({interface_type})\n"
                        f"   Hops: {node['hops']}\n"
                        f"   Expires: {node['expires']}{traffic_info}"
                        f"{lora_details}"
                    )
                })
                logging.info(f"New node: {dest_display} via {node['interface']}")
            
            elif previous_nodes[dest]['hops'] != node['hops']:
                self.alerts.append({
                    'type': 'hops_change',
                    'destination': dest,
                    'full_hash': dest,
                    'display_hash': dest_display,
                    'old_hops': previous_nodes[dest]['hops'],
                    'new_hops': node['hops'],
                    'interface': node['interface'],
                    'message': (
                        f"[ROUTE] CHANGED: {dest_display}\n"
                        f"   Interface: {node['interface']}\n"
                        f"   Hops: {previous_nodes[dest]['hops']} -> {node['hops']}\n"
                        f"   Expires: {node['expires']}"
                    )
                })
                logging.info(f"Hop change for {dest_display}")
    
    def check_traffic_spikes(self, current_traffic):
        previous_traffic = self.state.get('traffic', {})
        
        for interface, data in current_traffic.items():
            if interface in previous_traffic:
                old_down = previous_traffic[interface].get('down_bytes', 0)
                new_down = data.get('down_bytes', 0)
                
                if old_down > 0:
                    increase = ((new_down - old_down) / old_down) * 100
                    if increase > TRAFFIC_THRESHOLD_PERCENT:
                        if 'LoRa' in interface:
                            icon = "[LoRa]"
                            interface_type = "LoRa"
                        elif 'TCP' in interface:
                            icon = "[TCP]"
                            interface_type = "TCP"
                        else:
                            icon = "[Link]"
                            interface_type = interface
                        
                        details = ""
                        if 'noise_floor' in data:
                            details += f"\n   Noise Floor: {data.get('noise_floor', 'N/A')} dBm"
                        if 'interference' in data:
                            details += f"\n   Interference: {data.get('interference', 'N/A')} dBm"
                        if 'airtime_short' in data:
                            details += f"\n   Airtime: {data.get('airtime_short', 'N/A')}% ({data.get('airtime_short_period', 'N/A')})"
                        
                        lora_extra = ""
                        if SHOW_LORA_DETAILS and 'LoRa' in interface:
                            lora_data = self._get_lora_traffic_details()
                            if interface in lora_data:
                                l = lora_data[interface]
                                lora_extra = f"""
   LoRa Details:
      * Channel Load: {l.get('channel_load', 'N/A')}%
      * Airtime: {l.get('airtime', 'N/A')}%
      * Current Up/Down: {l.get('up', '0')} / {l.get('down', '0')}"""
                        
                        self.alerts.append({
                            'type': 'traffic_spike',
                            'interface': interface,
                            'interface_type': interface_type,
                            'icon': icon,
                            'increase_percent': round(increase, 1),
                            'new_traffic': data.get('down_bytes_human', f"{new_down} B"),
                            'old_traffic': previous_traffic[interface].get('down_bytes_human', f"{old_down} B"),
                            'new_rate': data.get('down_rate_human', 'N/A'),
                            'old_rate': previous_traffic[interface].get('down_rate_human', 'N/A'),
                            'details': details,
                            'lora_extra': lora_extra,
                            'message': (
                                f"{icon} TRAFFIC SPIKE on {interface}\n"
                                f"   Incoming: {previous_traffic[interface].get('down_bytes_human', f'{old_down}B')} -> {data.get('down_bytes_human', f'{new_down}B')} (+{round(increase, 1)}%)\n"
                                f"   Rate: {previous_traffic[interface].get('down_rate_human', 'N/A')} -> {data.get('down_rate_human', 'N/A')}{details}{lora_extra}"
                            )
                        })
                        logging.info(f"Traffic spike on {interface}: +{increase:.1f}%")
    
    def send_heartbeat(self):
        current_time = time.time()
        last_heartbeat = self.state.get('last_heartbeat', 0)
        
        if current_time - last_heartbeat > HEARTBEAT_INTERVAL:
            node_count = len(self.current.get('paths', []))
            interfaces = len(self.current.get('traffic', {}))
            
            lora_heartbeat = ""
            if SHOW_LORA_DETAILS:
                lora_data = self._get_lora_traffic_details()
                if lora_data:
                    lora_heartbeat = "\n   LoRa Traffic:"
                    for iface, data in lora_data.items():
                        clean_name = data.get('clean_name', iface)
                        lora_heartbeat += f"""
      * {clean_name}:
         Up: {data.get('up', '0')} | Down: {data.get('down', '0')}
         Rate: up {data.get('up_rate', '0')} down {data.get('down_rate', '0')}
         Noise: {data.get('noise_floor', 'N/A')} dBm | Airtime: {data.get('airtime', 'N/A')}%
         Channel Load: {data.get('channel_load', 'N/A')}%"""
            
            self.alerts.append({
                'type': 'heartbeat',
                'destination': 'system',
                'full_hash': 'heartbeat',
                'interface': 'system',
                'message': (
                    f"HEARTBEAT - Monitor is alive\n"
                    f"   Nodes: {node_count}\n"
                    f"   Interfaces: {interfaces}\n"
                    f"   Uptime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    f"{lora_heartbeat}"
                )
            })
            self.current['last_heartbeat'] = current_time
            logging.info(f"Heartbeat sent - {node_count} nodes, {interfaces} interfaces")
    
    def send_to_dashboard(self):
        if not self.alerts:
            return
        
        payload = {
            'timestamp': datetime.now().isoformat(),
            'alerts': self.alerts,
            'full_status': self.full_status,
            'traffic_summary': {
                iface: {
                    'down': t.get('down_bytes_human', '0'),
                    'up': t.get('up_bytes_human', '0'),
                    'down_rate': t.get('down_rate_human', '0'),
                    'up_rate': t.get('up_rate_human', '0'),
                    'noise_floor': t.get('noise_floor', 'N/A'),
                    'airtime': t.get('airtime_short', 'N/A'),
                    'channel_load': t.get('channel_load_short', 'N/A')
                }
                for iface, t in self.current.get('traffic', {}).items()
            }
        }
        
        try:
            auth_params = {}
            if AUTH_USERNAME and AUTH_PASSWORD:
                auth_params['auth'] = (AUTH_USERNAME, AUTH_PASSWORD)
            
            response = requests.post(
                PYTHONANYWHERE_URL,
                json=payload,
                timeout=10,
                headers={'Content-Type': 'application/json'},
                **auth_params
            )
            
            if response.status_code == 200:
                logging.info(f"Sent {len(self.alerts)} alerts to dashboard")
            else:
                if response.status_code == 401 and auth_params:
                    logging.warning("Authentication failed, trying without...")
                    response = requests.post(
                        PYTHONANYWHERE_URL,
                        json=payload,
                        timeout=10,
                        headers={'Content-Type': 'application/json'}
                    )
                    if response.status_code == 200:
                        logging.info(f"Sent {len(self.alerts)} alerts to dashboard (without auth)")
                    else:
                        logging.error(f"Dashboard returned {response.status_code}: {response.text}")
                else:
                    logging.error(f"Dashboard returned {response.status_code}: {response.text}")
        except Exception as e:
            logging.error(f"Failed to send alerts: {e}")
    
    def run(self):
        logging.info("=== Starting monitoring cycle ===")
        
        self.current['paths'] = self.get_rnpath()
        self.current['traffic'] = self.get_rnstatus_traffic()
        self.current['timestamp'] = datetime.now().isoformat()
        
        self.check_new_nodes(self.current['paths'])
        self.check_traffic_spikes(self.current['traffic'])
        self.send_heartbeat()
        
        if self.alerts:
            self.send_to_dashboard()
            logging.info(f"Found {len(self.alerts)} events")
        else:
            logging.info("No changes detected")
        
        self._save_state()


if __name__ == "__main__":
    monitor = ReticulumMonitor()
    monitor.run()