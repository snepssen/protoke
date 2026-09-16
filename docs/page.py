"""Protoke's page, as content.

The chrome — head, rail, header, jump navigation, ecosystem grid, footer —
is build.py's, shared byte-identically with every other project here. What is
in this file is what belongs to this page alone.

Each section names an HTML partial under `sections/`, so its markup stays
markup in a file an editor understands. build.py also takes structured blocks,
which siphon's page uses, for content regular enough to be worth it.
"""

PAGE = {
    "meta": {
        "slug": "protoke",
        "name": "Protoke",
        "title": "Protoke",
        "badge": "macOS · Windows · Linux · MIT",
        "fonts": "fonts.css",
        "description": "Karaoke and narration videos fronted by an animated protogen visor face — drawn as vector outlines by the same subtitle pass that draws the lyrics, with no image sequence and no video layer.",
        "og_description": "proto + karaoke. A karaoke and narration renderer whose face is a subtitle track.",
        "subhead": "<em>proto</em> + <em>karaoke</em>. A karaoke and narration renderer with a protogen visor face that mouths the words — drawn as vector outlines by the same subtitle pass that draws the lyrics, so there is no image sequence and no video layer to composite.",
        "stats": [
            "<b>14</b> dials shape the face",
            "<b>11</b> expressions",
            "<b>4</b> transcription engines, one free everywhere",
            "<b>173</b> checks passing",
            "<b>Local-first.</b> Nothing leaves the machine",
        ],
        "scripts": ["face-loop.js", "site.js"],
    },
    "sections": [
    {
        "id": "demo",
        "jump": "Demo",
        "eyebrow": "Twenty-eight seconds",
        "heading": "Everything moving here was written into a subtitle file",
        "body": "demo.html",
    },
    {
        "id": "how",
        "jump": "How",
        "eyebrow": "Why it works this way",
        "heading": "A face is cheaper as geometry than as pictures",
        "body": "how.html",
    },
    {
        "id": "face",
        "jump": "The face",
        "eyebrow": "The face",
        "heading": "Eleven expressions, no sprite sheet",
        "body": "face.html",
    },
    {
        "id": "app",
        "jump": "The app",
        "eyebrow": "The app",
        "heading": "A local page, not a cloud service",
        "body": "app.html",
    },
    {
        "id": "install",
        "jump": "Install",
        "eyebrow": "Get it",
        "heading": "Python, ffmpeg, and nothing else that is mandatory",
        "body": "install.html",
    },
    {"grid": True},
    {
        "id": "contact",
        "eyebrow": "If something looks wrong",
        "heading": "Say so",
        "body": "contact.html",
    },
    ],
    "footer": [
        "Protoke is MIT licensed. Source audio, lyric sheets and rendered videos are yours and stay outside the repository.",
    ],
}
