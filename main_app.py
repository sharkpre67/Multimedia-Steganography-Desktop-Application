import sys
import os
import time
import vlc

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QStackedWidget, QRadioButton,
    QLineEdit, QTextEdit, QProgressBar, QFileDialog, QButtonGroup, QDialog,
    QSlider, QStyle, QMessageBox
)
from PySide6.QtGui import (
    QPainter, QLinearGradient, QColor, QFont, QPixmap, QTransform,
    QBitmap
)
from PySide6.QtCore import Qt, QPoint, QRect, QTimer, Property, QThread, Signal

# --- IMPORT MODULE GIẤU TIN ---
try:
    import steganography_text
    import steganography_image
    import steganography_sound
    import steganography_video
except ImportError as e:
    app_check = QApplication.instance()
    if not app_check:
        app_check = QApplication(sys.argv)
    error_dialog = QDialog()
    error_dialog.setWindowTitle("Lỗi nghiêm trọng")
    layout = QVBoxLayout()
    layout.addWidget(QLabel(f"LỖI: Không thể import các module giấu tin.\nHãy chắc chắn các file steganography_*.py tồn tại.\n\nChi tiết: {e}"))
    error_dialog.setLayout(layout)
    error_dialog.exec()
    sys.exit(1)



COLOR_GRADIENT_START = QColor("#0f2027")
COLOR_GRADIENT_MIDDLE = QColor("#203a43")
COLOR_GRADIENT_END = QColor("#2c5364")
COLOR_SIDEBAR = QColor("#122b35")
COLOR_FRAME_BG = QColor(32, 68, 79, 150)
COLOR_FRAME_BORDER = QColor("#2a5f6a")
COLOR_BUTTON = QColor("#329D9C")
COLOR_BUTTON_HOVER = QColor("#2b8483")
COLOR_BUTTON_PRESSED_BG = QColor("#226867")
COLOR_BUTTON_PRESSED_BORDER = QColor("#a0e0de")
COLOR_TEXT = QColor("#e8e8e8")
COLOR_TEXT_DARK = QColor("#a0a0a0")
COLOR_NAV_ACTIVE_BG = QColor("#2a5f6a")
COLOR_INPUT_BG = QColor("#1a3a42")
COLOR_SUCCESS = QColor("#329D9C")
COLOR_FAILURE = QColor("#d9534f")

class Worker(QThread):
    finished = Signal(object)
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit(f"Lỗi trong worker: {e}")

class ClickableLabel(QLabel):
    clicked = Signal()
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

class ClickableFrame(QFrame):
    clicked = Signal()
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

