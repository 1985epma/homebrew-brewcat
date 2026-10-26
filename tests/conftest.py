import os
import sys

# Make the project modules importable and keep the GUI re-exec/launcher paths out of the tests.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BREWCAT_BRANDED"] = "1"
os.environ["BREWCAT_NO_APP"] = "1"
