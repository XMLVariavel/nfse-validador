"""
gerar_icone.py — NFS-e Validador Nacional v3.1
Identidade visual NFS-e: Verde #168821 + Amarelo #FFCD07
Renderiza em 512px e reduz com LANCZOS para ícone nítido em qualquer resolução.
Requer: pip install pillow
"""
from PIL import Image, ImageDraw, ImageFont
import struct, io
from pathlib import Path


# ── Cores oficiais NFS-e ──────────────────────────────────────────────────────
VERDE   = (22,  136, 33,  255)
VERDE_E = (14,  100, 22,  255)
AMARELO = (255, 205,  7,  255)
BRANCO  = (255, 255, 255, 255)
PRETO   = (20,  20,  20,  255)
CINZA   = (120, 120, 120, 255)
BG      = (252, 252, 250, 255)


def rr(d, x0, y0, x1, y1, r, fill):
    """Rounded rectangle sem borda."""
    r = min(r, (x1-x0)//2, (y1-y0)//2)
    if r <= 0:
        d.rectangle([x0,y0,x1,y1], fill=fill); return
    d.rectangle([x0+r,y0,x1-r,y1], fill=fill)
    d.rectangle([x0,y0+r,x1,y1-r], fill=fill)
    d.ellipse([x0,y0,x0+r*2,y0+r*2], fill=fill)
    d.ellipse([x1-r*2,y0,x1,y0+r*2], fill=fill)
    d.ellipse([x0,y1-r*2,x0+r*2,y1], fill=fill)
    d.ellipse([x1-r*2,y1-r*2,x1,y1], fill=fill)


def font(size, bold=False):
    candidates = []
    if bold:
        candidates = [
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\Arial Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\Arial.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for c in candidates:
        if Path(c).exists():
            try: return ImageFont.truetype(c, size)
            except: pass
    try: return ImageFont.load_default(size=size)
    except: return ImageFont.load_default()


def render(S=512):
    """Renderiza o ícone em tamanho S×S para depois reduzir."""
    img = Image.new("RGBA", (S, S), (0,0,0,0))
    d   = ImageDraw.Draw(img)

    pad = S // 20
    r   = S // 7

    # Fundo branco arredondado
    rr(d, pad, pad, S-pad, S-pad, r, BG)

    # Faixa verde topo
    fh = S // 14
    rr(d, pad, pad, S-pad, pad+fh, r, VERDE)

    # Faixa amarela
    ah = S // 20
    d.rectangle([pad, pad+fh, S-pad, pad+fh+ah], fill=AMARELO)

    # Bloco verde central
    bp, bt, bb = S//8, pad+fh+ah+S//18, int(S*0.52)
    br = S // 18
    rr(d, bp, bt, S-bp, bb, br, VERDE)

    # Documento (folha) dentro do bloco
    dw = int(S*0.28); dh = int(S*0.34)
    dx = (S-dw)//2;   dy = bt + int((bb-bt-dh)*0.12)
    doc_r = S//40

    # Sombra
    rr(d, dx+S//60, dy+S//60, dx+dw+S//60, dy+dh+S//60, doc_r, (0,0,0,45))
    # Folha
    rr(d, dx, dy, dx+dw, dy+dh, doc_r, (255,255,255,225))

    # Linhas no documento
    lx = dx + S//30; lw = dw - S//15
    for i in range(4):
        ly = dy + S//20 + i*(S//28)
        lc = max(2, S//80)
        lwidth = lw if i > 0 else lw*3//4
        d.rounded_rectangle([lx, ly, lx+lwidth, ly+lc], radius=lc//2,
                             fill=VERDE_E[:3]+(50+i*20,))

    # Check no documento
    cx, cy = S//2, dy + int(dh*0.72)
    cr = S // 13
    d.ellipse([cx-cr, cy-cr, cx+cr, cy+cr], fill=VERDE)
    lw_c = max(3, S//38)
    p1 = (cx-int(cr*0.52), cy+int(cr*0.05))
    p2 = (cx-int(cr*0.05), cy+int(cr*0.52))
    p3 = (cx+int(cr*0.58), cy-int(cr*0.50))
    d.line([p1, p2], fill=BRANCO, width=lw_c+2)
    d.line([p2, p3], fill=BRANCO, width=lw_c+2)

    # Texto "NFS-e"
    fn = font(S//7, bold=True)
    ty = bb + S//22
    bbox = d.textbbox((0,0), "NFS-e", font=fn)
    d.text(((S-(bbox[2]-bbox[0]))//2, ty), "NFS-e", font=fn, fill=VERDE)

    # Separador amarelo
    sy  = ty + (bbox[3]-bbox[1]) + S//38
    sh2 = S//28
    d.rounded_rectangle([S//7, sy, S-S//7, sy+sh2], radius=sh2//2, fill=AMARELO)

    # "VALIDADOR"
    fv  = font(S//9, bold=True)
    vy  = sy + sh2 + S//42
    bv  = d.textbbox((0,0), "VALIDADOR", font=fv)
    d.text(((S-(bv[2]-bv[0]))//2, vy), "VALIDADOR", font=fv, fill=PRETO)

    # "NACIONAL"
    fn2 = font(S//14, bold=False)
    ny  = vy + (bv[3]-bv[1]) + S//55
    bn  = d.textbbox((0,0), "NACIONAL", font=fn2)
    d.text(((S-(bn[2]-bn[0]))//2, ny), "NACIONAL", font=fn2, fill=CINZA)

    # Faixa verde rodapé
    ry = S - pad - fh
    rr(d, pad, ry, S-pad, S-pad, r, VERDE[:3]+(180,))

    return img


def salvar_ico(caminho="nfse.ico"):
    print("Renderizando ícone em 512×512...")
    base = render(512)

    sizes = [16, 24, 32, 48, 64, 128, 256]
    pngs  = []
    for s in sizes:
        buf = io.BytesIO()
        base.resize((s, s), Image.LANCZOS).save(buf, format="PNG")
        pngs.append(buf.getvalue())
        print(f"  {s}×{s} OK")

    # Montar ICO manualmente (Pillow tem bug no multi-size)
    n          = len(sizes)
    dir_size   = n * 16
    data_offset = 6 + dir_size

    header    = struct.pack("<HHH", 0, 1, n)
    directory = b""
    imagedata = b""
    offset    = data_offset

    for s, png in zip(sizes, pngs):
        w = s if s < 256 else 0
        h = s if s < 256 else 0
        directory += struct.pack("<BBBBHHII",
            w, h, 0, 0, 1, 32, len(png), offset)
        imagedata += png
        offset += len(png)

    ico_data = header + directory + imagedata
    Path(caminho).write_bytes(ico_data)
    print(f"\n✔ Ícone salvo: {Path(caminho).resolve()}")
    print(f"  {len(ico_data)//1024} KB | {n} tamanhos: {sizes}")

    # Preview PNG
    preview = Path(caminho).parent / (Path(caminho).stem + "_preview.png")
    base.save(str(preview))
    print(f"✔ Preview salvo: {preview.resolve()}")


if __name__ == "__main__":
    salvar_ico("nfse.ico")
