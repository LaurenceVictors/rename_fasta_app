import google.generativeai as genai
import os

# Paste your key here directly just for this test, or set the env var
os.environ["GOOGLE_API_KEY"] = "AIzaSyDs0lpsD-XtILjfD7xEgoKLYWRf1cT-CPY"
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

print("Available Models:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"- {m.name}")