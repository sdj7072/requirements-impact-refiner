from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont, ImageFilter


OUT = Path(__file__).resolve().parent
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
SCALE = 2
W, H = 1600, 1000

NAVY = (3, 16, 40)
NAVY_2 = (7, 28, 61)
SURFACE = (11, 34, 70)
SURFACE_2 = (15, 43, 84)
LINE = (40, 73, 118)
WHITE = (246, 249, 255)
MUTED = (158, 180, 210)
BLUE = (55, 132, 255)
BLUE_SOFT = (28, 74, 140)
GREEN = (75, 210, 160)
GREEN_SOFT = (22, 79, 67)
CORAL = (255, 122, 99)
CORAL_SOFT = (92, 47, 53)


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    index = {"regular": 0, "medium": 2, "semibold": 4, "bold": 6, "heavy": 16}[weight]
    return ImageFont.truetype(FONT_PATH, size, index=index)


def canvas() -> Image.Image:
    image = Image.new("RGB", (W, H), NAVY)
    px = image.load()
    for y in range(H):
        for x in range(W):
            rx = (x - 1260) / 780
            ry = (y - 250) / 620
            glow = max(0.0, 1.0 - (rx * rx + ry * ry))
            depth = y / H
            px[x, y] = (
                int(NAVY[0] + glow * 3 + depth * 1),
                int(NAVY[1] + glow * 19 + depth * 7),
                int(NAVY[2] + glow * 38 + depth * 10),
            )
    return image


def shadowed_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill=SURFACE) -> None:
    draw.rounded_rectangle(box, radius=34, fill=fill, outline=LINE, width=2)


def header(draw: ImageDraw.ImageDraw, eyebrow: str, title: str, subtitle: str | None = None) -> None:
    draw.text((84, 65), eyebrow, font=font(28, "semibold"), fill=BLUE)
    draw.text((84, 112), title, font=font(58, "heavy"), fill=WHITE)
    if subtitle:
        draw.text((86, 190), subtitle, font=font(29, "regular"), fill=MUTED)


def bullet(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, color=BLUE, text_color=MUTED) -> None:
    draw.ellipse((x, y + 11, x + 13, y + 24), fill=color)
    draw.text((x + 31, y), text, font=font(28, "medium"), fill=text_color)


def badge(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, fill, ink) -> tuple[int, int, int, int]:
    f = font(22, "semibold")
    bbox = draw.textbbox((0, 0), text, font=f)
    width = bbox[2] - bbox[0] + 34
    height = 48
    box = (x, y, x + width, y + height)
    draw.rounded_rectangle(box, radius=24, fill=fill)
    draw.text((x + 17, y + 9), text, font=f, fill=ink)
    return box


def save(image: Image.Image, filename: str) -> None:
    final = image.resize((800, 500), Image.Resampling.LANCZOS)
    final.save(OUT / filename, "PNG", optimize=True)


def render_as_is_to_be() -> None:
    image = canvas()
    draw = ImageDraw.Draw(image)
    header(draw, "왜 필요한가", "빨리 고치기 전에, 어디까지 바뀌는지부터", "요청한 부분만 고치던 방식에서, 영향을 먼저 확인하는 방식으로")

    left = (84, 278, 724, 875)
    right = (876, 278, 1516, 875)
    shadowed_panel(draw, left)
    shadowed_panel(draw, right)
    draw.rounded_rectangle((84, 278, 724, 288), radius=5, fill=CORAL)
    draw.rounded_rectangle((876, 278, 1516, 288), radius=5, fill=GREEN)

    badge(draw, 124, 320, "AS-IS", CORAL_SOFT, CORAL)
    draw.text((124, 398), "요청한 코드만 수정", font=font(44, "bold"), fill=WHITE)
    bullet(draw, 128, 492, "근거와 추론이 한 문장에 섞임", CORAL)
    bullet(draw, 128, 558, "모바일·캐시·권한 영향 누락 가능", CORAL)
    bullet(draw, 128, 624, "사용자 선택 전 정책 확정 위험", CORAL)
    draw.rounded_rectangle((124, 730, 680, 820), radius=20, fill=(19, 37, 66))
    draw.text((151, 757), "‘바뀐 곳’만 확인", font=font(31, "semibold"), fill=CORAL)

    badge(draw, 916, 320, "TO-BE", GREEN_SOFT, GREEN)
    draw.text((916, 398), "변경 전에 영향부터 확인", font=font(44, "bold"), fill=WHITE)
    bullet(draw, 920, 492, "verified · inferred · unknown 분리", GREEN)
    bullet(draw, 920, 558, "영향·결정·회귀 기준을 연결", GREEN)
    bullet(draw, 920, 624, "검토 후 기존 계획 흐름에 전달", GREEN)
    draw.rounded_rectangle((916, 730, 1472, 820), radius=20, fill=(16, 52, 63))
    draw.text((943, 757), "‘건드릴 수 있는 곳’까지 확인", font=font(31, "semibold"), fill=GREEN)

    draw.line((754, 574, 846, 574), fill=BLUE, width=6)
    draw.polygon([(846, 574), (817, 553), (817, 595)], fill=BLUE)
    save(image, "rir-as-is-to-be-800x500.png")


