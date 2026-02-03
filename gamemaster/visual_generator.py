import os
from pathlib import Path
from typing import Optional, Tuple, Union, List
from google import genai
from google.genai import types
from PIL import Image
import io
from npc_engine.engine.logging_config import get_logger

logger = get_logger("gamemaster.visual")

# Constants
IMAGE_CACHE_DIR = Path("static/images/locations")
DEFAULT_MODEL = "gemini-2.5-flash-image"

class VisualGenerator:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not found. Visual generation will be disabled.")
            self.client = None
        else:
            self.client = genai.Client(api_key=api_key)
        
        # Ensure cache directory exists
        IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def generate_location_visual(self, location_id: str, name: str, description: str, region: str = "Fantasy World") -> Optional[str]:
        """
        Generates an image for a location if not already cached.
        Returns the path to the image file.
        """
        target_file = IMAGE_CACHE_DIR / f"{location_id}.png"
        prompt = f"""
        Create a high-quality, atmospheric fantasy concept art image.
        Subject: {name}
        Region Style: {region}
        Details: {description}
        
        Style: Detailed, cinematic lighting, digital painting, immersive.
        """
        return self._generate_and_save(target_file, prompt)

    def generate_scene_visual(self, description: str, npc_name: str, npc_desc: str, location_name: str, image_ref_path: Optional[str] = None) -> Optional[str]:
        """
        Generates a visual for a specific dialogue scene/moment.
        Can use an optional image_ref_path for character consistency.
        Returns path to saved image.
        """
        import hashlib
        # Hash description to create unique ID for this specific moment
        scene_hash = hashlib.md5(description.encode()).hexdigest()[:12]
        # Sanitize filename
        safe_name = "".join(c for c in npc_name if c.isalnum() or c in (' ', '_')).rstrip()
        filename = f"scene_{safe_name}_{scene_hash}.png".replace(" ", "_").lower()
        target_file = IMAGE_CACHE_DIR / filename
        
        prompt = f"""
        Create a cinematic concept art for a RPG game scene.
        
        CHARACTER:
        Name: {npc_name}
        Appearance: {npc_desc}
        
        LOCATION:
        Name: {location_name}
        
        SCENE ACTION/ATMOSPHERE:
        {description}
        
        Style: Photorealistic, hyper-realistic, ultra-detailed, cinematic realism, dramatic lighting with deep shadows and volumetric god rays, 8K resolution, sharp focus, highly intricate details, realistic textures, lifelike skin and materials, focus on expressive character faces and dynamic action poses, in the style of hyperrealistic digital art, octane render, unreal engine 5
        """
        
        return self._generate_and_save(target_file, prompt, image_ref_path)

    def _generate_and_save(self, target_file: Path, prompt: str, image_ref_path: Optional[str] = None) -> Optional[str]:
        """Internal helper to handle API call and saving."""
        # 1. Check Cache
        if target_file.exists():
            logger.info(f"Visual: Cache hit for {target_file.name}")
            return str(target_file)

        if not self.client:
            return None

        # 2. Prepare Contents
        contents: List[Union[str, Image.Image]] = [prompt]
        if image_ref_path:
            try:
                ref_path = Path(image_ref_path)
                if ref_path.exists():
                    logger.info(f"Visual: Using image reference from {image_ref_path}")
                    contents.append(Image.open(ref_path))
                else:
                    logger.warning(f"Visual: Image reference path not found: {image_ref_path}")
            except Exception as e:
                logger.error(f"Visual: Failed to load image reference: {e}")

        # 3. Generate
        logger.info(f"Visual: Generating image for {target_file.name}...")
        logger.debug(f"Visual: Full text prompt sent to LLM:\n{prompt}")
        
        try:
            response = self.client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=['IMAGE'],
                )
            )
            
            # 4. Save
            for part in response.parts:
                # Direct check for image in parts (SDK dependent)
                try:
                    # Support for part.as_image() if available
                    if hasattr(part, "as_image"):
                        image = part.as_image()
                        image.save(target_file)
                        logger.info(f"Visual: Saved to {target_file}")
                        return str(target_file)
                except Exception as e:
                    logger.debug(f"Visual: part.as_image() failed: {e}")

                # Fallback for inline_data
                if hasattr(part, "inline_data") and part.inline_data:
                     img_data = part.inline_data.data
                     image = Image.open(io.BytesIO(img_data))
                     image.save(target_file)
                     logger.info(f"Visual: Saved via inline_data to {target_file}")
                     return str(target_file)
            
            logger.warning(f"Visual: No image found in response.")
            return None

        except Exception as e:
            logger.error(f"Visual Generation Error: {e}")
            return None