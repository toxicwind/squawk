# kite_reconnect_fix.py
# Emergent experimental work: Robust keepalive/reconnect for kite-cli gateway
import asyncio
import time
import random

class KiteGatewayReconnector:
    def __init__(self, host="localhost", port=8080, max_retries=5, base_delay=1.0):
        self.host = host
        self.port = port
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.connected = False

    async def connect(self):
        for attempt in range(self.max_retries):
            try:
                # Simulate connection attempt
                print(f"Attempting connection to {self.host}:{self.port} (attempt {attempt + 1})")
                # In real implementation, this would be aiohttp or websockets connect
                await asyncio.sleep(0.1) 
                self.connected = True
                print("Connected successfully.")
                return True
            except Exception as e:
                print(f"Connection failed: {e}")
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"Retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
                else:
                    print("Max retries reached. Gateway unreachable.")
                    return False
        return False

    async def keepalive_loop(self):
        while True:
            if not self.connected:
                await self.connect()
            else:
                # Simulate keepalive ping
                print("Keepalive ping sent.")
                await asyncio.sleep(30) # Ping every 30s

if __name__ == "__main__":
    gateway = KiteGatewayReconnector()
    # Run the keepalive loop
    asyncio.run(gateway.keepalive_loop())
