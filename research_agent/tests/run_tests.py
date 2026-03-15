#!/usr/bin/env python3
"""
Test Runner for Research Agent
==============================
Run all tests or specific test suites.
"""

import os
import sys
import subprocess
import argparse

def run_notion_tests():
    """Run Notion integration tests"""
    print("\n=== Running Notion Integration Tests ===\n")
    
    test_commands = [
        ["python", "notion/test_notion_integration.py", "--list-items"],
        ["python", "notion/test_notion_integration.py", "--test-workflow"],
    ]
    
    for cmd in test_commands:
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Test passed")
            print(result.stdout)
        else:
            print("❌ Test failed")
            print(result.stderr)
        print("-" * 50)

def run_context_isolation_tests():
    """Run context isolation tests"""
    print("\n=== Running Context Isolation Tests ===\n")
    
    cmd = ["python", "test_context_isolation.py"]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Test passed")
        print(result.stdout)
    else:
        print("❌ Test failed")
        print(result.stderr)
    print("-" * 50)

def main():
    parser = argparse.ArgumentParser(description='Run Research Agent tests')
    parser.add_argument('--notion', action='store_true', help='Run Notion tests only')
    parser.add_argument('--context', action='store_true', help='Run context isolation tests only')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    
    args = parser.parse_args()
    
    if args.notion:
        run_notion_tests()
    elif args.context:
        run_context_isolation_tests()
    elif args.all:
        run_notion_tests()
        run_context_isolation_tests()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()