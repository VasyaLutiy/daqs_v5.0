from google import genai
from google.genai import types
from PIL import Image
import os

prompt = "An office group photo of these people, they are making funny faces."
aspect_ratio = "5:4" # "1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9"
resolution = "2K" # "1K", "2K", "4K"

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("GEMINI_API_KEY not found. Visual generation will be disabled.")
    client = None
else:
    client = genai.Client(api_key=api_key)

prompt = (
    "Create a picture of Dolores night elf sitting on the cask tavern"
)

image = Image.open('npc_engine/config/social_world/nodes/personas/img_ref/img_Dolores_Reference.png'),

response = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents=[prompt, image],
)

for part in response.parts:
    if part.text is not None:
        print(part.text)
    elif part.inline_data is not None:
        image = part.as_image()
        image.save("generated_image.png")