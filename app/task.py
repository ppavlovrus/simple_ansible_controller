from pydantic import BaseModel
from datetime import datetime

class Task(BaseModel):
    playbook_path: str
    inventory: str
    run_time: datetime

    def calculate_eta(self):
        return (self.run_time - datetime.now()).total_seconds()