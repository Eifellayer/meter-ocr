from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
                                PageBreak, Table, TableStyle, Flowable, Image, KeepTogether)
from reportlab.lib.utils import ImageReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'Bedienungsanleitung-AI-Meter-Reader.pdf'
LOGO = ROOT / 'docs' / 'images' / 'project-logo-guide.jpg'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
pdfmetrics.registerFont(TTFont('GuideSans', FONT))
pdfmetrics.registerFont(TTFont('GuideSans-Bold', BOLD))

PAGE_W, PAGE_H = A4
INK = colors.HexColor('#152a39')
MUTED = colors.HexColor('#526575')
GREEN = colors.HexColor('#167246')
GREEN_BG = colors.HexColor('#e8f5ed')
YELLOW = colors.HexColor('#8a6212')
YELLOW_BG = colors.HexColor('#fff5d9')
RED = colors.HexColor('#a3363e')
RED_BG = colors.HexColor('#fff0ef')
DARK = colors.HexColor('#111a22')
SURFACE = colors.HexColor('#1b252e')
EDGE = colors.HexColor('#3b4b57')
LIGHT = colors.HexColor('#e8f0f5')

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleCustom', fontName='GuideSans-Bold', fontSize=26, leading=31, textColor=INK, spaceAfter=7))
styles.add(ParagraphStyle(name='SubTitle', fontName='GuideSans', fontSize=12, leading=17, textColor=MUTED, spaceAfter=12))
styles.add(ParagraphStyle(name='H1Custom', fontName='GuideSans-Bold', fontSize=21, leading=26, textColor=INK, spaceBefore=0, spaceAfter=8))
styles.add(ParagraphStyle(name='H2Custom', fontName='GuideSans-Bold', fontSize=13, leading=17, textColor=INK, spaceBefore=8, spaceAfter=5))
styles.add(ParagraphStyle(name='BodyCustom', fontName='GuideSans', fontSize=9.1, leading=13.2, textColor=INK, spaceAfter=5))
styles.add(ParagraphStyle(name='SmallCustom', fontName='GuideSans', fontSize=7.8, leading=10.5, textColor=MUTED, spaceAfter=3))
styles.add(ParagraphStyle(name='WhiteCustom', fontName='GuideSans', fontSize=9, leading=13, textColor=LIGHT, spaceAfter=4))
styles.add(ParagraphStyle(name='WhiteBold', fontName='GuideSans-Bold', fontSize=10, leading=13, textColor=LIGHT, spaceAfter=4))
styles.add(ParagraphStyle(name='CardHead', fontName='GuideSans-Bold', fontSize=10, leading=13, textColor=INK, spaceAfter=3))
styles.add(ParagraphStyle(name='TinyWhite', fontName='GuideSans', fontSize=7.2, leading=9, textColor=LIGHT))
styles.add(ParagraphStyle(name='TinyWhiteBold', fontName='GuideSans-Bold', fontSize=7.2, leading=9, textColor=LIGHT))
styles.add(ParagraphStyle(name='CenterSmall', fontName='GuideSans', fontSize=8.4, leading=11, alignment=TA_CENTER, textColor=INK))


def p(text, style='BodyCustom'):
    return Paragraph(text, styles[style])

