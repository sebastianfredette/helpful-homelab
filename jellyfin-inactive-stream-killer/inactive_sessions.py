#!/usr/bin/env python3
import requests
import json
import time
import logging
import argparse
import sys
import os
import pickle
from datetime import datetime, timedelta, timezone
import re

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('jellyfin-session-terminator')

class JellyfinSessionTerminator:
    def __init__(self, server_url, api_key, inactivity_timeout_minutes=30, dry_run=False, state_file=None):
        """
        Initialize the Jellyfin Session Terminator
        
        Args:
            server_url (str): The URL to your Jellyfin server
            api_key (str): Your Jellyfin API key
            inactivity_timeout_minutes (int): How long (in minutes) a paused session can be inactive before terminating
            dry_run (bool): If True, will only log what would be done without actually terminating sessions
            state_file (str): Path to file for storing session state between runs
        """
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self.inactivity_timeout = inactivity_timeout_minutes * 60  # Convert to seconds
        self.dry_run = dry_run
        self.headers = {
            'X-MediaBrowser-Token': self.api_key,
            'Content-Type': 'application/json'
        }
        
        # File to store session state between runs
        self.state_file = state_file or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jellyfin_sessions.state')
        self.session_state = self._load_session_state()
        
    def _load_session_state(self):
        """Load saved session state from file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'rb') as f:
                    return pickle.load(f)
            return {}
        except Exception as e:
            logger.warning(f"Error loading session state: {e}")
            return {}
    
    def _save_session_state(self):
        """Save session state to file"""
        try:
            with open(self.state_file, 'wb') as f:
                pickle.dump(self.session_state, f)
        except Exception as e:
            logger.warning(f"Error saving session state: {e}")
            
    def get_active_sessions(self):
        """Get all active Jellyfin sessions"""
        try:
            response = requests.get(
                f"{self.server_url}/Sessions",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching sessions: {e}")
            return []
    
    def terminate_session(self, session_id):
        """Terminate a specific session by ID"""
        if self.dry_run:
            logger.info(f"DRY RUN: Would terminate session {session_id}")
            return True
    
        try:
            # Optional: Notify user
            requests.post(
                f"{self.server_url}/Sessions/{session_id}/Command/DisplayMessage",
                headers=self.headers,
                json={
                    "Header": "Session Terminated",
                    "Text": "Your session was terminated due to inactivity"
                }
            )
    
            # Forcefully terminate session
            response = requests.post(
                f"{self.server_url}/Sessions/{session_id}/Playing/Stop",
                headers=self.headers
            )
            response.raise_for_status()
    
            logger.info(f"Sent Stop command to session {session_id}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending Stop command to session {session_id}: {e}")
            return False
    
    def process_sessions(self):
        """Process all sessions and terminate inactive ones"""
        sessions = self.get_active_sessions()
        now = datetime.now(timezone.utc)  # Use UTC time for consistency
        terminated_count = 0

        # Removed the current time log

        for session in sessions:
            session_id = session.get('Id')
            username = session.get('UserName', 'Unknown User')
            client_name = session.get('Client', 'Unknown client')
            device_name = session.get('DeviceName', 'Unknown device')
            media_info = session.get('NowPlayingItem', {}).get('Name', 'Unknown media')
            playstate = session.get('PlayState', {})

            if not session.get('UserId') or not playstate:
                continue

            is_paused = playstate.get('IsPaused', False)

            if is_paused:
                paused_since = self.session_state.get(session_id)
                if not paused_since:
                    # First time we see it paused, record timestamp
                    self.session_state[session_id] = now
                    logger.info(f"Session for {username} on {device_name} is now paused (started tracking)")
                    continue

                inactive_time = (now - paused_since).total_seconds()

                if inactive_time >= self.inactivity_timeout:
                    logger.info(f"Found inactive paused session for user {username} on {device_name} ({client_name})")
                    logger.info(f"Media: {media_info}, Inactive for: {timedelta(seconds=inactive_time)}")
                    if self.terminate_session(session_id):
                        terminated_count += 1
                        # Remove from state
                        self.session_state.pop(session_id, None)
                else:
                    remaining = self.inactivity_timeout - inactive_time
                    logger.info(
                        f"Session for {username} on {device_name} is paused "
                        f"({timedelta(seconds=inactive_time)}), "
                        f"will be terminated in {timedelta(seconds=remaining)}"
                    )
            else:
                # Not paused; clear tracking if it was paused before
                if session_id in self.session_state:
                    logger.info(f"Session for {username} on {device_name} resumed or stopped; removing from tracking")
                    self.session_state.pop(session_id, None)

        # Save updated session state
        self._save_session_state()
        return terminated_count


def main():
    parser = argparse.ArgumentParser(description='Terminate inactive Jellyfin sessions')
    parser.add_argument('--server', required=True, help='Jellyfin server URL (e.g. http://jellyfin:8096)')
    parser.add_argument('--api-key', required=True, help='Jellyfin API key')
    parser.add_argument('--timeout', type=int, default=30, help='Inactivity timeout in minutes (default: 30)')
    parser.add_argument('--dry-run', action='store_true', help='Only log what would be done without actually terminating sessions')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug logging (very verbose)')
    parser.add_argument('--state-file', help='Path to file for storing session state between runs')
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.INFO)
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    terminator = JellyfinSessionTerminator(
        server_url=args.server,
        api_key=args.api_key,
        inactivity_timeout_minutes=args.timeout,
        dry_run=args.dry_run,
        state_file=args.state_file
    )
    
    logger.info(f"Starting Jellyfin session terminator")
    logger.info(f"Server: {args.server}")
    logger.info(f"Timeout: {args.timeout} minutes")
    # Removed the dry run status log
    
    terminated = terminator.process_sessions()
    
    if args.dry_run:
        logger.info(f"Dry run completed. Would have terminated {terminated} session(s).")
    else:
        logger.info(f"Completed. Terminated {terminated} session(s).")

if __name__ == "__main__":
    main()
