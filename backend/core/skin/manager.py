"""
皮肤管理器 — 皮肤配置的读取、应用、AI 生成

核心能力:
    1. 列出所有皮肤 (从 data/skins/*.json 读取)
    2. 获取单个皮肤配置
    3. 应用皮肤 (写入 data/current_skin.json)
    4. 获取当前皮肤
    5. AI 生成皮肤 (调用 LLM 生成 CSS 变量方案)
    6. 从图片提取色彩方案 (Pillow + sklearn KMeans 聚类)
"""
import json
import uuid
from pathlib import Path
from typing import Optional

from config.settings import settings
from core.llm.gateway import llm_gateway


# 皮肤生成 Prompt 模板 — 要求 LLM 输出含 variables 与 preview_colors 的 JSON
SKIN_GEN_PROMPT = """你是一位专业的 UI 视觉设计师，擅长为深色/浅色界面设计和谐的配色方案。
根据用户的需求描述，生成一套完整的皮肤配色方案。

请严格输出以下 JSON 格式 (不要输出任何其他内容，不要使用 markdown 代码块):
{{
  "name": "皮肤中文名称",
  "description": "一句话描述该皮肤的风格与适用场景",
  "tags": ["标签1", "标签2", "标签3"],
  "preview_colors": ["#主背景", "#次背景", "#强调色", "#辅助强调色"],
  "variables": {{
    "--bg-0": "#最底层背景色",
    "--bg-1": "#卡片背景色",
    "--bg-2": "#悬浮层背景色",
    "--border": "rgba(边框色,含透明度)",
    "--text-0": "#主要文字色",
    "--text-1": "#次要文字色",
    "--text-2": "#辅助文字色",
    "--accent": "#主强调色",
    "--accent-2": "#辅助强调色",
    "--success": "#成功色",
    "--warning": "#警告色",
    "--error": "#错误色",
    "--radius": "圆角值,如 12px"
  }}
}}

设计要求:
- 配色需和谐统一，严格贴合用户描述的风格 (深色/浅色/科技/自然/暖调/冷调等)
- 深色主题: 背景使用低明度暗色，文字使用高明度亮色，保证可读性
- 浅色主题: 背景使用高明度亮色，文字使用低明度暗色
- --accent 与 --accent-2 形成层次，与背景对比度足够 (建议对比度 >= 4.5:1)
- --border 使用 rgba 格式，透明度 0.08~0.15
- --radius 取值范围 "8px"~"16px"
- 除 --border 与 --radius 外，所有颜色使用 # 开头的 6 位十六进制格式
- preview_colors 须从 variables 中选取 4 个最具代表性的颜色
- name、description、tags 使用中文
"""


# 皮肤 JSON 必须包含的变量键 (用于校验 LLM 输出)
REQUIRED_VARIABLES = [
    "--bg-0", "--bg-1", "--bg-2", "--border",
    "--text-0", "--text-1", "--text-2",
    "--accent", "--accent-2",
    "--success", "--warning", "--error", "--radius",
]


