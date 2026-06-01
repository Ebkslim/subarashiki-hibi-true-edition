import gradio as gr
import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModel

REPO_NAME = "p1atdev/MangaLineExtraction-hf"

# Load once at startup. trust_remote_code is required: this model ships a
# custom architecture in its repo.
model = AutoModel.from_pretrained(REPO_NAME, trust_remote_code=True)
processor = AutoImageProcessor.from_pretrained(REPO_NAME, trust_remote_code=True)
model.eval()

device = "cuda" if torch.cuda.is_available() else "cpu"
# The checkpoint is bf16; cast to float32 on CPU for stable inference.
model = model.to(device=device, dtype=torch.float32)


@torch.no_grad()
def extract_lines(image: Image.Image) -> Image.Image:
    if image is None:
        return None

    image = image.convert("RGB")
    inputs = processor(image, return_tensors="pt")
    pixel_values = inputs.pixel_values.to(device=device, dtype=torch.float32)

    outputs = model(pixel_values)

    line = outputs.pixel_values[0].cpu().float().numpy()
    line = np.clip(line, 0, 255).astype("uint8")
    return Image.fromarray(line, mode="L")


demo = gr.Interface(
    fn=extract_lines,
    inputs=gr.Image(type="pil", label="Input image"),
    outputs=gr.Image(type="pil", label="Extracted line art", image_mode="L"),
    title="✏️ MangaLineExtraction",
    description=(
        "Extract clean line art from manga / illustration images using "
        "[p1atdev/MangaLineExtraction-hf](https://huggingface.co/p1atdev/MangaLineExtraction-hf). "
        "Upload an image and the model returns a grayscale line drawing."
    ),
    allow_flagging="never",
)

if __name__ == "__main__":
    demo.launch()