class AppStatusMock(Flowable):
    def __init__(self, width=170*mm):
        super().__init__(); self.width = width; self.height = 100*mm
    def draw(self):
        c = self.canv; w=self.width; h=self.height
        c.setFillColor(DARK); c.roundRect(0,0,w,h,4*mm,fill=1,stroke=0)
        c.setFillColor(SURFACE); c.roundRect(3*mm,3*mm,w-6*mm,h-6*mm,3*mm,fill=1,stroke=0)
        c.setFillColor(LIGHT); c.setFont('GuideSans-Bold',10); c.drawString(7*mm,h-11*mm,'Automatische Kontrolle')
        c.setFillColor(GREEN_BG); c.setStrokeColor(colors.HexColor('#65a986')); c.roundRect(7*mm,h-30*mm,w-14*mm,13*mm,2*mm,fill=1,stroke=1)
        c.setFillColor(GREEN); c.setFont('GuideSans-Bold',9); c.drawString(11*mm,h-22*mm,'✓  Zählerstand bestätigt')
        c.setFont('GuideSans',7.5); c.drawString(11*mm,h-27*mm,'Vergleich erfolgreich bei der gewählten Genauigkeit.')
        c.setFillColor(LIGHT); c.setFont('GuideSans-Bold',7.5); c.drawString(7*mm,h-39*mm,'Automatik pausieren')
        c.setFillColor(YELLOW_BG); c.roundRect(7*mm,h-48*mm,w-14*mm,6*mm,1.3*mm,fill=1,stroke=0)
        c.setFillColor(YELLOW); c.setFont('GuideSans',6.6); c.drawString(10*mm,h-44*mm,'ESP erreichbar. Kein neues Bild seit der letzten Prüfung; das Bild ist noch aktuell genug.')
        labels=['Erkannter Stand','Referenz','Bildzeit','Letzte Prüfung','Nächste Prüfung']
        vals=['01234.567','01234.5671','10:22','10:23','59 min']
        y=h-54*mm
        for label,val in zip(labels,vals):
            c.setFillColor(colors.HexColor('#b8c9d7')); c.setFont('GuideSans',7.2); c.drawString(8*mm,y,label)
            c.setFillColor(LIGHT); c.setFont('GuideSans-Bold',7.4); c.drawString(43*mm,y,val)
            y-=6.5*mm
        c.setFillColor(colors.HexColor('#8799a8')); c.setFont('GuideSans',7); c.drawString(8*mm,7*mm,'Letztes Testbild  ▾')

class WizardMock(Flowable):
    def __init__(self, width=170*mm):
        super().__init__(); self.width=width; self.height=81*mm
    def draw(self):
        c=self.canv; w=self.width; h=self.height
        c.setFillColor(DARK); c.roundRect(0,0,w,h,4*mm,fill=1,stroke=0)
        c.setFillColor(SURFACE); c.roundRect(3*mm,3*mm,w-6*mm,h-6*mm,3*mm,fill=1,stroke=0)
        c.setFillColor(LIGHT); c.setFont('GuideSans-Bold',10); c.drawString(8*mm,h-12*mm,'Einrichtung - Bildquelle wählen')
        c.setFillColor(colors.HexColor('#aebcc8')); c.setFont('GuideSans',7.5); c.drawString(8*mm,h-20*mm,'Wähle den Weg, der zu deiner Kamera passt.')
        opts=[('1','SLFork / AI on the Edge','ESP liefert Bild + Vergleichswert'),('2','Home-Assistant-Kamera','Kamera liefert Bild, Referenz optional'),('3','ESPHome / lokale Ablesung','AI Meter Reader liest das Bild')]
        y=h-31*mm
        for n,title,sub in opts:
            c.setStrokeColor(EDGE); c.setFillColor(colors.HexColor('#202e38')); c.roundRect(8*mm,y-12*mm,w-16*mm,14*mm,2*mm,fill=1,stroke=1)
            c.setFillColor(colors.HexColor('#2ca56a')); c.circle(13*mm,y-5*mm,3*mm,fill=1,stroke=0)
            c.setFillColor(colors.white); c.setFont('GuideSans-Bold',7.4); c.drawCentredString(13*mm,y-7.5*mm,n)
            c.setFillColor(LIGHT); c.setFont('GuideSans-Bold',7.4); c.drawString(19*mm,y-3*mm,title)
            c.setFillColor(colors.HexColor('#b2c2ce')); c.setFont('GuideSans',6.4); c.drawString(19*mm,y-8*mm,sub)
            y-=15.5*mm

