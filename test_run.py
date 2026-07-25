import traceback
import sys
try:
    print("Running prediction_example...")
    with open("examples/prediction_example.py") as f:
        code = f.read()
    exec(code)
    print("Finished successfully")
except Exception as e:
    print("An error occurred:")
    traceback.print_exc()
