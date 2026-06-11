"""Professional neutral application stylesheet."""

APP_STYLESHEET = """
QMainWindow, QWidget {
    background: #f1f3f5;
    color: #20252b;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10pt;
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
QWidget#statusNavigationBar {
    background: #ffffff;
    border-bottom: 1px solid #d8dde3;
}
QWidget#bottomDecisionBar {
    background: #ffffff;
    border-top: 1px solid #d8dde3;
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
QToolButton#addComparisonButton {
    background: #ffffff;
    border: 2px solid #8193a5;
    border-radius: 38px;
    padding: 12px;
}
QToolButton#addComparisonButton:hover {
    background: #e6edf3;
    border-color: #536f8a;
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
    font-size: 10pt;
    font-weight: 700;
    min-width: 96px;
    padding: 7px 14px;
}
QPushButton#matchButton {
    background: #287a4b;
    border-color: #20633d;
}
QPushButton#matchButton:hover {
    background: #236b42;
}
QPushButton#matchButton:checked {
    border: 3px solid #153f28;
    padding: 5px 12px;
}
QPushButton#noMatchButton {
    background: #b33a3a;
    border-color: #923030;
}
QPushButton#noMatchButton:hover {
    background: #9e3333;
}
QPushButton#noMatchButton:checked {
    border: 3px solid #5f1f1f;
    padding: 5px 12px;
}
QPushButton#passButton {
    background: #69737d;
    border-color: #59636c;
}
QPushButton#passButton:hover {
    background: #59636c;
}
QPushButton#passButton:checked {
    border: 3px solid #333a40;
    padding: 5px 12px;
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
QPushButton#deleteHistoryButton {
    color: #8c2f2f;
    border-color: #d7aaaa;
}
QPushButton#deleteHistoryButton:hover {
    background: #f7e8e8;
    border-color: #bf7777;
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
QFrame#imageToolOverlay {
    background: rgba(32, 37, 43, 185);
    border-radius: 5px;
}
QToolButton#imageToolButton {
    background: transparent;
    border: none;
    padding: 4px;
}
QToolButton#imageToolButton:hover {
    background: rgba(255, 255, 255, 45);
}
QListWidget#sourceDropList {
    background: #ffffff;
    border: 1px dashed #9ba8b5;
    border-radius: 6px;
    padding: 6px;
}
QListWidget#pairNavigationList {
    background: #ffffff;
    border: 1px solid #d8dde3;
    border-radius: 4px;
    padding: 3px;
}
QListWidget#pairNavigationList::item {
    border-bottom: 1px solid #e5e8eb;
    padding: 6px;
}
QListWidget#pairNavigationList::item:selected {
    background: #dce6ef;
    color: #20252b;
    font-weight: 600;
}
QLabel#sourceStatus {
    color: #52606d;
}
QLabel#sourceTitle {
    color: #3f4a55;
    font-size: 12pt;
    font-weight: 600;
    padding: 8px 2px 2px 2px;
}
QFrame#recordHeader {
    background: #ffffff;
    border: 1px solid #cbd3db;
    border-radius: 6px;
}
QLabel#recordHeaderTitle {
    color: #27313b;
    font-size: 13pt;
    font-weight: 700;
}
QLabel#recordHeaderFilename {
    color: #3f4a55;
    font-size: 10pt;
    font-weight: 600;
}
QLabel#recordHeaderReferenceNumber {
    color: #27313b;
    font-size: 10pt;
    font-weight: 700;
}
QLabel#recordHeaderStats {
    color: #697580;
    font-size: 9pt;
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