def render_impact_path() -> None:
    image = canvas()
    draw = ImageDraw.Draw(image)
    header(draw, "대표 예시", "필드 하나를 바꾸면, 어디까지 확인해야 할까?", "displayName → name 변경의 대표 영향 경로")

    stages = [
        ("요구사항", "필드 이름 변경", BLUE),
        ("API 응답", "공개 계약", BLUE),
        ("iOS DTO", "기존 디코더", CORAL),
        ("캐시 JSON", "저장된 값", CORAL),
        ("호환성 약속", "한 버전 유지", GREEN),
    ]
    xs = [84, 388, 692, 996, 1300]
    cy = 512
    for index, ((name, desc, color), x) in enumerate(zip(stages, xs), start=1):
        if index < len(stages):
            draw.line((x + 226, cy, xs[index] - 20, cy), fill=LINE, width=5)
            draw.polygon([(xs[index] - 20, cy), (xs[index] - 42, cy - 16), (xs[index] - 42, cy + 16)], fill=LINE)
        box = (x, 385, x + 236, 650)
        shadowed_panel(draw, box, SURFACE_2)
        draw.ellipse((x + 78, 418, x + 158, 498), fill=color)
        draw.text((x + 106, 433), str(index), font=font(35, "bold"), fill=NAVY)
        name_box = draw.textbbox((0, 0), name, font=font(32, "bold"))
        draw.text((x + (236 - (name_box[2] - name_box[0])) / 2, 530), name, font=font(32, "bold"), fill=WHITE)
        desc_box = draw.textbbox((0, 0), desc, font=font(25, "regular"))
        draw.text((x + (236 - (desc_box[2] - desc_box[0])) / 2, 580), desc, font=font(25, "regular"), fill=MUTED)

    draw.rounded_rectangle((178, 742, 1422, 863), radius=28, fill=(10, 37, 75), outline=LINE, width=2)
    draw.text((217, 772), "결정 선택지", font=font(26, "semibold"), fill=BLUE)
    choices = ["즉시 변경", "두 필드 병행", "명시적 마이그레이션"]
    x = 414
    for choice in choices:
        box = badge(draw, x, 776, choice, BLUE_SOFT, WHITE)
        x = box[2] + 28
    save(image, "rir-impact-path-800x500.png")


def render_compact_delivery() -> None:
    image = canvas()
    draw = ImageDraw.Draw(image)
    header(draw, "결과 요약", "짧게 읽고, 근거까지 따라가는 영향 보고서", "대화에는 핵심만 보여주고 전체 상태는 검증 가능한 보고서로 보존")

    panel = (84, 274, 1516, 884)
    shadowed_panel(draw, panel, (246, 249, 255))
    draw.rounded_rectangle((84, 274, 1516, 338), radius=30, fill=(226, 237, 251))
    draw.rectangle((84, 310, 1516, 338), fill=(226, 237, 251))
    draw.ellipse((118, 297, 136, 315), fill=(255, 107, 95))
    draw.ellipse((148, 297, 166, 315), fill=(255, 188, 78))
    draw.ellipse((178, 297, 196, 315), fill=(73, 205, 133))
    draw.text((226, 291), "Change Impact Summary", font=font(27, "bold"), fill=(22, 48, 81))

    columns = [108, 304, 700, 938, 1182]
    labels = ["Impact", "Possible issue", "Evidence", "Status", "Prevention"]
    for x, label in zip(columns, labels):
        draw.text((x, 373), label, font=font(24, "semibold"), fill=(68, 91, 122))
    draw.line((108, 420, 1490, 420), fill=(201, 214, 230), width=2)

    rows = [
        ("IMP-001", "모바일 디코딩 실패", "verified", "refining", "기존 DTO 회귀 테스트"),
        ("IMP-002", "저장된 캐시 호환성", "verified", "detected", "캐시 fixture 확인"),
        ("IMP-003", "외부 소비자 미확인", "unknown", "blocked", "소유자와 범위 확인"),
    ]
    y = 454
    for i, row in enumerate(rows):
        if i:
            draw.line((108, y - 20, 1490, y - 20), fill=(222, 230, 240), width=2)
        draw.text((columns[0], y), row[0], font=font(25, "bold"), fill=(36, 101, 210))
        draw.text((columns[1], y), row[1], font=font(25, "medium"), fill=(24, 44, 70))
        evidence_color = (35, 141, 102) if row[2] == "verified" else (198, 105, 55)
        draw.text((columns[2], y), row[2], font=font(24, "semibold"), fill=evidence_color)
        draw.text((columns[3], y), row[3], font=font(24, "medium"), fill=(72, 92, 118))
        draw.text((columns[4], y), row[4], font=font(23, "regular"), fill=(52, 73, 100))
        y += 104

    draw.rounded_rectangle((108, 772, 1490, 846), radius=18, fill=(229, 240, 255))
    draw.text((136, 792), "Decision needed", font=font(23, "bold"), fill=(34, 99, 201))
    draw.text((376, 792), "즉시 변경  /  두 필드 병행  /  명시적 마이그레이션", font=font(24, "medium"), fill=(35, 57, 84))
    save(image, "rir-compact-delivery-800x500.png")


