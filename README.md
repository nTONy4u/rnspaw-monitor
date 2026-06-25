# RPi Reticulum Network Monitor

Monitor your [Reticulum](https://reticulum.network) network for new nodes, traffic spikes, and LoRa details with cloud dashboard on PythonAnywhere.

[![Python](https://img.shields.io/badge/Python-3.6+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com)

---

## Features

- New node detection in Reticulum network
- Traffic spike monitoring with percentage increase
- Route change tracking (hop count changes)
- Detailed LoRa traffic information (noise floor, airtime, channel load)
- Heartbeat with network status (nodes, interfaces, LoRa details)
- Cloud dashboard on PythonAnywhere
- Automatic database cleanup (keeps 500 records, 30 days retention)
- Flexible authentication (works with or without password protection)
- Configurable hash display (full or shortened)

---

## Architecture

- RPi4 runs `rnspaw_monitor.py` which collects data from `rnpath` and `rnstatus`
- Data is sent via HTTP POST to PythonAnywhere API endpoint
- PythonAnywhere stores alerts in SQLite database
- Web dashboard displays recent alerts with filtering by type

---

## Quick Start

### 1. On your machine

**1.1** Clone the repository:

```git clone https://github.com/ntony4u/rnspaw-monitor.git ```

```cd rnspaw-monitor ```  
  


**1.2** Install dependencies:  

```pip3 install requests ```  
  


**1.3** Find Reticulum command paths:  

```which rnpath ```  
```which rnstatus ```  


Usually: `/home/USERNAME/venv/reticulum/bin/rnpath`  
  


**1.4** Edit configuration in `rnspaw_monitor.py`:  

`PYTHONANYWHERE_URL = "https://YOUR_USERNAME.pythonanywhere.com/api/alert"`  
  


**1.5** Also update `rnpath` and `rnstatus` paths to match your system.  
  


**1.6** Test the script:  

```python3 rnspaw_monitor.py ```  
  


**1.7** Add to crontab (every 15 minutes):  

```crontab -e ```

Add this line:  
`*/15 * * * * /usr/bin/python3 /home/USERNAME/rnspaw-monitor/rnspaw_monitor.py >> /tmp/rn_monitor.log 2>&1`  



### 2. On PythonAnywhere

1. Go to **Web** tab -> **Add a new web app** -> Manual configuration -> Python 3.10
2. Go to **Files** -> Create `mysite/app.py` and paste the code
3. Go to **Web** -> **WSGI configuration file** -> Replace with `wsgi.py` content
4. (Optional) Enable **Password protection** in Web tab
5. Click **Reload**
6. Visit `https://YOUR_USERNAME.pythonanywhere.com`

---

## Configuration

### Machine (`rnspaw_monitor.py`)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `PYTHONANYWHERE_URL` | Dashboard URL | `https://YOUR_USERNAME.pythonanywhere.com/api/alert` |
| `AUTH_USERNAME` | PythonAnywhere username for password protection | Empty (no auth) |
| `AUTH_PASSWORD` | PythonAnywhere password for password protection | Empty (no auth) |
| `SHOW_FULL_HASH` | Show full node hash or shortened (8 chars) | `True` |
| `SHOW_LORA_DETAILS` | Show LoRa traffic details (noise, airtime, etc.) | `True` |
| `TRAFFIC_THRESHOLD_PERCENT` | Alert threshold for traffic spikes | `10.0` |
| `HEARTBEAT_INTERVAL` | Heartbeat interval in seconds | `3600` (1 hour) |

### PythonAnywhere (`app.py`)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `MAX_RECORDS` | Maximum alerts in database | `500` |
| `MAX_AGE_DAYS` | Maximum age of records in days | `30` |

---

## Files

- `rnspaw_monitor.py` - Main monitoring script for RPi4
- `app.py` - Flask dashboard application for PythonAnywhere
- `wsgi.py` - WSGI configuration for PythonAnywhere

---

## Troubleshooting

### Cron cannot find rnpath/rnstatus

**Error:** `No such file or directory: 'rnpath'`

**Solution:** Use full paths in the script:
`/home/USERNAME/venv/reticulum/bin/rnpath', '-t', '-r'  `  
`/home/USERNAME/venv/reticulum/bin/rnstatus`



### Dashboard returns 401 Unauthorized

**Error:** `Dashboard returned 401: Unauthorized`

**Solution:** Configure authentication in `rnspaw_monitor.py`:  
`AUTH_USERNAME = "your_username"`  
`AUTH_PASSWORD = "your_password"`



Or disable password protection on PythonAnywhere.

### Database grows too large

The script automatically keeps only 500 records and deletes data older than 30 days.

---

## Acknowledgments

- [Reticulum Network](https://reticulum.network) - The amazing mesh networking stack
- [PythonAnywhere](https://pythonanywhere.com) - For free Python hosting
- [Flask](https://flask.palletsprojects.com) - The lightweight web framework
