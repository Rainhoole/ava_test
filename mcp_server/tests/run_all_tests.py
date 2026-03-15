#!/usr/bin/env python3
"""
Run All Tool Tests
"""

import sys
import os
import time
from pathlib import Path

# Add parent directory to path to import python_tools
sys.path.append(str(Path(__file__).parent.parent))

# Import all test modules
from test_twitter_profile import test_twitter_profile
from test_twitter_following import test_twitter_following
from test_twitter_tweets import test_twitter_tweets
from test_web_scraping import test_web_scraping
from test_web_search import test_web_search
from test_bulk_twitter import test_bulk_twitter_profiles

def run_all_tests():
    """Run all tool tests sequentially."""
    print("🚀 Running All Python Tool Tests")
    print("=" * 60)
    
    tests = [
        ("Twitter Profile Lookup", test_twitter_profile),
        ("Twitter Following", test_twitter_following),
        ("Twitter Tweets", test_twitter_tweets),
        ("Web Scraping", test_web_scraping),
        ("Web Search", test_web_search),
        ("Bulk Twitter Profiles", test_bulk_twitter_profiles),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n📋 Starting: {test_name}")
        print("=" * 60)
        
        start_time = time.time()
        
        try:
            test_func()
            duration = time.time() - start_time
            results.append((test_name, "✅ PASSED", duration))
            print(f"✅ {test_name} completed in {duration:.2f}s")
        except Exception as e:
            duration = time.time() - start_time
            results.append((test_name, f"❌ FAILED: {str(e)}", duration))
            print(f"❌ {test_name} failed in {duration:.2f}s: {str(e)}")
        
        print("-" * 60)
        time.sleep(1)  # Brief pause between tests
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    total_duration = sum(result[2] for result in results)
    passed = sum(1 for result in results if result[1].startswith("✅"))
    failed = len(results) - passed
    
    for test_name, status, duration in results:
        print(f"{status:<20} {test_name:<25} ({duration:.2f}s)")
    
    print("-" * 60)
    print(f"Total Tests: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total Duration: {total_duration:.2f}s")
    print("=" * 60)
    
    if failed == 0:
        print("🎉 All tests passed!")
    else:
        print(f"⚠️  {failed} test(s) failed")

if __name__ == "__main__":
    run_all_tests() 