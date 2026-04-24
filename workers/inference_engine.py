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
    "blow_job": "A woman performing fellatio on a man. She takes his penis deeply into her mouth, moving her head rhythmically with steady oral strokes, lips tightly wrapped around the shaft. The penetration into her mouth is clearly visible with each bob of her head. -- blow_job",
    "cowgirl": "The woman, in a cowgirl position atop the man, facing him, drives her hips downward with fierce, rhythmic intensity, guiding his penis deep into her vagina with each deliberate thrust. The penetration is forceful, each motion probing the depths and textures within, the slight resistance at the entrance amplifying their raw connection. Her hands tightly clutch a nearby surface or her thighs, her body arching with unrestrained fervor. Her head tilts back sharply, lips parting in a ragged, primal moan that echoes her overwhelming desire. Her eyes, clenched shut in a storm of pleasure tinged with fleeting pain, flutter open momentarily, revealing a fevered, almost pleading gaze. Her brows knit tightly, a faint wince crossing her face as the intensity peaks, yet her cheeks burn with a deep, crimson flush, betraying her immersion in the consuming ecstasy. Her breath comes in sharp, uneven gasps, her lower lip quivering as she bites it fiercely, a strained yet enraptured smile breaking through with each powerful motion. Her hair whips wildly with her movements, catching the soft light that bathes her glistening skin, heightening the primal allure.",
    "doggy": "The man stands behind the woman, extending his penis toward her vagina. As his penis presses against the entrance, he enters with a forceful yet controlled rhythm, each thrust delving deep into the texture and warmth within. The slight resistance of the vaginal opening intensifies the precision of his movements, his hands gripping her hips firmly for support. The woman, on her hands and knees, arches her back sharply, her mouth opening slightly with each powerful thrust. Her head then turns to face forward, tilted slightly back, revealing the back of her head. The room's dim light casts stark shadows on her glistening skin, amplifying the raw intensity of the moment.",
    "handjob": "In the scene, the woman tightly grasps the man's penis with both hands, moving them slowly up and down, the motion of her fingers clearly visible as they glide deliberately to the tip and descend, delivering a perfect handjob. Her expression is vivid, cheeks flushed with a deep blush, mouth wide open as she gasps heavily, letting out bold moans, her gaze intensely fixed on him before half-closing. Her eyebrows arch with a wicked charm, a sly smirk curling her lips, her breathing rapid, tongue grazing her lips, biting them with a hungry edge.",
    "tit_job": "In the scene, the woman tightly grasps the man's penis with both hands, moving them slowly up and down, the motion of her fingers clearly visible as they glide deliberately to the tip and descend, delivering a perfect handjob. Her expression is vivid, cheeks flushed with a deep blush, mouth wide open as she gasps heavily, letting out bold moans, her gaze intensely fixed on him before half-closing. Her eyebrows arch with a wicked charm, a sly smirk curling her lips, her breathing rapid, tongue grazing her lips, biting them with a hungry edge.",
    "lift_clothes": "A female grips the hem of her shirt with both hands and pulls the fabric upward in a smooth motion, lifting the top up her torso until her breasts are fully exposed underneath with clearly visible erect pink nipples. She then cups and gently jiggles her breasts with both hands, nipples remaining visibly exposed throughout. Front view medium shot, static camera, moderately paced. --lift_clothes",
    "masturbation": "The woman, reclining or seated, explores her body with slow, deliberate touches, her fingers tracing over her skin before settling on her clitoris with focused, rhythmic strokes. Each movement is intentional, alternating between gentle circles and firmer presses, the slick warmth of her arousal heightening the tactile intensity. Her other hand roams, teasing her breasts or inner thighs, amplifying the building sensation. Her head tilts back sharply, lips parting in a soft, primal moan that betrays her deepening pleasure. Her eyes, clenched shut in a wave of ecstasy tinged with fleeting intensity, flicker open briefly, revealing a wild, introspective glint. Her brows furrow subtly, a faint wince crossing her face as the sensation peaks, yet her cheeks flush with a deep, feverish blush, surrendering to the consuming desire. Her breath comes in ragged, uneven gasps, her lower lip trembling as she bites it gently, a strained yet rapturous smile breaking through with each pulsing touch. The soft light bathes her glistening skin, casting stark shadows that heighten the raw, intimate solitude of the moment.",
    "missionary": "The woman, a fair-skinned blonde with piercing blue eyes, lies on her back in a missionary pose, her legs spread wide as she drives her hips upward with fierce, rhythmic intensity. Each motion is forceful, meeting the man's penetrating thrusts, the penis delving deep into her vagina, exploring its texture and warmth with relentless precision. The slight resistance of the entrance heightens their connection, her body arching with unrestrained fervor. Her head tilts back, lips parting in a gasping, primal moan that echoes her consuming desire. Her eyes, squeezed shut in a mix of overwhelming pleasure and fleeting pain, flicker open briefly, revealing a fevered, almost pleading gaze. Her brows knit tightly, a faint wince crossing her face with each powerful thrust, yet her cheeks flush with a deep, crimson blush, betraying her immersion in ecstasy. Her breath comes in ragged bursts, her lower lip quivering as she bites it hard, a strained yet rapturous smile breaking through, her body trembling in sync with the relentless rhythm. The camera, positioned between her legs, captures the glistening sheen of her skin under soft light, amplifying the raw intensity.",
    "reverse_cowgirl": "The woman, positioned above the man and facing forward, drives her hips downward with fierce, rhythmic intensity, guiding his penis deep into her vagina with each deliberate thrust. The penetration is forceful, each motion probing the depths and textures within, the slight resistance of the entrance amplifying their raw connection. Her hands clutch a nearby surface or her thighs tightly, her body arching with unrestrained fervor. Her head is tilted slightly back, eyes fixed forward, maintaining a steady gaze ahead. Her hair whips wildly with her movements, catching the soft light that bathes her glistening skin, heightening the primal allure of the scene.",
    "dildo": "A woman masturbating with a dildo. She inserts the sex toy into her vagina and thrusts it rhythmically, moaning with pleasure as the dildo penetrates her deeply with each stroke. The insertion and withdrawal motion is clearly visible, her hips rocking to meet each thrust. Her free hand caresses her body, her expression flushed with arousal, lips parted in breathless moans as the pleasure builds. -- dildo",
    "boobs_play": "A woman playing with her own breasts and nipples. She squeezes, fondles, and massages her breasts sensually with both hands, lifting and pressing them together. Her fingers pinch and rub her erect nipples with visible pleasure, her head tilting back with a soft moan. Her expression is flushed and aroused, lips parted as she loses herself in the sensation, the soft light highlighting the curves of her chest. -- boobs_play",
    "cumshot": "A close-up POV view of male ejaculation. An erect penis is positioned near the woman's face. White semen spurts from the urethral opening at the tip of the penis in rhythmic pulses. Streams of cum travel through the air and land on the woman's lips, chin, and cheeks. Realistic liquid viscosity. ltxmove_cumshot",
}

