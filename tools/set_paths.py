import os
import sys
from pathlib import Path

script_path = Path(os.path.dirname(__file__))
os.environ['RPW_SCRIPT_BASE'] = str(script_path.parent)
os.environ['RPW_LOG_PATH'] = str(script_path.parent / 'logs/')
os.environ['RPW_LOG_LEVEL'] = 'DEBUG'
sys.path.append(os.path.abspath(os.path.join(script_path, '..')))
