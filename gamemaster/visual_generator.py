import os
from pathlib import Path
from typing import Optional, Tuple, Union, List
from google import genai
from google.genai import types
from PIL import Image
import io
import base64
import re
from npc_engine.engine.logging_config import get_logger

logger = get_logger("gamemaster.visual")

# Constants
IMAGE_CACHE_DIR = Path("static/images/locations")
DEFAULT_MODEL = "gemini-3-pro-image-preview"

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

    def _validate_image_file(self, file_path: Path) -> bool:
        """Check that the saved file is a valid image. Returns True if OK."""
        try:
            with Image.open(file_path) as img:
                img.verify()  # type: ignore[attr-defined]
            return True
        except Exception as e:
            logger.warning(f"Visual: Saved file is not a valid image ({file_path}): {e}")
            try:
                file_path.unlink(missing_ok=True)
            except Exception:
                pass
            return False

    def _decode_to_bytes(self, blob) -> Optional[bytes]:
        """
        Try to coerce different blob formats (bytes, str, base64) into raw bytes.
        """
        if blob is None:
            return None

        # If already bytes-like, use it but also attempt base64 decode.
        if isinstance(blob, (bytes, bytearray)):
            raw = bytes(blob)
            decoded = self._try_base64_decode(raw)
            return decoded or raw

        if isinstance(blob, str):
            decoded = self._try_base64_decode(blob)
            if decoded:
                return decoded
            return blob.encode("utf-8")

        # Unknown type: try to cast to bytes
        try:
            raw = bytes(blob)
            decoded = self._try_base64_decode(raw)
            return decoded or raw
        except Exception:
            return None

    def _try_base64_decode(self, data: Union[str, bytes]) -> Optional[bytes]:
        """
        Attempt base64 decoding; return bytes if plausible, else None.
        """
        try:
            if isinstance(data, str):
                data_bytes = data.encode("utf-8")
            else:
                data_bytes = data

            # Quick heuristic: allow typical base64 charset
            if not re.fullmatch(rb"[A-Za-z0-9+/=\r\n]+", data_bytes):
                return None

            decoded = base64.b64decode(data_bytes, validate=False)
            return decoded if decoded else None
        except Exception:
            return None

    def _save_image_bytes(self, img_bytes: bytes, target_file: Path) -> bool:
        """Save bytes to file as an image, validate, and return success."""
        try:
            image = Image.open(io.BytesIO(img_bytes))
            image.save(target_file)
            return self._validate_image_file(target_file)
        except Exception as e:
            logger.warning(f"Visual: Failed to save image bytes: {e}")
            return False

    def generate_location_visual(self, location_id: str, name: str, description: str, region: str = "Fantasy World", image_ref_path: Optional[str] = None) -> Optional[str]:
        """
        Generates an image for a location if not already cached.
        Returns the path to the image file.
        """
        target_file = IMAGE_CACHE_DIR / f"{location_id}.png"
        prompt = f"""
        Create a cinematic concept art for an explorable RPG location.

        LOCATION:
        Name: {name}
        Region Style: {region}

        ENVIRONMENT DETAILS:
        {description}

        VISUAL CONTINUITY:
        - Show paths/exits described above so adjacent locations feel connected.
        - Emphasize landmarks that help navigation (bridges, gates, statues, thickets).

        STYLE:
        Photorealistic, hyper-detailed, cinematic lighting, atmospheric, digital painting.
        """
        return self._generate_and_save(target_file, prompt, image_ref_path)

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
            if self._validate_image_file(target_file):
                logger.info(f"Visual: Cache hit for {target_file.name}")
                return str(target_file)
            else:
                logger.warning(f"Visual: Cache file invalid, regenerating: {target_file}")

        if not self.client:
            return None

        # 2. Prepare Contents
        contents: List[Union[str, Image.Image]] = [prompt]
        if image_ref_path:
            try:
                ref_path = Path(image_ref_path)
                # Fallback extension swap if missing
                if not ref_path.exists() and ref_path.suffix.lower() in [".jpg", ".jpeg"]:
                    alt = ref_path.with_suffix(".png")
                    if alt.exists():
                        ref_path = alt
                elif not ref_path.exists() and ref_path.suffix.lower() == ".png":
                    alt = ref_path.with_suffix(".jpg")
                    if alt.exists():
                        ref_path = alt

                if ref_path.exists():
                    logger.info(f"Visual: Using image reference from {ref_path}")
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
        except Exception as e:
            logger.error(f"Visual Generation Error (API call): {e}")
            return None
        
        try:
            logger.warning("Visual: image generation ready.")
            for part in response.parts:
                if part.text is not None:
                    print(part.text)
                elif part.inline_data is not None:
                    image = part.as_image()
                    image.save(target_file)
                    logger.info(f"Visual: Saved to {target_file}")
                    return str(target_file)        
        except Exception as e:
            logger.error(f"Visual Generation Error (parsing): {e}")
            return None


        '''
        # 4. Save
        try:
            parts = getattr(response, "parts", None)
            if not parts:
                logger.warning("Visual: Response missing image parts.")
                return None

            for part in parts:
                # Direct check for image in parts (SDK dependent)
                try:
                    if hasattr(part, "as_image"):
                        img_obj = part.as_image()
                        # Some SDKs may return bytes/base64 instead of an Image
                        if hasattr(img_obj, "save"):
                            img_obj.save(target_file)  # type: ignore[union-attr]
                            if self._validate_image_file(target_file):
                                logger.info(f"Visual: Saved to {target_file}")
                                return str(target_file)
                        else:
                            img_bytes = self._decode_to_bytes(img_obj)
                            if img_bytes and self._save_image_bytes(img_bytes, target_file):
                                logger.info(f"Visual: Saved to {target_file}")
                                return str(target_file)
                except Exception as e:
                    logger.debug(f"Visual: part.as_image() failed: {e}")

                # Fallback for inline_data
                if hasattr(part, "inline_data") and part.inline_data:
                    try:
                        raw_data = part.inline_data.data
                        img_bytes = self._decode_to_bytes(raw_data)

                        if not img_bytes:
                            logger.warning("Visual: inline_data present but empty or undecodable.")
                            continue

                        if self._save_image_bytes(img_bytes, target_file):
                            logger.info(f"Visual: Saved via inline_data to {target_file}")
                            return str(target_file)
                    except Exception as e:
                        logger.error(f"Visual: Failed to process inline_data: {e}")

            logger.warning("Visual: No image found in response.")
            return None
        except Exception as e:
            logger.error(f"Visual Generation Error (parsing): {e}")
            return None
        '''
