import json
import time

class MessagePackager:
    def __init__(self, device_id: str, location: str):
        self.device_id = device_id
        self.location = location
        self.counter = 0

    def package(self, value: float) -> str:
        self.counter += 1
        timestamp = time.time()
        payload = {
            "packet_id": f"{self.device_id}-{self.counter}",
            "timestamp": timestamp,
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
            "device_id": self.device_id,
            "location": self.location,
            "sensor_data": {
                "value": round(value, 2) if isinstance(value, float) else value,
                "units": "celsius",
                "reading_type": "temperature"
            }
        }
        return json.dumps(payload)




