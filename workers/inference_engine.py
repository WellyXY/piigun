"""
Inference engine: HTTP client that calls the local LTX server (server.py on RunPod).
The server already has the model loaded in VRAM — no need to reload here.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

INFERENCE_SERVER_URL = os.getenv("INFERENCE_SERVER_URL", "http://localhost:8000")

DEFAULT_PROMPTS = {
    "blow_job": "A long-haired woman, facing the camera, holding a man's penis, performing a blow job. She slowly takes the entire penis completely into her mouth, fully submerging it until her lips press against the base of the penis and lightly touch the testicles, with the penis fully accommodated in her throat, and repeatedly moves it in and out with a steady, fluid rhythm multiple times.",
    "cowgirl": "The woman, in a cowgirl position atop the man, facing him, drives her hips downward with fierce, rhythmic intensity, guiding his penis deep into her vagina with each deliberate thrust. The penetration is forceful, each motion probing the depths and textures within, the slight resistance at the entrance amplifying their raw connection. Her hands tightly clutch a nearby surface or her thighs, her body arching with unrestrained fervor. Her head tilts back sharply, lips parting in a ragged, primal moan that echoes her overwhelming desire.",
    "doggy": "The man stands behind the woman, extending his penis toward her vagina. As his penis presses against the entrance, he enters with a forceful yet controlled rhythm, each thrust delving deep into the texture and warmth within. The slight resistance of the vaginal opening intensifies the precision of his movements, his hands gripping her hips firmly for support. The woman, on her hands and knees, arches her back sharply, her mouth opening slightly with each powerful thrust.",
    "handjob": "In the scene, the woman tightly grasps the man's penis with both hands, moving them slowly up and down, the motion of her fingers clearly visible as they glide deliberately to the tip and descend, delivering a perfect handjob. Her expression is vivid, cheeks flushed with a deep blush, mouth wide open as she gasps heavily, letting out bold moans, her gaze intensely fixed on him before half-closing.",
    "lift_clothes": "A female lifts her shirt to reveal her breasts. She cups and jiggles them with both hands. Her facial expression is neutral, and her lips are slightly parted. The pose is front view, and the motion level is moderate. The camera is static with a medium shot. The performance is suggestive and moderately paced.",
    "masturbation": "The woman, reclining or seated, explores her body with slow, deliberate touches, her fingers tracing over her skin before settling on her clitoris with focused, rhythmic strokes. Each movement is intentional, alternating between gentle circles and firmer presses, the slick warmth of her arousal heightening the tactile intensity. Her other hand roams, teasing her breasts or inner thighs, amplifying the building sensation. Her head tilts back sharply, lips parting in a soft, primal moan that betrays her deepening pleasure.",
    "missionary": "The woman, a fair-skinned blonde with piercing blue eyes, lies on her back in a missionary pose, her legs spread wide as she drives her hips upward with fierce, rhythmic intensity. Each motion is forceful, meeting the man's penetrating thrusts, the penis delving deep into her vagina. Her head tilts back, lips parting in a gasping, primal moan that echoes her consuming desire.",
    "reverse_cowgirl": "The woman, positioned above the man and facing forward, drives her hips downward with fierce, rhythmic intensity, guiding his penis deep into her vagina with each deliberate thrust. Her hands clutch a nearby surface or her thighs tightly, her body arching with unrestrained fervor. Her head is tilted slightly back, eyes fixed forward, maintaining a steady gaze ahead.",
}

DEFAULT_AUDIO = {
    "blow_job":        "wet slurping sounds, she moans softly around the shaft, occasional gagging followed by breathless gasps, whispering 'you taste so good' in a husky voice, her breathing deepening with arousal.",
    "cowgirl":         "rhythmic skin-on-skin contact, soft bed springs creaking, she moans loudly between heavy breaths, whispering \"you feel so good\" and \"don't stop\" in a sultry breathless voice, her moans building in intensity with each thrust.",
    "doggy":           "loud rhythmic slapping sounds, she moans deeply with each thrust, gasping \"harder\" and \"right there\" in a breathy desperate voice, the sounds of her gripping the sheets, heavy panting mixed with sharp cries of pleasure.",
    "handjob":         "wet stroking sounds, she whispers \"you like that?\" and \"come for me\" in a teasing seductive voice, soft moaning between strokes, her breathing getting heavier and faster, occasional giggles mixed with sultry encouragement.",
    "lift_clothes":    "soft fabric rustling, she giggles playfully and whispers \"want to see more?\" in a teasing innocent voice, light breathing, a soft moan as she touches herself, whispering \"do you like what you see?\"",
    "masturbation":    "wet rhythmic sounds, soft building moans, she whispers \"oh god\" and \"yes\" breathlessly, her breathing becoming ragged and desperate, crescendo of pleasure sounds, gasping and whimpering with increasing urgency.",
    "missionary":      "bed creaking rhythmically, skin slapping sounds, she moans \"deeper\" and \"don't stop\" with increasing desperation, heavy breathing mixed with sharp gasps, her voice breaking with pleasure, whispering \"I'm so close\".",
    "reverse_cowgirl": "rhythmic bouncing sounds, skin contact, she moans with a deep primal intensity, gasping \"you feel amazing\" and \"so deep\" in a breathy voice, heavy panting and sharp exhales punctuating each downward thrust.",
}


@dataclass
class InferenceEngine:
    gpu_id: int
    model_path: str = ""
    lora_dir: str = ""
    fast_lora_dir: str = ""
    server_url: str = field(default_factory=lambda: INFERENCE_SERVER_URL)

    def startup(self):
        """Verify the local inference server is reachable."""
        for attempt in range(10):
            try:
                resp = httpx.get(f"{self.server_url}/status", timeout=10)
                resp.raise_for_status()
                status = resp.json()
                logger.info(f"[GPU {self.gpu_id}] Inference server ready: {status.get('status')}")
                return
            except Exception as e:
                logger.warning(f"[GPU {self.gpu_id}] Server not ready (attempt {attempt + 1}): {e}")
                time.sleep(5)
        raise RuntimeError(f"Inference server at {self.server_url} not reachable after 10 attempts")

    def generate(
        self,
        *,
        position: str,
        image_path: str,
        prompt: str = "",
        duration: int = 10,
        seed: int = 42,
        include_audio: bool = False,
        audio_description: str = "",
        **kwargs,
    ) -> tuple[str, float]:
        """
        Call the local server to generate a video.
        Returns (output_path, generation_time_seconds).
        """
        # LTX-Video requires frames = 8n+1. Round up to nearest valid count.
        raw = duration * 30
        num_frames = ((raw - 1 + 7) // 8) * 8 + 1  # 5s→153, 10s→305

        # Use full default prompt if user didn't provide one
        effective_prompt = prompt.strip() or DEFAULT_PROMPTS.get(position, position.replace("_", " "))
        # Auto-fill audio description from presets when audio is enabled
        effective_audio = audio_description.strip() if audio_description else (DEFAULT_AUDIO.get(position, "") if include_audio else "")

        t0 = time.time()
        logger.info(f"[GPU {self.gpu_id}] Calling server: position={position}, frames={num_frames}, audio={include_audio}")

        payload: dict = {
            "prompt": effective_prompt,
            "position": position,
            "image_path": image_path,
            "num_frames": num_frames,
            "seed": seed,
            "enhance": True,
        }
        if include_audio and effective_audio:
            payload["audio_description"] = effective_audio

        resp = httpx.post(
            f"{self.server_url}/generate",
            json=payload,
            timeout=600,
        )
        resp.raise_for_status()
        result = resp.json()
        gen_time = time.time() - t0

        # Prefer enhanced video (GFPGAN), fall back to raw
        video_path = result.get("enhanced_video") or result["raw_video"]
        logger.info(f"[GPU {self.gpu_id}] Server returned: {video_path} in {gen_time:.1f}s")

        return video_path, result.get("inference_s", gen_time)