def bar(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, ratio: float, color, label: str, value: str) -> None:
    draw.text((x, y), label, font=font(26, "medium"), fill=MUTED)
    draw.rounded_rectangle((x, y + 48, x + width, y + 82), radius=17, fill=(19, 47, 86))
    draw.rounded_rectangle((x, y + 48, x + int(width * ratio), y + 82), radius=17, fill=color)
    draw.text((x + width + 28, y + 40), value, font=font(32, "bold"), fill=WHITE)


def render_benchmark() -> None:
    image = canvas()
    draw = ImageDraw.Draw(image)
    header(draw, "검증 결과", "실사용 수치 대신, 재현 가능한 전후 비교", "같은 유형의 요청을 반복 실행하고 원문과 채점 기준을 저장소에 보존")

    shadowed_panel(draw, (84, 286, 998, 844))
    draw.text((128, 324), "근거 연결 탐지", font=font(37, "bold"), fill=WHITE)
    bar(draw, 128, 402, 620, 8 / 15, CORAL, "스킬 미적용", "8/15")
    bar(draw, 128, 548, 620, 1.0, BLUE, "RIR 적용", "15/15")
    draw.text((128, 710), "53.3% → 100%", font=font(46, "heavy"), fill=BLUE)
    draw.text((500, 724), "+46.7%p", font=font(29, "semibold"), fill=GREEN)

    shadowed_panel(draw, (1040, 286, 1516, 540))
    draw.text((1082, 328), "계획 흐름 침범", font=font(31, "bold"), fill=WHITE)
    draw.text((1082, 392), "3/5", font=font(58, "heavy"), fill=CORAL)
    draw.text((1214, 405), "→", font=font(40, "bold"), fill=MUTED)
    draw.text((1304, 392), "0/5", font=font(58, "heavy"), fill=GREEN)
    draw.text((1082, 470), "통제 평가에서 관찰된 위반", font=font(23, "regular"), fill=MUTED)

    shadowed_panel(draw, (1040, 570, 1516, 844))
    draw.text((1082, 612), "워크플로 연동", font=font(31, "bold"), fill=WHITE)
    draw.text((1082, 674), "25/30", font=font(54, "heavy"), fill=MUTED)
    draw.text((1261, 687), "→", font=font(38, "bold"), fill=MUTED)
    draw.text((1341, 674), "30/30", font=font(54, "heavy"), fill=BLUE)
    draw.text((1082, 760), "generic 진입 경계 5건 보완", font=font(23, "regular"), fill=MUTED)

    draw.text((86, 910), "※ 통제 평가 결과이며 실제 업무 시간·비용 절감 수치는 아직 측정하지 않았습니다.", font=font(24, "regular"), fill=MUTED)
    save(image, "rir-benchmark-800x500.png")


def contact_sheet(files: Iterable[str]) -> None:
    images = [Image.open(OUT / f).convert("RGB") for f in files]
    sheet = Image.new("RGB", (1620, 1020), (8, 18, 38))
    positions = [(0, 0), (820, 0), (0, 520), (820, 520)]
    for image, position in zip(images, positions):
        sheet.paste(image, position)
    sheet.save(OUT / "rir-submission-images-contact-sheet.png", "PNG", optimize=True)


if __name__ == "__main__":
    render_as_is_to_be()
    render_impact_path()
    render_compact_delivery()
    render_benchmark()
    contact_sheet(
        [
            "rir-as-is-to-be-800x500.png",
            "rir-impact-path-800x500.png",
            "rir-compact-delivery-800x500.png",
            "rir-benchmark-800x500.png",
        ]
    )
