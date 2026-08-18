"""
Agnes 图像生成节点
使用 Agnes Image API (agnes-image-2.1-flash)
"""
import requests
import torch
import numpy as np
from PIL import Image
import io
import folder_paths
from ..api import AgnesClient, BASE_URL, IMAGE_MODEL


class AgnesImageGen:
    """使用 Agnes AI 生成图像"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入图像描述..."
                }),
                "api_key": ("STRING", {
                    "default": "sk-你的Key",
                    "placeholder": "Agnes API Key"
                }),
                "width": ("INT", {"default": 1024, "min": 256, "max": 2048}),
                "height": ("INT", {"default": 1024, "min": 256, "max": 2048}),
                "quality": (["1K", "2K"], {"default": "1K"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING",)
    RETURN_NAMES = ("image", "url",)
    FUNCTION = "generate"
    CATEGORY = "🎬 Agnes Novel"

    def generate(self, prompt, api_key, width, height, quality):
        print(f"\n[Agnes Image] 开始生成...")
        print(f"Prompt: {prompt[:80]}...")
        print(f"Size: {width}x{height}, Quality: {quality}")

        try:
            client = AgnesClient(api_key)
            urls = client.generate_image(
                prompt=prompt,
                model=IMAGE_MODEL,
                size=f"{width}x{height}",
                n=1
            )

            if urls:
                image_url = urls[0]
                print(f"[Agnes Image] 图片 URL: {image_url}")
                
                # 下载图片
                img_response = requests.get(image_url, timeout=60)
                pil_img = Image.open(io.BytesIO(img_response.content)).convert("RGB")
                
                # 转换为 ComfyUI 格式
                img_np = np.array(pil_img).astype(np.float32) / 255.0
                img_tensor = torch.from_numpy(img_np).unsqueeze(0)
                
                print(f"[Agnes Image] 生成成功: {pil_img.size}")
                return (img_tensor, image_url)
            else:
                raise Exception("未获取到图片 URL")

        except Exception as e:
            print(f"[Agnes Image] 失败: {e}")
            # 返回黑色图片作为占位
            black = torch.zeros(1, height, width, 3)
            return (black, "")


NODE_CLASS_MAPPINGS = {"AgnesImageGen": AgnesImageGen}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesImageGen": "🎨 Agnes 图像生成"}
