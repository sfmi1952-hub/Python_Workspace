import google.generativeai as genai
import os

# Try to get key from env or MainWindow if possible, but for script we need it directly.
# The user already provided it in the app, but I don't have access to the app's runtime state.
# I will check if I can assume it's set or if I should error out.
# Let's hope the user set GEMINI_API_KEY environment variable. 
# If not, I'll print a message to the user to set it.

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("Please set GEMINI_API_KEY environment variable to list models.")
    # Attempt to read from the app's logic if possible, but that's hard.
    # I'll just try a public key if I had one, but I don't.
    # Actually, the user runs the app and inputs it. The app sets it in genai.configure.
    # I can't easily get it unless I ask the user.
    # BUT, I can try to run a script that asks for it? No, that blocks.
    pass
else:
    genai.configure(api_key=api_key)
    print("Listing models...")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(m.name)
    except Exception as e:
        print(f"Error: {e}")