class SkinManager:
    """皮肤管理器 — 统一管理皮肤配置的读取、应用与生成"""

    def __init__(self):
        self.skins_dir = Path(settings.skins_dir)
        self.data_dir = Path(settings.data_dir)
        # 确保目录存在 (便于在应用启动前或测试中独立使用)
        self.skins_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 基础 CRUD: 列表 / 读取 / 应用 / 当前
    # ------------------------------------------------------------------ #

    def list_skins(self) -> list[dict]:
        """
        列出所有皮肤 (预置 + 用户自定义，从 data/skins/*.json 读取)

        :return: 皮肤摘要列表 [{id, name, description, tags, preview_colors, variables}, ...]
                 variables 也包含在摘要里，前端切换皮肤时无需再次请求详情
        """
        skins: list[dict] = []
        if not self.skins_dir.exists():
            return skins

        for skin_file in sorted(self.skins_dir.glob("*.json")):
            try:
                with open(skin_file, "r", encoding="utf-8") as f:
                    skin = json.load(f)
                skins.append({
                    "id": skin.get("id", skin_file.stem),
                    "name": skin.get("name", skin_file.stem),
                    "description": skin.get("description", ""),
                    "tags": skin.get("tags", []),
                    "preview_colors": skin.get("preview_colors", []),
                    "variables": skin.get("variables", {}),  # 一并返回，切换皮肤无需二次请求
                })
            except (json.JSONDecodeError, OSError):
                # 跳过损坏的皮肤文件
                continue
        return skins

    def get_skin(self, skin_id: str) -> Optional[dict]:
        """
        获取单个皮肤的完整配置

        :param skin_id: 皮肤 ID (文件名，不含扩展名)
        :return: 皮肤完整 JSON；不存在时返回 None
        """
        skin_path = self.skins_dir / f"{skin_id}.json"
        if not skin_path.exists():
            return None
        with open(skin_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def apply_skin(self, skin_id: str) -> bool:
        """
        应用皮肤 — 写入当前皮肤偏好 (data/current_skin.json)
        前端读取后注入对应的 CSS 变量

        :param skin_id: 要应用的皮肤 ID
        :return: 应用成功返回 True；皮肤不存在返回 False
        """
        skin_path = self.skins_dir / f"{skin_id}.json"
        if not skin_path.exists():
            return False

        current_path = self.data_dir / "current_skin.json"
        with open(current_path, "w", encoding="utf-8") as f:
            json.dump({"skin_id": skin_id}, f, ensure_ascii=False, indent=2)

        print(f"[SkinManager] 已应用皮肤: {skin_id}")
        return True

    def get_current_skin(self) -> dict:
        """
        获取当前生效皮肤 — 返回偏好 ID 与完整配置

        :return: {"skin_id": str, "skin": Optional[dict]}
                 若无偏好记录，skin_id 回退为 "default"
        """
        current_path = self.data_dir / "current_skin.json"
        if not current_path.exists():
            return {"skin_id": "default", "skin": self.get_skin("default")}

        with open(current_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        skin_id = data.get("skin_id", "default")
        return {"skin_id": skin_id, "skin": self.get_skin(skin_id)}

    # ------------------------------------------------------------------ #
    # AI 生成皮肤
    # ------------------------------------------------------------------ #

    async def generate_skin(self, prompt: str) -> dict:
        """
        AI 生成皮肤 — 调用 LLM 生成 CSS 变量方案

        :param prompt: 用户的自然语言需求描述
        :return: {"success": bool, "skin": dict, "error": str}
        """
        if not llm_gateway.available:
            return {
                "success": False,
                "skin": None,
                "error": "LLM 推理引擎未就绪，请检查 llama-server 是否已启动",
            }

        # 构造消息并调用 LLM
        messages = [
            {"role": "system", "content": SKIN_GEN_PROMPT},
            {"role": "user", "content": f"用户需求: {prompt}"},
        ]

        try:
            result = await llm_gateway.chat(messages, temperature=0.4)
            raw_output = result["content"]
        except Exception as e:
            return {
                "success": False,
                "skin": None,
                "error": f"LLM 调用失败: {e}",
            }

        # 解析 LLM 输出的 JSON
        parsed = self._extract_json(raw_output)
        if parsed is None:
            return {
                "success": False,
                "skin": None,
                "error": "LLM 输出无法解析为 JSON",
                "raw_output": raw_output[:500],
            }

        # 校验必要字段
        variables = parsed.get("variables") or {}
        missing = [k for k in REQUIRED_VARIABLES if k not in variables]
        if missing:
            return {
                "success": False,
                "skin": None,
                "error": f"生成的皮肤缺少必要变量: {missing}",
                "raw_output": raw_output[:500],
            }
        if not parsed.get("preview_colors"):
            return {
                "success": False,
                "skin": None,
                "error": "生成的皮肤缺少 preview_colors",
                "raw_output": raw_output[:500],
            }

        # 补充元信息并持久化
        skin_id = f"ai_{uuid.uuid4().hex[:8]}"
        skin_config = {
            "id": skin_id,
            "name": parsed.get("name", "AI 生成皮肤"),
            "version": "1.0.0",
            "description": parsed.get("description", ""),
            "tags": parsed.get("tags", ["AI 生成"]),
            "preview_colors": parsed.get("preview_colors", []),
            "variables": variables,
        }

        save_path = self.skins_dir / f"{skin_id}.json"
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(skin_config, f, ensure_ascii=False, indent=2)

        print(f"[SkinManager] 皮肤已生成: {skin_id} ({skin_config['name']})")
        return {"success": True, "skin": skin_config, "error": ""}

    # ------------------------------------------------------------------ #
    # 从图片提取色彩方案
    # ------------------------------------------------------------------ #

    def extract_colors_from_image(
        self,
        image_path: str,
        n_colors: int = 6,
    ) -> dict:
        """
        从图片提取主色调方案 (Pillow + sklearn KMeans 聚类)

        :param image_path: 图片文件路径
        :param n_colors: 提取的主色数量 (默认 6)
        :return: {"success": bool, "colors": list[str], "error": str}
                 colors 为十六进制颜色列表，按占比从高到低排序
        """
        # 延迟导入图像处理依赖 (避免在未使用该功能时强依赖 numpy/sklearn)
        try:
            from PIL import Image
            import numpy as np
            from sklearn.cluster import KMeans
        except ImportError as e:
            return {
                "success": False,
                "colors": [],
                "error": f"缺少图像处理依赖库: {e}",
            }

        try:
            img = Image.open(image_path).convert("RGB")
            # 缩小尺寸以加速聚类，降低内存占用
            img.thumbnail((150, 150))
            pixels = np.array(img).reshape(-1, 3).astype(np.float32)

            # 过滤极端亮度像素 (近白/近黑)，聚焦有意义的色彩
            not_black = np.any(pixels > 15, axis=1)
            not_white = np.any(pixels < 240, axis=1)
            filtered = pixels[not_black & not_white]
            # 有效像素不足时回退使用全部像素
            if len(filtered) < n_colors * 2:
                filtered = pixels

            # KMeans 聚类提取主色
            kmeans = KMeans(
                n_clusters=n_colors,
                n_init=10,
                random_state=42,
            )
            kmeans.fit(filtered)

            # 按聚类样本数从高到低排序
            counts = np.bincount(kmeans.labels_, minlength=n_colors)
            order = np.argsort(-counts)
            centers = kmeans.cluster_centers_[order]

            colors = [
                self._rgb_to_hex(int(r), int(g), int(b))
                for r, g, b in centers
            ]
            print(f"[SkinManager] 从图片提取 {len(colors)} 个主色: {colors}")
            return {"success": True, "colors": colors, "error": ""}
        except Exception as e:
            return {
                "success": False,
                "colors": [],
                "error": f"色彩提取失败: {e}",
            }

    # ------------------------------------------------------------------ #
    # 内部工具方法
    # ------------------------------------------------------------------ #

    def _extract_json(self, text: str) -> Optional[dict]:
        """从 LLM 输出中提取 JSON (容错处理 markdown 代码块与多余文本)"""
        text = text.strip()

        # 去除 markdown 代码块标记
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取第一个 JSON 对象
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _rgb_to_hex(r: int, g: int, b: int) -> str:
        """将 RGB 值转换为 #RRGGBB 十六进制字符串"""
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        return f"#{r:02x}{g:02x}{b:02x}"


# 全局皮肤管理器单例
skin_manager = SkinManager()
