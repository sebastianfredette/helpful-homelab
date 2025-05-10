#!/bin/bash
# This script can be added to your host's crontab to run the terminator script periodically

# Path to where you've saved the Python script
SCRIPT_PATH="/path/to/inactive_sessions.py"

# Your Jellyfin details
JELLYFIN_SERVER="YOUR INTERNAL URL HERE:PORT"
API_KEY="API KEY HERE"
TIMEOUT_MINUTES=45 #time in minutes

# Execute the script
python3 $SCRIPT_PATH --server $JELLYFIN_SERVER --api-key $API_KEY --timeout $TIMEOUT_MINUTES

# To add this to crontab, you can use:
# crontab -e
# Then add a line like:
# */5 * * * * /path/to/cron_script.sh >> /var/log/jellyfin-session-terminator.log 2>&1
