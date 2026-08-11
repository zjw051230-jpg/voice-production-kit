---
name: generate-tts-emotion-prompt-json
description: Generate or rewrite Chinese TTS task JSON whose instructions control only emotion, dramatic intent, pacing, pauses, emphasis, and sentence endings. Use for emotion-only TTS instructions or when saving one batch into the selected voice project's task directory.
---

# Generate TTS Emotion Prompt JSON

Create compact, playable TTS `instructions` while leaving speaker and voice selection to the API request or external voice mapping.

## Workflow

1. Read the source dialogue, nearby plot context, and any earlier prompt for the same line.
2. Preserve `台词`, punctuation, role, and requested duration exactly unless the user explicitly changes them.
3. Reconstruct only facts supported by the source. Do not invent relationships, knowledge, or events.
4. Write a new emotion-only `提示词` using [references/prompt-spec.md](references/prompt-spec.md).
5. Put every item from one user request in one batch with one file-level task ID. Assign item IDs as `<task_id>_1`, `<task_id>_2`, and so on. Never split the same request into separate task IDs by role, line, or source file.
6. Choose the next unused task ID when the user gives only a starting pattern. Never overwrite an existing output unless explicitly instructed.
7. Save and validate with `scripts/save_tts_emotion_prompts.py`.

## Output Schema

Return a JSON array. Each object must contain exactly these keys in this order:

```json
{
  "剧本名字": "末日-新",
  "task_ID": "0723003_1",
  "角色名字": "阿瓜",
  "台词": "我赶到的时候，发现商场内有打斗的痕迹。",
  "时长": "7秒",
  "提示词": "……"
}
```

Use a single `剧本名字` throughout the file. Treat the voice ID, voice clone, reference audio, gender, age, pitch, resonance, and accent as external configuration, not prompt content.

## Save

Create a temporary UTF-8 JSON draft, then run:

```powershell
python scripts/save_tts_emotion_prompts.py --task-id 0723003 --input draft.json
```

Always pass the selected project's `文字素材` compatibility path with `--output-dir`. The script refuses an existing destination unless `--overwrite` is supplied after explicit user authorization.

## Quality Check

- Verify all lines are copied exactly and appear only in `台词`, not embedded in `提示词`.
- Verify the instruction states the immediate trigger, listener and purpose, emotional progression, delivery mechanics, and wrong-performance exclusions.
- Use one main emotion and no more than two supporting emotions.
- Avoid voice identity, audio or video reference, visual direction, soundtrack, and output-format boilerplate.
- Require no added interjections, laughter, narration, repetition, or continuation.
- Keep one user-requested batch under one task ID with continuous item suffixes.
