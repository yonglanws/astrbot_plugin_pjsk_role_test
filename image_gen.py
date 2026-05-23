import math
import os
import uuid
import io
import urllib.request
from PIL import Image, ImageDraw, ImageFont

# 大五人格维度
DIMS = ["EXT", "AGR", "CON", "NEU", "OPN"]
DIM_LABELS = {
    "EXT": "外向性",
    "AGR": "宜人性",
    "CON": "尽责性",
    "NEU": "神经质",
    "OPN": "开放性",
}

# Apple-like 色彩体系
BG_COLOR = (245, 245, 247)
CARD_BG = (255, 255, 255)
TEXT_MAIN = (29, 29, 31)
TEXT_SUB = (134, 134, 139)
TEXT_WHITE = (255, 255, 255)
LINE_COLOR = (229, 229, 234)
RADAR_FILL_ALPHA = 35


_font_cache = {}


def _get_font(size: int, bold: bool = False):
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    misans_path = os.path.join(plugin_dir, "MiSans-Medium.ttf")
    if os.path.exists(misans_path):
        try:
            font = ImageFont.truetype(misans_path, size)
            _font_cache[key] = font
            return font
        except Exception:
            pass

    font_paths = [
        "C:/Windows/Fonts/Segoe UI Bold.ttf" if bold else "C:/Windows/Fonts/Segoe UI.ttf",
        "C:/Windows/Fonts/MSYH.ttc",
        "C:/Windows/Fonts/MSYHBD.ttc",
        "C:/Windows/Fonts/simsun.ttc",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, size)
                _font_cache[key] = font
                return font
            except Exception:
                pass
    font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _draw_rounded_rect(draw, xy, radius, fill):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=fill)


