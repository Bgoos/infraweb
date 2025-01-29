import schedule
import time
import threading
import logging
from datetime import datetime
from typing import Callable, Optional
from ..services.credentials import credentials_manager
from ..services.vcenter.collector import VCenterCollector
from ..services.database.manager import DatabaseManager
from ..utils.config import UPDATE_SCHEDULE_TIME

class SchedulerManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.scheduler_thread: Optional[threading.Thread] = None
        self.is_running = False
        self.db_manager = DatabaseManager()

    def start(self):
        """Start the scheduler"""
        if not self.is_running:
            self.is_running = True
            self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self.scheduler_thread.start()
            self.logger.info("Scheduler started")

    def stop(self):
        """Stop the scheduler"""
        self.is_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join()
            self.logger.info("Scheduler stopped")

    def _run_scheduler(self):
        """Run the scheduler loop"""
        schedule.every().day.at(UPDATE_SCHEDULE_TIME).do(self.perform_update)
        
        while self.is_running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

    def perform_update(self) -> bool:
        """Perform the database update"""
        try:
            self.logger.info(f"Starting scheduled update at {datetime.now()}")
            
            # Get credentials
            credentials = credentials_manager.get_credentials()
            
            # Initialize collector
            collector = VCenterCollector(credentials)
            
            # Collect data
            self.logger.info("Collecting data from vCenters...")
            vcenter_data = collector.collect_from_all_vcenters()
            
            # Update database
            self.logger.info("Updating database...")
            success = self.db_manager.perform_full_update(vcenter_data)
            
            if success:
                self.logger.info("Scheduled update completed successfully")
            else:
                self.logger.error("Scheduled update failed")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error during scheduled update: {str(e)}")
            return False

    def manual_update(self) -> bool:
        """Trigger a manual update"""
        self.logger.info("Manual update triggered")
        return self.perform_update()

# Create a singleton instance
scheduler_manager = SchedulerManager()