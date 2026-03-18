from qgis.PyQt.QtCore import QSize, pyqtSignal
from qgis.PyQt.QtGui import QPixmap, QFont
from qgis.PyQt.QtWidgets import QWidget, QLineEdit, QPushButton
from qgis.core import QgsLayerTreeModel, QgsLayerTreeNode
from qgis.core import QgsMapRendererParallelJob, QgsWkbTypes, QgsMapLayer
from roam.ui.ui_testwidget import Ui_testWidget

ICON_SIZE = QSize(32, 32)


class TestWidget(Ui_testWidget, QWidget):
    showmap = pyqtSignal()
    valueSubmitted = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super(TestWidget, self).__init__(parent)
        self.setupUi(self)

        # Simple input to send a value to the MapWidget
        self.input = QLineEdit(self)
        self.input.setPlaceholderText("Enter text to show on map…")
        self.verticalLayout.insertWidget(1, self.input)

        self.sendButton = QPushButton("Send to Map", self)
        self.verticalLayout.insertWidget(2, self.sendButton)

        self.sendButton.clicked.connect(self._emit_value)

    def _emit_value(self):
        text = self.input.text()
        self.valueSubmitted.emit(text,"other info")