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

# Constants — absolute so the path is correct regardless of process CWD
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGE_CACHE_DIR = _PROJECT_ROOT / "static" / "images" / "locations"
DEFAULT_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview")

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

    def generate_location_visual(
        self,
        location_id: str,
        name: str,
        description: str,
        region: str = "Fantasy World",
        image_ref_path: Optional[str] = None,
        npcs: Optional[List[dict]] = None,
    ) -> Optional[str]:
        """
        Generates an image for a location if not already cached.
        npcs: list of dicts with keys: name, desc, ref_path (optional).
        All NPCs are included in the prompt simultaneously.
        Returns the path to the image file.
        """
        target_file = IMAGE_CACHE_DIR / f"{location_id}.png"

        ref_paths = []
        if image_ref_path:
            ref_paths.append(image_ref_path)

        if npcs:
            lines = []
            for npc in npcs:
                lines.append(f"- {npc['name']}: {npc.get('desc') or 'A mysterious figure.'}")
                if npc.get("ref_path"):
                    ref_paths.append(npc["ref_path"])
            characters_list = "\n        ".join(lines)
            npc_names = ", ".join(n["name"] for n in npcs)
            character_block = f"""
        CHARACTERS IN SCENE (show ALL simultaneously):
        {characters_list}
        Depict every character listed above in the same image, each as a distinct entity.
        """
            no_people_rule = f"Show only the listed characters: {npc_names}. No other figures."
        else:
            character_block = ""
            no_people_rule = "NO PEOPLE. No human figures, no characters, no NPCs in the scene."

        prompt = f"""
        Create a cinematic concept art for an explorable RPG location.

        LOCATION:
        Name: {name}
        Region Style: {region}

        ENVIRONMENT DETAILS:
        {description}
        {character_block}
        VISUAL CONTINUITY:
        - Show paths/exits described above so adjacent locations feel connected.
        - Emphasize landmarks that help navigation (bridges, gates, statues, thickets).
        - {no_people_rule}

        Style: Photorealistic environment concept art, ultra-detailed, cinematic realism, dramatic lighting with deep shadows and volumetric god rays, 8K resolution, sharp focus, highly intricate details, realistic textures, atmospheric perspective, in the style of hyperrealistic environment art, octane render, unreal engine 5
        """
        return self._generate_and_save(target_file, prompt, ref_paths or None)

    def generate_scene_visual(self, description: str, npc_name: str, npc_desc: str, location_name: str, image_ref_path: Optional[str] = None, location_ref_path: Optional[str] = None) -> Optional[str]:
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
        Single Character Rule: Show only one instance of {npc_name}. Do not duplicate or mirror the character even if reference images include them. No extra people.
        
        LOCATION:
        Name: {location_name}
        
        SCENE ACTION/ATMOSPHERE:
        {description}
        
        Reference Usage: Use character reference for likeness; use location reference only for environment. If any reference already contains the character, still depict a single instance of {npc_name}.

        Style: Photorealistic, hyper-realistic, ultra-detailed, cinematic realism, dramatic lighting with deep shadows and volumetric god rays, 8K resolution, sharp focus, highly intricate details, realistic textures, lifelike skin and materials, focus on expressive character faces and dynamic action poses, in the style of hyperrealistic digital art, octane render, unreal engine 5
        """
        ref_paths = []
        if image_ref_path:
            ref_paths.append(image_ref_path)
        if location_ref_path:
            ref_paths.append(location_ref_path)

        return self._generate_and_save(target_file, prompt, ref_paths or None)

    def _generate_and_save(self, target_file: Path, prompt: str, image_ref_paths: Optional[List[str]] = None) -> Optional[str]:
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
        if image_ref_paths:
            for path_str in image_ref_paths:
                if not path_str:
                    continue
                try:
                    ref_path = Path(path_str)
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
                        logger.warning(f"Visual: Image reference path not found: {path_str}")
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
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                logger.warning(
                    f"Visual: 429 RESOURCE_EXHAUSTED — quota exceeded for model {DEFAULT_MODEL}. "
                    f"Skipping image generation. ({err_str[:200]})"
                )
            else:
                logger.error(f"Visual Generation Error (API call): {e}")
            return None
        
        try:
            logger.info("Visual: parsing API response parts.")
            image_found = False
            for part in response.parts:
                if part.text is not None:
                    logger.debug(f"Visual: model returned text instead of image: {part.text[:120]}")
                elif part.inline_data is not None:
                    image_found = True
                    image = part.as_image()
                    image.save(target_file)
                    logger.info(f"Visual: Saved to {target_file}")
                    return str(target_file)
            if not image_found:
                logger.warning(f"Visual: model returned no image parts for {target_file.name}")
            return None
        except Exception as e:
            logger.error(f"Visual Generation Error (parsing): {e}")
            return None