def _draw_radar(draw, cx, cy, radius, scores, color_rgb):
    n = len(DIMS)
    max_score = 5  # 大五人格每维最高5分

    for level in [0.25, 0.5, 0.75, 1.0]:
        r = radius * level
        points = []
        for i in range(n):
            angle = math.pi / 2 + 2 * math.pi * i / n
            px = cx + r * math.cos(angle)
            py = cy - r * math.sin(angle)
            points.append((px, py))
        draw.polygon(points, outline=(220, 220, 225), fill=None)

    for i in range(n):
        angle = math.pi / 2 + 2 * math.pi * i / n
        ex = cx + radius * math.cos(angle)
        ey = cy - radius * math.sin(angle)
        draw.line([(cx, cy), (ex, ey)], fill=(220, 220, 225), width=2)

    data_points = []
    for i, d in enumerate(DIMS):
        val = scores.get(d, 0)
        ratio = min(val / max_score, 1.0)
        angle = math.pi / 2 + 2 * math.pi * i / n
        px = cx + radius * ratio * math.cos(angle)
        py = cy - radius * ratio * math.sin(angle)
        data_points.append((px, py))

    fill_color = (*color_rgb, RADAR_FILL_ALPHA)
    overlay = Image.new("RGBA", draw.im.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.polygon(data_points, fill=fill_color, outline=(*color_rgb, 200))

    for px, py in data_points:
        overlay_draw.ellipse(
            [(px - 5, py - 5), (px + 5, py + 5)],
            fill=(*color_rgb, 220),
            outline=TEXT_WHITE,
        )

    return overlay


def _draw_bar(draw, x, y, w, h, ratio, fill_color, bg_color=(230, 230, 235)):
    _draw_rounded_rect(draw, (x, y, x + w, y + h), h // 2, bg_color)
    if ratio > 0:
        fw = max(int(w * ratio), 6)
        _draw_rounded_rect(draw, (x, y, x + fw, y + h), h // 2, fill_color)


def _build_dim_interp(scores: dict) -> str:
    """根据用户五维分数生成解读文本，逻辑与 index.html 一致"""
    lines = []
    vals = [scores.get(d, 3.0) for d in DIMS]

    if vals[0] < 2.5:
        lines.append("你的外向性得分偏低，这意味着你更喜欢安静独处，在内心世界中汲取能量，而不是在热闹的社交场合中感到舒适。")
    elif vals[0] > 3.5:
        lines.append("你的外向性得分偏高，说明你热情活跃，喜欢与人交往，常常成为聚会中的焦点，从社交中获得能量。")
    else:
        lines.append("你的外向性中等，你既能享受独处的宁静，也能在社交中自如表现，动静皆宜。")

    if vals[1] < 2.5:
        lines.append("你的宜人性得分偏低，表明你更倾向于直接坦率，不会为了迎合他人而改变自己，有时显得强势但真实。")
    elif vals[1] > 3.5:
        lines.append("你的宜人性得分偏高，显示你善良体贴，乐于助人，总是优先考虑他人的感受，是团队中的温暖存在。")
    else:
        lines.append("你的宜人性中等，你懂得平衡自己与他人的需求，既不过分讨好也不冷漠，关系处理得当。")

    if vals[2] < 2.5:
        lines.append("你的尽责性得分偏低，说明你随性自由，不喜欢被规则束缚，更愿意凭感觉行事，灵活应对变化。")
    elif vals[2] > 3.5:
        lines.append("你的尽责性得分偏高，表明你自律严谨，做事有计划有目标，能够坚持不懈地完成任务，值得信赖。")
    else:
        lines.append("你的尽责性中等，你既有规划意识也能接受变动，在有序和灵活之间找到了适合自己的平衡点。")

    if vals[3] < 2.5:
        lines.append("你的神经质得分偏低，说明你情绪稳定，不易焦虑，面对压力能保持冷静，心态平和。")
    elif vals[3] > 3.5:
        lines.append("你的神经质得分偏高，显示你敏感细腻，容易受到外界影响，情绪波动较大，但这也让你更有同理心。")
    else:
        lines.append("你的神经质中等，你能够感知情绪但不会被其淹没，在敏感与稳定之间保持了良好的平衡。")

    if vals[4] < 2.5:
        lines.append("你的开放性得分偏低，说明你务实传统，喜欢熟悉的环境和事物，对新奇尝试持谨慎态度。")
    elif vals[4] > 3.5:
        lines.append("你的开放性得分偏高，表明你充满好奇心，乐于接受新事物，喜欢探索未知领域，富有创造力。")
    else:
        lines.append("你的开放性中等，你愿意尝试新事物但不会盲目追求，在传统与创新之间找到了自己的节奏。")

    return "\n".join(lines)


def _wrap_text(text: str, font, max_width: int, draw: ImageDraw.ImageDraw = None) -> list:
    """按最大宽度将文本折行"""
    lines = []
    for paragraph in text.split("\n"):
        current = ""
        for char in paragraph:
            test = current + char
            if draw is not None:
                bbox = draw.textbbox((0, 0), test, font=font)
            else:
                bbox = font.getbbox(test)
            if bbox and (bbox[2] - bbox[0]) > max_width and current:
                lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)
    return lines


def generate_result_image(
    scores: dict,
    top_char: dict,
    ranked: list,
    plugin_dir: str,
) -> str:
    data_dir = os.path.join(plugin_dir, "data")
    output_path = os.path.join(plugin_dir, f"result_{uuid.uuid4().hex}.png")

    for name in os.listdir(plugin_dir):
        if not name.startswith("result_") or not name.endswith(".png"):
            continue
        old_path = os.path.join(plugin_dir, name)
        try:
            os.remove(old_path)
        except Exception:
            pass

    W, H = 1600, 1180

    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    font_title = _get_font(52, bold=True)
    font_desc = _get_font(28)
    font_match = _get_font(32, bold=True)
    font_tiny = _get_font(20)
    font_label = _get_font(24)
    font_pct = _get_font(26, bold=True)

    card_margin = 60
    card_x1, card_y1 = card_margin, card_margin
    card_x2, card_y2 = W - card_margin, H - card_margin
    _draw_rounded_rect(draw, (card_x1, card_y1, card_x2, card_y2), 32, CARD_BG)

    left_w = 380
    left_x = card_x1 + 30
    left_y = card_y1 + 30

    char_img = None
    img_id = top_char.get('img_id', '')
    remote_url = f"https://storage.exmeaning.com/sekai-jp-assets/character/character_select/chr_tl_{img_id}.webp"
    try:
        with urllib.request.urlopen(remote_url, timeout=10) as resp:
            img_data = resp.read()
        char_img = Image.open(io.BytesIO(img_data)).convert("RGBA")
        target_h = int((card_y2 - card_y1 - 60) * 0.78)
        ratio = target_h / char_img.height
        new_w = int(char_img.width * ratio)
        char_img = char_img.resize((new_w, target_h), Image.LANCZOS)
    except Exception:
        char_img = None

    if char_img is None:
        portrait_path = os.path.join(data_dir, f"chr_tl_{img_id}.webp")
        if not os.path.exists(portrait_path):
            for i in range(1, 27):
                p = os.path.join(data_dir, f"chr_tl_{i}.webp")
                if os.path.exists(p):
                    portrait_path = p
                    break
        if os.path.exists(portrait_path):
            try:
                char_img = Image.open(portrait_path).convert("RGBA")
                target_h = int((card_y2 - card_y1 - 60) * 0.78)
                ratio = target_h / char_img.height
                new_w = int(char_img.width * ratio)
                char_img = char_img.resize((new_w, target_h), Image.LANCZOS)
            except Exception:
                char_img = None

    if char_img:
        img_x = left_x + (left_w - char_img.width) // 2
        img_y = left_y + (card_y2 - card_y1 - char_img.height) // 2 - 20
        img.paste(char_img, (img_x, img_y), char_img)

    sep_x = left_x + left_w + 30
    draw.line([(sep_x, card_y1 + 40), (sep_x, card_y2 - 40)], fill=LINE_COLOR, width=2)

    right_x = sep_x + 48
    right_y = card_y1 + 40

    draw.text((right_x, right_y), top_char.get("name", ""), font=font_title, fill=TEXT_MAIN)
    right_y += 72

    desc_text = top_char.get("desc", "")
    draw.text((right_x, right_y), desc_text, font=font_desc, fill=TEXT_SUB)
    right_y += 64

    draw.text((right_x, right_y), "契合度分析", font=font_match, fill=TEXT_MAIN)
    right_y += 56

    bar_h = 16
    bar_max_w = 500
    for i, (score, c) in enumerate(ranked[:3]):
        c_color = _hex_to_rgb(c.get("color", "#7c3aed"))
        ratio = score / 100.0

        dot_r = 16
        draw.ellipse(
            [(right_x, right_y + 4), (right_x + dot_r * 2, right_y + 4 + dot_r * 2)],
            fill=c_color,
        )
        num_text = str(i + 1)
        bbox = draw.textbbox((0, 0), num_text, font=font_tiny)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((right_x + dot_r - tw // 2, right_y + 4 + dot_r - th // 2 - 4), num_text, font=font_tiny, fill=TEXT_WHITE)

        name_x = right_x + 48
        draw.text((name_x, right_y), c.get("name", ""), font=font_label, fill=TEXT_MAIN)
        draw.text((name_x, right_y + 30), c.get("unit", ""), font=font_tiny, fill=TEXT_SUB)

        bar_x = name_x + 220
        bar_y = right_y + 18
        _draw_bar(draw, bar_x, bar_y, bar_max_w, bar_h, ratio, c_color)
        draw.text((bar_x + bar_max_w + 30, right_y + 4), f"{score}%", font=font_pct, fill=TEXT_MAIN)

        right_y += 76

    right_y += 8

    tag_color = _hex_to_rgb(top_char.get("color", "#7c3aed"))

    dim_x = right_x
    dim_y = right_y + 10
    font_dim_label = _get_font(24)
    font_dim_value = _get_font(24, bold=True)

    sorted_dims = sorted(DIMS, key=lambda d: scores.get(d, 0), reverse=True)

    draw.text((dim_x, dim_y), "维度分析", font=font_match, fill=TEXT_MAIN)
    dim_y += 50

    for i, d in enumerate(sorted_dims):
        val = scores.get(d, 0)
        label = DIM_LABELS.get(d, d)
        row_y = dim_y + i * 52

        rank_text = f"{i+1}."
        draw.text((dim_x, row_y), rank_text, font=font_dim_label, fill=TEXT_SUB)

        draw.text((dim_x + 40, row_y), label, font=font_dim_label, fill=TEXT_SUB)

        val_text = f"{val:.1f}" if isinstance(val, float) else f"{val}"
        bbox = draw.textbbox((0, 0), val_text, font=font_dim_value)
        tw = bbox[2] - bbox[0]
        draw.text((dim_x + 320 - tw, row_y), val_text, font=font_dim_value, fill=tag_color)

        bar_w = 140
        bar_h = 10
        ratio = min(val / 5, 1.0)
        _draw_bar(draw, dim_x + 125, row_y + 8, bar_w, bar_h, ratio, tag_color)

    radar_size = 380
    radar_cx = dim_x + 450 + radar_size // 2
    radar_cy = right_y + radar_size // 2 + 10
    radar_radius = 145

    radar_overlay = _draw_radar(draw, radar_cx, radar_cy, radar_radius, scores, tag_color)
    img = Image.alpha_composite(img.convert("RGBA"), radar_overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    n = len(DIMS)
    label_radius = radar_radius + 40
    for i, d in enumerate(DIMS):
        angle = math.pi / 2 + 2 * math.pi * i / n
        lx = radar_cx + label_radius * math.cos(angle)
        ly = radar_cy - label_radius * math.sin(angle)
        label = DIM_LABELS.get(d, d)
        bbox = draw.textbbox((0, 0), label, font=font_tiny)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        lx = max(tw // 2 + 4, min(W - tw // 2 - 4, lx))
        ly = max(th // 2 + 4, min(H - th // 2 - 4, ly))
        draw.text((lx - tw // 2, ly - th // 2), label, font=font_tiny, fill=TEXT_SUB)

    # 五维解读区域（在维度分析和雷达图下方）
    interp_text = _build_dim_interp(scores)
    font_interp = _get_font(20)
    interp_max_w = card_x2 - right_x - 40
    interp_lines = _wrap_text(interp_text, font_interp, interp_max_w, draw)
    line_height = 30

    interp_y = radar_cy + radar_radius
    draw.text((right_x, interp_y), "五维解读", font=font_match, fill=TEXT_MAIN)
    interp_y += 50
    for line in interp_lines:
        if interp_y > H - 60:
            break
        draw.text((right_x, interp_y), line, font=font_interp, fill=TEXT_SUB)
        interp_y += line_height

    footer_y = H - 48
    footer_text = "Designed by yangzihao1234567 & 慵懒午睡  Generated by mzkbot · 结果仅供娱乐"
    bbox = draw.textbbox((0, 0), footer_text, font=font_tiny)
    tw = bbox[2] - bbox[0]
    draw.text((W // 2 - tw // 2, footer_y), footer_text, font=font_tiny, fill=TEXT_SUB)

    img.save(output_path, "PNG", quality=95)
    return output_path
