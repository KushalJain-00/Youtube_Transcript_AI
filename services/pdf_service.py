import io
from datetime import datetime

def generate_pdf(sections, video_info, transcript_text, word_count):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, HRFlowable
    from reportlab.lib.units import inch
    from reportlab.lib import colors

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.8*inch, rightMargin=0.8*inch,
                            topMargin=0.8*inch, bottomMargin=0.8*inch)
    styles = getSampleStyleSheet()

    def S(name, **kw):
        return ParagraphStyle(name, parent=styles["Normal"], **kw)

    title_s = S("T", fontSize=22, textColor=colors.HexColor("#0f172a"), spaceAfter=6, alignment=1, fontName="Helvetica-Bold")
    sub_s = S("Sub", fontSize=10, textColor=colors.HexColor("#64748b"), spaceAfter=4, alignment=1)
    head_s = S("H", fontSize=13, textColor=colors.HexColor("#1e40af"), spaceBefore=16, spaceAfter=6, fontName="Helvetica-Bold")
    body_s = S("B", fontSize=10, textColor=colors.HexColor("#1e293b"), leading=15, spaceAfter=4)
    bullet_s = S("Bl", fontSize=10, textColor=colors.HexColor("#374151"), leading=14, leftIndent=14, spaceAfter=3)
    trans_s = S("Tr", fontSize=9, textColor=colors.HexColor("#6b7280"), leading=13, spaceAfter=6)

    def safe(t):
        return (t or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

    story = []
    story.append(Paragraph("AI YouTube Learner", title_s))
    story.append(Paragraph("Transcript & AI Summary Report", sub_s))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=12))

    if video_info:
        story.append(Paragraph(safe(video_info.get("title","")), S("VT", fontSize=14, textColor=colors.HexColor("#0f172a"), alignment=1, spaceAfter=4, fontName="Helvetica-Bold")))
        story.append(Paragraph(f"Channel: {safe(video_info.get('channel',''))}", sub_s))
        url = video_info.get("url","")
        if url:
            story.append(Paragraph(f'<a href="{url}" color="#1d4ed8">{url}</a>', sub_s))
    story.append(Paragraph(f"Words: {word_count:,} | Generated: {datetime.now().strftime('%d %b %Y %H:%M')}", sub_s))
    story.append(Spacer(1, 0.2*inch))

    if sections.get("summary"):
        story.append(Paragraph("Summary", head_s))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#bfdbfe"), spaceAfter=8))
        story.append(Paragraph(safe(sections["summary"]), body_s))

    if sections.get("takeaways"):
        story.append(Paragraph("Key Takeaways", head_s))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#bfdbfe"), spaceAfter=8))
        for i, t in enumerate(sections["takeaways"][:5], 1):
            story.append(Paragraph(f"{i}. {safe(t)}", bullet_s))

    if sections.get("study_notes"):
        story.append(Paragraph("Study Notes", head_s))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#bfdbfe"), spaceAfter=8))
        for n in sections["study_notes"]:
            story.append(Paragraph(f"• {safe(n)}", bullet_s))

    story.append(PageBreak())
    story.append(Paragraph("Full Transcript", head_s))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#bfdbfe"), spaceAfter=8))
    for line in (transcript_text or "").split("\\n"):
        if line.strip():
            story.append(Paragraph(safe(line), trans_s))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
