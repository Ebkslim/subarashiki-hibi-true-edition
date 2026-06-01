---
title: MangaLineExtraction
emoji: ✏️
colorFrom: gray
colorTo: indigo
sdk: gradio
sdk_version: 6.15.2
python_version: "3.12"
app_file: app.py
pinned: false
license: mit
---

# MangaLineExtraction Space

A minimal Gradio demo around
[`p1atdev/MangaLineExtraction-hf`](https://huggingface.co/p1atdev/MangaLineExtraction-hf):
upload an image and get back extracted grayscale line art.

## Deploy this Space

1. Create a new Space at <https://huggingface.co/new-space> (SDK: **Gradio**).
2. Upload `app.py`, `requirements.txt`, and this `README.md` (the YAML
   header above configures the Space).
3. The Space builds automatically — first build downloads the model
   (~43M params), so give it a minute.

> Tip: A free CPU Space works fine. Pick a GPU hardware tier if you want
> faster inference on large images.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```
