# TTS Emotion Prompt Specification

## Required Shape

Write one compact paragraph in this order:

1. **Trigger**: what just happened or what the speaker has realized.
2. **Target and purpose**: whom the speaker addresses and what response or action they want.
3. **Emotion**: one main emotion and at most two supporting emotions, including what is restrained and what leaks through.
4. **Delivery**: speed, meaningful pause points, emphasized words or clauses, and sentence-ending direction.
5. **Negative direction**: name likely wrong readings such as announcer voice, melodrama, comedy, shouting, or sweetness.
6. **Content boundary**: `只说输入台词，不添加语气词、笑声、旁白，不重复或续说。`

Recommended pattern:

`此刻……。说话者对……说，目的是……。以……为主，带一点……，但……。语速……，在……处短停，重读……，句尾……。不要演成……。只说输入台词，不添加语气词、笑声、旁白，不重复或续说。`

## Forbidden Content

Do not mention or request:

- reference audio, reference video, uploaded material, voice cloning, voiceprint copying, imitation, or voice restoration;
- gender, age, pitch, resonance, accent, vocal texture, or a named person's voice;
- frames, shots, images, character appearance, camera, video resolution, aspect ratio, or visual action;
- music, sound effects, ambience, recording cleanliness, file format, or silence padding unless the target TTS API explicitly needs it.

Do not paste the target dialogue into `提示词`; the API sends it separately through `input`.

## Evidence Rules

- Prefer the original prompt's plot trigger and psychological logic after removing all voice-clone and audiovisual boilerplate.
- Preserve uncertainty. A character cannot emotionally react to facts they do not yet know.
- Give action verbs and audible controls instead of adjective piles.
- Keep emotions playable: explain whether they rise, break through, or remain suppressed.
- Use punctuation as written. Do not normalize ellipses, question marks, wording, or names.
