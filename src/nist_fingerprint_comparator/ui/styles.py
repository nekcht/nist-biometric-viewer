"""Professional neutral application stylesheet."""

APP_STYLESHEET = """
QMainWindow, QWidget {
    background: #f1f3f5;
    color: #20252b;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
}
QToolBar {
    background: #ffffff;
    border: none;
    border-bottom: 1px solid #d8dde3;
    spacing: 6px;
    padding: 5px 8px;
}
QToolButton, QPushButton {
    background: #ffffff;
    border: 1px solid #c9d0d8;
    border-radius: 4px;
    padding: 5px 10px;
}
QToolButton:hover, QPushButton:hover {
    background: #e9edf1;
}
QWidget#decisionBar {
    background: #ffffff;
    border-bottom: 1px solid #d8dde3;
}
QWidget#setupPage, QWidget#loadingPage {
    background: #f1f3f5;
}
QLabel#setupTitle, QLabel#loadingTitle {
    color: #27313b;
    font-size: 18pt;
    font-weight: 600;
}
QLabel#setupText, QLabel#loadingMessage {
    color: #52606d;
    font-size: 11pt;
}
QProgressBar#loadingProgress {
    background: #e0e5ea;
    border: 1px solid #c8d0d8;
    border-radius: 5px;
    min-height: 12px;
    max-height: 12px;
    text-align: center;
}
QProgressBar#loadingProgress::chunk {
    background: #536f8a;
    border-radius: 4px;
}
QLabel#reviewProgress {
    color: #34404c;
    font-size: 11pt;
    font-weight: 600;
}
QPushButton#matchButton, QPushButton#noMatchButton, QPushButton#passButton {
    color: #ffffff;
    font-size: 11pt;
    font-weight: 700;
    min-width: 120px;
    padding: 9px 18px;
}
QPushButton#matchButton {
    background: #287a4b;
    border-color: #20633d;
}
QPushButton#matchButton:hover {
    background: #236b42;
}
QPushButton#noMatchButton {
    background: #b33a3a;
    border-color: #923030;
}
QPushButton#noMatchButton:hover {
    background: #9e3333;
}
QPushButton#passButton {
    background: #b17818;
    border-color: #946313;
}
QPushButton#passButton:hover {
    background: #986714;
}
QPushButton#matchButton:disabled,
QPushButton#noMatchButton:disabled,
QPushButton#passButton:disabled {
    background: #aeb5bc;
    border-color: #9ca4ad;
    color: #edf0f2;
}
QToolButton:disabled {
    color: #9ca4ad;
}
QStatusBar {
    background: #ffffff;
    border-top: 1px solid #d8dde3;
}
QSplitter::handle {
    background: #d8dde3;
    width: 1px;
}
QGroupBox {
    background: #ffffff;
    border: 1px solid #d8dde3;
    border-radius: 6px;
    margin-top: 12px;
    padding: 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QTableWidget {
    background: #ffffff;
    alternate-background-color: #f7f8fa;
    border: none;
    gridline-color: #e5e8eb;
}
QHeaderView::section {
    background: #eef1f4;
    border: none;
    border-bottom: 1px solid #d8dde3;
    padding: 4px;
    font-weight: 600;
}
QGraphicsView {
    background: #e8ebee;
    border: 1px solid #d8dde3;
    border-radius: 4px;
}
QLabel#cardTitle {
    font-size: 12pt;
    font-weight: 600;
}
QLabel#pairTitle {
    color: #4a5561;
    font-size: 11pt;
    font-weight: 600;
    padding: 5px 2px;
}
QLabel#sectionTitle {
    color: #27313b;
    font-size: 15pt;
    font-weight: 600;
    padding: 14px 2px 4px 2px;
}
QLabel#sourceTitle {
    color: #3f4a55;
    font-size: 12pt;
    font-weight: 600;
    padding: 8px 2px 2px 2px;
}
QLabel#disclaimer {
    background: #e8eef4;
    border: 1px solid #cbd7e2;
    border-radius: 5px;
    color: #334455;
    padding: 9px;
}
QLabel#fileSummary {
    background: #ffffff;
    border: 1px solid #d8dde3;
    border-radius: 5px;
    padding: 9px;
}
QLabel#placeholder {
    color: #697580;
    padding: 18px;
}
QLabel#warning {
    background: #fff7e6;
    border: 1px solid #ead7ad;
    border-radius: 4px;
    color: #725a24;
    padding: 6px;
}
QScrollArea {
    border: none;
}
"""
