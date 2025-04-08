import os
import sys
import requests
import webbrowser
import logging
from yt_dlp import YoutubeDL
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QIcon, QFontDatabase, QFont
from PyQt5.QtWidgets import QMessageBox, QApplication

APP_VERSION = "1.0.2"
VERSION_URL = "https://raw.githubusercontent.com/hi-bernardo/HB-Downloader/main/src/latest_version.txt"
EXECUTABLE_URL = "https://github.com/hi-bernardo/HB-Downloader/releases/download/v1/HB_Downloader.exe"


def check_for_updates():
    try:
        response = requests.get(VERSION_URL, timeout=5)
        if response.status_code == 200:
            latest_version = response.text.strip()
            if latest_version != APP_VERSION:
                show_update_popup(latest_version)
    except Exception as e:
        print(f"Erro ao verificar atualizações: {e}")


def show_update_popup(latest_version):
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setWindowTitle("Atualização disponível")
    msg.setText(f"Uma nova versão ({latest_version}) está disponível!")
    msg.setInformativeText("Deseja baixar e instalar agora?")
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

    if msg.exec_() == QMessageBox.Yes:
        download_and_replace_executable()


def download_and_replace_executable():
    try:
        current_path = os.path.realpath(sys.argv[0])
        temp_path = current_path + ".new"

        response = requests.get(EXECUTABLE_URL, stream=True)
        total = int(response.headers.get('content-length', 0))
        downloaded = 0

        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    done = int(50 * downloaded / total)
                    print(f"\r[{'=' * done}{' ' * (50 - done)}] {int(downloaded / total * 100)}%", end='')

        print("\nDownload concluído. Atualizando...")

        bat_script = f"""
        @echo off
        timeout /t 1 > NUL
        taskkill /f /pid {os.getpid()}
        move /Y "{temp_path}" "{current_path}"
        start "" "{current_path}"
        exit
        """
        bat_path = os.path.join(os.path.dirname(current_path), "update.bat")
        with open(bat_path, 'w') as bat_file:
            bat_file.write(bat_script)

        os.startfile(bat_path)
        sys.exit(0)

    except Exception as e:
        QMessageBox.critical(None, "Erro na atualização", f"Erro ao baixar nova versão:\n{e}")


def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class Logger:
    def __init__(self, path="log.txt", enabled=False):
        self.logger = logging.getLogger("Downloader")
        self.logger.setLevel(logging.DEBUG)

        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        self.enabled = enabled
        if not self.enabled:
            self.logger.disabled = True
            return

        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

        fh = logging.FileHandler(path, mode='w', encoding='utf-8')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

    def get(self):
        return self.logger


class TextAnimator(QtCore.QObject):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_animation)
        self.animation_patterns = {
            "starting": ["Iniciando", "Iniciando.", "Iniciando..", "Iniciando..."],
            "downloading": "Baixando {percent}%",
            "canceling": ["Cancelando", "Cancelando.", "Cancelando..", "Cancelando..."],
            "finishing": ["Finalizando", "Finalizando.", "Finalizando..", "Finalizando..."]
        }
        self.current_animation = ""
        self.frame_index = 0
        self.percent = 0

    def start_animation(self, animation_type, percent=None):
        self.current_animation = animation_type
        self.frame_index = 0
        if percent is not None:
            self.percent = percent
        self.timer.start(300)

    def update_animation(self):
        animation = self.animation_patterns.get(self.current_animation, "")

        if isinstance(animation, list):
            current_frame = animation[self.frame_index % len(animation)]
            self.update_widget_text(current_frame)
            self.frame_index += 1
        elif isinstance(animation, str) and "{percent}" in animation:
            self.update_widget_text(animation.format(percent=self.percent))

    def update_widget_text(self, text):
        if isinstance(self.widget, QtWidgets.QProgressBar):
            self.widget.setFormat(text)
        elif isinstance(self.widget, QtWidgets.QLabel):
            self.widget.setText(text)

    def stop_animation(self, final_text=""):
        self.timer.stop()
        if final_text:
            self.update_widget_text(final_text)


