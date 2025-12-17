"""Main window: 3-pane layout (nav | chat | inspection)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    """ReOS desktop app: transparent AI reasoning in a 1080p window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ReOS - Attention Kernel")
        self.resize(QSize(1920, 1080))  # 1080p-ish (width for 3 panes)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # Left pane: Navigation
        left_pane = self._create_nav_pane()

        # Center pane: Chat
        center_pane = self._create_chat_pane()

        # Right pane: Inspection
        right_pane = self._create_inspection_pane()

        # Use splitters for resizable panes
        main_split = QSplitter(Qt.Orientation.Horizontal)
        main_split.addWidget(left_pane)
        main_split.addWidget(center_pane)
        main_split.addWidget(right_pane)

        # Default proportions: nav (15%), chat (50%), inspection (35%)
        main_split.setSizes([288, 960, 672])
        layout.addWidget(main_split)

    def _create_nav_pane(self) -> QWidget:
        """Left navigation pane."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("Navigation")
        title.setStyleSheet(
            "font-weight: bold; font-size: 14px;"
        )
        layout.addWidget(title)

        # Placeholder list
        self.nav_list = QListWidget()
        self.nav_list.addItem("Recent Sessions")
        self.nav_list.addItem("Events Log")
        self.nav_list.addItem("Reflections")
        self.nav_list.addItem("Settings")
        layout.addWidget(self.nav_list)

        layout.addStretch()
        return widget

    def _create_chat_pane(self) -> QWidget:
        """Center chat pane."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Chat history display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        initial_msg = (
            "ReOS: Hello! I'm here to help you understand your "
            "attention patterns.\n\nTell me about your work."
        )
        self.chat_display.setText(initial_msg)
        layout.addWidget(self.chat_display, stretch=1)

        # Input area
        input_label = QLabel("You:")
        input_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(input_label)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type a message...")
        self.chat_input.returnPressed.connect(self._on_send_message)
        layout.addWidget(self.chat_input)

        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._on_send_message)
        layout.addWidget(send_btn)

        return widget

    def _create_inspection_pane(self) -> QWidget:
        """Right inspection pane: click on AI responses to see reasoning."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("Inspection Pane")
        title.setStyleSheet(
            "font-weight: bold; font-size: 14px;"
        )
        layout.addWidget(title)

        info = QLabel(
            "(Click on an AI message in the chat to inspect "
            "its reasoning trail)"
        )
        info.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(info)

        self.inspection_display = QTextEdit()
        self.inspection_display.setReadOnly(True)
        default_text = (
            "No message selected.\n\nInspection details will "
            "appear here."
        )
        self.inspection_display.setText(default_text)
        layout.addWidget(self.inspection_display, stretch=1)

        return widget

    def _on_send_message(self) -> None:
        """Handle user message (placeholder for now)."""
        text = self.chat_input.text().strip()
        if not text:
            return

        # Append to chat
        self.chat_display.append(f"\nYou: {text}")
        self.chat_input.clear()

        # Placeholder response
        response = (
            "\nReOS: I received your message. "
            "(Command interpreter and Ollama integration coming next.)"
        )
        self.chat_display.append(response)
