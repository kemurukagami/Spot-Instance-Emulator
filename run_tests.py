#!/usr/bin/env python3
"""
Test runner for Spot Instance Emulator
Runs all unit tests and generates coverage report
"""
import unittest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_all_tests():
    """Run all tests"""
    # Discover and run all tests
    loader = unittest.TestLoader()
    suite = loader.discover('tests', pattern='test_*.py')
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


def run_module_tests(module):
    """Run tests for a specific module"""
    loader = unittest.TestLoader()
    
    if module == 'common':
        suite = loader.discover('tests/test_common', pattern='test_*.py')
    elif module == 'head':
        suite = loader.discover('tests/test_head_node', pattern='test_*.py')
    elif module == 'instance':
        suite = loader.discover('tests/test_instance_node', pattern='test_*.py')
    else:
        print(f"Unknown module: {module}")
        print("Available modules: common, head, instance")
        return False
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


def run_specific_test(test_path):
    """Run a specific test file or test case"""
    loader = unittest.TestLoader()
    
    try:
        # Try to load as module path (e.g., tests.test_common.test_messages)
        suite = loader.loadTestsFromName(test_path)
    except:
        # Try to load as file path
        if os.path.exists(test_path):
            suite = loader.discover(os.path.dirname(test_path), 
                                   pattern=os.path.basename(test_path))
        else:
            print(f"Could not load test: {test_path}")
            return False
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Run tests for Spot Instance Emulator')
    parser.add_argument('--module', choices=['common', 'head', 'instance'],
                       help='Run tests for specific module')
    parser.add_argument('--test', help='Run specific test file or test case')
    parser.add_argument('--coverage', action='store_true',
                       help='Run with coverage report (requires coverage package)')
    
    args = parser.parse_args()
    
    if args.coverage:
        try:
            import coverage
            cov = coverage.Coverage()
            cov.start()
        except ImportError:
            print("Coverage package not installed. Run: pip install coverage")
            sys.exit(1)
    
    # Determine which tests to run
    if args.test:
        success = run_specific_test(args.test)
    elif args.module:
        success = run_module_tests(args.module)
    else:
        success = run_all_tests()
    
    if args.coverage:
        cov.stop()
        cov.save()
        
        print("\n" + "="*70)
        print("Coverage Report:")
        print("="*70)
        cov.report(include="sie/*")
        
        # Generate HTML report
        cov.html_report(directory="htmlcov", include="sie/*")
        print("\nDetailed HTML coverage report generated in htmlcov/index.html")
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)