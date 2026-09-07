# Protoke

*proto* + *karaoke*.

Turn an audio track, cover image, and word timings into a karaoke video with
burned-in lyrics and an animated protogen-style visor face that mouths the
words. Choose landscape (1920x1080) for desktop/YouTube or portrait
(1080x1920) for Shorts and Reels.

The face is the reason this exists, but it is optional in both directions:
turn it off for a plain karaoke render, or drop the lyrics and background and
put the face alone on black over a narration track.

Runs on macOS, Windows and Linux.

**[Project page →](https://snepssen.github.io/protoke/)** — a 28-second clip of
what it renders, the face animating from the renderer's own exported geometry,
and screenshots of the interface.

## Requirements

- Python 3.10 or newer
- ffmpeg built with the `subtitles`/libass filter
  (`brew install ffmpeg`, `winget install Gyan.FFmpeg`, `apt install ffmpeg`)
- A transcription engine, or an existing timed JSON file beside each track

The rendering, alignment, face and ASS-generation modules use only Python's
standard library. Every dependency is confined to an optional transcription
engine.

## Setup

```sh
./setup.sh
```

`setup.bat` on Windows. This creates `.venv` and installs the portable
Parakeet engine, then prints which engines the tool can see. It is optional —
skip it if you already have timed JSON files.

Add `--with-separation` to also install vocal separation, which lets the face
follow singing that has no words in the lyric sheet. It is a separate step
because it pulls PyTorch, around a gigabyte.

## Start

Double-click `Start Protoke.command` (macOS), run `start.bat`
(Windows), or:

```sh
./start.sh
```

The app opens in a desktop window when `pywebview` is installed, and in your
browser otherwise — `--browser` forces the browser. Either way it is a
token-protected page on `127.0.0.1`; the token changes every run, so use the
page the app opens rather than typing the bare address.

**Why a webview and not Electron.** The interface is already a local web page
and the backend is already Python, so a desktop shell only has to supply a
window. pywebview uses the operating system's own webview: a couple of
megabytes, one toolchain, one codebase. Electron would ship Node and Chromium
*alongside* Python — two runtimes for one app, and a couple of hundred
megabytes per platform. A native Swift shell would be macOS only, which is the
opposite of the point.

The interface itself stays about the video. The face has its own configurator
(**Configure…** in the Face panel, with Look, Motion and Shape tabs), and
transcription and vocal separation live under **Settings**, because neither is
something you change per render.

File chooser dialogs use the platform's native picker, falling back to Tk. On a
desktop with neither — a headless Linux box, or one without `python3-tk` — the
app asks for a typed path instead and resolves it the same way.

Select a single file or a folder. Matching artwork and lyrics are selected
automatically, so their rows turn green when the track is ready; those controls
remain available only when you want an override. Choose an output folder if
needed, set the format and lyric treatment, then create the video. A batch
searches the chosen folder recursively and processes supported audio files
sequentially.

For each audio track, the app automatically finds sibling artwork and lyrics
with the same logical filename. Punctuation and case do not need to match, so
`A04 Red Aura.wav` pairs with `A04 - Red Aura.png` and `A04 - Red Aura.md`.

Suno-style Markdown is cleaned for display without modifying the source file:
the title, bracketed arrangement directions, Suno style tags, negative tags,
Markdown decoration, and display-hostile punctuation are omitted. Lyrics render
in stable reading pages so fast phrases remain visible while the current word is
highlighted. The UI controls whether each page contains one to five lines,
places it in the lower third or centre, and previews the selected font,
character capacity, spacing, and colours. Portrait renders use a conservative
mobile-safe lyric position and add `-short` to the filename so they can sit
beside the landscape render.

## Transcription engines

The tool has no built-in transcriber. `transcribe.probe()` reports which
engines are installed and the app offers only those, so nothing is assumed
about the machine it runs on. Automatic picks the best available.

| Engine | `--engine` | Platforms | Install |
| --- | --- | --- | --- |
| Parakeet (MLX) | `mlx-parakeet` | Apple silicon | `pip install parakeet-mlx` |
| Parakeet (ONNX) | `onnx-parakeet` | Windows, Linux, macOS · x86 and Arm | `pip install 'onnx-asr[cpu,hub]'` |
| MacWhisper | `macwhisper` | macOS, needs MacWhisper Pro | MacWhisper → Settings → Advanced → Command-Line Tool |
| Whisper | `faster-whisper` | Windows, Linux, macOS | `pip install faster-whisper` |

**Parakeet (ONNX) is the portable default.** It runs NVIDIA's
`parakeet-tdt-0.6b-v2` through ONNX Runtime and uses CUDA, CoreML, DirectML or
ROCm when one is present, falling back to CPU. Weights (about 600 MB) download
from Hugging Face on first use and are cached afterwards.

Long tracks are decoded to mono and split at their quietest points before
transcription, so peak memory stays flat regardless of track length and
progress can be reported. Cuts never land in the middle of a sung word.

List what this machine can run:

```sh
python3 app.py --engines
```

MacWhisper remains supported but is no longer required: existing `mw` setups
keep working, and an already-transcribed session is still read from
MacWhisper's database when one matches the track.

Timed JSON is searched beside the audio as `<song>.words.json` and then
`<song>.json`. Accepted formats are documented in `lyrics_engine.py`.

## The face

An optional protogen-style visor face is drawn over the artwork and under the
lyrics. It blinks on its own, mouths the words as they are sung, and reacts to
the shape of the performance.

A protogen's face is a dark visor carrying two lit elements: **the eyes and the
mouth. Nothing else** — no nose, no iris, no detail inside the eye. The
hardware the fursuit builders use makes that literal: the open-source
[flexOS](https://github.com/OpenSourceProtogenCollection/flexOS) firmware
drives `visorEyes` and `visorMouth` as two separate LED panels, and there is no
third one. Its proportions informed these: the eyes sit well outboard, and the
mouth is about as wide as the eyes are far apart.

The face is vector geometry emitted as a second ASS subtitle track, so it needs
no image sequence and no extra dependency — the same libass that draws the
lyrics draws the face.

### One face, on dials

Every eye and every mouth is the same shape with its dials in a different
position — not a menu of outlines to pick from. That is the whole point: a face
assembled by swapping between fixed shapes can never be half way between two of
them, and never being between anything is what makes such a face read as pieces
stuck to a background rather than as a face.

[ProtoTracer](https://github.com/coelacant1/ProtoTracer), which drives some of
the larger visor builds, reaches the same conclusion from the other end: it
holds a mesh plus morph targets — anger, doubt, surprise, the visemes, blink —
each with an independent weight, and the face at any instant is the base plus
every weighted target. Nothing there picks an expression either.

The eye dials are `openness`, `bow`, `slant`, `hook`, `roundness` and `weight`;
the mouth's are `width`, `aperture`, `curve`, `skew`, `jag` and `weight`; and
the face carries a `sharpness` of its own.
**`hook`** is the one that matters most — the outer end of the eye curling down
into a point is what makes a visor eye read as a visor eye rather than an
eyebrow. **`roundness`** carries the same outline all the way to a filled oval,
so a sharp wedge and `o_o` are one object at two settings.

**`sharpness`** straightens every curve towards its control polygon: at 1.0 the
arcs become straight runs meeting at hard corners, and an open mouth becomes a
diamond rather than an ellipse. It belongs to the face rather than to either
feature because it is a quality of the whole expression.

That is what `sharp` is built from. Anger is directness, and directness draws
as straight edges and hard angles — not as tighter curves. It also **holds
still**: an expression carries a motion multiplier as well as a shape, and
`sharp` moves at 0.22 of normal, because a scowl that bobs along to the music
stops being a scowl. Measured on a render, 31.8 px of head travel becomes
7.0 px and 3.32° of tilt becomes 0.73°.

| `--face-expression` | Reads as | |
| --- | --- | --- |
| `visor` (default) | `◤‿◥` | hooked eyes, smirk |
| `grin` | `◤w◥` | hooked eyes, zigzag grin |
| `hooked` | `︿﹀` | thin hooked crescents |
| `sharp` | `▶~◀` | downward slant |
| `smug` | `¬‿¬` | half-lidded |
| `content` | `^_^` | |
| `happy` | `^w^` | |
| `wide` | `o_o` | |
| `sleepy` | `-_-` | |
| `delighted` | `^o^` | |
| `curious` | `owo` | |

### Blinking

`--blink-every` sets the average seconds between blinks, and the range that
matters is wide: **rested eyes go about ten seconds; an awake, talking person
is nearer four or five.** The default is 5, because a face on screen that
rarely blinks reads as switched off.

Intervals are drawn skewed rather than evenly — real blinking clusters, with
occasional long gaps, and evenly spaced blinks are conspicuously metronomic —
and about one in five arrives as a pair, which is the other thing whose
absence reads as mechanical. A double counts as one blink when the rate is
measured, because that is how the eye reads it.

The first blink is placed early and within a bounded window rather than left
to the skewed draw, so a short clip does not open on ten seconds of unblinking
stare.

Eyes do not react to the music.

### The face editor

The built-in expressions are a starting point, not a fixed menu. **Edit this
face** in the Face panel opens a slider for every dial, with a looping preview
beside them: the head moving, a blink, and the mouth travelling through a few
articulations. Name it and save, and it joins the expression list and renders
exactly as previewed.

The preview is drawn by the **renderer's own geometry**, sent frame by frame
from the server rather than redrawn in the browser. A second implementation in
JavaScript would drift from the first the moment either was touched, and an
editor that lies about the result is worse than no editor.

Saved faces live in the user configuration directory — `face-presets.json`,
alongside the app's other settings rather than in the cache, because a cache is
something you delete to reclaim disk and these are not. Every dial has a
declared range, and what arrives from the browser is clamped to it: a preset
that cannot be drawn is worse than one quietly brought back into bounds.

### Solid or matrix

`--face-style matrix` samples the same outlines onto a lit-cell grid, the way
an LED visor shows them, with `--face-columns` setting how coarse it is. One
face definition, two ways of showing it — the dots are not separate artwork.

Filling is done by scanline rather than by testing every cell: a face is a few
hundred edges and a grid is a few hundred cells, and at twenty-four poses a
second the difference is what makes a render take an hour. Matrix style writes
a heavier subtitle track — roughly 9 MB against 4 MB for a four-minute song at
32 columns — because a grid of dots is more geometry than the curves it
samples.

### The muzzle

The face is laid out as though it sits on a helmet with a snout, because that
is what it is drawn on. The mouth is **narrower than the eyes are far apart**
and sits below them, where a muzzle would put it — not centred on a flat
panel.

It is also further **forward**, and that is what stops the face reading as a
sticker being slid around the frame: when the head moves, the mouth swings
about 1.7 times as far as the eyes do. Measured on a render at exaggerated
amplitude, the eyes travel 157px while the mouth travels 300px.

### Head movement

The face is treated as though mounted on a head you cannot see: it bobs, sways
and tilts, and moves more freely between sung phrases than during them.

The bob follows the beat — but only when there **is** a beat. Narration, free
time and ambient beds have none, every candidate tempo scores about the same,
and a head nodding to a tempo nobody can hear looks worse than a still one. So
the tempo estimate also returns a confidence, and below a threshold the bob
fades out and the face breathes on a slow cycle instead. Measured: a song
scores 2.88, spoken narration 0.27.

Where there is a beat, the bob needs its **phase** as well as its rate, or the
head nods precisely between the beats. Both come from the track's onsets;
`--bpm` overrides the rate.

Displacements are fractions of the face's own width, so movement scales with
the face. `--face-motion 0` holds it still; `2` doubles it.

### Mouth

Mouth shapes come from spelling: each word is split into the articulations you
can actually see — vowel groups plus consonants like `m`, `f` and `w` — and the
word's duration is shared between them. One parametric mouth is reshaped by
each articulation, so every shape lies on a continuum with every other and the
mouth is interpolated between them rather than cut.

What happens between words depends on the gap:

- **inside a phrase** (under 0.4 s) the mouth travels straight on to the next
  shape without closing, because a mouth that returns home between every word
  looks like it is chewing;
- **between phrases** it closes to a ready position and starts forming the
  next shape before the sound arrives, the way a real mouth anticipates;
- **after three seconds** with nothing to sing it settles back to the resting
  expression and the idle bob takes over. That handover is a morph between
  outlines, not a cut.

The mouth is **solid, never an outline**. Drawn as a ring it has to put a hole
inside itself, and that ring thins towards nothing as the mouth closes — it
reads as fragile and disappears at small sizes. Filled, it grows from a stroke
of fixed thickness into a filled lens, so there is no width at which it stops
reading. It is also what the LED panels actually display.

### Wordless singing

A yodel, a held "ahh" or a scat run has no words in the lyric sheet, so a mouth
driven only by the sheet sits shut through all of it.

The signal is not raw volume. A voice fluctuates at roughly syllable rate, two
to ten times a second, whether or not it is forming words, while instruments
sustain or land on the beat. Measuring how strongly the level modulates in that
band separates singing from backing. Where the sheet is silent but that signal
is strong, the mouth opens with the level and narrows as the voice jumps
register.

**An isolated vocal makes this exact**, and there are two ways to get one.

If a stem already sits beside the track — `<song>_(Vocals).wav`, as UVR5 and
friends name it — it is used as-is.

Otherwise the tool can separate the voice itself, if a separator is installed:

```sh
pip install "audio-separator[cpu]" audioread
python3 app.py --separators
```

That one package runs the UVR models, and the quality setting picks between
them:

| `--separation-quality` | Model | Trade |
| --- | --- | --- |
| `fast` (default) | Demucs `htdemucs` | Quick; leaves some backing in the vocal |
| `smooth` | MDX-Net `UVR-MDX-NET-Inst_HQ_3` | Slower; cleaner separation |

**`fast` is the right default here**, and not as a compromise: the face only
needs to know where the voice is and how loud it is. Backing leaking into the
vocal does not move the mouth differently. `smooth` exists for when the
isolated vocal is wanted for something fussier.

Separation is cached under the user cache directory and keyed on the track's
identity, so re-rendering the same song in another colour does not pay for it
again. `--keep-vocal-stem` also writes the vocal beside the track, where it is
found directly from then on and can be used by other tools.

Weights are never bundled. They download on first use and are cached, the same
arrangement the transcription engines use. **This is the heaviest dependency in
the tool** — `audio-separator` pulls PyTorch, around a gigabyte, with or
without a GPU — which is why it is optional and why the full-mix estimate
remains the default behaviour.

Without any of it the estimate is honest but imperfect: on a busy mix it will
occasionally mistake an instrument for a singer. `--no-separate-vocals` keeps
the estimate; `--no-face-vocals` turns the whole feature off.

### Controls

- **Colour** follows the sung-word colour unless you set it separately.
- **Resting expression**, **placement** (upper, centre, lower), and **size** as
  a share of the frame.
- **Neon bloom** and **follow wordless singing** toggle off, and **head
  movement** scales from held still to lively.
- The face **replaces the waveform equaliser** — selecting it turns the bars
  off, since the face carries the motion they used to.
- It layers over Still, Ambient and Party Hard alike, and keeps its own colour
  through Party Hard's beat-stepped hue changes.

## Motion and light

- **Still** leaves the artwork clean and motionless.
- **Ambient** adds slow cover drift and a shallow, fully fading edge glow.
- **Party Hard** adds stronger movement and jumps the colour treatment once per
  beat. Leave BPM empty to estimate it from the audio, or enter 40–240 BPM for
  deterministic timing.

Party Hard also exposes an **Extreme strobe** switch. This deliberately adds
rapid full-frame flashes, RGB channel separation, spectrum trails, faster
colour jumps, and a scrolling audio-reactive wash across the artwork. It is
off by default and carries an in-app photosensitivity warning because the
result can trigger seizures. Any published output using it should include a
prominent photosensitivity warning.

The audio equaliser can be disabled or placed along the bottom or right edge.
Its frequency bars are drawn from the real audio stream and remain behind the
burned-in lyrics. It is unavailable while the face is on.

## Correct lyrics

An optional `.rtf`, `.txt`, or `.md` sheet can replace transcription mistakes
while retaining word timing. Separate tracks with a line of three or more
underscores or hyphens; put the track title first and its lyrics below it.
Titles are matched to filenames after normalizing punctuation, case, and a
leading track number.

## Headless render

```sh
python3 app.py --render \
  --audio song.wav --json song.words.json \
  --format portrait --lines 3 --lyric-position center \
  --visual ambient --waveform bottom --out song-short.mp4
```

Omit `--format portrait` (or pass `--format landscape`) for a 1920x1080 video.
If no matching image sits beside the audio, pass `--cover cover.jpg`.
For Party Hard, pass `--visual party`; optionally add `--bpm 128`. Add
`--extreme` only for the explicitly warned high-intensity treatment.
Pass `--engine onnx-parakeet` to pin a transcriber instead of choosing
automatically.

With the face:

```sh
python3 app.py --render --audio song.wav --out song.mp4 \
  --face --face-expression '^w^' --face-placement upper --face-scale 0.62
```

`--face-color` is optional; without it the face follows the sung-word colour.
`--face-expression` takes any of `¬‿¬ ^_^ ^w^ o_o -_- ^o^ owo`,
`--face-style matrix` draws it as an LED grid, `--face-motion` scales the head
movement, `--no-face-glow` strips the bloom, and `--no-face-vocals` ignores
singing that is not in the lyric sheet.

Convert the simple MacWhisper word-list form to SRT with:

```sh
python3 json_to_srt.py transcript.json output.srt
```

Generated corrected JSON, ASS subtitles, and video files are intentionally
ignored by Git.

## The wider workshop

Protoke is one of four local-first projects:

- [Gateway Forge](https://snepssen.github.io/gateway-forge/) — guided-session
  authoring and an experience journal.
- [Voice Forge](https://snepssen.github.io/voice-forge/) — measured Piper
  speech, pronunciation, and export.
- [Protoke](https://snepssen.github.io/protoke/) — this project.
- [tools-core](https://snepssen.github.io/tools-core/) — the field utilities
  behind the larger applications.
