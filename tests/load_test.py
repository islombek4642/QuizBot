import asyncio
import httpx
import time
import os
import hmac
import hashlib
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Default to local if not set, but user likely wants to test prod
TARGET_URL = "http://localhost:8000" 
if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
    TARGET_URL = sys.argv[1]

if not BOT_TOKEN:
    print("❌ Error: BOT_TOKEN not found in .env file.")
    sys.exit(1)

def generate_token(user_id: int) -> str:
    """Generate a valid auth token for testing"""
    timestamp = int(time.time())
    data = f"{user_id}:{timestamp}"
    secret = BOT_TOKEN.encode()
    signature = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
    return f"{user_id}:{timestamp}:{signature}"

async def simulate_user(client: httpx.AsyncClient, user_id: int, total_requests: int):
    """Simulate a single user making multiple requests"""
    token = generate_token(user_id)
    headers = {"X-Auth-Token": token}
    
    success = 0
    fail = 0
    times = []

    for _ in range(total_requests):
        start = time.time()
        try:
            # Hit the quizzes list endpoint (lightweight but DB involved)
            resp = await client.get(f"{TARGET_URL}/api/quizzes", headers=headers)
            if resp.status_code == 200:
                success += 1
            else:
                fail += 1
                # print(f"Fail: {resp.status_code}") # Uncomment for verbose debug
        except Exception as e:
            fail += 1
            # print(f"Error: {e}")
        
        times.append(time.time() - start)
        # Small sleep to be realistic (0.1s to 0.5s) if acts as real user, 
        # but for STRESS test we usually hammer it.
        # await asyncio.sleep(0.1) 

    return success, fail, times

async def run_load_test(concurrent_users: int, requests_per_user: int):
    print(f"🚀 Starting Load Test on {TARGET_URL}")
    print(f"👥 Users: {concurrent_users}")
    print(f"🔄 Requests per user: {requests_per_user}")
    print(f"📨 Total requests: {concurrent_users * requests_per_user}")
    print("-" * 40)

    async with httpx.AsyncClient(timeout=10.0) as client:
        start_time = time.time()
        
        tasks = []
        for i in range(concurrent_users):
            # Use different user_ids to simulate distinct users
            user_id = 1000 + i 
            tasks.append(simulate_user(client, user_id, requests_per_user))
            
        results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        
    # Aggregate results
    total_success = sum(r[0] for r in results)
    total_fail = sum(r[1] for r in results)
    all_times = [t for r in results for t in r[2]]
    avg_latency = (sum(all_times) / len(all_times)) * 1000 if all_times else 0
    
    print("-" * 40)
    print(f"✅ Test Completed in {total_time:.2f} seconds")
    print(f"📊 Results:")
    print(f"   Success: {total_success}")
    print(f"   Failed:  {total_fail}")
    print(f"   RPS (Req/sec): {len(all_times) / total_time:.2f}")
    print(f"   Avg Latency: {avg_latency:.2f} ms")

if __name__ == "__main__":
    # Default settings
    USERS = 50
    REQS = 20
    
    # Simple CLI args
    # python tests/load_test.py [url] [users] [reqs]
    if len(sys.argv) > 2:
        USERS = int(sys.argv[2])
    if len(sys.argv) > 3:
        REQS = int(sys.argv[3])

    asyncio.run(run_load_test(USERS, REQS))
