# 12社区 10周年纪念电子杂志 · 12 Club 10th Anniversary Ebook

The 12 Club 10th anniversary e-magazine (2014, made with iebook 超级精灵), played in the browser by
[Ruffle](https://ruffle.rs/) from the SWF files inside the original `10th_Anniversary.exe`.

```sh
./build.sh                          # writes the site to dist/ (needs python3, curl, tar)
python3 -m http.server -d dist 8000 # then open http://localhost:8000/ (not file://)
```

**GitHub Pages:** `.github/workflows/pages.yml` runs `build.sh` and publishes `dist/` on every push to `main`.
Turn it on once under Settings → Pages → Build and deployment → Source: **GitHub Actions**.
Any other static host can serve `dist/` as it is.

## Files

```
10th_Anniversary.exe     the original e-magazine (iebook player 6.0.0.4)
build.sh                 exe -> dist/book/, Ruffle -> dist/ruffle/, web/index.html -> dist/
tools/extract_iebook.py  unpacks the files packed in an iebook .exe
tools/patch_main_swf.py  lets Ruffle accept the engine's SharedObject name (bookmarks, doodles)
web/index.html           the page: Ruffle (autoplay) and one <embed>
.github/workflows/pages.yml  GitHub Pages deployment
```

## How the exe is packed

The exe is a Delphi player (F-IN-BOX) with the book appended after the PE image: an `IERD` header, one entry
per file, and a 12-byte trailer pointing back to it. Each entry's name is hex text XOR-ed with an 8-byte key,
and the first three bytes of every file are cut off and stored XOR-ed beside the name. That hides every
SWF's `CWS`/`FWS` signature, so SWF extractors find nothing in the exe. `tools/extract_iebook.py` documents the format:

```
$ python3 tools/extract_iebook.py 10th_Anniversary.exe out/
iebook v5001, window 800x600, key b209aa55936d8447
98 entries, 94 files -> out/  (36 .jpg, 7 .mp3, 6 .png, 44 .swf, 1 .xml)
```

`main.swf` is the iebook engine (ActionScript 2). It reads `config.xml` and loads the pages, `tools.swf` and
the music by itself, so the page only has to show it the way the exe did: 800×600, no scaling, with
`book/` as the base for relative URLs. It starts on its own; browsers hold back sound until the first click.

## Known limitations

- iebook's online features (comments, IM, statistics server) are long gone.
- The engine's fullscreen, minimize and close buttons only send commands to the exe, so on the web they
  do nothing; Ruffle's right-click menu has fullscreen.
- The settings dialog's two checkbox labels stay blank: Ruffle's canvas font renderer doesn't draw them.

## Credit

12 Club (12社区) for the book · [Ruffle](https://ruffle.rs/) (MIT/Apache-2.0)