DEFAULT_AUDIO = {
    "blow_job":        "wet slurping sounds, she moans softly around the shaft, occasional gagging followed by breathless gasps, whispering 'you taste so good' in a husky voice, her breathing deepening with arousal.",
    "cowgirl":         "rhythmic skin-on-skin contact, soft bed springs creaking, she moans loudly between heavy breaths, whispering \"you feel so good\" and \"don't stop\" in a sultry breathless voice, her moans building in intensity with each thrust, punctuated by sharp gasps.",
    "doggy":           "loud rhythmic slapping sounds, she moans deeply with each thrust, gasping \"harder\" and \"right there\" in a breathy desperate voice, the sounds of her gripping the sheets, heavy panting mixed with sharp cries of pleasure.",
    "handjob":         "wet stroking sounds, she whispers \"you like that?\" and \"come for me\" in a teasing seductive voice, soft moaning between strokes, her breathing getting heavier and faster, occasional giggles mixed with sultry encouragement.",
    "tit_job":         "wet stroking sounds, she whispers \"you like that?\" and \"come for me\" in a teasing seductive voice, soft moaning between strokes, her breathing getting heavier and faster, occasional giggles mixed with sultry encouragement.",
    "lift_clothes":    "soft fabric rustling, she giggles playfully and whispers \"want to see more?\" in a teasing innocent voice, light breathing, a soft moan as she touches herself, whispering \"do you like what you see?\"",
    "masturbation":    "wet rhythmic sounds, soft building moans, she whispers \"oh god\" and \"yes\" breathlessly, her breathing becoming ragged and desperate, crescendo of pleasure sounds, gasping and whimpering with increasing urgency.",
    "missionary":      "bed creaking rhythmically, skin slapping sounds, she moans \"deeper\" and \"don't stop\" with increasing desperation, heavy breathing mixed with sharp gasps, her voice breaking with pleasure, whispering \"I'm so close\".",
    "reverse_cowgirl": "rhythmic bouncing sounds, skin contact, she moans with a deep primal intensity, gasping \"you feel amazing\" and \"so deep\" in a breathy voice, heavy panting and sharp exhales punctuating each downward thrust.",
    "dildo":      "wet rhythmic sounds of the toy thrusting, she moans breathlessly with each stroke, whispering \"feels so good\" and \"deeper\" in a desperate voice, her breathing becoming ragged and urgent, building gasps of pleasure.",
    "boobs_play": "soft moaning as she touches herself, she whispers \"my nipples are so sensitive\" in a breathy voice, gentle squeezing sounds, her breathing quickening with arousal, soft sighs of pleasure as she caresses her chest.",
    "cumshot":    "rhythmic pulsing sounds building to climax, she moans eagerly, begging \"give me more\" and \"cum all over my face\" in a hungry desperate voice, gasping \"yes, yes, yes\" as wet splashing sounds hit her skin, whimpering \"it's so warm\" and \"please don't stop\", breath catching with each pulse, soft cries of \"fuck me\" and \"I want it all\" mixed with satisfied moans.",
}

