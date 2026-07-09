"""设置对话框：编辑笔记目录与 LLM 必填配置（模型地址 / 密钥 / 模型名称）。

仅负责采集与校验输入，落盘与重建 Agent 由调用方（ChatWindow）完成。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config import AppConfig

DIALOG_STYLE = """
* { font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", sans-serif; }
QDialog { background: #F7F6F3; }
QLabel#dlgTitle { color: #23211E; font-size: 16px; font-weight: 600; }
QLabel#dlgHint { color: #A8A296; font-size: 12px; }
QLabel { color: #4A463F; font-size: 13px; }
QLineEdit {
    background: #FFFFFF; border: 1px solid #E4DFD4; border-radius: 8px;
    padding: 7px 10px; color: #23211E; font-size: 13.5px;
    selection-background-color: #BfDAD6;
    min-height: 20px;  min-width: 350px;
}
QLineEdit:focus { border: 1px solid #2A6F6B; }
QPushButton#browse {
    background: #EFE7DA; color: #8A6D3B; border: none; border-radius: 8px;
    padding: 7px 12px; font-size: 13px;
}
QPushButton#browse:hover { background: #E6DBC9; }
QPushButton#cancel {
    background: transparent; color: #8A857C; border: 1px solid #E4DFD4;
    border-radius: 9px; padding: 8px 18px; font-size: 13.5px;
}
QPushButton#cancel:hover { color: #6F6A62; border-color: #D6D0C4; }
QPushButton#save {
    background: #2A6F6B; color: #FFFFFF; border: none;
    border-radius: 9px; padding: 8px 20px; font-size: 13.5px; font-weight: 600;
}
QPushButton#save:hover { background: #235B57; }
"""


class SettingsDialog(QDialog):
    """采集设置项；exec() 返回 Accepted 后用 values() 取值。"""

    def __init__(self, config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setStyleSheet(DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(6)

        title = QLabel("设置")
        title.setObjectName("dlgTitle")
        root.addWidget(title)
        hint = QLabel("修改后立即生效；配置同时写回 config.yaml。")
        hint.setObjectName("dlgHint")
        root.addWidget(hint)
        root.addSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        # 笔记目录 + 浏览
        self.notes_edit = QLineEdit(config.notes_dir)
        browse = QPushButton("浏览…")
        browse.setObjectName("browse")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(self._pick_dir)
        dir_row = QHBoxLayout()
        dir_row.setContentsMargins(0, 0, 0, 0)
        dir_row.setSpacing(8)
        dir_row.addWidget(self.notes_edit, 1)
        dir_row.addWidget(browse)
        dir_wrap = QWidget()
        dir_wrap.setLayout(dir_row)
        form.addRow("笔记目录", dir_wrap)

        self.url_edit = QLineEdit(config.llm.api_url)
        self.url_edit.setPlaceholderText("https://…/chat/completions")
        form.addRow("模型地址", self.url_edit)

        self.key_edit = QLineEdit(config.llm.api_key)
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("API 密钥")
        form.addRow("API 密钥", self.key_edit)

        self.model_edit = QLineEdit(config.llm.model)
        self.model_edit.setPlaceholderText("如 gpt-4o-mini、deepseek-chat")
        form.addRow("模型名称", self.model_edit)

        root.addLayout(form)
        root.addSpacing(16)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("cancel")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setObjectName("save")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._on_save)
        btn_row.addWidget(cancel)
        btn_row.addWidget(save)
        root.addLayout(btn_row)

    def _pick_dir(self) -> None:
        current = self.notes_edit.text().strip()
        chosen = QFileDialog.getExistingDirectory(self, "选择笔记目录", current)
        if chosen:
            self.notes_edit.setText(chosen)

    def _on_save(self) -> None:
        required = {
            "笔记目录": self.notes_edit.text().strip(),
            "模型地址": self.url_edit.text().strip(),
            "API 密钥": self.key_edit.text().strip(),
            "模型名称": self.model_edit.text().strip(),
        }
        missing = [name for name, val in required.items() if not val]
        if missing:
            QMessageBox.warning(self, "请完善配置", "以下为必填项：\n" + "、".join(missing))
            return
        self.accept()

    def values(self) -> dict:
        return {
            "notes_dir": self.notes_edit.text().strip(),
            "api_url": self.url_edit.text().strip(),
            "api_key": self.key_edit.text().strip(),
            "model": self.model_edit.text().strip(),
        }
