import os
from PIL import Image, ImageDraw


def generate_app_icon():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(base_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    uploaded_path = os.path.join(assets_dir, "icon_uploaded.png")
    icon_path_ico = os.path.join(assets_dir, "icon.ico")
    icon_path_png = os.path.join(assets_dir, "icon.png")

    if os.path.exists(uploaded_path):
        src = Image.open(uploaded_path).convert("RGBA")
        w, h = src.size
        pixels = src.load()

        # Localiza a caixa delimitadora (bounding box) do desenho do ícone (pixels não brancos)
        min_x, min_y = w, h
        max_x, max_y = 0, 0
        for y in range(h):
            for x in range(w):
                r, g, b, a = pixels[x, y]
                if a > 0 and (r < 245 or g < 245 or b < 245):
                    if x < min_x:
                        min_x = x
                    if y < min_y:
                        min_y = y
                    if x > max_x:
                        max_x = x
                    if y > max_y:
                        max_y = y

        if min_x < max_x and min_y < max_y:
            cropped = src.crop((min_x, min_y, max_x + 1, max_y + 1))
        else:
            cropped = src

        # Aplica máscara de retângulo arredondado acompanhando o contorno externo do livro
        # para remover o fundo branco externo preservando o branco interno da capa e das páginas
        cw, ch = cropped.size
        mask = Image.new("L", (cw, ch), 0)
        mask_draw = ImageDraw.Draw(mask)
        corner_r = max(4, int(min(cw, ch) * 0.12))
        mask_draw.rounded_rectangle([(0, 0), (cw - 1, ch - 1)], radius=corner_r, fill=255)
        cropped.putalpha(mask)

        # Centraliza em um canvas quadrado 256x256 com leve margem e fundo branco arredondado suave
        # para garantir contraste perfeito tanto na barra de tarefas escura quanto clara do Windows
        size = 256
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(canvas)
        bg_margin = 10
        bg_draw.rounded_rectangle(
            [(bg_margin, bg_margin), (size - bg_margin, size - bg_margin)],
            radius=44,
            fill=(255, 255, 255, 255),
        )

        # Redimensiona o ícone mantendo a proporção original
        target_box = size - 52
        scale = min(target_box / cw, target_box / ch)
        new_w = max(1, int(round(cw * scale)))
        new_h = max(1, int(round(ch * scale)))
        resized = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)

        offset_x = (size - new_w) // 2
        offset_y = (size - new_h) // 2
        canvas.paste(resized, (offset_x, offset_y), resized)
        img = canvas
    else:
        # Fallback vetorial idêntico ao ícone enviado (livro preto e branco com etiqueta e elástico)
        size = 256
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([(12, 12), (244, 244)], radius=44, fill=(255, 255, 255, 255))
        draw.rounded_rectangle([(44, 32), (212, 224)], radius=20, fill=(20, 20, 20, 255))
        draw.rectangle([(76, 46), (196, 188)], fill=(255, 255, 255, 255))
        draw.rounded_rectangle([(102, 70), (156, 98)], radius=6, fill=(20, 20, 20, 255))
        draw.rectangle([(174, 46), (184, 224)], fill=(20, 20, 20, 255))
        draw.rectangle([(60, 202), (212, 212)], fill=(255, 255, 255, 255))
        draw.rectangle([(174, 202), (184, 212)], fill=(20, 20, 20, 255))

    img.save(icon_path_png, format="PNG")
    img.save(
        icon_path_ico,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("Ícone gerado com sucesso em:", icon_path_ico, "e", icon_path_png)


if __name__ == "__main__":
    generate_app_icon()