class OCRMock(Flowable):
    def __init__(self, width=170*mm):
        super().__init__(); self.width=width; self.height=54*mm
    def draw(self):
        c=self.canv; w=self.width; h=self.height
        c.setFillColor(DARK); c.roundRect(0,0,w,h,3*mm,fill=1,stroke=0)
        c.setStrokeColor(colors.HexColor('#2ca56a')); c.setLineWidth(1.4)
        digits=list('01234567'); uncertain={5}; unclear={6}
        x=7*mm; boxw=(w-14*mm)/8
        for i,d in enumerate(digits):
            col=(colors.HexColor('#cb464b') if i in unclear else
                 colors.HexColor('#f1b836') if i in uncertain else colors.HexColor('#28a56a'))
            c.setStrokeColor(col); c.setLineWidth(1.4); c.rect(x+boxw*i,12*mm,boxw-1.5*mm,34*mm,fill=0,stroke=1)
            c.setFillColor(col); c.rect(x+boxw*i,39*mm,5*mm,7*mm,fill=1,stroke=0)
            c.setFillColor(colors.white); c.setFont('GuideSans-Bold',7); c.drawCentredString(x+boxw*i+2.5*mm,41*mm,str(i+1))
            c.setFillColor(colors.HexColor('#0c434a')); c.setFont('GuideSans-Bold',25); c.drawCentredString(x+boxw*i+(boxw-1.5*mm)/2,19*mm,d)
        c.setFillColor(colors.HexColor('#94a5b2')); c.setFont('GuideSans',6.7); c.drawString(7*mm,5*mm,'Grün = gelesen   Gelb = schwankte / zusammengesetzt   Rot = weiterhin unklar')

class ModeCards(Flowable):
    def __init__(self,width=170*mm): self.width=width; self.height=43*mm
    def draw(self):
        c=self.canv; w=self.width; gap=3*mm; cw=(w-2*gap)/3
        cards=[('SLFork / AI on the Edge','Dein ESP liefert das Bild und einen Vergleichswert.'),('Home-Assistant-Kamera','Bild aus HA; Referenzsensor ist optional.'),('ESPHome / lokal','Bild aus HA; AI Meter Reader liest den Stand.')]
        for i,(title,txt) in enumerate(cards):
            x=i*(cw+gap)
            c.setFillColor(colors.HexColor('#f2f6f8')); c.setStrokeColor(colors.HexColor('#d5e0e6')); c.roundRect(x,0,cw,self.height,2.5*mm,fill=1,stroke=1)
            c.setFillColor(GREEN); c.circle(x+7*mm,self.height-8*mm,3*mm,fill=1,stroke=0)
            c.setFillColor(colors.white); c.setFont('GuideSans-Bold',8); c.drawCentredString(x+7*mm,self.height-10.5*mm,str(i+1))
            pp=Paragraph(title,styles['CardHead']); pp.wrapOn(c,cw-16*mm,12*mm); pp.drawOn(c,x+13*mm,self.height-13*mm)
            body=Paragraph(txt,styles['SmallCustom']); body.wrapOn(c,cw-8*mm,24*mm); body.drawOn(c,x+4*mm,8*mm)

class TipBox(Flowable):
    def __init__(self,title,text,bg=GREEN_BG,fg=GREEN,width=170*mm): self.title=title; self.text=text; self.bg=bg; self.fg=fg; self.width=width; self.height=20*mm
    def draw(self):
        c=self.canv; c.setFillColor(self.bg); c.roundRect(0,0,self.width,self.height,2*mm,fill=1,stroke=0)
        c.setFillColor(self.fg); c.setFont('GuideSans-Bold',8.5); c.drawString(4*mm,self.height-6*mm,self.title)
        para=Paragraph(self.text,styles['SmallCustom']); para.wrapOn(c,self.width-8*mm,10*mm); para.drawOn(c,4*mm,3*mm)

