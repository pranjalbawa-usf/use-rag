"""
Load Testing Script for RAG System
===================================
Tests the system with concurrent requests to measure performance.
"""

import asyncio
import aiohttp
import time
import statistics
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"
CONCURRENT_REQUESTS = 50  # Number of concurrent requests
TEST_QUESTIONS = [
    "What is in this document?",
    "Tell me more about the content",
    "Summarize the key points",
    "What are the main details?",
    "Give me an overview",
    "What information is available?",
    "Describe the document",
    "What can you tell me?",
    "Extract the important data",
    "What is the summary?",
]


async def make_chat_request(session, question, request_id):
    """Make a single chat request and measure response time."""
    start_time = time.time()
    
    try:
        async with session.post(
            f"{BASE_URL}/chat/stream",
            json={"question": question, "n_chunks": 3},
            timeout=aiohttp.ClientTimeout(total=120)
        ) as response:
            # Read the full response
            content = await response.text()
            end_time = time.time()
            
            duration = end_time - start_time
            status = response.status
            
            return {
                "request_id": request_id,
                "status": status,
                "duration": duration,
                "success": status == 200,
                "response_length": len(content)
            }
    except asyncio.TimeoutError:
        return {
            "request_id": request_id,
            "status": "timeout",
            "duration": time.time() - start_time,
            "success": False,
            "error": "Request timed out"
        }
    except Exception as e:
        return {
            "request_id": request_id,
            "status": "error",
            "duration": time.time() - start_time,
            "success": False,
            "error": str(e)
        }


