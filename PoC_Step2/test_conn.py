import socket
import sys

target = "generativelanguage.googleapis.com"
port = 443

print(f"Testing DNS resolution for {target}...")
try:
    ip = socket.gethostbyname(target)
    print(f"Resolved to: {ip}")
except Exception as e:
    print(f"DNS Resolution Failed: {e}")

print(f"Testing TCP connection to {target}:{port}...")
try:
    s = socket.create_connection((target, port), timeout=5)
    print("Connection successful!")
    s.close()
except Exception as e:
    print(f"Connection Failed: {e}")
