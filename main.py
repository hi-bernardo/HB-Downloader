import os
import sys
import logging
import webbrowser
from typing import Optional, Dict, List, Union
from pathlib import Path

import requests
from yt_dlp import YoutubeDL
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QIcon, QFontDatabase, QFont
from PyQt5.QtWidgets import QMessageBox, QApplication

# Constants
APP_VERSION = "1.0.0"
VERSION_URL = "https://raw.githubusercontent.com/hi-bernardo/HB-Downloader/main/src/latest_version.txt"
DOWNLOAD_URL = "https://github.com/hi-bernardo/HB-Downloader/releases"
DOWNLOADS_FOLDER = Path.home() / "Downloads"
SUPPORTED_VIDEO_FORMATS = ["MP4", "MKV", "WEBM"]
SUPPORTED_AUDIO_FORMATS = ["MP3", "FLAC", "ACC", "M4A", "OPUS", "OGG", "WAV"]
VIDEO_QUALITIES = ["Melhor", "1440p", "1080p", "720p", "480p", "360p", "144p"]
AUDIO_QUALITIES = ["128k", "192k", "256k", "320k"]


class UpdateChecker:
    """Handles application update checks."""

    @staticmethod
    def check_for_updates() -> None:
        """Check for updates and show popup if new version is available."""
        try:
            response = requests.get(VERSION_URL, timeout=5)
            if response.status_code == 200:
                latest_version = response.text.strip()
                if latest_version != APP_VERSION:
                    UpdateChecker.show_update_popup(latest_version)
        except Exception as e:
            logging.warning(f"Error checking for updates: {e}")

    @staticmethod
    def show_update_popup(latest_version: str) -> None:
        """Show update available popup."""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Atualização disponível")
        msg.setText(f"Uma nova versão ({latest_version}) está disponível!")
        msg.setInformativeText("Deseja ir até a página de download?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        if msg.exec_() == QMessageBox.Yes:
            webbrowser.open(DOWNLOAD_URL)


class ResourceManager:
    """Handles resource paths for both development and packaged versions."""

    @staticmethod
    def get_path(relative_path: str) -> str:
        """Get absolute path to resource, works for dev and for PyInstaller."""
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.abspath("."), relative_path)


class Logger:
    """Custom logger configuration."""

    def __init__(self, path: str = "log.txt", enabled: bool = False):
        """Initialize logger with file and console handlers."""
        self.logger = logging.getLogger("Downloader")
        self.logger.setLevel(logging.DEBUG)

        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        self.enabled = enabled
        if not self.enabled:
            self.logger.disabled = True
            return

        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

        # File handler
        fh = logging.FileHandler(path, mode='w', encoding='utf-8')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

    def get_logger(self) -> logging.Logger:
        """Get the configured logger instance."""
        return self.logger


class TextAnimator(QtCore.QObject):
    """Handles text animations for UI elements."""

    def __init__(self, widget: QtWidgets.QWidget):
        super().__init__()
        self.widget = widget
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._update_animation)

        self.animation_patterns = {
            "starting": ["Iniciando", "Iniciando.", "Iniciando..", "Iniciando..."],
            "downloading": "Baixando {percent}%",
            "canceling": ["Cancelando", "Cancelando.", "Cancelando..", "Cancelando..."],
            "finishing": ["Finalizando", "Finalizando.", "Finalizando..", "Finalizando..."]
        }

        self.current_animation = ""
        self.frame_index = 0
        self.percent = 0

    def start_animation(self, animation_type: str, percent: Optional[int] = None) -> None:
        """Start animation with given type and optional percentage."""
        self.current_animation = animation_type
        self.frame_index = 0
        if percent is not None:
            self.percent = percent
        self.timer.start(300)

    def _update_animation(self) -> None:
        """Update animation frame."""
        animation = self.animation_patterns.get(self.current_animation, "")

        if isinstance(animation, list):
            current_frame = animation[self.frame_index % len(animation)]
            self._update_widget_text(current_frame)
            self.frame_index += 1
        elif isinstance(animation, str) and "{percent}" in animation:
            self._update_widget_text(animation.format(percent=self.percent))

    def _update_widget_text(self, text: str) -> None:
        """Update widget text based on widget type."""
        if isinstance(self.widget, QtWidgets.QProgressBar):
            self.widget.setFormat(text)
        elif isinstance(self.widget, QtWidgets.QLabel):
            self.widget.setText(text)

    def stop_animation(self, final_text: str = "") -> None:
        """Stop animation and optionally set final text."""
        self.timer.stop()
        if final_text:
            self._update_widget_text(final_text)


