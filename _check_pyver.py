import sys
msg = f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
with open(r"H:\project_development\xuangu\_py_version.txt", "w") as f:
    f.write(msg)