class GuideDoc(BaseDocTemplate):
    def __init__(self,filename,**kw):
        super().__init__(filename,pagesize=A4,leftMargin=19*mm,rightMargin=19*mm,topMargin=18*mm,bottomMargin=17*mm,**kw)
        frame=Frame(self.leftMargin,self.bottomMargin,self.width,self.height,id='normal',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
        self.addPageTemplates(PageTemplate(id='all',frames=frame,onPage=self.draw_page))
    def draw_page(self,canvas,doc):
        canvas.saveState()
        if doc.page>1:
            canvas.setFillColor(GREEN); canvas.rect(0,PAGE_H-5*mm,PAGE_W,5*mm,fill=1,stroke=0)
            canvas.setFillColor(MUTED); canvas.setFont('GuideSans',7)
            canvas.drawString(19*mm,PAGE_H-10*mm,'AI Meter Reader | Bedienungsanleitung')
            canvas.setStrokeColor(colors.HexColor('#dce4e9')); canvas.line(19*mm,13*mm,PAGE_W-19*mm,13*mm)
            canvas.drawString(19*mm,8*mm,'AI Meter Reader | Kernabläufe')
            canvas.drawRightString(PAGE_W-19*mm,8*mm,f'{doc.page}')
        canvas.restoreState()

story=[]
# Cover
story += [Spacer(1,7*mm), Image(str(LOGO),width=49*mm,height=49*mm), Spacer(1,3*mm),
          p('AI Meter Reader','TitleCustom'),
          p('Bebilderte Bedienungsanleitung','SubTitle'),
          TipBox('Kamera rein. Zählerstand im Blick.', 'AI Meter Reader liest Zählerbilder in Home Assistant und prüft den erkannten Stand - je nach Bildquelle mit oder ohne Referenzwert.', GREEN_BG, GREEN),
          Spacer(1,7*mm), AppStatusMock(), Spacer(1,4*mm),
          p('Diese Anleitung erklärt die Einrichtung, den ersten Bildtest und die wichtigsten Hinweise im Statusbereich. Die Abbildungen zeigen typische Bedienelemente; einzelne Texte können je nach gewählter Sprache und Einrichtung abweichen.', 'BodyCustom'),
          p('<b>Bedienungsanleitung für 0.5 Beta.</b> Die App ist ein privates Hobbyprojekt und keine geeichte Messeinrichtung. Vor Abrechnungen bitte den Zählerstand direkt am Gerät prüfen.', 'SmallCustom'),
          PageBreak()]
# Page 2
story += [p('1. Einrichten','H1Custom'),
          p('Beim ersten Öffnen startet der Einrichtungsassistent. Du kannst ihn überspringen und später erneut aufrufen. Bereits gespeicherte Werte werden dabei vorausgefüllt.', 'BodyCustom'),
          WizardMock(), Spacer(1,4*mm),
          p('Wähle zuerst deine Bildquelle:','H2Custom'), ModeCards(), Spacer(1,3*mm),
          p('<b>SLFork / AI on the Edge:</b> Verwende die Adresse deines vorhandenen ESP. Er liefert das Foto und den dort erkannten Vergleichswert.', 'BodyCustom'),
          p('<b>Home-Assistant-Kamera:</b> Wähle eine Kamera-Entität. Wenn vorhanden, kannst du zusätzlich einen Sensor mit dem aktuellen Zählerstand angeben.', 'BodyCustom'),
          p('<b>ESPHome / lokale Ablesung:</b> Wähle eine Kamera-Entität. AI Meter Reader wertet das Bild selbst aus und erstellt einen Zählerstandssensor.', 'BodyCustom'),
          TipBox('Danach Zählerformat festlegen', 'Gib an, wie viele Stellen vor und nach dem Komma dein Zähler hat. Die Standardkontrolle vergleicht volle Kubikmeter. Nachkommastellen kannst du in den Einstellungen zusätzlich berücksichtigen.', YELLOW_BG, YELLOW),
          Spacer(1,4*mm),
          p('<b>Sprache:</b> „Automatisch (Home Assistant)“ folgt der Profilsprache, wenn sie Deutsch oder Englisch ist. Eine manuelle Auswahl findest du oben in der App.', 'BodyCustom'),
          PageBreak()]
# Page 3
story += [p('2. Kamera und Bildausschnitt','H1Custom'),
          p('Bevor du ein Gehäuse druckst oder die Kamera endgültig befestigst: erst ein Testbild aufnehmen. Ein passender Ausschnitt, ruhige Befestigung und gleichmäßiges Licht sind für die Erkennung wichtiger als ein besonders schickes Gehäuse.', 'BodyCustom'),
          p('Für ein zuverlässiges Bild','H2Custom'),
          p('• Richte die Kamera möglichst gerade auf die Ziffern. Bei schräger Montage Bilddrehung und Ausschnitt im Test anpassen.<br/>• Halte Abstand und Fokus so, dass alle relevanten Stellen scharf und ausreichend groß erscheinen.<br/>• Vermeide Spiegelungen auf einer Abdeckung und starke Schatten. Bei Bedarf Lichtquelle oder Kamerawinkel leicht verändern.<br/>• Befestige die Kamera so, dass sie beim Öffnen der Tür oder bei Berührung nicht verrutscht. Nach jeder Änderung ein neues Testbild prüfen.', 'BodyCustom'),
          TipBox('Erst probieren, dann drucken', 'Ein Papier- oder provisorischer Halter reicht zum Prüfen von Winkel, Fokus und Bildausschnitt. Wenn das Testbild passt, lohnt sich der endgültige Druck deutlich mehr.', YELLOW_BG, YELLOW),
          Spacer(1,6*mm),
          p('Ausschnitt und Drehung lernen','H2Custom'),
          p('Wähle im Assistenten bei <b>Bildbereich</b> die Option <b>Ausschnitt und Drehung lernen</b>. Nach dem Speichern startet die Suche. Später findest du sie auch direkt über <b>Selbsteinrichtung</b> in der Übersicht.', 'BodyCustom'),
          p('Die App prüft 4 bis 100 unterschiedliche Bilder, höchstens 100 Rahmenversuche und maximal 15 Minuten lang. Der Zeitbalken läuft weiter, wenn die App auf ein neues Bild wartet. Drei Bestätigungen und eine abschließende Gegenprüfung sind nötig. Erst dann übernimmt sie den Rahmen und die Drehung für die Automatik und als Vorgabe für den manuellen Test.', 'BodyCustom'),
          TipBox('Grün oder Rot', 'Grün bedeutet, dass die Gegenprüfung gelungen ist. Bei einem roten Fehlschlag bleiben deine bisherigen Bild-Einstellungen erhalten. Du kannst dann beim manuellen Test selbst einen Rahmen um die Ziffern ziehen.', GREEN_BG, GREEN),
          PageBreak()]
# Page 4
story += [p('3. Erstes Bild prüfen','H1Custom'),
          p('Starte nach der Einrichtung einen manuellen Test. So siehst du, ob Bildausschnitt, Drehung und Zählerformat passen, bevor du dich auf die Automatik verlässt.', 'BodyCustom'),
          p('1. Öffne <b>Manueller Test</b> und drücke <b>Test starten</b>. Der Fortschritt zeigt, ob das Bild geladen oder gerade ausgewertet wird.', 'BodyCustom'),
          p('2. Prüfe das <b>Letzte Testbild</b>. Grüne Rahmen bedeuten, dass eine Ziffer gelesen wurde. Gelb markiert Ziffern, die zwischen OCR-Versuchen schwankten oder aus mehreren Versuchen zusammengesetzt wurden. Rot markiert weiterhin unklare Stellen. Die Farben zeigen OCR-Erkennung, nicht den Abgleich mit dem Referenzwert.', 'BodyCustom'),
          OCRMock(), Spacer(1,3*mm),
          p('3. Bei falschem Ausschnitt kannst du den Bildbereich und die Drehung im manuellen Test anpassen. Die Vorschau zeigt eine neue Drehung sofort. Du kannst jeden Ziffernrahmen einzeln verschieben oder an seiner unteren Ecke skalieren. Prüfe das Ergebnis und übernimm einen passenden Rahmen für die Automatik.', 'BodyCustom'),
          p('4. Wenn keine Referenzquelle vorhanden ist, kannst du im manuellen Test den Wert selbst ablesen und als vorübergehenden Vergleichswert eingeben. Das Bild muss zuerst geladen sein. Ein fehlendes Bild wird in der Oberfläche angezeigt.', 'BodyCustom'),
          TipBox('Manueller Test bleibt Diagnose', 'Ein erfolgreicher manueller Test setzt den nächsten automatischen Prüftermin neu. Ein hochgeladenes oder eigens ausgewähltes Testbild ersetzt den automatischen Prüfnachweis nicht.', GREEN_BG, GREEN),
          Spacer(1,6*mm), p('Die automatische Kontrolle zeigt Ergebnis, Referenz, Bildzeit, letzte Prüfung und nächsten Prüftermin an. Das letzte Testbild lässt sich bei Bedarf aufklappen.','BodyCustom'),
          PageBreak()]
# Page 4
story += [p('4. Statusmeldungen verstehen','H1Custom'),
          p('Die Farbe hilft dir, das Ergebnis schnell einzuordnen. Ein Hinweis zur Bildquelle ist nicht automatisch ein Fehler beim Zählerstand.', 'BodyCustom')]
status_rows = [
    [p('GRÜN  |  Zählerstand bestätigt','CardHead'), p('Der erkannte Stand stimmt innerhalb der eingestellten Genauigkeit mit der Referenz überein. Bei „volle m³“ werden Nachkommastellen nicht bewertet.','BodyCustom')],
    [p('GELB  |  Prüfung fehlgeschlagen oder Hinweis','CardHead'), p('Zum Beispiel: kein neues Bild seit der letzten Prüfung. Die Quelle kann erreichbar sein, obwohl ihr Zeitstempel unverändert blieb. Ein frisches Bild wird nach kurzer Wartezeit erneut angefordert, wenn die erste automatische Prüfung scheitert.','BodyCustom')],
    [p('ROT  |  Längerer kritischer Fehler','CardHead'), p('Wird vor allem bei anhaltendem Ausfall der Bildaufnahme angezeigt. Ein kurzer Fehler beim Aktualisieren des App-Status wird zunächst als vorübergehend gemeldet; die Oberfläche versucht es erneut.','BodyCustom')],
]
t=Table(status_rows,colWidths=[53*mm,117*mm],rowHeights=[28*mm,36*mm,33*mm])
t.setStyle(TableStyle([
    ('BACKGROUND',(0,0),(-1,0),GREEN_BG),('BACKGROUND',(0,1),(-1,1),YELLOW_BG),('BACKGROUND',(0,2),(-1,2),RED_BG),
    ('BOX',(0,0),(-1,-1),.4,colors.HexColor('#d5e0e6')),('INNERGRID',(0,0),(-1,-1),.4,colors.HexColor('#d5e0e6')),
    ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)
]))
story += [t,Spacer(1,5*mm),
          p('Automatische Nachprüfung','H2Custom'),
          p('Nach einer fehlgeschlagenen automatischen Prüfung folgen bis zu zwei weitere Bildprüfungen im Abstand von fünf Minuten. Dabei wird das aktuelle Bild der Quelle erneut abgerufen; ob es tatsächlich neu ist, prüft die App am Zeitstempel. Bleiben drei Prüfungen erfolglos, wartet sie eine Stunde auf einen höheren Zählerstand oder ein neues Bild und versucht es dann erneut. Der Zähler der Fehlprüfungen bleibt sichtbar.', 'BodyCustom'),
          p('Mit <b>Automatik pausieren</b> hältst du neue automatische Prüfungen an. Ein gelber Hinweis zeigt die Pause; manuelle Tests bleiben möglich. Mit <b>Automatik fortsetzen</b> geht es weiter.', 'BodyCustom'),
          TipBox('Kein neues Bild, aber noch nicht alt?', 'Das ist zunächst ein Quellenhinweis: Die Verbindung kann bestehen und das vorhandene Bild noch innerhalb der zulässigen Altersgrenze liegen. Die App kennzeichnet es deshalb nicht automatisch als kritischen Fehler. Wenn die Lesung weiter unsicher ist, prüfe Beleuchtung, Abstand und Fokus.', YELLOW_BG, YELLOW),
          PageBreak()]