class DownloadWorker(QtCore.QObject):
    """Worker class for handling downloads in background thread."""

    progress = QtCore.pyqtSignal(int, str)
    finished = QtCore.pyqtSignal(bool, str)

    def __init__(self, url: str, media_type: str, quality: str, fmt: str, no_audio: bool):
        super().__init__()
        self.url = url
        self.media_type = media_type
        self.quality = quality
        self.fmt = fmt.lower()
        self.no_audio = no_audio
        self.cancelled = False

    def run(self) -> None:
        """Main download execution method."""
        try:
            opts = self._get_download_options()

            with YoutubeDL(opts) as ydl:
                ydl.download([self.url])

            if not self.cancelled:
                self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))

    def _get_download_options(self) -> Dict:
        """Generate download options based on media type and settings."""
        outtmpl = str(DOWNLOADS_FOLDER / '%(title)s-%(resolution)s.%(ext)s')
        opts = {
            'outtmpl': outtmpl,
            'progress_hooks': [self._progress_hook],
            'format': 'bestaudio/best',
        }

        if self.media_type == "Vídeo":
            opts = self._configure_video_options(opts)
        else:
            opts = self._configure_audio_options(opts)

        return opts

    def _configure_video_options(self, opts: Dict) -> Dict:
        """Configure options for video downloads."""
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
        return opts

    def _configure_audio_options(self, opts: Dict) -> Dict:
        """Configure options for audio downloads."""
        opts['format'] = 'bestaudio'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': self.fmt,
            'preferredquality': self.quality.replace('k', '')
        }]
        return opts

    def cancel(self) -> None:
        """Cancel current download and clean up partial files."""
        self.cancelled = True
        self._clean_partial_downloads()
        self.finished.emit(False, "Cancelado pelo usuário")

    def _clean_partial_downloads(self) -> None:
        """Clean up partially downloaded files."""
        try:
            for file in DOWNLOADS_FOLDER.iterdir():
                if any(self.url.split("/")[-1] in file.name for ext in ['.mp4', '.webm', '.mkv', '.mp3']):
                    file.unlink()
        except Exception as e:
            logging.warning(f"Error cleaning partial downloads: {e}")

    def _progress_hook(self, d: Dict) -> None:
        """Handle download progress updates."""
        if self.cancelled:
            raise Exception("Download cancelado")

        if d.get('status') == 'downloading':
            percent_str = d.get('_percent_str', '0.0%')
            percent = float(percent_str.strip('%'))
            self.progress.emit(int(percent), percent_str)
        elif d.get('status') == 'finished':
            self.progress.emit(100, 'Finalizando...')


