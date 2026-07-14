import os
import io
import subprocess
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- HELPER: Temporäre Dateien bereinigen ---
def clean_files(*filepaths):
    for path in filepaths:
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

# --- 1. PDFs ZUSAMMENFÜGEN (Merge) ---
@app.route('/merge', methods=['POST'])
def merge_pdfs():
    files = request.files.getlist('files')
    if not files or len(files) < 2:
        return jsonify({"error": "Mindestens zwei PDFs werden benötigt."}), 400
    
    writer = PdfWriter()
    try:
        for file in files:
            reader = PdfReader(io.BytesIO(file.read()))
            for page in reader.pages:
                writer.add_page(page)
        
        out = io.BytesIO()
        writer.write(out)
        out.seek(0)
        return send_file(out, mimetype='application/pdf', as_attachment=True, download_name="zusammengefuegt.pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 2. PDF SEITEN LÖSCHEN / EXTRAHIEREN / ORGANISIEREN ---
@app.route('/manipulate-pages', methods=['POST'])
def manipulate_pages():
    file = request.files.get('file')
    # Erwartet eine Liste von 0-basierten Indizes als String, z.B. "0,2,3"
    pages_input = request.form.get('pages', '') 
    action = request.form.get('action') # 'extract' oder 'delete'

    if not file or not pages_input or not action:
        return jsonify({"error": "Fehlende Parameter"}), 400

    try:
        target_pages = [int(p.strip()) for p in pages_input.split(',') if p.strip().isdigit()]
        reader = PdfReader(io.BytesIO(file.read()))
        writer = PdfWriter()

        for idx, page in enumerate(reader.pages):
            if action == 'extract' and idx in target_pages:
                writer.add_page(page)
            elif action == 'delete' and idx not in target_pages:
                writer.add_page(page)

        out = io.BytesIO()
        writer.write(out)
        out.seek(0)
        return send_file(out, mimetype='application/pdf', as_attachment=True, download_name="manipuliert.pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 3. PDF DREHEN (Rotate) ---
@app.route('/rotate', methods=['POST'])
def rotate_pdf():
    file = request.files.get('file')
    angle = int(request.form.get('angle', 90)) # Standard 90 Grad im Uhrzeigersinn

    if not file:
        return jsonify({"error": "Keine Datei hochgeladen"}), 400

    try:
        reader = PdfReader(io.BytesIO(file.read()))
        writer = PdfWriter()

        for page in reader.pages:
            page.rotate(angle)
            writer.add_page(page)

        out = io.BytesIO()
        writer.write(out)
        out.seek(0)
        return send_file(out, mimetype='application/pdf', as_attachment=True, download_name="gedreht.pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 4. PDF OCR (Texterkennung) ---
@app.route('/ocr', methods=['POST'])
def ocr_pdf():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "Keine Datei hochgeladen"}), 400

    in_path = "/tmp/input_ocr.pdf"
    out_path = "/tmp/output_ocr.pdf"

    try:
        file.save(in_path)
        # Ruft das CLI-Tool ocrmypdf auf (installiert im Dockerfile)
        # --skip-text sorgt dafür, dass bereits vorhandener Text nicht überschrieben wird
        subprocess.run(["ocrmypdf", "-l", "deu", "--skip-text", in_path, out_path], check=True)
        
        with open(out_path, 'rb') as f:
            pdf_data = f.read()
        
        clean_files(in_path, out_path)
        return send_file(io.BytesIO(pdf_data), mimetype='application/pdf', as_attachment=True, download_name="ocr_ergebnis.pdf")
    except Exception as e:
        clean_files(in_path, out_path)
        return jsonify({"error": f"OCR fehlgeschlagen: {str(e)}"}), 500

# --- 5. SCHWÄRZEN / FLATTEN (Ebenen entfernen) ---
@app.route('/flatten', methods=['POST'])
def flatten_pdf():
    # "Flattening" zeichnet alle Anmerkungen, Unterschriften und Formularelemente fest in die Bildebene
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "Keine Datei"}), 400
        
    try:
        reader = PdfReader(io.BytesIO(file.read()))
        writer = PdfWriter()
        
        for page in reader.pages:
            writer.add_page(page)
            
        # Entfernt interaktive Formulare und flacht ab
        writer.remove_links()
        
        out = io.BytesIO()
        writer.write(out)
        out.seek(0)
        return send_file(out, mimetype='application/pdf', as_attachment=True, download_name="abgeflacht.pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 6. VERSCHLÜSSELN / PASSWORT ENTFERNEN ---
@app.route('/security', methods=['POST'])
def security_pdf():
    file = request.files.get('file')
    password = request.form.get('password', '')
    action = request.form.get('action') # 'encrypt' oder 'decrypt'

    if not file or not action:
        return jsonify({"error": "Fehlende Parameter"}), 400

    try:
        reader = PdfReader(io.BytesIO(file.read()))
        
        # Falls entschlüsselt werden soll
        if action == 'decrypt':
            if reader.is_encrypted:
                reader.decrypt(password)
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
        
        # Falls verschlüsselt werden soll
        elif action == 'encrypt':
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            writer.encrypt(user_password=password, owner_password=None, use_128bit=True)

        out = io.BytesIO()
        writer.write(out)
        out.seek(0)
        return send_file(out, mimetype='application/pdf', as_attachment=True, download_name="sicherheit_angepasst.pdf")
    except Exception as e:
        return jsonify({"error": "Passwort falsch oder Operation fehlgeschlagen."}), 400

if __name__ == '__main__':
    app.run(port=8080)
