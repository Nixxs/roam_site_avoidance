from qgis.PyQt.QtCore import QSize, pyqtSignal
from qgis.PyQt.QtGui import QPixmap, QFont
from qgis.PyQt.QtWidgets import QWidget
from qgis.core import QgsLayerTreeModel, QgsLayerTreeNode
from qgis.core import QgsMapRendererParallelJob, QgsWkbTypes, QgsMapLayer
from roam.ui.ui_testwidget import Ui_testWidget

ICON_SIZE = QSize(32, 32)


class TestWidget(Ui_testWidget, QWidget):
    showmap = pyqtSignal()

    def __init__(self, parent=None):
        super(TestWidget, self).__init__(parent)
        self.setupUi(self)