class DownloaderUI(QtWidgets.QWidget):
    """Main application UI class."""

    def __init__(self):
        super().__init__()
        self._setup_logger()
        self._init_ui()
        self._setup_connections()

    def _setup_logger(self) -> None:
        """Initialize and configure logger."""
        self.logger = Logger().get_logger()

    def _init_ui(self) -> None:
        """Initialize UI components."""
        self.setWindowIcon(QtGui.QIcon(ResourceManager.get_path('src/icon.ico')))
        self.setWindowTitle("HB Downloader")
        self.setFixedSize(550, 350)
        self.setStyleSheet(self._get_stylesheet())

        self._create_widgets()
        self._setup_layout()

    def _get_stylesheet(self) -> str:
        """Return application stylesheet."""
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

    def _create_widgets(self) -> None:
        """Create all UI widgets."""
        # URL input
        self.url_input = QtWidgets.QLineEdit()
        self.url_input.setPlaceholderText("Cole a URL aqui")

        self.btn_paste = QtWidgets.QPushButton()
        self.btn_paste.setIcon(QIcon(ResourceManager.get_path('src/paste.ico')))
        self.btn_paste.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.btn_paste.setFixedWidth(40)

        # Media type selection
        self.media_type = QtWidgets.QComboBox()
        self.media_type.addItem("Escolha uma opção")
        self.media_type.addItems(["Vídeo", "Áudio"])
        self.media_type.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

        self.checkbox_no_audio = QtWidgets.QCheckBox("Sem áudio")
        self.checkbox_no_audio.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.checkbox_no_audio.setFixedWidth(105)
        self.checkbox_no_audio.setVisible(False)

        # Quality and format
        self.label_quality = self._create_label("QUALIDADE")
        self.label_format = self._create_label("FORMATO")

        self.quality_combo = QtWidgets.QComboBox()
        self.quality_combo.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.quality_combo.setVisible(False)

        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.format_combo.setVisible(False)

        # Progress and actions
        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False)
        self.progress.setAlignment(QtCore.Qt.AlignCenter)
        self.progress_animator = TextAnimator(self.progress)

        self.btn_download = QtWidgets.QPushButton("Iniciar Download")
        self.btn_download.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.btn_download.setVisible(False)

        self.signature = QtWidgets.QLabel("by oBrazoo")
        self.signature.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom)
        self.signature.setStyleSheet("color: gray; font-size: 10px;")

    def _create_label(self, text: str) -> QtWidgets.QLabel:
        """Helper to create styled labels."""
        label = QtWidgets.QLabel(text)
        label.setStyleSheet("font-size: 16px;")
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setVisible(False)
        return label

    def _setup_layout(self) -> None:
        """Setup main layout structure."""
        layout = QtWidgets.QVBoxLayout(self)

        # URL row
        url_layout = QtWidgets.QHBoxLayout()
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.btn_paste)

        # Media type row
        type_layout = QtWidgets.QHBoxLayout()
        type_layout.addWidget(self.media_type)
        type_layout.addWidget(self.checkbox_no_audio)

        # Quality/format labels
        label_layout = QtWidgets.QHBoxLayout()
        label_layout.addWidget(self.label_quality)
        label_layout.addWidget(self.label_format)

        # Quality/format combos
        combo_layout = QtWidgets.QHBoxLayout()
        combo_layout.addWidget(self.quality_combo)
        combo_layout.addWidget(self.format_combo)

        # Assemble main layout
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

    def _setup_connections(self) -> None:
        """Setup signal-slot connections."""
        self.url_input.textChanged.connect(self._on_url_change)
        self.btn_paste.clicked.connect(self._paste_url)
        self.media_type.currentIndexChanged.connect(self._update_options)
        self.btn_download.clicked.connect(self._toggle_download)

    def _on_url_change(self, text: str) -> None:
        """Handle URL input changes."""
        valid = text.strip().startswith("http") and self.media_type.currentIndex() != 0
        self.btn_download.setVisible(valid)
        self.logger.info(f"URL changed: {text}")

    def _paste_url(self) -> None:
        """Paste URL from clipboard."""
        text = QtWidgets.QApplication.clipboard().text()
        self.url_input.setText(text)
        self.logger.info("Pasted from clipboard")

    def _update_options(self) -> None:
        """Update quality and format options based on media type."""
        self.quality_combo.clear()
        self.format_combo.clear()

        # Hide all optional elements initially
        for widget in [self.quality_combo, self.format_combo,
                       self.checkbox_no_audio, self.label_quality, self.label_format]:
            widget.setVisible(False)

        media_type = self.media_type.currentText()

        if media_type == "Vídeo":
            self.quality_combo.addItems(VIDEO_QUALITIES)
            self.format_combo.addItems(SUPPORTED_VIDEO_FORMATS)
            self.checkbox_no_audio.setVisible(True)
        elif media_type == "Áudio":
            self.quality_combo.addItems(AUDIO_QUALITIES)
            self.format_combo.addItems(SUPPORTED_AUDIO_FORMATS)

        # Show relevant elements
        for widget in [self.quality_combo, self.format_combo,
                       self.label_quality, self.label_format]:
            widget.setVisible(media_type in ["Vídeo", "Áudio"])

        self._on_url_change(self.url_input.text())

    def _toggle_download(self) -> None:
        """Toggle between start/cancel download."""
        if self.btn_download.text() == "Iniciar Download":
            self._start_download()
        else:
            self._cancel_download()

    def _start_download(self) -> None:
        """Start download process."""
        url = self.url_input.text().strip()
        media_type = self.media_type.currentText()
        quality = self.quality_combo.currentText()
        fmt = self.format_combo.currentText()
        no_audio = self.checkbox_no_audio.isChecked()

        # Setup progress UI
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.progress_animator.start_animation("starting")

        # Create and start worker thread
        self.thread = QtCore.QThread()
        self.worker = DownloadWorker(url, media_type, quality, fmt, no_audio)
        self.worker.moveToThread(self.thread)

        # Connect signals
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._update_progress)
        self.worker.finished.connect(self._finish_download)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()
        self.btn_download.setText("Cancelar")
        self.btn_download.setEnabled(True)

        self.logger.info(
                f"Download started - URL: {url}, Type: {media_type}, "
                f"Quality: {quality}, Format: {fmt}, No Audio: {no_audio}"
        )

    def _cancel_download(self) -> None:
        """Cancel current download."""
        if hasattr(self, 'worker'):
            self.worker.cancel()

        self.progress_animator.start_animation("canceling")
        QtCore.QTimer.singleShot(
                3000,
                lambda: self.progress_animator.stop_animation("❌ Download cancelado")
        )

    def _update_progress(self, percent: int, text: str) -> None:
        """Update download progress display."""
        self.progress.setValue(percent)

        if percent < 100:
            self.progress_animator.start_animation("downloading", percent)
        elif percent == 100:
            self.progress_animator.start_animation("finishing")
            QtCore.QTimer.singleShot(
                    3600,
                    lambda: self.progress_animator.stop_animation("✅ Download concluído!")
            )

    def _finish_download(self, success: bool, msg: str) -> None:
        """Handle download completion."""
        if success:
            self.progress.setFormat("✅ Download concluído!")
            self.logger.info("Download completed successfully.")
        elif "Cancelado" in msg:
            self.progress.setFormat("❌ Download cancelado")
            self.logger.warning("Download canceled by user")
        else:
            self.progress.setFormat(f"⚠️ {msg[:30]}...")
            self.logger.error(f"Download error: {msg}")

        QtCore.QTimer.singleShot(3000, lambda: self.progress.setVisible(False))
        self.progress.style().polish(self.progress)
        self.btn_download.setText("Iniciar Download")


def main():
    """Main application entry point."""
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Brazoo.HB_Downloader.1.0')

    app = QtWidgets.QApplication(sys.argv)

    # Setup fonts
    QFontDatabase.addApplicationFont(ResourceManager.get_path("src/font/Inter-Variable.ttf"))
    QFontDatabase.addApplicationFont(ResourceManager.get_path("src/font/Inter-Italic.ttf"))
    app.setFont(QFont("Inter Variable", 11))

    # Check for updates and show main window
    UpdateChecker.check_for_updates()

    window = DownloaderUI()
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()