story += [p('5. Automatik im Hintergrund verbessern','H1Custom'),
          p('Die folgenden Funktionen sind für den Langzeittest in 0.5 Beta vorgesehen. Öffne dafür <b>Einstellungen → Automatische Prüfung</b>.', 'BodyCustom'),
          p('Rahmen langfristig feinjustieren','H2Custom'),
          p('Die App sammelt auf bestätigten Bildern unterschiedliche Ziffernstellungen. Ein vorgeschlagener Rahmen wird erst nach mehreren erfolgreichen Gegenproben übernommen. Scheitern danach mehrere neue OCR-Prüfungen, stellt sie den vorherigen Rahmen wieder her.', 'BodyCustom'),
          p('Kürzer prüfen, wenn sich eine Ziffer dreht','H2Custom'),
          p('Im SLFork-Modus kann die App das reguläre Intervall bei einem erwarteten Rollenwechsel verkürzen. Zwischen regulären Prüfungen liegen mindestens fünf Minuten. Doppelt gelieferte Messzyklen zählen nur einmal.', 'BodyCustom'),
          p('Verdeckte Ziffern ergänzen','H2Custom'),
          p('Wenn aus dem letzten sicheren Stand und dem maximalen Durchfluss genau ein Wert folgt, kann die App je eine Stelle vor und nach dem Komma ergänzen. Gelb markierte Stellen sind vorläufig. Bei eindeutiger OCR übernimmt wieder die normale Ablesung.', 'BodyCustom'),
          p('Startwert speichern','H2Custom'),
          p('Trage in den Einstellungen den am Zähler abgelesenen Stand und den Zeitpunkt ein und wähle <b>Fallback-Wert speichern</b>. Der Fallback dient als Startwert, bis eine sichere automatische Ablesung vorliegt.', 'BodyCustom'),
          PageBreak()]
