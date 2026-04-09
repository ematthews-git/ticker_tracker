import sys
from pathlib import Path

# Add src directory to path so tests can import the package
src_path = Path(__file__).parent / 'src'
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

def run_tests():
    import pytest
    result = pytest.main(['tests', '-v', '--tb=short', '--no-header'])
    sys.exit(result)

if __name__ == '__main__':
    run_tests()
