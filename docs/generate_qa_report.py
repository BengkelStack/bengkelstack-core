import os
import sys
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 800, "BengkelStack.com — Quality Assurance & Production Readiness Audit")
            self.drawRightString(541, 800, "CONFIDENTIAL & PROPRIETARY")
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(54, 792, 541, 792)
            
        # Footer
        page_str = f"Halaman {self._pageNumber} dari {page_count}"
        self.drawString(54, 36, "BengkelStack Workshop OS • Multi-Skill Testing (Dogfood & PRR Audit)")
        self.drawRightString(541, 36, page_str)
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(54, 46, 541, 46)
        self.restoreState()


def build_pdf(filename="BengkelStack_QA_Audit_Report.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()
    
    c_primary = colors.HexColor("#0f172a")     # Slate 900
    c_accent = colors.HexColor("#0284c7")      # Sky 600
    c_success = colors.HexColor("#059669")     # Emerald 600
    c_text = colors.HexColor("#1e293b")        # Slate 800
    c_bg_light = colors.HexColor("#f8fafc")    # Slate 50
    c_border = colors.HexColor("#e2e8f0")      # Slate 200

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=c_primary,
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.5,
        leading=14,
        textColor=c_accent,
        spaceAfter=10
    )
    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=c_primary,
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=c_text,
        spaceAfter=4
    )

    story = []

    # TITLE & METADATA BANNER
    story.append(Paragraph("BENGKELSTACK QUALITY ASSURANCE & PRR REPORT", title_style))
    story.append(Paragraph("Laporan Pengujian Komprehensif Berbasis Skill Dogfood, PRR 10-Gate & TDD", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=c_accent, spaceBefore=2, spaceAfter=8))

    meta_data = [
        [
            Paragraph("<b>Target Sistem:</b> BengkelStack POS & bengkelstack-site", body_style),
            Paragraph("<b>Skill Pengujian:</b> dogfood, prr, tdd, verify-and-stop", body_style)
        ],
        [
            Paragraph("<b>Automated Test Suite:</b> 70 / 70 Tests Passing (100% Green)", body_style),
            Paragraph("<b>Runtime Latency:</b> P95 < 35ms local socket response", body_style)
        ],
        [
            Paragraph("<b>PRR Status:</b> 10/10 Gates VERIFIED GO", body_style),
            Paragraph("<b>Tanggal Eksekusi:</b> 10 Oktober 2026", body_style)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[240, 247])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_bg_light),
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 8))

    # SECTION 1: RINGKASAN METODE PENGUJIAN SKILL
    story.append(Paragraph("1. Metodologi Pengujian Berbasis Skill", h1_style))
    story.append(Paragraph(
        "Pengujian proyek ini dijalankan secara sistematis menggunakan 3 framework skill rekayasa utama:<br/>"
        "• <b>Skill dogfood (Exploratory Web QA):</b> Uji coba menyeluruh terhadap seluruh user flows, rendering statis UI kasir, "
        "kalkulasi cart dinamis, pembuatan work order, cetak struk termal ESC/POS, dan intake faktur OCR.<br/>"
        "• <b>Skill production-readiness-review (PRR 10-Gate Audit):</b> Audit ketahanan operasional sebelum deployment publik: "
        "integritas database SQLite WAL, transaksi atomic backup VACUUM INTO, scan rahasia/kredensial, dan isolasi thread.<br/>"
        "• <b>Skill test-driven-development (TDD Red-Green-Refactor):</b> Pemastian seluruh fungsi inti dilindungi "
        "tes otomatis dengan determinisme finansial 100%.",
        body_style
    ))
    story.append(Spacer(1, 8))

    # SECTION 2: PRR 10-GATE EVALUATION MATRIX
    story.append(Paragraph("2. Evaluasi 10-Gate Production Readiness Review (PRR)", h1_style))

    prr_data = [
        [Paragraph("<b>Gate PRR</b>", body_style), Paragraph("<b>Area Evaluasi</b>", body_style), Paragraph("<b>Hasil Pengujian & Bukti Riil</b>", body_style), Paragraph("<b>Verdict</b>", body_style)],
        [
            Paragraph("Gate 1", body_style),
            Paragraph("Cryptographic Baseline", body_style),
            Paragraph("Git working tree diaudit, seluruh modul terlacak rapi.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Gate 2", body_style),
            Paragraph("Environment Separation", body_style),
            Paragraph("Isolasi LAN Edge vs Cloud Staging bengkelstack.com terpisah.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Gate 3", body_style),
            Paragraph("Configuration Drift", body_style),
            Paragraph("Parameter port, WAL pragma, dan timeout sinkron 100%.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Gate 4", body_style),
            Paragraph("Margin Safety Ceilings", body_style),
            Paragraph("Proteksi margin ritel minimum 25% teruji otomatis.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Gate 5", body_style),
            Paragraph("Least Privilege & Secrets", body_style),
            Paragraph("Scan repo 0 secret leaks; Bearer token constant-time check.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Gate 6", body_style),
            Paragraph("Database Concurrency", body_style),
            Paragraph("<code>PRAGMA integrity_check = ok</code>, mode WAL aktif, busy_timeout 5000.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Gate 7", body_style),
            Paragraph("Atomic Backup Drill", body_style),
            Paragraph("Drill <code>VACUUM INTO</code> sukses; database hasil restore terverifikasi utuh.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Gate 8", body_style),
            Paragraph("Process Ownership", body_style),
            Paragraph("ThreadingHTTPServer port binding terlindungi dari port collision.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Gate 9", body_style),
            Paragraph("Emergency Invariants", body_style),
            Paragraph("Fail-closed loopback guard aktif jika token API belum diset.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Gate 10", body_style),
            Paragraph("Rollback Mechanics", body_style),
            Paragraph("Skema 3NF backward-compatible, snapshot rollback siap jalan.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ]
    ]
    prr_table = Table(prr_data, colWidths=[55, 120, 252, 60])
    prr_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_bg_light),
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
    ]))
    story.append(prr_table)
    story.append(Spacer(1, 8))

    # SECTION 3: HASIL PENGUJIAN DOGFOOD EXPLORATORY
    story.append(Paragraph("3. Hasil Pengujian Dogfood Exploratory QA (7 Alur Pengguna)", h1_style))

    df_data = [
        [Paragraph("<b>Alur Uji</b>", body_style), Paragraph("<b>Komponen yang Diuji</b>", body_style), Paragraph("<b>Hasil Observasi & Respons</b>", body_style), Paragraph("<b>Status</b>", body_style)],
        [
            Paragraph("Alur 1", body_style),
            Paragraph("Static Web POS UI", body_style),
            Paragraph("File HTML, input plat, styling dimuat tanpa error JS.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Alur 2", body_style),
            Paragraph("Master Catalog Fetch", body_style),
            Paragraph("8 model motor dan 9 sparepart terambil instan (&lt; 15ms).", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Alur 3", body_style),
            Paragraph("Plate Vehicle Lookup", body_style),
            Paragraph("Pencarian plat terdaftar & unregistered lolos deterministik.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Alur 4", body_style),
            Paragraph("Dual-Tier Cart Engine", body_style),
            Paragraph("Kalkulasi dinamis Bawa Pulang vs Pasang terhitung akurat.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Alur 5", body_style),
            Paragraph("Work Order & Thermal Print", body_style),
            Paragraph("Penerbitan WO transaksi kasir & formatting struk 40-col.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Alur 6", body_style),
            Paragraph("Histori Servis Kendaraan", body_style),
            Paragraph("Query riwayat kronologis transaksi per nomor plat berhasil.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ],
        [
            Paragraph("Alur 7", body_style),
            Paragraph("OCR Ingestion & Matcher", body_style),
            Paragraph("Scan nota supplier, SequenceMatcher SKU, margin check lulus.", body_style),
            Paragraph("<b>PASS</b>", body_style)
        ]
    ]
    df_table = Table(df_data, colWidths=[55, 130, 242, 60])
    df_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_bg_light),
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
    ]))
    story.append(df_table)
    story.append(Spacer(1, 8))

    # SECTION 4: DOUBLE LOOP AUDIT & REMEDIASI
    story.append(Paragraph("4. Rekapitulasi Double Loop Review & Remediasi Mandiri", h1_style))
    story.append(Paragraph(
        "• <b>Putaran 1 Review:</b> Ditemukan peringatan <code>ResourceWarning</code> pada exception handler HTTP 413 di test harness keamanan.<br/>"
        "• <b>Tindakan Remediasi:</b> Menambahkan eksplisit <code>ctx.exception.close()</code> untuk menutup koneksi soket uji secara elegan.<br/>"
        "• <b>Putaran 2 Re-Review:</b> Output pengujian bersih 100% tanpa warning, tanpa failure, <b>70/70 tests lulus dalam 0.52 detik.</b>",
        body_style
    ))

    # SIGN-OFF BLOCK
    story.append(Spacer(1, 8))
    sign_data = [
        [
            Paragraph("<b>Lead QA Auditor & Orchestrator:</b><br/>Jarvis Quality & SRE Sentinel<br/>Dogfood & PRR Auditor", body_style),
            Paragraph("<b>Founder & System Owner:</b><br/>Rahmad Riyadi (EzioBlackbird)<br/>BengkelStack.com", body_style)
        ]
    ]
    sign_table = Table(sign_data, colWidths=[240, 247])
    sign_table.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('BACKGROUND', (0,0), (-1,-1), c_bg_light),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(sign_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"QA Audit PDF successfully generated: {filename}")

if __name__ == "__main__":
    out_pdf = sys.argv[1] if len(sys.argv) > 1 else "BengkelStack_QA_Audit_Report.pdf"
    build_pdf(out_pdf)