async def make_stats_request(session, request_id):
    """Make a stats request (lightweight endpoint)."""
    start_time = time.time()
    
    try:
        async with session.get(
            f"{BASE_URL}/stats",
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            await response.json()
            end_time = time.time()
            
            return {
                "request_id": request_id,
                "status": response.status,
                "duration": end_time - start_time,
                "success": response.status == 200
            }
    except Exception as e:
        return {
            "request_id": request_id,
            "status": "error",
            "duration": time.time() - start_time,
            "success": False,
            "error": str(e)
        }


async def run_load_test(num_requests, test_type="mixed"):
    """Run load test with specified number of concurrent requests."""
    print(f"\n{'='*60}")
    print(f"LOAD TEST: {num_requests} Concurrent Requests")
    print(f"Test Type: {test_type}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    connector = aiohttp.TCPConnector(limit=num_requests, limit_per_host=num_requests)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        
        for i in range(num_requests):
            if test_type == "chat":
                question = TEST_QUESTIONS[i % len(TEST_QUESTIONS)]
                tasks.append(make_chat_request(session, question, i))
            elif test_type == "stats":
                tasks.append(make_stats_request(session, i))
            else:  # mixed
                if i % 3 == 0:
                    tasks.append(make_stats_request(session, i))
                else:
                    question = TEST_QUESTIONS[i % len(TEST_QUESTIONS)]
                    tasks.append(make_chat_request(session, question, i))
        
        # Run all requests concurrently
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
    
    return results, total_time


def analyze_results(results, total_time):
    """Analyze and print test results."""
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    durations = [r["duration"] for r in successful]
    
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    
    print(f"\n📊 Overall Statistics:")
    print(f"   Total Requests:     {len(results)}")
    print(f"   Successful:         {len(successful)} ({len(successful)/len(results)*100:.1f}%)")
    print(f"   Failed:             {len(failed)} ({len(failed)/len(results)*100:.1f}%)")
    print(f"   Total Test Time:    {total_time:.2f}s")
    print(f"   Requests/Second:    {len(results)/total_time:.2f}")
    
    if durations:
        print(f"\n⏱️  Response Times (successful requests):")
        print(f"   Min:                {min(durations):.3f}s")
        print(f"   Max:                {max(durations):.3f}s")
        print(f"   Average:            {statistics.mean(durations):.3f}s")
        print(f"   Median:             {statistics.median(durations):.3f}s")
        if len(durations) > 1:
            print(f"   Std Dev:            {statistics.stdev(durations):.3f}s")
        
        # Percentiles
        sorted_durations = sorted(durations)
        p90_idx = int(len(sorted_durations) * 0.9)
        p95_idx = int(len(sorted_durations) * 0.95)
        p99_idx = int(len(sorted_durations) * 0.99)
        
        print(f"\n📈 Percentiles:")
        print(f"   P90:                {sorted_durations[p90_idx] if p90_idx < len(sorted_durations) else 'N/A'}s")
        print(f"   P95:                {sorted_durations[p95_idx] if p95_idx < len(sorted_durations) else 'N/A'}s")
        print(f"   P99:                {sorted_durations[p99_idx] if p99_idx < len(sorted_durations) else 'N/A'}s")
    
    if failed:
        print(f"\n❌ Failed Requests:")
        for f in failed[:5]:  # Show first 5 failures
            error = f.get("error", f.get("status", "Unknown"))
            print(f"   Request {f['request_id']}: {error}")
        if len(failed) > 5:
            print(f"   ... and {len(failed) - 5} more failures")
    
    print(f"\n{'='*60}\n")
    
    return {
        "total": len(results),
        "successful": len(successful),
        "failed": len(failed),
        "total_time": total_time,
        "avg_response_time": statistics.mean(durations) if durations else 0,
        "requests_per_second": len(results) / total_time
    }


async def main():
    """Run multiple load tests."""
    print("\n" + "="*60)
    print("RAG SYSTEM LOAD TESTING")
    print("="*60)
    
    # Check if server is running
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    print("❌ Server is not responding properly!")
                    return
                print("✅ Server is running\n")
    except Exception as e:
        print(f"❌ Cannot connect to server at {BASE_URL}")
        print(f"   Error: {e}")
        print("   Make sure the server is running!")
        return
    
    all_results = []
    
    # Test 1: 20 concurrent stats requests (warmup)
    print("\n🔥 Warmup: 20 Stats Requests...")
    results, total_time = await run_load_test(20, "stats")
    summary = analyze_results(results, total_time)
    all_results.append(("Warmup (20 stats)", summary))
    
    # Test 2: 20 concurrent chat requests
    print("\n📝 Test 1: 20 Concurrent Chat Requests...")
    results, total_time = await run_load_test(20, "chat")
    summary = analyze_results(results, total_time)
    all_results.append(("20 Chat Requests", summary))
    
    # Test 3: 30 concurrent chat requests
    print("\n📝 Test 2: 30 Concurrent Chat Requests...")
    results, total_time = await run_load_test(30, "chat")
    summary = analyze_results(results, total_time)
    all_results.append(("30 Chat Requests", summary))
    
    # Test 4: 50 concurrent chat requests
    print("\n📝 Test 3: 50 Concurrent Chat Requests...")
    results, total_time = await run_load_test(50, "chat")
    summary = analyze_results(results, total_time)
    all_results.append(("50 Chat Requests", summary))
    
    # Test 5: 50 mixed requests
    print("\n📝 Test 4: 50 Mixed Requests (Chat + Stats)...")
    results, total_time = await run_load_test(50, "mixed")
    summary = analyze_results(results, total_time)
    all_results.append(("50 Mixed Requests", summary))
    
    # Final Summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    print(f"\n{'Test Name':<25} {'Success%':<10} {'Avg Time':<12} {'Req/s':<10}")
    print("-"*60)
    for name, summary in all_results:
        success_pct = summary['successful'] / summary['total'] * 100
        print(f"{name:<25} {success_pct:>6.1f}%    {summary['avg_response_time']:>8.3f}s    {summary['requests_per_second']:>6.2f}")
    
    print("\n✅ Load testing complete!")


if __name__ == "__main__":
    asyncio.run(main())
