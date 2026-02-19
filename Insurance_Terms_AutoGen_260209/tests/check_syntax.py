import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'src'))

try:
    print("Checking src/tag_processor.py...")
    import src.tag_processor
    print("✅ src/tag_processor.py imported successfully.")

    print("Checking src/print_dambo.py...")
    import src.print_dambo
    print("✅ src/print_dambo.py imported successfully.")
    
except ImportError as e:
    print(f"❌ Import Error: {e}")
except SyntaxError as e:
    print(f"❌ Syntax Error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
