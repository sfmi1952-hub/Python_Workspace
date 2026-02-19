import psutil

print("Listing python processes:")
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    if 'python' in p.info['name']:
        print(p.info)
