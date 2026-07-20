"""Stile grafico dell'applicazione Mahogany DoppelFinder."""

APP_STYLE = """
QWidget#mainWindow {
    background-color: #f4f7fb;
    color: #1f2937;
    font-family: "Inter", "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 14px;
}

QFrame#pathCard {
    background-color: #ffffff;
    border: 1px solid #dce3ec;
    border-radius: 14px;
}

QFrame#pathCard:hover {
    border-color: #3b82a0;
}

QComboBox {
    min-height: 34px;
    padding: 0 12px;
    background-color: #ffffff;
    border: 1px solid #cfd8e3;
    border-radius: 8px;
    color: #27364a;
}

QComboBox:hover,
QComboBox:focus {
    border-color: #287b9b;
}

QComboBox::drop-down {
    width: 28px;
    border: none;
}

QComboBox QAbstractItemView {
    padding: 4px;
    background-color: #ffffff;
    border: 1px solid #cfd8e3;
    border-radius: 6px;
    selection-background-color: #dceff5;
    selection-color: #1f3441;
    outline: none;
}

QPushButton#pathButton {
    background-color: transparent;
    border: none;
    border-radius: 12px;
    padding: 8px;
}

QPushButton#pathButton[empty="false"]:hover {
    background-color: #eaf3f7;
}

QPushButton#pathButton[empty="false"]:pressed {
    background-color: #d7eaf1;
}

QLabel#pathLabel {
    background-color: transparent;
    color: #64748b;
    font-size: 13px;
    padding: 2px 4px;
}

QScrollArea#pathScrollArea {
    background-color: transparent;
    border: none;
}

QScrollArea#pathScrollArea > QWidget > QWidget {
    background-color: transparent;
}

QPushButton#compareButton {
    min-height: 42px;
    padding: 0 22px;
    background-color: palette(button);
    color: palette(button-text);
    font-size: 14px;
    font-weight: 600;
    border: 1px solid palette(mid);
    border-radius: 10px;
}

QPushButton#compareButton:hover {
    background-color: palette(light);
}

QPushButton#compareButton:pressed {
    background-color: palette(midlight);
}

QPushButton#compareButton:disabled {
    color: palette(mid);
}

QScrollBar:horizontal {
    height: 7px;
    background: transparent;
}

QScrollBar::handle:horizontal {
    min-width: 28px;
    background: #9eb8c4;
    border-radius: 3px;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}
"""