class DownloadWorker(QtCore.QObject):
    progress = QtCore.pyqtSignal(int, str)
    finished = QtCore.pyqtSignal(bool, str)

    def __init__(self, url, media_type, quality, fmt, no_audio):
        super().__init__()
        self.url = url
        self.media_type = media_type
        self.quality = quality
        self.fmt = fmt.lower()
        self.no_audio = no_audio
        self.cancelled = False

    def run(self):
        try:
            path = os.path.join(os.path.expanduser("~"), 'Downloads')
            outtmpl = os.path.join(path, '%(title)s-%(resolution)s.%(ext)s')
            opts = {
                'outtmpl': outtmpl,
                'progress_hooks': [self.progress_hook],
                'format': 'bestaudio/best',
            }

            if self.media_type == "Vídeo":
                if self.quality.lower() == 'melhor':
                    opts['format'] = 'bestvideo+bestaudio/best'
                elif self.quality.endswith('p'):
                    height = self.quality[:-1]
                    opts['format'] = f'bestvideo[height<={height}]+bestaudio/best'
                elif self.quality == '2k':
                    opts['format'] = 'bestvideo[height<=1440]+bestaudio/best'
                if self.no_audio:
                    opts['format'] = opts['format'].split('+')[0]
                opts['merge_output_format'] = self.fmt
            else:
                opts['format'] = 'bestaudio'
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': self.fmt,
                    'preferredquality': self.quality.replace('k', '')
                }]

            with YoutubeDL(opts) as ydl:
                ydl.download([self.url])

            if not self.cancelled:
                self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))

    def cancel(self):
        self.cancelled = True
        try:
            downloads_path = os.path.join(os.path.expanduser("~"), 'Downloads')
            for file in os.listdir(downloads_path):
                if any(self.url.split("/")[-1] in file for ext in ['.mp4', '.webm', '.mkv', '.mp3']):
                    os.remove(os.path.join(downloads_path, file))
        except Exception:
            pass
        self.finished.emit(False, "Cancelado pelo usuário")

    def progress_hook(self, d):
        if self.cancelled:
            raise Exception("Download cancelado")
        if d.get('status') == 'downloading':
            percent_str = d.get('_percent_str', '0.0%')
            percent = float(percent_str.strip('%'))
            self.progress.emit(int(percent), percent_str)
        elif d.get('status') == 'finished':
            self.progress.emit(100, 'Finalizando...')


class DownloaderUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.logger = Logger().get()
        self.setWindowIcon(QtGui.QIcon(resource_path('src/icon.ico')))
        self.setWindowIcon(QIcon(resource_path('src/icon.ico')))
        self.setWindowTitle("HB Downloader")
        self.setFixedSize(550, 350)

        self.setStyleSheet(self.style())

        self.setup_ui()

    def style(self):
        return """
        QWidget {
            background-color: #2b2b2b;
            color: white;
            font-family: 'Inter';
        }
        QLabel {
            margin-top: 25px;
            font-weight: bold;
        }
        QCheckBox::indicator:checked {
            background-color: #3ab0fc;
            border: 2px solid #999;
            spacing: 4px;
            transition: all 0.3s ease;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border-radius: 8px;
            border: 2px solid #999;
        }
        QLineEdit {
            background-color: rgba(255, 255, 255, 0.05);
            border: 0.5px solid #9c9c9c;
            border-radius: 10px;
            padding: 12px;
        }
        QPushButton {
            background-color: rgba(255, 255, 255, 0.05);
            border: 0.5px solid #9c9c9c;
            border-radius: 10px;
            padding: 11px;
            color: white;
            transition: all 0.3s ease;
        }
        QPushButton:hover {
            font-weight: bold;
            background-color: #2980b9;
            border: 0.5px solid #3498db;
            transform: translateY(-1px);
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        QComboBox {
            background-color: rgba(255, 255, 255, 0.05);
            border: 0.5px solid #9c9c9c;
            border-radius: 10px;
            padding: 8px;
            transition: all 0.3s ease;
        }
        QComboBox:hover {
            background-color: rgba(41, 128, 185, 0.2);
            border: 0.5px solid #3498db;
        }
        QComboBox::drop-down {
            border: none;
        }
        QPushButton:pressed {
            transform: translateY(1px);
            background-color: #1a5276;
        }
        QProgressBar {
            border: 1px solid #9c9c9c;
            border-radius: 6px;
            background-color: #f8f9fa;
            text-align: center;
            color: black;
            font-weight: bold;
            min-height: 24px;
        }
        QProgressBar::chunk {
            background-color: #3498db;
            width: 24px;
            border-radius: 4px;
            margin-left: -20px;
        }
        """

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        self.url_input = QtWidgets.QLineEdit()
        self.url_input.setPlaceholderText("V1.0.2")
        self.url_input.textChanged.connect(self.on_url_change)

        self.btn_paste = QtWidgets.QPushButton("")
        self.btn_paste.setIcon(QIcon(resource_path('src/paste.ico')))
        self.btn_paste.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.btn_paste.setFixedWidth(40)
        self.btn_paste.clicked.connect(self.paste_url)

        url_layout = QtWidgets.QHBoxLayout()
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.btn_paste)

        self.media_type = QtWidgets.QComboBox()
        self.media_type.addItem("Escolha uma opção")
        self.media_type.addItems(["Vídeo", "Áudio"])
        self.media_type.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.media_type.currentIndexChanged.connect(self.update_options)

        self.checkbox_no_audio = QtWidgets.QCheckBox("Sem áudio")
        self.checkbox_no_audio.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.checkbox_no_audio.setFixedWidth(105)
        self.checkbox_no_audio.setVisible(False)

        type_layout = QtWidgets.QHBoxLayout()
        type_layout.addWidget(self.media_type)
        type_layout.addWidget(self.checkbox_no_audio)

        self.label_quality = QtWidgets.QLabel("QUALIDADE")
        self.label_format = QtWidgets.QLabel("FORMATO")
        self.label_quality.setStyleSheet("font-size: 16px;")
        self.label_format.setStyleSheet("font-size: 16px;")
        self.label_quality.setAlignment(QtCore.Qt.AlignCenter)
        self.label_format.setAlignment(QtCore.Qt.AlignCenter)
        self.label_quality.setVisible(False)
        self.label_format.setVisible(False)

        label_layout = QtWidgets.QHBoxLayout()
        label_layout.addWidget(self.label_quality)
        label_layout.addWidget(self.label_format)

        self.quality_combo = QtWidgets.QComboBox()
        self.quality_combo.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.quality_combo.setVisible(False)
        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.format_combo.setVisible(False)

        combo_layout = QtWidgets.QHBoxLayout()
        combo_layout.addWidget(self.quality_combo)
        combo_layout.addWidget(self.format_combo)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False)
        self.progress.setAlignment(QtCore.Qt.AlignCenter)
        self.progress_animator = TextAnimator(self.progress)
        # self.progress.setStyleSheet(self.style())

        self.btn_download = QtWidgets.QPushButton("Iniciar Download")
        self.btn_download.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.btn_download.clicked.connect(self.toggle_download)
        self.btn_download.setVisible(False)

        self.signature = QtWidgets.QLabel("by oBrazoo")
        self.signature.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom)
        self.signature.setStyleSheet("color: gray; font-size: 10px;")

        layout.addLayout(url_layout)
        layout.addLayout(type_layout)
        layout.addLayout(label_layout)
        layout.addLayout(combo_layout)
        layout.addSpacing(10)
        layout.addWidget(self.progress)
        layout.addSpacing(10)
        layout.addWidget(self.btn_download)
        layout.addStretch()
        layout.addWidget(self.signature)

    def on_url_change(self, text):
        valid = text.strip().startswith("http") and self.media_type.currentIndex() != 0
        self.btn_download.setVisible(valid)
        self.logger.info(f"URL alterada {text}")

    def paste_url(self):
        text = QtWidgets.QApplication.clipboard().text()
        self.url_input.setText(text)
        self.logger.info("Colada do clipboard")

    def update_options(self):
        self.quality_combo.clear()
        self.format_combo.clear()

        self.quality_combo.setVisible(False)
        self.format_combo.setVisible(False)
        self.checkbox_no_audio.setVisible(False)
        self.label_quality.setVisible(False)
        self.label_format.setVisible(False)

        if self.media_type.currentText() == "Vídeo":
            self.quality_combo.addItems(["Melhor", "1440p", "1080p", "720p", "480p", "360p", "144p"])
            self.format_combo.addItems(["MP4", "MKV", "WEBM"])
            self.checkbox_no_audio.setVisible(True)
            self.quality_combo.setVisible(True)
            self.format_combo.setVisible(True)
            self.label_quality.setVisible(True)
            self.label_format.setVisible(True)
        elif self.media_type.currentText() == "Áudio":
            self.quality_combo.addItems(["128k", "192k", "256k", "320k"])
            self.format_combo.addItems(["MP3", "FLAC", "ACC", "M4A", "OPUS", "OGG", "WAV"])
            self.quality_combo.setVisible(True)
            self.format_combo.setVisible(True)
            self.label_quality.setVisible(True)
            self.label_format.setVisible(True)

        self.on_url_change(self.url_input.text())

    def toggle_download(self):
        if self.btn_download.text() == "Iniciar Download":
            self.start_download()
        else:
            self.cancel_download()

    def start_download(self):
        url = self.url_input.text().strip()
        media_type = self.media_type.currentText()
        quality = self.quality_combo.currentText()
        fmt = self.format_combo.currentText()
        no_audio = self.checkbox_no_audio.isChecked()

        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.progress_animator.start_animation("starting")  # Animação de início
        # self.btn_download.setEnabled(False)

        self.thread = QtCore.QThread()
        self.worker = DownloadWorker(url, media_type, quality, fmt, no_audio)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.finish_download)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()
        self.btn_download.setText("Cancelar")
        self.btn_download.setEnabled(True)
        self.logger.info(f"Download iniciado: {url}, tipo: {media_type}, qualidade: {quality}, formato: {fmt}")

    def cancel_download(self):
        if hasattr(self, 'worker'):
            self.worker.cancel()
        self.progress_animator.start_animation("canceling")
        QtCore.QTimer.singleShot(3000, lambda: self.progress_animator.stop_animation("❌ Download cancelado"))

    def update_progress(self, percent, text):
        self.progress.setValue(percent)

        if percent < 100:
            self.progress_animator.start_animation("downloading", percent)
        elif percent == 100:
            self.progress_animator.start_animation("finishing")
            QtCore.QTimer.singleShot(3600, lambda: self.progress_animator.stop_animation("✅ Download concluído!"))

    def finish_download(self, success, msg):
        if success:
            self.progress.setFormat("✅ Download concluído!")  # Sucesso
            self.logger.info("Download finalizado com sucesso.")
        elif "Cancelado" in msg:
            self.progress.setFormat("❌ Download cancelado")  # Cancelado
            self.logger.warning("Download cancelado pelo usuário")
        else:
            self.progress.setFormat(f"⚠️ {msg[:30]}...")
            self.logger.error(f"Erro no download: {msg}")
        QtCore.QTimer.singleShot(3000, lambda: self.progress.setVisible(False))
        self.progress.style().polish(self.progress)  # Força a atualização do estilo
        self.btn_download.setText("Iniciar Download")


if __name__ == '__main__':
    # ========== FORCE APPUSERMODELID BEFORE ANY QT OPERATION ==========
    if sys.platform == 'win32':
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Brazoo.HB_Downloader.1.0')

    app = QtWidgets.QApplication(sys.argv)

    # ========== CONFIGURAÇÕES DE FONTE ==========
    QFontDatabase.addApplicationFont(resource_path("src/font/Inter-Variable.ttf"))
    QFontDatabase.addApplicationFont(resource_path("src/font/Inter-Italic.ttf"))
    app.setFont(QFont("Inter Variable", 11))

    # ========== ÍCONE GLOBAL ==========
    app.setWindowIcon(QtGui.QIcon(resource_path('srsc/icon.ico')))

    # ========== JANELA PRINCIPAL ==========
    check_for_updates()
    window = DownloaderUI()
    window.setWindowIcon(QtGui.QIcon(resource_path('src/icon.ico')))  # Redundância proposital
    window.show()

    sys.exit(app.exec_())
