# -*- coding: utf-8 -*-
"""Gera o PPTX de 5 slides e o vídeo narrado da demonstração."""
import os
import subprocess
import textwrap
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent
CAP = ROOT / "capturas"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 1280, 720

BRAND = RGBColor(0xC8, 0x10, 0x2E)
GOLD = RGBColor(0xE8, 0xB0, 0x4B)
CREAM = RGBColor(0xF7, 0xED, 0xE4)
INK = RGBColor(0x14, 0x0D, 0x0B)


def font(size, bold=False):
    name = "seguibl.ttf" if bold else "segoeui.ttf"
    path = Path(os.environ["WINDIR"]) / "Fonts" / name
    return ImageFont.truetype(str(path), size)


def slide_deck():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    slides = [
        ("O buffet esvazia sem a cozinha ver.", [
            "A panela acaba no meio do serviço.",
            "A sobra do fim do dia não é medida por prato.",
            "Mesa livre, ocupada e paga não aparecem juntas.",
        ]),
        ("Cinco passos até o sistema.", [
            "Servidor Python e banco SQLite.",
            "Peso da balança vira alimento disponível.",
            "Painel da cozinha, de 10 em 10 minutos.",
            "Relatório de consumo por balança.",
            "QR da mesa, caixa e alerta sonoro.",
        ]),
        ("Uma API, três telas.", [
            "Balança e QR entram pela mesma API.",
            "O SQLite guarda panela, pesagem e mesa.",
            "Cozinha, relatório, salão e caixa leem o mesmo dado.",
            "Arquivos centrais: server.py, web/ e bovinus.db.",
        ]),
        ("Cozinha, salão e caixa no mesmo fluxo.", [
            "A balança avisa a cozinha e alimenta o relatório.",
            "O QR do garçom marca a mesa como ocupada.",
            "O pagamento no caixa libera a mesa.",
            "O salão apita para a equipe limpar a mesa.",
        ]),
        ("O que a banca vê na prática.", [
            "Panela baixa vira alerta de repor agora.",
            "O dia fecha com quilos, porções e sobra.",
            "A mesa ocupa no segundo em que o QR é lido.",
            "O pagamento no caixa apita no salão.",
        ]),
    ]
    kickers = [
        "PROBLEMA",
        "DESENVOLVIMENTO",
        "ESTRUTURA",
        "INTEGRAÇÃO",
        "APRESENTAÇÃO FINAL",
    ]
    for i, ((title, bullets), kicker) in enumerate(zip(slides, kickers), 1):
        s = prs.slides.add_slide(blank)
        bg = s.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = INK
        bg.line.fill.background()
        bar = s.shapes.add_shape(1, 0, 0, Inches(0.18), prs.slide_height)
        bar.fill.solid()
        bar.fill.fore_color.rgb = BRAND
        bar.line.fill.background()
        box = s.shapes.add_textbox(Inches(0.7), Inches(0.45), Inches(11.5), Inches(0.4))
        p = box.text_frame.paragraphs[0]
        p.text = f"BOVINU'S GRILL  ·  {kicker}  ·  {i} / 5"
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = GOLD
        tbox = s.shapes.add_textbox(Inches(0.7), Inches(1.05), Inches(11.8), Inches(1.6))
        tp = tbox.text_frame.paragraphs[0]
        tp.text = title
        tp.font.size = Pt(36)
        tp.font.bold = True
        tp.font.color.rgb = CREAM
        body = s.shapes.add_textbox(Inches(0.9), Inches(3.0), Inches(11.5), Inches(3.6))
        tf = body.text_frame
        tf.word_wrap = True
        for n, item in enumerate(bullets):
            para = tf.paragraphs[0] if n == 0 else tf.add_paragraph()
            para.text = item
            para.level = 0
            para.font.size = Pt(24)
            para.font.color.rgb = CREAM
            para.space_after = Pt(12)
            para.alignment = PP_ALIGN.LEFT
    out = ROOT / "BovinuScale-apresentacao.pptx"
    prs.save(out)
    print("pptx", out)


def speak(text, wav):
    ps = f'''
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice("Microsoft Maria Desktop")
$s.Rate = 2
$s.SetOutputToWaveFile("{wav}")
$s.Speak(@"
{text}
"@)
$s.Dispose()
'''
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