# Audio-ON prompts: audio/speech interwoven with visuals (model expects inline soundscape, NOT appended)
DEFAULT_PROMPTS_AUDIO = {
    "blow_job": 'A woman performing fellatio on a man. Wet slurping sounds fill the room as she takes his penis deeply into her mouth, moving her head rhythmically with steady oral strokes, lips tightly wrapped around the shaft. She moans softly around the shaft, whispering "you taste so good" in a husky voice between strokes. The penetration into her mouth is clearly visible with each bob of her head, occasional gagging followed by breathless gasps, her breathing deepening with arousal. -- blow_job',
    "cowgirl": 'The woman, in a cowgirl position atop the man, facing him, drives her hips downward with fierce, rhythmic intensity. Rhythmic skin-on-skin contact and soft bed springs creaking accompany each motion. She guides his penis deep into her vagina with each deliberate thrust, moaning loudly between heavy breaths, whispering "you feel so good" in a sultry breathless voice. The penetration is forceful, each motion probing the depths within. Her hands tightly clutch a nearby surface, her body arching with unrestrained fervor. She gasps "don\'t stop" as the intensity peaks, her moans building with each thrust, punctuated by sharp gasps. Her head tilts back sharply, lips parting in a ragged, primal moan. Her cheeks burn with a deep crimson flush, her breath coming in sharp, uneven gasps, her lower lip quivering as she bites it fiercely.',
    "doggy": 'The man stands behind the woman, extending his penis toward her vagina. Loud rhythmic slapping sounds echo as his penis presses against the entrance. He enters with a forceful yet controlled rhythm, each thrust delving deep within. She moans deeply with each thrust, gasping "harder" in a breathy desperate voice. The slight resistance of the vaginal opening intensifies the precision of his movements, his hands gripping her hips firmly. She grips the sheets tightly, crying out "right there" between heavy panting and sharp cries of pleasure. The woman, on her hands and knees, arches her back sharply, her mouth opening with each powerful thrust. The room\'s dim light casts stark shadows on her glistening skin.',
    "handjob": 'In the scene, the woman tightly grasps the man\'s penis with both hands, moving them slowly up and down with wet stroking sounds. The motion of her fingers is clearly visible as they glide deliberately to the tip and descend. She whispers "you like that?" in a teasing seductive voice, soft moaning escaping between strokes. Her expression is vivid, cheeks flushed with a deep blush, mouth wide open as she gasps heavily. Her breathing gets heavier and faster as she whispers "come for me" with a sly smirk curling her lips. Occasional giggles mix with sultry encouragement, her tongue grazing her lips, biting them with a hungry edge.',
    "tit_job": 'In the scene, the woman tightly grasps the man\'s penis with both hands, moving them slowly up and down with wet stroking sounds. The motion of her fingers is clearly visible as they glide deliberately to the tip and descend. She whispers "you like that?" in a teasing seductive voice, soft moaning escaping between strokes. Her expression is vivid, cheeks flushed with a deep blush, mouth wide open as she gasps heavily. Her breathing gets heavier and faster as she whispers "come for me" with a sly smirk curling her lips. Occasional giggles mix with sultry encouragement, her tongue grazing her lips, biting them with a hungry edge.',
    "lift_clothes": 'A female lifts her shirt up slowly, soft fabric rustling as the material rises. She giggles playfully, whispering "want to see more?" in a teasing innocent voice as her round, natural breasts are revealed with soft smooth skin and clearly visible erect nipples. She cups both breasts with her hands, a soft moan escaping as she touches herself, lifting and squeezing them gently. She whispers "do you like what you see?" with light breathing, then jiggles them with a slow bouncing motion, the natural weight swaying with each movement. The camera is static, medium shot, front view. Her expression is subtly aroused, lips slightly parted.',
    "masturbation": 'The woman, reclining or seated, explores her body with slow deliberate touches, wet rhythmic sounds accompanying her fingers as they trace over her skin. She settles on her clitoris with focused rhythmic strokes, soft building moans escaping her lips. She whispers "oh god" breathlessly as each movement alternates between gentle circles and firmer presses. Her other hand roams, teasing her breasts. Her head tilts back, whispering "yes" as the sensation peaks, her breathing becoming ragged and desperate. Her eyes clench shut in a wave of ecstasy, gasping and whimpering with increasing urgency. Her cheeks flush with a deep feverish blush, her lower lip trembling as she bites it gently, a strained yet rapturous smile breaking through with each pulsing touch.',
    "missionary": 'The woman lies on her back in a missionary pose, her legs spread wide. Bed creaking rhythmically and skin slapping sounds fill the room as she drives her hips upward with fierce intensity. Each motion meets the man\'s penetrating thrusts, she moans "deeper" with increasing desperation, heavy breathing mixed with sharp gasps. The penis delves deep into her vagina with relentless precision. Her head tilts back, her voice breaking with pleasure as she whispers "don\'t stop" in a fevered, almost pleading tone. Her brows knit tightly with each powerful thrust, yet her cheeks flush with a deep crimson blush. She gasps "I\'m so close" as her breath comes in ragged bursts, her body trembling in sync with the relentless rhythm. The glistening sheen of her skin under soft light amplifies the raw intensity.',
    "reverse_cowgirl": 'The woman, positioned above the man and facing forward, drives her hips downward with fierce rhythmic intensity. Rhythmic bouncing sounds and skin contact echo as she guides his penis deep into her vagina with each deliberate thrust. She moans with a deep primal intensity, gasping "you feel amazing" in a breathy voice. The penetration is forceful, each motion probing the depths within. Heavy panting and sharp exhales punctuate each downward thrust as she gasps "so deep" with unrestrained fervor. Her hair whips wildly with her movements, catching the soft light that bathes her glistening skin, heightening the primal allure of the scene.',
    "dildo": 'A woman masturbating with a dildo. Wet rhythmic sounds of the toy thrusting fill the room as she inserts the sex toy into her vagina. She thrusts it rhythmically, moaning breathlessly with each stroke, whispering "feels so good" in a desperate voice. The insertion and withdrawal motion is clearly visible, her hips rocking to meet each thrust. She gasps "deeper" as her breathing becomes ragged and urgent, building gasps of pleasure. Her free hand caresses her body, her expression flushed with arousal, lips parted in breathless moans as the pleasure builds. -- dildo',
    "boobs_play": 'A woman playing with her own breasts and nipples. She squeezes, fondles, and massages her breasts sensually with both hands, soft moaning escaping as she touches herself. She whispers "my nipples are so sensitive" in a breathy voice as her fingers pinch and rub her erect nipples with visible pleasure. Gentle squeezing sounds accompany her movements, her breathing quickening with arousal. Her head tilts back with soft sighs of pleasure as she caresses her chest, lifting and pressing her breasts together. Her expression is flushed and aroused, lips parted as she loses herself in the sensation. -- boobs_play',
    "cumshot": 'A close-up POV view of male ejaculation. An erect penis is positioned near the woman\'s face, rhythmic pulsing sounds building with urgent anticipation. She moans eagerly, begging "give me more" and "cum all over my face" in a hungry desperate voice, her tongue out waiting. White semen spurts from the urethral opening at the tip of the penis in rhythmic pulses. Streams of cum travel through the air with wet splashing sounds, landing on the woman\'s lips, chin, and cheeks as she gasps "yes, yes, yes". She whimpers "it\'s so warm" and "please don\'t stop", breath catching with each pulse. Soft cries of "fuck me" and "I want it all" mix with satisfied moans, her lips parting hungrily to catch every drop. Realistic liquid viscosity. ltxmove_cumshot',
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
        nsfw_weight: float | None = None,
        motion_weight: float | None = None,
        position_weight: float | None = None,
        **kwargs,
    ) -> tuple[str, float]:
        """
        Call the local server to generate a video.
        Returns (output_path, generation_time_seconds).
        """
        # LTX-Video requires frames = 8n+1. Round up to nearest valid count.
        # Pod runs at 25fps (frame_rate default in server.py/config.py)
        raw = duration * 25
        num_frames = ((raw - 1 + 7) // 8) * 8 + 1  # 5s→121, 10s→249

        # Use custom prompt if provided, otherwise fall back to default
        custom = prompt.strip() if prompt and prompt.strip() else ""
        if include_audio and not custom:
            # Audio ON + no custom prompt → use interleaved prompt (audio woven into visuals)
            effective_prompt = DEFAULT_PROMPTS_AUDIO.get(position, DEFAULT_PROMPTS.get(position, position.replace("_", " ")))
            effective_audio = DEFAULT_AUDIO.get(position, "")
        elif include_audio and custom:
            # Audio ON + custom prompt → interleave user's audio into the custom prompt
            user_audio = audio_description.strip()
            effective_audio = user_audio if user_audio else DEFAULT_AUDIO.get(position, "")
            # Weave audio inline instead of appending "Audio:" at end
            effective_prompt = (
                f'{custom} She moans with deep intensity, '
                f'{effective_audio}'
            )
        else:
            # Audio OFF → visual-only prompt
            effective_prompt = custom if custom else DEFAULT_PROMPTS.get(position, position.replace("_", " "))
            effective_audio = ""

        logger.info(f"[GPU {self.gpu_id}] prompt ({('audio' if include_audio else 'visual')}): {effective_prompt[:120]}...")

        t0 = time.time()
        logger.info(f"[GPU {self.gpu_id}] Calling server: position={position}, frames={num_frames}, audio={include_audio}, nsfw_w={nsfw_weight}, motion_w={motion_weight}, pos_w={position_weight}")

        payload: dict = {
            "prompt": effective_prompt,
            "position": position,
            "image_path": image_path,
            "num_frames": num_frames,
            "seed": seed,
            "enhance": True,
            # enhance_prompt disabled — Gemma rewrite exceeds 1024 token limit
            # "enhance_prompt": include_audio,
        }
        # Audio is now inline in the prompt — Gemma enhance_prompt handles speech generation
        if nsfw_weight is not None:
            payload["nsfw_weight"] = nsfw_weight
        if motion_weight is not None:
            payload["motion_weight"] = motion_weight
        if position_weight is not None:
            payload["position_weight"] = position_weight

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

        return video_path, result.get("inference_s", gen_time), effective_prompt, effective_audio
