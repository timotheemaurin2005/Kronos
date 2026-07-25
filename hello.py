import os
print("Running run_msft.py via os.system with -u")
exit_code = os.system("venv/bin/python -u run_msft.py")
print("Exit code:", exit_code)