def frame(title, subtitle, image_name=None):
    img = Image.new("RGB", (W, H), "#140d0b")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 10, H), fill="#C8102E")
    d.text((36, 24), "BOVINU'S GRILL", font=font(18, True), fill="#C8102E")
    d.text((36, 52), title, font=font(32, True), fill="#f7ede4")
    if image_name:
        shot = Image.open(CAP / image_name).convert("RGB")
        shot.thumbnail((1180, 500))
        x = (W - shot.width) // 2
        y = 110
        img.paste(shot, (x, y))
        d.rectangle((0, H - 64, W, H), fill="#2b1b17")
        d.text((36, H - 44), subtitle, font=font(22), fill="#E8B04B")
    else:
        y = 160
        for line in textwrap.wrap(subtitle, 42):
            d.text((36, y), line, font=font(28), fill="#f7ede4")
            y += 42
    return img


SCENES = [
    ("BovinuScale", "Solução prática para a cozinha e para o salão do Grupo Bovinu's.", None,
     "BovinuScale, do Grupo Bovinu's Grill. Uma solução para a cozinha e para o salão."),
    ("O problema", "A cozinha não vê a panela esvaziar. O salão não vê qual mesa já foi paga.", None,
     "O problema. A cozinha não vê a panela esvaziar. O prato acaba no serviço, ou sobra no fim do dia. No salão, a equipe não vê qual mesa está livre, ocupada ou já paga."),
    ("Cozinha", "Alerta de reposição quando a panela baixa.", "01-cozinha.png",
     "Na cozinha, cada panela tem uma balança. A cada dez minutos o painel atualiza o peso e avisa a reposição. O pão de alho chegou a nove por cento."),
    ("Relatório do dia", "Consumo por balança, sem contar a reposição.", "02-relatorio.png",
     "No fim do dia, o relatório mostra o consumo de cada balança: quilos, porções, reposições, sobra e horário de pico. Reposição não conta como consumo."),
    ("Salão", "24 mesas numeradas, de 2 a 10 cadeiras.", "03-atendimento.png",
     "No salão são vinte e quatro mesas numeradas, com duas a dez cadeiras. O painel mostra livre, ocupada e liberada. Cada mesa tem o seu QR Code."),
    ("QR do garçom", "A leitura marca a mesa como ocupada.", "05-checkin.png",
     "Quando o cliente chega, o garçom escaneia o QR. A mesa vinte e um passa na hora para ocupada."),
    ("Caixa", "O pagamento libera a mesa e o salão apita.", "04-caixa.png",
     "Quando a conta é paga no caixa, a mesa fica liberada e o painel do salão apita, para a equipe limpar e disponibilizar a mesa."),
    ("Um sistema só", "Cozinha, salão e caixa no mesmo banco.", None,
     "Cozinha, salão e caixa no mesmo banco. BovinuScale está pronto para a demonstração."),
]


def video():
    tmp = ROOT / "_tmp_video"
    tmp.mkdir(exist_ok=True)
    parts = []
    for i, (title, subtitle, shot, narration) in enumerate(SCENES):
        png = tmp / f"f{i}.png"
        wav = tmp / f"a{i}.wav"
        mp4 = tmp / f"p{i}.mp4"
        frame(title, subtitle, shot).save(png)
        speak(narration, wav)
        subprocess.run([
            FFMPEG, "-y", "-loop", "1", "-i", str(png), "-i", str(wav),
            "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
            str(mp4),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        parts.append(mp4)
        print("cena", i, title)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    out = ROOT / "bovinascale-demo.mp4"
    subprocess.run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-c", "copy", str(out),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    probe = subprocess.run([
        FFMPEG, "-i", str(out),
    ], capture_output=True, text=True)
    err = probe.stderr
    for line in err.splitlines():
        if "Duration" in line:
            print(line.strip())
            break
    web = ROOT.parent / "web" / "bovinascale-demo.mp4"
    web.write_bytes(out.read_bytes())
    print("video", out, out.stat().st_size)


if __name__ == "__main__":
    slide_deck()
    video()
