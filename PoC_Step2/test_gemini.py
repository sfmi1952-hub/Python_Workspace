import google.generativeai as genai
import os

print("Testing Gemini Library Connectivity...")
try:
    # Use a dummy key to trigger a connection attempt.
    # Response should be 400 Invalid Key, not Connection Error.
    genai.configure(api_key="AIzaSy_TEST_KEY_12345")
    
    print("Listing models with test key...")
    # This call makes a network request
    for m in genai.list_models():
        print(m.name)
        
except Exception as e:
    print(f"Gemini Error detected: {e}")
    # Print type of error
    print(f"Error Type: {type(e)}")
