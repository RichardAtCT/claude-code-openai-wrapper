#!/usr/bin/env python3
"""
Browser authentication handler for Claude in Docker container.
Monitors for authentication needs and automates the browser login flow.
"""

import os
import time
import subprocess
import logging
from pathlib import Path
import json
import asyncio
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DockerAuthHandler:
    def __init__(self):
        self.config_dir = Path("/config/claude")
        self.auth_verified_file = self.config_dir / ".auth_verified"
        self.need_auth_file = Path("/tmp/need_auth")
        self.display = os.environ.get("DISPLAY", ":1")
        
    def check_auth_needed(self) -> bool:
        """Check if authentication is needed."""
        # Check if we're using browser auth
        if os.environ.get("AUTH_METHOD") != "browser":
            logger.info("Not using browser authentication method")
            return False
            
        # Check if auth is already verified
        if self.auth_verified_file.exists():
            logger.info("Authentication already verified")
            return False
            
        # Check if auth is needed
        if self.need_auth_file.exists():
            return True
            
        # Try to verify Claude CLI auth
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                logger.info("Claude CLI is working")
                self.auth_verified_file.touch()
                return False
        except Exception as e:
            logger.error(f"Error checking Claude CLI: {e}")
            
        return True
    
    def wait_for_desktop(self, max_wait: int = 30):
        """Wait for desktop environment to be ready."""
        logger.info("Waiting for desktop environment...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                # Check if XFCE is running
                result = subprocess.run(
                    ["pgrep", "-f", "xfce4-session"],
                    capture_output=True
                )
                if result.returncode == 0:
                    logger.info("Desktop environment is ready")
                    time.sleep(2)  # Give it a bit more time to fully start
                    return True
            except Exception as e:
                logger.debug(f"Desktop check error: {e}")
            
            time.sleep(1)
        
        logger.warning("Desktop environment did not start in time")
        return False
    
    def launch_browser_for_auth(self):
        """Launch Firefox for Claude authentication."""
        logger.info("Launching browser for authentication...")
        
        try:
            # Set display
            env = os.environ.copy()
            env["DISPLAY"] = self.display
            
            # First, try to run claude auth login to get the URL
            logger.info("Running claude auth login...")
            auth_process = subprocess.Popen(
                ["claude", "auth", "login"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            
            # Wait a bit for the process to output the URL
            time.sleep(2)
            
            # Launch Firefox
            logger.info("Opening Firefox...")
            subprocess.Popen(
                ["firefox", "--new-window"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Monitor for successful authentication
            logger.info("Waiting for authentication to complete...")
            logger.info("Please complete the login in the browser window")
            
            # Check periodically if auth is successful
            for i in range(300):  # Wait up to 5 minutes
                time.sleep(1)
                
                # Check if claude CLI now works
                try:
                    result = subprocess.run(
                        ["claude", "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        logger.info("Authentication successful!")
                        self.save_auth_state()
                        self.auth_verified_file.touch()
                        if self.need_auth_file.exists():
                            self.need_auth_file.unlink()
                        return True
                except Exception:
                    pass
                
                if i % 30 == 0:
                    logger.info(f"Still waiting for authentication... ({i}/300 seconds)")
            
            logger.error("Authentication timeout - please try again")
            return False
            
        except Exception as e:
            logger.error(f"Error launching browser: {e}")
            return False
    
    def save_auth_state(self):
        """Save authentication state to persistent storage."""
        logger.info("Saving authentication state...")
        
        # Copy claude config to persistent storage
        claude_config_dir = Path.home() / ".config" / "claude"
        if claude_config_dir.exists():
            try:
                subprocess.run(
                    ["cp", "-r", str(claude_config_dir), "/config/claude/.claude_auth"],
                    check=True
                )
                logger.info("Authentication state saved")
            except Exception as e:
                logger.error(f"Error saving auth state: {e}")
    
    async def run(self):
        """Main run loop."""
        logger.info("Docker authentication handler started")
        
        # Initial wait for services to start
        await asyncio.sleep(5)
        
        while True:
            try:
                if self.check_auth_needed():
                    logger.info("Authentication needed")
                    
                    if self.wait_for_desktop():
                        if self.launch_browser_for_auth():
                            logger.info("Authentication completed successfully")
                        else:
                            logger.error("Authentication failed")
                    else:
                        logger.error("Desktop environment not available")
                
                # Check every 30 seconds
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in auth handler: {e}")
                await asyncio.sleep(30)

def main():
    """Main entry point."""
    handler = DockerAuthHandler()
    asyncio.run(handler.run())

if __name__ == "__main__":
    main()