# Page 5
story += [p('6. Dashboard, Sprache und Hilfe','H1Custom'),
          p('Wert im Home-Assistant-Dashboard anzeigen','H2Custom'),
          p('1. Öffne in Home Assistant das gewünschte Dashboard und wähle <b>Bearbeiten</b>.<br/>2. Füge eine Karte hinzu, zum Beispiel eine <b>Entitäten-Karte</b>.<br/>3. Suche die AI Meter Reader-Entität für den Zählerstand. Für einen kumulierten Verbrauch steht außerdem <b>sensor.rf1_beta_verbrauch_gesamt</b> bereit.<br/>4. Speichere die Karte. Home Assistant kann den kumulierten Verbrauch anschließend in der Energieansicht verwenden, sofern Einheit und Geräteeinstellungen passen.', 'BodyCustom'),
          TipBox('Hinweis zu Entitätsnamen', 'Einige bestehende Home-Assistant-Entitäten behalten aus Kompatibilitätsgründen ältere IDs. Die sichtbaren Namen können abweichen. Wähle im Dashboard die Entität über die Suche aus.', GREEN_BG, GREEN),
          Spacer(1,4*mm), p('Sprache wechseln','H2Custom'),
          p('Wähle oben in AI Meter Reader <b>Deutsch</b>, <b>English</b> oder <b>Automatisch (Home Assistant)</b>. Bei automatischer Auswahl übernimmt die Oberfläche die Profilsprache Deutsch oder Englisch. Nach einer Änderung der Home-Assistant-Profilsprache aktualisiert sich die App normalerweise innerhalb weniger Sekunden selbst; bei einem Verbindungs- oder Browserproblem hilft weiterhin ein Neuladen.', 'BodyCustom'),
          p('Wichtige Grenzen','H2Custom'),
          p('AI Meter Reader liest derzeit vor allem Ziffernrollen. Kleine analoge Zeiger werden nicht zuverlässig ausgewertet. Unterstützung verschiedener Wasser-, Strom- und anderer Zähler wird weiter geprüft; nicht jeder Zähler und jede Beleuchtung ist bereits praktisch getestet. Der Maintainer testet reale Zähler mit AI on the Edge / SLFork; andere Quellen und Situationen sind bisher vor allem automatisiert oder simuliert geprüft.', 'BodyCustom'),
          p('Bei Problemen','H2Custom'),
          p('Öffne die automatische Übersicht und prüfe Bildzeit, letzten Prüftermin, Referenzwert und Quellenhinweis. Danach kannst du einen manuellen Test starten. Für Fehlerberichte: App-Version, Zählertyp und Bildquelle angeben; Zugangsdaten nicht veröffentlichen.', 'BodyCustom'),
          p('Projekt und ausführliche Informationen','H2Custom'),
          p('GitHub: <link href="https://github.com/Eifellayer/meter-ocr" color="#167246">github.com/Eifellayer/meter-ocr</link><br/>Ausführliche Dokumentation und Nutzungshinweise stehen in der Projekt-README. Die Anleitung wird bei wesentlichen Funktions- oder Ablaufänderungen aktualisiert; kleine Umbenennungen erfordern keine neue Ausgabe.', 'BodyCustom'),
          Spacer(1,3*mm),
          p('<b>Keine geeichte Messung.</b> OCR-Ergebnisse können falsch sein. Für Abrechnung und offizielle Meldungen zählt der am Zähler direkt geprüfte Stand. Die Software wird ohne Gewähr bereitgestellt, soweit gesetzlich zulässig; zwingende gesetzliche Haftungsregeln bleiben unberührt.', 'SmallCustom')]

doc=GuideDoc(str(OUT),title='AI Meter Reader - Bedienungsanleitung',author='Eifellayer')
doc.build(story)
print(OUT)
