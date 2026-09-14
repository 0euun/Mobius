# 무결성 매니페스트와 함께 제공하는 증거 PDF/ZIP 생성기

from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas

from .analysis import build_evidence_manifest
from .schemas import EventResponse


def build_evidence_zip(events: list[EventResponse]) -> bytes:
    manifest = build_evidence_manifest(events)
    pdf_buffer = BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    pdf = Canvas(pdf_buffer, pagesize=A4, invariant=1)
    _, height = A4
    y = height - 52
    pdf.setFont("HYSMyeongJo-Medium", 16)
    pdf.drawString(48, y, "Mobius 증거 패키지")
    y -= 28
    pdf.setFont("HYSMyeongJo-Medium", 9)
    pdf.drawString(48, y, f"대상: {manifest.target_id} / 패키지 SHA-256: {manifest.package_sha256}")
    y -= 18
    pdf.drawString(48, y, "이 문서는 수집 시각과 SHA-256으로 무결성 검증을 지원합니다.")
    y -= 14
    pdf.drawString(48, y, "법적 증거능력은 사건·관할·수집 방식에 따라 별도 판단이 필요합니다.")
    y -= 30
    for index, event in enumerate(events, start=1):
        if y < 90:
            pdf.showPage()
            pdf.setFont("HYSMyeongJo-Medium", 9)
            y = height - 52
        digest = manifest.items[index - 1].sha256
        pdf.drawString(48, y, f"{index}. [{event.occurred_at.isoformat()}] {event.platform} / {event.event_id}")
        y -= 14
        pdf.drawString(60, y, event.text[:90])
        y -= 14
        pdf.drawString(60, y, f"SHA-256: {digest}")
        y -= 22
    pdf.save()

    package = BytesIO()
    with ZipFile(package, "w", ZIP_DEFLATED) as archive:
        for name, content in (
            ("evidence-report.pdf", pdf_buffer.getvalue()),
            ("integrity-manifest.json", json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2).encode()),
        ):
            item = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            item.compress_type = ZIP_DEFLATED
            archive.writestr(item, content)
    return package.getvalue()