class SpinningDiscWidget(ClickableFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(150, 150)
        self.angle = 0

        disc_pixmap = QPixmap("disc2.png")
        if disc_pixmap.isNull():
            disc_pixmap = QPixmap(200, 200); disc_pixmap.fill(Qt.transparent)
            painter = QPainter(disc_pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(Qt.black); painter.drawEllipse(1, 1, 198, 198)
            painter.setBrush(QColor("#333333")); painter.drawEllipse(75, 75, 50, 50)
            painter.end()
        
        mask = QBitmap(disc_pixmap.size()); mask.fill(Qt.color0)
        mask_painter = QPainter(mask); mask_painter.setBrush(Qt.color1)
        mask_painter.drawEllipse(0, 0, disc_pixmap.width(), disc_pixmap.height())
        mask_painter.end()
        disc_pixmap.setMask(mask)
        self.original_pixmap = disc_pixmap

        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(40) 
        self.animation_timer.timeout.connect(self.rotate)

    def rotate(self):
        self.angle = (self.angle + 3) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        x, y = (self.width() - side) / 2, (self.height() - side) / 2
        painter.save()
        painter.translate(x + side / 2, y + side / 2); painter.rotate(self.angle); painter.translate(-(x + side / 2), -(y + side / 2))
        target_rect = QRect(int(x), int(y), int(side), int(side))
        painter.drawPixmap(target_rect, self.original_pixmap)
        painter.restore()
        
    def start_animation(self): self.animation_timer.start()
    def stop_animation(self): self.animation_timer.stop(); self.angle = 0; self.update()

class GradientWidget(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(QPoint(0, 0), QPoint(self.width(), self.height()))
        gradient.setColorAt(0.0, COLOR_GRADIENT_START); gradient.setColorAt(0.5, COLOR_GRADIENT_MIDDLE); gradient.setColorAt(1.0, COLOR_GRADIENT_END)
        painter.fillRect(self.rect(), gradient)

class NotificationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground); self.setObjectName("notificationDialog")
        self.main_frame = QFrame(self); self.main_frame.setObjectName("notificationPopup")
        layout = QVBoxLayout(self.main_frame)
        layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(15)
        self.icon_label = QLabel(); self.icon_label.setObjectName("notificationIcon")
        self.message_label = QLabel(); self.message_label.setObjectName("notificationText"); self.message_label.setWordWrap(True)
        self.confirm_button = QPushButton("Xác nhận"); self.confirm_button.clicked.connect(self.accept)
        layout.addWidget(self.icon_label, alignment=Qt.AlignCenter); layout.addWidget(self.message_label, alignment=Qt.AlignCenter); layout.addWidget(self.confirm_button, alignment=Qt.AlignCenter)
        main_layout = QVBoxLayout(self); main_layout.setContentsMargins(0,0,0,0); main_layout.addWidget(self.main_frame)
    def show_message(self, is_success, message):
        self.message_label.setText(message)
        self.icon_label.setText("✔" if is_success else "✖")
        self.main_frame.setProperty("status", "success" if is_success else "failure")
        self.main_frame.style().unpolish(self.main_frame); self.main_frame.style().polish(self.main_frame)
        self.adjustSize(); self.exec()


# --- LỚP ỨNG DỤNG CHÍNH ---
class SteganographyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Steganography - Ứng dụng Giấu tin")
        self.resize(1100, 800); self.setMinimumSize(800, 600)
        
        self.nav_buttons, self.embed_widgets, self.extract_widgets = {}, {}, {}
        self.worker, self.progress_timer = None, None
        self.current_progress = 0
        self.current_cover_pixmap_path = None
        self.current_media_path = None
        self.current_stego_pixmap_path = None
        self.current_stego_media_path = None

        try:
            self.vlc_instance = vlc.Instance()
            self.embed_media_player = self.vlc_instance.media_player_new()
            self.extract_media_player = self.vlc_instance.media_player_new()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi VLC", f"Không thể khởi tạo VLC. Hãy chắc chắn bạn đã cài đặt đúng phiên bản VLC Media Player (32-bit hoặc 64-bit) tương ứng với Python.\nLỗi: {e}")
            sys.exit(1)
        
        self.embed_vlc_timer = QTimer(self); self.embed_vlc_timer.setInterval(200)
        self.embed_vlc_timer.timeout.connect(self.update_embed_vlc_ui)
        
        self.extract_vlc_timer = QTimer(self); self.extract_vlc_timer.setInterval(200)
        self.extract_vlc_timer.timeout.connect(self.update_extract_vlc_ui)
        
        self.setStyleSheet(self.load_stylesheet())
        main_widget = QWidget(); main_layout = QHBoxLayout(main_widget); main_layout.setContentsMargins(0,0,0,0); main_layout.setSpacing(0)
        sidebar = self.create_sidebar(); main_layout.addWidget(sidebar)
        content_area = GradientWidget(); content_layout = QVBoxLayout(content_area); content_layout.setContentsMargins(30,20,30,20)
        self.stacked_widget = QStackedWidget(); self.stacked_widget.setStyleSheet("background: transparent;")
        self.embedding_view = self.create_embedding_view()
        self.extraction_view = self.create_extraction_view()
        self.stacked_widget.addWidget(self.embedding_view)
        self.stacked_widget.addWidget(self.extraction_view)
        content_layout.addWidget(self.stacked_widget); main_layout.addWidget(content_area, 1)
        self.setCentralWidget(main_widget)
        self.notification = NotificationDialog(self)
        self.update_active_nav("embedding")
        self._on_cover_type_changed()
        self._on_stego_type_changed()

    def create_embedding_view(self):
        view_widget = QWidget()
        layout = QVBoxLayout(view_widget); layout.setContentsMargins(0,0,0,0); layout.setSpacing(15)
        title = QLabel("Giao diện Giấu Tin"); title.setObjectName("viewTitle"); layout.addWidget(title)
        
        top_section_layout = QHBoxLayout()
        left_controls_widget = QWidget()
        left_controls_layout = QVBoxLayout(left_controls_widget); left_controls_layout.setContentsMargins(0,0,0,0); left_controls_layout.setSpacing(15)
        cover_file_frame = self.create_frame_cover_file()
        data_to_hide_frame = self.create_frame_data_to_hide()
        left_controls_layout.addWidget(cover_file_frame); left_controls_layout.addWidget(data_to_hide_frame); left_controls_layout.addStretch()
        top_section_layout.addWidget(left_controls_widget, 1)

        preview_frame = self.create_preview_frame(self.embed_widgets, self.embed_media_player, self.play_embed_media, self.set_embed_position, "cover")
        top_section_layout.addWidget(preview_frame, 1)
        
        layout.addLayout(top_section_layout, 1)
        bottom_layout = QHBoxLayout(); bottom_layout.addWidget(self.create_frame_security()); bottom_layout.addWidget(self.create_frame_output())
        layout.addLayout(bottom_layout)
        layout.addWidget(self.create_frame_progress(self.embed_widgets, self.hide_data))
        return view_widget

    def create_extraction_view(self):
        view_widget = QWidget()
        layout = QVBoxLayout(view_widget); layout.setContentsMargins(0,0,0,0); layout.setSpacing(15)
        title = QLabel("Giao diện Trích Xuất Tin"); title.setObjectName("viewTitle"); layout.addWidget(title)
        
        top_section_layout = QHBoxLayout()
        left_controls_widget = QWidget()
        left_controls_layout = QVBoxLayout(left_controls_widget); left_controls_layout.setContentsMargins(0,0,0,0); left_controls_layout.setSpacing(15)
        stego_file_frame = self.create_frame_stego_file()
        extract_security_frame = self.create_frame_extract_security()
        left_controls_layout.addWidget(stego_file_frame); left_controls_layout.addWidget(extract_security_frame); left_controls_layout.addStretch()
        top_section_layout.addWidget(left_controls_widget, 1)

        preview_frame = self.create_preview_frame(self.extract_widgets, self.extract_media_player, self.play_extract_media, self.set_extract_position, "stego")
        top_section_layout.addWidget(preview_frame, 1)

        layout.addLayout(top_section_layout, 1)
        layout.addWidget(self.create_frame_progress(self.extract_widgets, self.extract_data))
        layout.addWidget(self.create_frame_extract_result()); layout.addStretch()
        return view_widget

    def create_preview_frame(self, widgets_dict, media_player, play_callback, position_callback, name_prefix):
        frame = QFrame(); frame.setObjectName("functionalFrame")
        layout = QVBoxLayout(frame)
        title_text = "Xem trước Tệp Tin Nền (Nhấn để phóng to)" if name_prefix == "cover" else "Xem trước Tệp Tin Stego (Nhấn để phóng to)"
        title = QLabel(title_text); title.setObjectName("frameTitle")
        layout.addWidget(title)
        
        widgets_dict['preview_stack'] = QStackedWidget()
        layout.addWidget(widgets_dict['preview_stack'], 1)

        widgets_dict['text_preview'] = QTextEdit(); widgets_dict['text_preview'].setReadOnly(True)
        widgets_dict['text_preview'].mousePressEvent = lambda event: self.open_enlarged_preview(f'{name_prefix}_text')
        widgets_dict['preview_stack'].addWidget(widgets_dict['text_preview'])

        widgets_dict['image_preview'] = ClickableLabel(); widgets_dict['image_preview'].setObjectName("imagePreview"); widgets_dict['image_preview'].setAlignment(Qt.AlignCenter)
        widgets_dict['image_preview'].clicked.connect(lambda: self.open_enlarged_preview(f'{name_prefix}_image'))
        widgets_dict['preview_stack'].addWidget(widgets_dict['image_preview'])
        
        widgets_dict['audio_disc_preview'] = SpinningDiscWidget()
        widgets_dict['audio_disc_preview'].clicked.connect(lambda: self.open_enlarged_preview(f'{name_prefix}_audio'))
        widgets_dict['preview_stack'].addWidget(widgets_dict['audio_disc_preview'])

        widgets_dict['video_frame'] = ClickableFrame(); widgets_dict['video_frame'].setObjectName("videoFrame")
        widgets_dict['video_frame'].clicked.connect(lambda: self.open_enlarged_preview(f'{name_prefix}_video'))
        widgets_dict['preview_stack'].addWidget(widgets_dict['video_frame'])
        
        if sys.platform.startswith('win'): media_player.set_hwnd(widgets_dict['video_frame'].winId())
        
        widgets_dict['media_controls_widget'] = QWidget()
        controls_layout = QHBoxLayout(widgets_dict['media_controls_widget']); controls_layout.setContentsMargins(0,0,0,0)
        
        widgets_dict['play_button'] = QPushButton(); widgets_dict['play_button'].setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        widgets_dict['play_button'].clicked.connect(play_callback)
        widgets_dict['current_time_label'] = QLabel("00:00")
        widgets_dict['position_slider'] = QSlider(Qt.Horizontal); widgets_dict['position_slider'].setRange(0, 1000)
        widgets_dict['position_slider'].sliderMoved.connect(position_callback)
        widgets_dict['total_duration_label'] = QLabel("00:00")
        
        controls_layout.addWidget(widgets_dict['play_button']); controls_layout.addWidget(widgets_dict['current_time_label'])
        controls_layout.addWidget(widgets_dict['position_slider'], 1); controls_layout.addWidget(widgets_dict['total_duration_label'])
        layout.addWidget(widgets_dict['media_controls_widget'])
        
        return frame

    def _on_cover_type_changed(self):
        if 'cover_type_group' not in self.embed_widgets: return
        cover_type = self.embed_widgets['cover_type_group'].checkedButton().text()
        
        is_media = cover_type in ["Âm thanh", "Video"]
        self.embed_widgets['media_controls_widget'].setVisible(is_media)

        if cover_type == "Văn bản": self.embed_widgets['preview_stack'].setCurrentIndex(0)
        elif cover_type == "Hình ảnh": self.embed_widgets['preview_stack'].setCurrentIndex(1)
        elif cover_type == "Âm thanh": self.embed_widgets['preview_stack'].setCurrentIndex(2)
        elif cover_type == "Video": self.embed_widgets['preview_stack'].setCurrentIndex(3)

        options_map = {"Văn bản": ["Nhập trực tiếp", "Văn bản"], "Hình ảnh": ["Nhập trực tiếp", "Văn bản", "Hình ảnh"],
                       "Âm thanh": ["Nhập trực tiếp", "Văn bản", "Hình ảnh", "Âm thanh"],
                       "Video":   ["Nhập trực tiếp", "Văn bản", "Hình ảnh", "Âm thanh"]}
        valid_options = options_map.get(cover_type, [])
        data_type_layout = self.embed_widgets['data_type_layout']
        while data_type_layout.count():
            child = data_type_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
        button_group = QButtonGroup(self); self.embed_widgets['data_type_group'] = button_group
        for option in valid_options:
            radio_button = QRadioButton(option); data_type_layout.addWidget(radio_button); button_group.addButton(radio_button)
            if option == "Nhập trực tiếp": radio_button.setChecked(True)
        data_type_layout.addStretch(); button_group.buttonClicked.connect(self._on_data_type_changed)
        self._on_data_type_changed()
        
        self.embed_widgets['cover_path_input'].clear()
        self.embed_widgets['image_preview'].clear()
        self.embed_widgets['text_preview'].clear()
        if self.embed_media_player.is_playing(): self.embed_media_player.stop()
        self.embed_widgets['audio_disc_preview'].stop_animation()
        self.current_cover_pixmap_path = None
        self.current_media_path = None

    def _on_stego_type_changed(self):
        if 'stego_type_group' not in self.extract_widgets: return
        cover_type = self.extract_widgets['stego_type_group'].checkedButton().text()
        is_media = cover_type in ["Âm thanh", "Video"]
        self.extract_widgets['media_controls_widget'].setVisible(is_media)

        if cover_type == "Văn bản": self.extract_widgets['preview_stack'].setCurrentIndex(0)
        elif cover_type == "Hình ảnh": self.extract_widgets['preview_stack'].setCurrentIndex(1)
        elif cover_type == "Âm thanh": self.extract_widgets['preview_stack'].setCurrentIndex(2)
        elif cover_type == "Video": self.extract_widgets['preview_stack'].setCurrentIndex(3)

        self.extract_widgets['stego_path_input'].clear()
        self.extract_widgets['image_preview'].clear()
        self.extract_widgets['text_preview'].clear()
        if self.extract_media_player.is_playing(): self.extract_media_player.stop()
        self.extract_widgets['audio_disc_preview'].stop_animation()
        self.current_stego_pixmap_path = None
        self.current_stego_media_path = None
    
    def play_embed_media(self): self.play_media_generic(self.embed_media_player, self.embed_vlc_timer, self.embed_widgets, 'cover_type_group')
    def play_extract_media(self): self.play_media_generic(self.extract_media_player, self.extract_vlc_timer, self.extract_widgets, 'stego_type_group')
    def set_embed_position(self, v): self.set_position_generic(self.embed_media_player, v)
    def set_extract_position(self, v): self.set_position_generic(self.extract_media_player, v)
    def update_embed_vlc_ui(self): self.update_vlc_ui_generic(self.embed_media_player, self.embed_vlc_timer, self.embed_widgets)
    def update_extract_vlc_ui(self): self.update_vlc_ui_generic(self.extract_media_player, self.extract_vlc_timer, self.extract_widgets)

    def play_media_generic(self, player, timer, widgets, group_name):
        if player.get_media() is None: return
        if player.is_playing():
            player.pause(); timer.stop(); widgets['audio_disc_preview'].stop_animation()
        else:
            player.play(); timer.start()
            if widgets[group_name].checkedButton().text() == "Âm thanh": widgets['audio_disc_preview'].start_animation()
        self.update_vlc_ui_generic(player, timer, widgets)
    
    def set_position_generic(self, player, value):
        if player.get_media() is not None: player.set_position(value / 1000.0)

    def format_time(self, milliseconds):
        if milliseconds < 0: milliseconds = 0
        seconds = milliseconds // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def update_vlc_ui_generic(self, player, timer, widgets):
        pos = player.get_position()
        widgets['position_slider'].blockSignals(True); widgets['position_slider'].setValue(int(pos * 1000)); widgets['position_slider'].blockSignals(False)
        widgets['current_time_label'].setText(self.format_time(player.get_time()))
        widgets['total_duration_label'].setText(self.format_time(player.get_length()))
        widgets['play_button'].setIcon(self.style().standardIcon(QStyle.SP_MediaPause if player.is_playing() else QStyle.SP_MediaPlay))
        if player.get_state() == vlc.State.Ended:
            player.stop(); timer.stop(); widgets['audio_disc_preview'].stop_animation()
            self.update_vlc_ui_generic(player, timer, widgets)

    def browse_cover_file_and_show_preview(self):
        cover_type = self.embed_widgets['cover_type_group'].checkedButton().text()
        file_filter = ""
        if cover_type == "Văn bản": file_filter = "Text Files (*.txt)"
        elif cover_type == "Hình ảnh": file_filter = "Image Files (*.png *.jpg *.bmp)"
        elif cover_type == "Âm thanh": file_filter = "Audio Files (*.mp3 *.wav *.ogg)"
        elif cover_type == "Video": file_filter = "Video Files (*.mp4 *.avi *.mkv)"
        file_path, _ = QFileDialog.getOpenFileName(self, f"Chọn Tệp Tin Nền {cover_type}", "", file_filter)
        if file_path:
            self.current_media_path = file_path
            self.embed_widgets['cover_path_input'].setText(file_path)
            if self.embed_media_player.is_playing(): self.embed_media_player.stop()
            self.embed_widgets['audio_disc_preview'].stop_animation()
            self.embed_media_player.audio_set_volume(100)
            if cover_type == "Văn bản":
                self.embed_widgets['preview_stack'].setCurrentIndex(0)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f: self.embed_widgets['text_preview'].setText(f.read())
                except Exception as e: self.embed_widgets['text_preview'].setText(f"Không thể đọc tệp: {e}")
            elif cover_type == "Hình ảnh":
                self.embed_widgets['preview_stack'].setCurrentIndex(1)
                self.current_cover_pixmap_path = file_path
                pixmap = QPixmap(file_path)
                self.embed_widgets['image_preview'].setPixmap(pixmap.scaled(self.embed_widgets['image_preview'].size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            elif cover_type in ["Âm thanh", "Video"]:
                idx = 2 if cover_type == "Âm thanh" else 3
                self.embed_widgets['preview_stack'].setCurrentIndex(idx)
                media = self.vlc_instance.media_new(file_path)
                self.embed_media_player.set_media(media)
                self.play_embed_media()

    def browse_stego_file_and_show_preview(self):
        cover_type = self.extract_widgets['stego_type_group'].checkedButton().text()
        file_filter = ""
        if cover_type == "Văn bản": file_filter = "Text Files (*.txt)"
        elif cover_type == "Hình ảnh": file_filter = "Image Files (*.png *.jpg *.bmp)"
        elif cover_type == "Âm thanh": file_filter = "Audio Files (*.mp3 *.wav *.ogg)"
        elif cover_type == "Video": file_filter = "Video Files (*.mp4 *.avi *.mkv)"
        file_path, _ = QFileDialog.getOpenFileName(self, f"Chọn Tệp Tin Stego {cover_type}", "", file_filter)
        if file_path:
            self.current_stego_media_path = file_path
            self.extract_widgets['stego_path_input'].setText(file_path)
            if self.extract_media_player.is_playing(): self.extract_media_player.stop()
            self.extract_widgets['audio_disc_preview'].stop_animation()
            self.extract_media_player.audio_set_volume(100)
            
            if cover_type == "Văn bản":
                self.extract_widgets['preview_stack'].setCurrentIndex(0)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f: self.extract_widgets['text_preview'].setText(f.read())
                except Exception as e: self.extract_widgets['text_preview'].setText(f"Không thể đọc tệp: {e}")
            elif cover_type == "Hình ảnh":
                self.extract_widgets['preview_stack'].setCurrentIndex(1)
                self.current_stego_pixmap_path = file_path
                pixmap = QPixmap(file_path)
                self.extract_widgets['image_preview'].setPixmap(pixmap.scaled(self.extract_widgets['image_preview'].size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            elif cover_type in ["Âm thanh", "Video"]:
                idx = 2 if cover_type == "Âm thanh" else 3
                self.extract_widgets['preview_stack'].setCurrentIndex(idx)
                media = self.vlc_instance.media_new(file_path)
                self.extract_media_player.set_media(media)
                self.play_extract_media()

    def open_enlarged_preview(self, preview_type):
        media_player, media_path, pixmap_path, text_content = None, None, None, None
        
        parts = preview_type.split('_')
        source_tab, media_type = parts[0], parts[1]

        if source_tab == 'cover':
            was_playing = self.embed_media_player.is_playing()
            if was_playing: self.embed_media_player.pause()
            media_player_to_resume = self.embed_media_player
            media_path = self.current_media_path
            pixmap_path = self.current_cover_pixmap_path
            text_content = self.embed_widgets['text_preview'].toPlainText()
        else: # stego
            was_playing = self.extract_media_player.is_playing()
            if was_playing: self.extract_media_player.pause()
            media_player_to_resume = self.extract_media_player
            media_path = self.current_stego_media_path
            pixmap_path = self.current_stego_pixmap_path
            text_content = self.extract_widgets['text_preview'].toPlainText()

        dialog = QDialog(self); dialog.setWindowTitle("Xem trước phóng to"); dialog.setMinimumSize(800, 600); dialog.setStyleSheet("background-color: #203a43;")
        layout = QVBoxLayout(dialog)

        if media_type == 'image':
            if not pixmap_path: return
            pixmap = QPixmap(pixmap_path)
            label = QLabel(); label.setPixmap(pixmap.scaled(dialog.size() * 0.95, Qt.KeepAspectRatio, Qt.SmoothTransformation)); label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
        
        elif media_type == 'text':
            if not text_content: return
            text_edit = QTextEdit(); text_edit.setPlainText(text_content); text_edit.setReadOnly(True)
            layout.addWidget(text_edit)

        elif media_type in ['audio', 'video']:
            if not media_path: return
            enlarged_player = self.vlc_instance.media_player_new()
            video_frame = QFrame()
            if sys.platform.startswith('win'): enlarged_player.set_hwnd(video_frame.winId())
            if media_type == 'audio':
                disc_widget = SpinningDiscWidget(); layout.addWidget(disc_widget); disc_widget.start_animation()
                dialog.finished.connect(disc_widget.stop_animation)
            else: layout.addWidget(video_frame, 1)
            media = self.vlc_instance.media_new(media_path); enlarged_player.set_media(media)
            enlarged_player.audio_set_volume(100); enlarged_player.play()
            dialog.finished.connect(enlarged_player.release)

        dialog.exec()
        if was_playing: media_player_to_resume.play()

    def switch_view(self, index, button_name):
        if self.embed_media_player.is_playing(): self.embed_media_player.pause()
        if self.extract_media_player.is_playing(): self.extract_media_player.pause()
        self.stacked_widget.setCurrentIndex(index)
        self.update_active_nav(button_name)

    def closeEvent(self, event):
        self.embed_media_player.release()
        self.extract_media_player.release()
        event.accept()
    
    # --- CÁC HÀM CÒN LẠI KHÔNG THAY ĐỔI ---
    def load_stylesheet(self):
        return f"""
            #sidebar {{ background-color:{COLOR_SIDEBAR.name()};}} 
            #logoIcon{{font-size:24px;color:{COLOR_BUTTON.name()};}}
            #logoTitle{{font-size:22px;font-weight:bold;color:{COLOR_TEXT.name()};}}
            #sidebar QPushButton{{background-color:transparent;color:{COLOR_TEXT.name()};border:none;padding:12px;font-size:15px;font-weight:bold;text-align:left;border-radius:8px;}}
            #sidebar QPushButton:hover{{background-color:{COLOR_NAV_ACTIVE_BG.name()};}} 
            #sidebar QPushButton[active="true"]{{background-color:{COLOR_NAV_ACTIVE_BG.name()};}}
            #quitButton{{color:{COLOR_TEXT_DARK.name()};}} #quitButton:hover{{color:{COLOR_TEXT.name()};}}
            #viewTitle{{font-size:24px;font-weight:bold;color:{COLOR_TEXT.name()};padding-bottom:10px;}}
            #functionalFrame{{background-color:{COLOR_FRAME_BG.name(QColor.HexArgb)};border:1px solid {COLOR_FRAME_BORDER.name()};border-radius:15px;padding:15px;}}
            #frameTitle{{font-size:15px;font-weight:bold;color:{COLOR_TEXT.name()};padding:5px 5px 0px 5px;}}
            QLabel{{color:{COLOR_TEXT_DARK.name()};font-size:14px;background:transparent;}}
            #imagePreview {{
                border: 2px dashed {COLOR_FRAME_BORDER.name()}; border-radius: 8px;
                background-color: {COLOR_INPUT_BG.name()};
                color: {COLOR_TEXT_DARK.name()};
            }}
            #imagePreview:hover {{ border-color: {COLOR_BUTTON.name()}; }}
            QRadioButton{{color:{COLOR_TEXT_DARK.name()};font-size:13px;spacing:5px;}} QRadioButton::indicator{{width:15px;height:15px;}}
            QLineEdit,QTextEdit{{background-color:{COLOR_INPUT_BG.name()};color:{COLOR_TEXT.name()};border:1px solid {COLOR_FRAME_BORDER.name()};border-radius:8px;padding:8px;font-size:14px;}}
            QLineEdit:focus,QTextEdit:focus{{border:1px solid {COLOR_BUTTON.name()};}} 
            QTextEdit{{min-height:70px;}}
            QPushButton{{background-color:{COLOR_BUTTON.name()};color:white;font-weight:bold;font-size:14px;border:2px solid {COLOR_FRAME_BORDER.name()};border-radius:8px;padding:8px 16px;min-height:20px;}}
            QPushButton:hover{{background-color:{COLOR_BUTTON_HOVER.name()};border-color:{COLOR_BUTTON.name()};}}
            QPushButton:pressed{{background-color:{COLOR_BUTTON_PRESSED_BG.name()};border-color:{COLOR_BUTTON_PRESSED_BORDER.name()};}}
            #actionButton{{padding:12px;font-size:16px;}}
            QProgressBar{{border:1px solid {COLOR_FRAME_BORDER.name()};background-color:{COLOR_INPUT_BG.name()};border-radius:8px;text-align:center;height:16px;}}
            QProgressBar::chunk{{background-color:{COLOR_BUTTON.name()};border-radius:7px;}}
            #notificationDialog{{background:transparent;}}
            #notificationPopup{{border-radius:15px;background-color:{COLOR_FRAME_BG.name(QColor.HexArgb)};border:1px solid {COLOR_FRAME_BORDER.name()};}}
            #notificationPopup[status="success"]{{border:1px solid {COLOR_SUCCESS.name()};}} 
            #notificationPopup[status="failure"]{{border:1px solid {COLOR_FAILURE.name()};}}
            #notificationIcon{{font-size:48px;font-weight:bold;}} 
            #notificationText{{font-size:16px;color:{COLOR_TEXT.name()};}}
            #notificationPopup[status="success"] #notificationIcon{{color:{COLOR_SUCCESS.name()};}} 
            #notificationPopup[status="failure"] #notificationIcon{{color:{COLOR_FAILURE.name()};}}
            #videoFrame {{ background-color: black; border: 1px solid #1a3a42; }}
        """
    def create_sidebar(self):
        sidebar_widget = QWidget(); sidebar_widget.setFixedWidth(240); sidebar_widget.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar_widget); sidebar_layout.setContentsMargins(20,20,20,20); sidebar_layout.setSpacing(10)
        title_layout = QHBoxLayout(); logo_label = QLabel("❖"); logo_label.setObjectName("logoIcon"); title_label = QLabel("Steganography"); title_label.setObjectName("logoTitle")
        title_layout.addWidget(logo_label); title_layout.addWidget(title_label); title_layout.addStretch(); sidebar_layout.addLayout(title_layout); sidebar_layout.addSpacing(20)
        self.nav_buttons['embedding'] = QPushButton("Giấu Tin (Embed)"); self.nav_buttons['embedding'].clicked.connect(lambda: self.switch_view(0, 'embedding'))
        self.nav_buttons['extraction'] = QPushButton("Trích Xuất (Extract)"); self.nav_buttons['extraction'].clicked.connect(lambda: self.switch_view(1, 'extraction'))
        sidebar_layout.addWidget(self.nav_buttons['embedding']); sidebar_layout.addWidget(self.nav_buttons['extraction']); sidebar_layout.addStretch()
        quit_button = QPushButton("← Thoát"); quit_button.setObjectName("quitButton"); quit_button.clicked.connect(self.close); sidebar_layout.addWidget(quit_button)
        return sidebar_widget
    def create_frame(self, title_text):
        frame = QFrame(); frame.setObjectName("functionalFrame"); layout = QVBoxLayout(frame); layout.setSpacing(10)
        title = QLabel(title_text); title.setObjectName("frameTitle"); layout.addWidget(title)
        return frame, layout
    def create_frame_cover_file(self):
        frame, layout = self.create_frame("1. Chọn Tệp Tin Nền")
        radio_layout = QHBoxLayout(); button_group = QButtonGroup(self); self.embed_widgets['cover_type_group'] = button_group
        options = ["Văn bản", "Hình ảnh", "Âm thanh", "Video"]
        for option in options:
            radio_button = QRadioButton(option)
            if option == "Hình ảnh": radio_button.setChecked(True)
            radio_layout.addWidget(radio_button); button_group.addButton(radio_button)
        radio_layout.addStretch(); layout.addLayout(radio_layout)
        button_group.buttonClicked.connect(self._on_cover_type_changed)
        file_layout = QHBoxLayout(); self.embed_widgets['cover_path_input'] = QLineEdit(placeholderText="Chưa có tệp nào được chọn")
        browse_button = QPushButton("Duyệt..."); browse_button.clicked.connect(self.browse_cover_file_and_show_preview)
        file_layout.addWidget(self.embed_widgets['cover_path_input']); file_layout.addWidget(browse_button); layout.addLayout(file_layout)
        return frame
    def create_frame_data_to_hide(self):
        frame, layout = self.create_frame("2. Chọn Dữ Liệu Cần Giấu")
        self.embed_widgets['data_type_layout'] = QHBoxLayout(); layout.addLayout(self.embed_widgets['data_type_layout'])
        self.embed_widgets['data_file_widget'] = QWidget(); file_layout = QHBoxLayout(self.embed_widgets['data_file_widget']); file_layout.setContentsMargins(0,0,0,0)
        self.embed_widgets['data_path_input'] = QLineEdit(placeholderText="Chọn tệp tin cần giấu...")
        browse_button = QPushButton("Duyệt..."); browse_button.clicked.connect(lambda: self.browse_file(self.embed_widgets['data_path_input'], "Chọn Tệp Tin Cần Giấu"))
        file_layout.addWidget(self.embed_widgets['data_path_input']); file_layout.addWidget(browse_button); layout.addWidget(self.embed_widgets['data_file_widget'])
        self.embed_widgets['secret_text_input'] = QTextEdit(placeholderText="Nhập văn bản bí mật của bạn vào đây"); layout.addWidget(self.embed_widgets['secret_text_input'])
        return frame
    def _on_data_type_changed(self):
        if 'data_type_group' not in self.embed_widgets: return
        data_type = self.embed_widgets['data_type_group'].checkedButton().text()
        is_direct_input = (data_type == "Nhập trực tiếp")
        self.embed_widgets['secret_text_input'].setVisible(is_direct_input)
        self.embed_widgets['data_file_widget'].setVisible(not is_direct_input)
    def create_frame_security(self):
        frame, layout = self.create_frame("3. Nhập mật khẩu")
        self.embed_widgets['password_input'] = QLineEdit(placeholderText="Mật khẩu", echoMode=QLineEdit.Password)
        self.embed_widgets['confirm_password_input'] = QLineEdit(placeholderText="Xác nhận mật khẩu", echoMode=QLineEdit.Password)
        layout.addWidget(self.embed_widgets['password_input']); layout.addWidget(self.embed_widgets['confirm_password_input'])
        return frame
    def create_frame_output(self):
        frame, layout = self.create_frame("4. Vị trí Lưu Tệp Tin")
        file_layout = QHBoxLayout(); self.embed_widgets['output_path_input'] = QLineEdit(placeholderText="Chọn vị trí lưu tệp đầu ra...")
        browse_button = QPushButton("Lưu dưới dạng..."); browse_button.clicked.connect(lambda: self.browse_save_file(self.embed_widgets['output_path_input'], "Lưu Tệp Tin Đầu Ra"))
        file_layout.addWidget(self.embed_widgets['output_path_input']); file_layout.addWidget(browse_button); layout.addLayout(file_layout)
        return frame
    def create_frame_stego_file(self):
        frame, layout = self.create_frame("1. Chọn Tệp Tin Đã Giấu Dữ Liệu")
        radio_layout = QHBoxLayout(); button_group = QButtonGroup(self); self.extract_widgets['stego_type_group'] = button_group
        options = ["Văn bản", "Hình ảnh", "Âm thanh", "Video"]
        for option in options:
            radio_button = QRadioButton(option)
            if option == "Hình ảnh": radio_button.setChecked(True)
            radio_layout.addWidget(radio_button); button_group.addButton(radio_button)
        radio_layout.addStretch(); layout.addLayout(radio_layout)
        button_group.buttonClicked.connect(self._on_stego_type_changed)
        file_layout = QHBoxLayout(); self.extract_widgets['stego_path_input'] = QLineEdit(placeholderText="Chưa có tệp nào được chọn")
        browse_button = QPushButton("Duyệt..."); browse_button.clicked.connect(self.browse_stego_file_and_show_preview)
        file_layout.addWidget(self.extract_widgets['stego_path_input']); file_layout.addWidget(browse_button); layout.addLayout(file_layout)
        return frame
    def create_frame_extract_security(self):
        frame, layout = self.create_frame("2. Nhập Mật khẩu & Vị trí Lưu")
        self.extract_widgets['password_input'] = QLineEdit(placeholderText="Nhập mật khẩu để giải mã", echoMode=QLineEdit.Password); layout.addWidget(self.extract_widgets['password_input'])
        self.extract_widgets['output_folder_input'] = QLineEdit(placeholderText="Chọn thư mục để lưu kết quả...")
        browse_button = QPushButton("Duyệt Thư mục..."); browse_button.clicked.connect(lambda: self.browse_folder(self.extract_widgets['output_folder_input'], "Chọn Thư mục Lưu"))
        output_layout = QHBoxLayout(); output_layout.addWidget(self.extract_widgets['output_folder_input']); output_layout.addWidget(browse_button); layout.addLayout(output_layout)
        return frame
    def create_frame_extract_result(self):
        frame, layout = self.create_frame("Kết quả Trích xuất")
        self.extract_widgets['result_text'] = QTextEdit(); self.extract_widgets['result_text'].setReadOnly(True); layout.addWidget(self.extract_widgets['result_text'])
        return frame
    def create_frame_progress(self, widgets_dict, action_callback):
        frame = QFrame(); frame.setObjectName("functionalFrame"); layout = QVBoxLayout(frame);
        top_layout = QHBoxLayout()
        widgets_dict['status_label'] = QLabel("Sẵn sàng xử lý"); top_layout.addWidget(widgets_dict['status_label'], 1)
        action_button = QPushButton("Bắt đầu Xử lý"); action_button.setObjectName("actionButton"); action_button.clicked.connect(action_callback); widgets_dict['process_button'] = action_button
        top_layout.addWidget(action_button)
        bottom_layout = QHBoxLayout()
        widgets_dict['progress_bar'] = QProgressBar(); widgets_dict['progress_bar'].setValue(0); widgets_dict['progress_bar'].setTextVisible(False)
        widgets_dict['percentage_label'] = QLabel("0%");
        bottom_layout.addWidget(widgets_dict['progress_bar'], 1); bottom_layout.addWidget(widgets_dict['percentage_label'])
        layout.addLayout(top_layout); layout.addLayout(bottom_layout)
        return frame
    def start_progress_simulation(self, widgets_dict):
        self.current_progress = 0
        self.widgets_to_update = widgets_dict
        self.widgets_to_update['progress_bar'].setValue(0); self.widgets_to_update['percentage_label'].setText("0%")
        self.progress_timer = QTimer(self); self.progress_timer.timeout.connect(self.update_progress_simulation); self.progress_timer.start(50)
    def update_progress_simulation(self):
        if self.current_progress < 99:
            self.current_progress += 1
            self.widgets_to_update['progress_bar'].setValue(self.current_progress)
            self.widgets_to_update['percentage_label'].setText(f"{self.current_progress}%")
    def stop_progress_simulation(self, success=True):
        if self.progress_timer and self.progress_timer.isActive(): self.progress_timer.stop()
        if success:
            self.widgets_to_update['progress_bar'].setValue(100); self.widgets_to_update['percentage_label'].setText("100%")
        else:
            self.widgets_to_update['progress_bar'].setValue(0); self.widgets_to_update['percentage_label'].setText("Lỗi!")
    def browse_file(self, line_edit_widget, caption):
        file_path, _ = QFileDialog.getOpenFileName(self, caption)
        if file_path: line_edit_widget.setText(file_path)
    def browse_save_file(self, line_edit_widget, caption):
        file_path, _ = QFileDialog.getSaveFileName(self, caption)
        if file_path: line_edit_widget.setText(file_path)
    def browse_folder(self, line_edit_widget, caption):
        folder_path = QFileDialog.getExistingDirectory(self, caption)
        if folder_path: line_edit_widget.setText(folder_path)
    def hide_data(self):
        cover_type = self.embed_widgets['cover_type_group'].checkedButton().text()
        data_type_text = self.embed_widgets['data_type_group'].checkedButton().text()
        cover_path = self.embed_widgets['cover_path_input'].text()
        output_path = self.embed_widgets['output_path_input'].text()
        password = self.embed_widgets['password_input'].text()
        confirm_password = self.embed_widgets['confirm_password_input'].text()
        is_file = (data_type_text != "Nhập trực tiếp")
        secret_data_to_pass = self.embed_widgets['data_path_input'].text() if is_file else self.embed_widgets['secret_text_input'].toPlainText()

        if not all([cover_path, output_path]): self.notification.show_message(False, "Vui lòng chọn tệp nền và vị trí lưu."); return
        if password != confirm_password: self.notification.show_message(False, "Mật khẩu không khớp."); return
        if not secret_data_to_pass: self.notification.show_message(False, "Dữ liệu cần giấu không được để trống."); return

        func, args = None, []
        try:
            if cover_type == "Văn bản":
                if is_file:
                    with open(secret_data_to_pass, 'r', encoding='utf-8') as f: secret_data_to_pass = f.read()
                func = steganography_text.embed_securely_in_text
                with open(cover_path, 'r', encoding='utf-8') as f: cover_text = f.read()
                args = [cover_text, secret_data_to_pass, password]
            else:
                if cover_type == "Hình ảnh": func = steganography_image.hide_securely_in_image; data_type = 'file' if is_file else 'text'; args = [cover_path, output_path,password,secret_data_to_pass,data_type]
                elif cover_type == "Âm thanh": func = steganography_sound.hide_securely_in_audio; data_type = 'file' if is_file else 'text'; args = [cover_path, output_path,password,secret_data_to_pass,data_type]
                elif cover_type == "Video": func = steganography_video.embed_securely; data_type_for_video = 'file' if is_file else 'text'; args = [cover_path, output_path, password, secret_data_to_pass, data_type_for_video]
            
            if func:
                self.embed_widgets['process_button'].setEnabled(False)
                self.embed_widgets['status_label'].setText(f"Đang giấu tin vào {cover_type}..."); self.start_progress_simulation(self.embed_widgets)
                self.worker = Worker(func, *args); self.worker.finished.connect(self.on_embedding_finished); self.worker.start()
            else: self.notification.show_message(False, "Phương pháp chưa được hỗ trợ.")
        except Exception as e:
            import traceback 
            traceback.print_exc() 
            self.notification.show_message(False, f"Lỗi khi chuẩn bị giấu tin:\n{e}"); self.embed_widgets['process_button'].setEnabled(True); self.stop_progress_simulation(False)
    def extract_data(self):
        stego_type = self.extract_widgets['stego_type_group'].checkedButton().text()
        stego_path = self.extract_widgets['stego_path_input'].text()
        password = self.extract_widgets['password_input'].text()
        output_folder = self.extract_widgets['output_folder_input'].text()
        if not all([stego_path, output_folder]): self.notification.show_message(False, "Vui lòng chọn tệp và thư mục lưu."); return
        
        func, args = None, []
        try:
            if stego_type == "Văn bản":
                func = steganography_text.extract_securely_from_text
                with open(stego_path, 'r', encoding='utf-8') as f: stego_text = f.read()
                args = [stego_text, password]
            elif stego_type == "Hình ảnh": func = steganography_image.extract_securely_from_image; args = [stego_path, password, output_folder]
            elif stego_type == "Âm thanh": func = steganography_sound.extract_securely_from_audio; args = [stego_path, password, output_folder]
            elif stego_type == "Video": func = steganography_video.extract_securely; args = [stego_path, password, output_folder]
            
            if func:
                self.extract_widgets['process_button'].setEnabled(False)
                self.extract_widgets['status_label'].setText(f"Đang trích xuất từ {stego_type}..."); self.extract_widgets['result_text'].clear(); self.start_progress_simulation(self.extract_widgets)
                self.worker = Worker(func, *args); self.worker.finished.connect(self.on_extraction_finished); self.worker.start()
            else: self.notification.show_message(False, "Phương pháp chưa được hỗ trợ.")
        except Exception as e:
            self.notification.show_message(False, f"Lỗi khi chuẩn bị trích xuất:\n{e}"); self.extract_widgets['process_button'].setEnabled(True); self.stop_progress_simulation(False)
    def on_embedding_finished(self, result):
        self.stop_progress_simulation(True); self.embed_widgets['process_button'].setEnabled(True); self.embed_widgets['status_label'].setText("Sẵn sàng xử lý")
        if result is True or (isinstance(result, str) and not str(result).lower().startswith("lỗi")):
            if isinstance(result, str):
                output_path = self.embed_widgets['output_path_input'].text()
                try:
                    with open(output_path, 'w', encoding='utf-8') as f: f.write(result)
                    self.notification.show_message(True, "Giấu tin thành công!")
                except Exception as e: self.notification.show_message(False, f"Lỗi khi lưu tệp: {e}"); self.stop_progress_simulation(False)
            else: self.notification.show_message(True, "Giấu tin thành công!")
        else: self.notification.show_message(False, f"Giấu tin thất bại:\n{result}"); self.stop_progress_simulation(False)
    def on_extraction_finished(self, result):
        self.stop_progress_simulation(True); self.extract_widgets['process_button'].setEnabled(True); self.extract_widgets['status_label'].setText("Sẵn sàng xử lý")
        success, message = False, "Không có dữ liệu hoặc lỗi không xác định."
        if isinstance(result, str) and result not in ["SAI_MAT_KHAU", ""]: success, message = True, result
        elif isinstance(result, bytes):
            success, file_path = True, os.path.join(self.extract_widgets['output_folder_input'].text(), "extracted_data.bin")
            try:
                with open(file_path, 'wb') as f: f.write(result)
                message = f"Dữ liệu nhị phân đã được lưu tại:\n{file_path}"
            except Exception as e: message = f"Lỗi khi lưu tệp nhị phân: {e}"
        elif isinstance(result, tuple) and len(result) == 2: success, message = result
        elif result == "SAI_MAT_KHAU": message = "Trích xuất thất bại: Sai mật khẩu."
        elif not result: message = "Trích xuất thất bại: Không tìm thấy dữ liệu hoặc có lỗi."
        if success:
            self.notification.show_message(True, "Trích xuất thành công!"); self.extract_widgets['result_text'].setText(message)
        else:
            self.notification.show_message(False, message); self.extract_widgets['result_text'].setText(f"Thất bại: {message}"); self.stop_progress_simulation(False)
    def update_active_nav(self, active_button_name):
        for name, button in self.nav_buttons.items():
            button.setProperty("active", name == active_button_name)
            button.style().unpolish(button); button.style().polish(button)
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.embed_widgets['cover_type_group'].checkedButton().text() == "Hình ảnh" and self.current_cover_pixmap_path:
            pixmap = QPixmap(self.current_cover_pixmap_path)
            self.embed_widgets['image_preview'].setPixmap(pixmap.scaled(self.embed_widgets['image_preview'].size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if self.extract_widgets['stego_type_group'].checkedButton().text() == "Hình ảnh" and self.current_stego_pixmap_path:
            pixmap = QPixmap(self.current_stego_pixmap_path)
            self.extract_widgets['image_preview'].setPixmap(pixmap.scaled(self.extract_widgets['image_preview'].size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SteganographyApp()
    window.show()
    sys.exit(app.exec())